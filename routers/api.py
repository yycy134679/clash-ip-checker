from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from ruamel.yaml import YAML, YAMLError
import asyncio
import uuid
import json
import copy
import io
import os
from typing import Dict, List, Any

# Local imports
from state import state
from schemas import StartRequest, UpdateNodeRequest, ExportRequest, RecheckRequest
from core.clash_api import ClashController
from core.results import (
    SOURCES,
    build_node_result,
    failure_aggregate,
    not_requested,
)

router = APIRouter(prefix="/api")
yaml = YAML()
yaml.preserve_quotes = True

def node_from_result(node_id, original_name, proxy, result, source, display_base_name=None, name_suffix=None):
    return build_node_result(
        node_id=node_id,
        original_name=original_name,
        proxy=proxy,
        result=result,
        requested_source=source,
        display_base_name=display_base_name,
        name_suffix=name_suffix,
    )


# --- Helper Function to run check in background ---
async def _run_check(proxies: List[Dict], config: Dict):
    """Background task: check all nodes using Clash API"""
    # Get config values
    api_url = config.get("clash_api_url", "http://127.0.0.1:9097")
    api_secret = config.get("clash_api_secret", "")
    selector = config.get("selector_name", "GLOBAL")
    fast_mode = config.get("fast_mode", True)
    source = config.get("source", "both")
    fallback = config.get("fallback", True)
    headless = config.get("headless", True)

    # Update checker headless setting dynamically
    state.checker.headless = headless

    # Check if empty
    if not proxies:
        state.is_running = False
        state.events.append({"type": "complete", "total": 0})
        return

    state.total = len(proxies)

    # Initialize Clash controller
    controller = ClashController(api_url, api_secret)

    try:
        async with controller.testing_session(selector):
            port = await controller.get_running_port()
            proxy_url = f"http://127.0.0.1:{port}"
            checked_count = 0

            for i, proxy in enumerate(proxies):
                if state.stop_requested:
                    break

                name = proxy.get("name", f"Node {i}")
                state.current_node = name

                try:
                    # 1. Switch to this node via Clash API
                    print(f"[Web] Switching to: {name}")
                    switched = await controller.switch_proxy(selector, name)

                    if not switched:
                        node_data = node_from_result(
                            i,
                            name,
                            proxy,
                            failure_aggregate(source, "切换节点失败"),
                            source,
                            name_suffix="【❌ 切换失败】",
                        )
                        node_data["status"] = "❌ 切换失败"
                        state.nodes[i] = node_data
                        state.events.append({"type": "progress", "progress": checked_count + 1, "total": state.total, "node": node_data})
                        checked_count += 1
                        continue

                    # 2. Wait for switch to take effect
                    await asyncio.sleep(1)

                    # 3. Check IP through Clash proxy
                    result = await state.checker.check_sources(
                        proxy_url,
                        mode="fast" if fast_mode else "browser",
                        source=source,
                        fallback=fallback,
                    )

                    node_data = node_from_result(i, name, proxy, result, source)
                    state.nodes[i] = node_data

                    # Push event
                    checked_count += 1
                    state.events.append({
                        "type": "progress",
                        "progress": checked_count,
                        "total": state.total,
                        "node": node_data
                    })

                except Exception as e:
                    node_data = node_from_result(
                        i,
                        name,
                        proxy,
                        failure_aggregate(source, str(e)),
                        source,
                        name_suffix="【❌ Error】",
                    )
                    node_data["error"] = str(e)
                    state.nodes[i] = node_data
                    checked_count += 1
                    state.events.append({
                        "type": "error",
                        "node_name": name,
                        "error": str(e)
                    })
                    state.events.append({"type": "progress", "progress": checked_count, "total": state.total, "node": node_data})

                state.progress = checked_count

    except Exception as e:
        state.events.append({"type": "error", "node_name": "Clash API", "error": str(e)})
    finally:
        state.checker.clear_cache()
        for node in state.nodes:
            if node.get("status") == "pending":
                node["status"] = "⏹ 未检测" if state.stop_requested else "❌ 未检测"
                node["ip"] = "❓"
                state.events.append({"type": "update", "node": node})
        state.is_running = False
        event_type = "stopped" if state.stop_requested else "complete"
        state.events.append({"type": event_type, "total": len(state.nodes)})


# --- Routes ---

@router.post("/validate")
async def validate_yaml(request: StartRequest):
    """Validate YAML format"""
    try:
        data = yaml.load(request.yaml_content)
        if not data:
            return JSONResponse({"valid": False, "error": "YAML 内容为空"}, status_code=400)

        proxies = data.get("proxies", [])
        if not proxies:
            return JSONResponse({"valid": False, "error": "未找到 proxies 节点"}, status_code=400)

        return {"valid": True, "node_count": len(proxies)}

    except YAMLError as e:
        return JSONResponse({"valid": False, "error": f"YAML 解析错误: {str(e)}"}, status_code=400)


@router.post("/start")
async def start_check(request: StartRequest):
    """Start node checking task"""
    if state.is_running:
        raise HTTPException(status_code=409, detail="任务正在运行中")

    try:
        data = yaml.load(request.yaml_content)
        proxies = data.get("proxies", [])

        if not proxies:
            raise HTTPException(status_code=400, detail="未找到 proxies 节点")

        # Initialize state
        state.task_id = str(uuid.uuid4())
        state.is_running = True
        state.stop_requested = False
        state.original_yaml = data
        state.nodes = []
        state.events = []  # Clear previous events
        state.progress = 0
        # Filter proxies based on skip keywords
        skip_keywords_str = request.config.get("skip_keywords_str", "")
        skip_keywords = [kw.strip() for kw in skip_keywords_str.split(",") if kw.strip()]

        active_proxies = []
        for p in proxies:
            name = p.get("name", "")
            if skip_keywords and any(kw in name for kw in skip_keywords):
                print(f"[Web] Skipping (in start): {name}")
                continue
            active_proxies.append(p)

            # Pre-fill node for immediate display
            state.nodes.append({
                "id": len(active_proxies) - 1,
                "original_name": name,
                "display_base_name": name,
                "name": name,
                "ip": "...",
                "risk": "",
                "shared": "",
                "type": "",
                "native": "",
                "source": "",
                "source_results": {source_name: not_requested(source_name) for source_name in SOURCES},
                "check_status": "failed",
                "ip_mismatch": False,
                "status": "pending",
                "proxy_config": p
            })

        state.total = len(active_proxies)

        # Start background task with filtered proxies
        state.task = asyncio.create_task(_run_check(active_proxies, request.config))

        return {"task_id": state.task_id, "total": state.total}

    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML 解析错误: {str(e)}")


@router.get("/progress")
async def progress_stream():
    """SSE endpoint for progress updates"""
    async def event_generator():
        last_sent = 0
        while True:
            # Send new events
            while last_sent < len(state.events):
                event = state.events[last_sent]
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_sent += 1

            # Check if complete
            if not state.is_running and last_sent >= len(state.events):
                break

            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.post("/stop")
async def stop_check():
    """Stop running task"""
    if not state.is_running:
        raise HTTPException(status_code=400, detail="没有正在运行的任务")

    state.stop_requested = True
    return {"status": "stopping"}


@router.get("/nodes")
async def get_nodes():
    """Get all nodes"""
    return {"nodes": state.nodes, "is_running": state.is_running}


@router.put("/nodes/{node_id}")
async def update_node(node_id: int, request: UpdateNodeRequest):
    """Update node name"""
    if state.is_running:
        raise HTTPException(status_code=409, detail="请等待检测结束后再编辑或删除节点")
    for node in state.nodes:
        if node["id"] == node_id:
            old_base = node.get("display_base_name", node.get("original_name", ""))
            old_name = node.get("name", "")
            old_suffix = old_name[len(old_base):] if old_name.startswith(old_base) else ""
            new_base = request.name
            if old_suffix and new_base.endswith(old_suffix):
                new_base = new_base[:-len(old_suffix)]
            if not new_base.strip():
                new_base = request.name
            node["name"] = request.name
            node["display_base_name"] = new_base
            return {"status": "updated", "node": node}

    raise HTTPException(status_code=404, detail="节点不存在")


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: int):
    """Delete node"""
    if state.is_running:
        raise HTTPException(status_code=409, detail="请等待检测结束后再编辑或删除节点")
    for i, node in enumerate(state.nodes):
        if node["id"] == node_id:
            state.nodes.pop(i)
            return {"status": "deleted"}

    raise HTTPException(status_code=404, detail="节点不存在")


@router.post("/nodes/{node_id}/recheck")
async def recheck_node(node_id: int, request: RecheckRequest):
    """Recheck a specific node"""
    if state.is_running:
        raise HTTPException(status_code=409, detail="请先停止当前的批量检测任务")

    # Find the node
    target_node = None
    target_index = -1
    for i, node in enumerate(state.nodes):
        if node["id"] == node_id:
            target_node = node
            target_index = i
            break

    if not target_node:
        raise HTTPException(status_code=404, detail="节点不存在")

    original_name = target_node.get("original_name", target_node["name"])
    display_base_name = target_node.get("display_base_name", original_name)

    # Get config from request
    config = request.config

    api_url = config.get("clash_api_url", "http://127.0.0.1:9097")
    api_secret = config.get("clash_api_secret", "")
    selector = config.get("selector_name", "GLOBAL")
    fast_mode = config.get("fast_mode", True)
    source = config.get("source", "both")
    fallback = config.get("fallback", True)
    headless = config.get("headless", True)

    # Update checker headless setting dynamically
    state.checker.headless = headless




    controller = ClashController(api_url, api_secret)

    state.is_running = True
    state.stop_requested = False
    try:
        async with controller.testing_session(selector):
            # 1. Switch
            print(f"[Recheck] Switching to: {original_name}")
            switched = await controller.switch_proxy(selector, original_name)

            if not switched:
                 raise Exception("切换节点失败")

            # 2. Wait
            await asyncio.sleep(1)



            # 3. Check
            port = await controller.get_running_port()
            proxy_url = f"http://127.0.0.1:{port}"

            # 3. Check IP through Clash proxy
            result = await state.checker.check_sources(
                proxy_url,
                mode="fast" if fast_mode else "browser",
                source=source,
                fallback=fallback,
                use_cache=False,
            )

            # 4. Update Node
            node_data = node_from_result(
                target_node["id"],
                original_name,
                target_node["proxy_config"],
                result,
                source,
                display_base_name=display_base_name,
            )

            state.nodes[target_index] = node_data

            # 5. Push Event manually to trigger UI update
            event = {
                "type": "update", # New event type for single update
                "node": node_data
            }
            state.events.append(event)

            return {"status": "success", "node": node_data}

    except Exception as e:
        print(f"[Recheck] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        state.checker.clear_cache()
        state.is_running = False



@router.post("/export")
async def export_yaml(request: ExportRequest):
    """Export selected nodes as YAML"""
    selected_nodes = [n for n in state.nodes if n["id"] in request.node_ids]

    if not selected_nodes:
        raise HTTPException(status_code=400, detail="请选择要导出的节点")

    # Build name mapping for proxy-groups sync
    name_map = {n["original_name"]: n["name"] for n in selected_nodes}
    deleted_names = set(n["original_name"] for n in state.nodes if n["id"] not in request.node_ids)

    # Clone original YAML (Deep Copy to avoid mutating state)
    export_data = copy.deepcopy(state.original_yaml)

    # Replace proxies with updated config and name
    new_proxies = []
    for node in selected_nodes:
        proxy = node["proxy_config"].copy()
        proxy["name"] = node["name"]
        new_proxies.append(proxy)

    export_data["proxies"] = new_proxies

    # Update proxy-groups
    for group in export_data.get("proxy-groups", []):
        new_group_proxies = []
        for proxy_name in group.get("proxies", []):
            if proxy_name in deleted_names:
                continue  # Skip deleted nodes
            if proxy_name in name_map:
                new_group_proxies.append(name_map[proxy_name])
            else:
                new_group_proxies.append(proxy_name)  # Keep DIRECT, REJECT, etc.
        group["proxies"] = new_group_proxies

    # Generate YAML
    stream = io.StringIO()
    yaml.dump(export_data, stream)
    yaml_content = stream.getvalue()

    # Save to file system for URL access
    task_id = state.task_id or str(uuid.uuid4())
    filename = f"clash_checked_{task_id[:8]}.yaml"
    filepath = os.path.join("exports", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    return {
        "yaml": yaml_content,
        "filename": filename,
        "url": f"/exports/{filename}"
    }

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from ruamel.yaml import YAML, YAMLError
import asyncio
import uuid
import json
import copy
import io
import os

# Local imports
from state import state, TaskBusyError, NodeNotFoundError
from schemas import StartRequest, UpdateNodeRequest, ExportRequest, RecheckRequest

router = APIRouter(prefix="/api")
yaml = YAML()
yaml.preserve_quotes = True

@router.post("/validate")
async def validate_yaml(request: StartRequest):
    try:
        proxies = state.validate_input(yaml.load(request.yaml_content))
        return {"valid": True, "node_count": len(proxies)}
    except (YAMLError, ValueError) as exc:
        return JSONResponse({"valid": False, "error": str(exc)}, status_code=400)


@router.post("/start")
async def start_check(request: StartRequest):
    if state.is_running:
        raise HTTPException(status_code=409, detail="任务正在运行中")
    try:
        return state.start_batch(yaml.load(request.yaml_content), request.config)
    except TaskBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (YAMLError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
    try:
        state.request_stop()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    try:
        return await state.recheck_node(node_id, request.config)
    except TaskBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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

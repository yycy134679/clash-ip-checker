import asyncio
import uuid
from collections.abc import Mapping

from core.clash_api import ClashController
from core.ip_checker import IPChecker
from core.node_check import NodeCheckRunner, NodeSwitchError
from core.results import SOURCES, build_node_result, failure_aggregate, not_requested


class TaskBusyError(Exception):
    pass


class NodeNotFoundError(Exception):
    pass


class AppState:
    def __init__(self, checker=None, controller_factory=None, sleep=None):
        self.checker = checker or IPChecker(headless=True)
        self.controller_factory = controller_factory or ClashController
        self.sleep = sleep
        self._phase = "idle"
        self.task_id = None
        self.task = None
        self.nodes = []
        self.original_yaml = {}
        self.progress = 0
        self.total = 0
        self.current_node = ""
        self.events = []

    @property
    def is_running(self):
        return self._phase != "idle"

    @property
    def stop_requested(self):
        return self._phase == "stopping"

    @staticmethod
    def validate_input(data):
        if not isinstance(data, Mapping):
            raise ValueError("YAML 顶层必须是映射")
        proxies = data.get("proxies")
        if not isinstance(proxies, list) or not proxies:
            raise ValueError("未找到 proxies 节点")
        for proxy in proxies:
            if not isinstance(proxy, Mapping) or not isinstance(proxy.get("name"), str) or not proxy["name"].strip():
                raise ValueError("每个节点必须是映射并包含非空名称")
        return proxies

    def start_batch(self, data, config):
        if self.is_running:
            raise TaskBusyError("任务正在运行中")
        proxies = self.validate_input(data)
        keywords = [kw.strip() for kw in config.get("skip_keywords_str", "").split(",") if kw.strip()]
        active = [p for p in proxies if not any(kw in p["name"] for kw in keywords)]
        nodes = [{"id": i, "original_name": p["name"], "display_base_name": p["name"],
                  "name": p["name"], "ip": "...", "risk": "", "shared": "", "type": "",
                  "native": "", "source": "", "source_results": {s: not_requested(s) for s in SOURCES},
                  "check_status": "failed", "ip_mismatch": False, "status": "pending", "proxy_config": p}
                 for i, p in enumerate(active)]
        task_id = str(uuid.uuid4())
        coroutine = self._run_batch(active, config)
        try:
            task = asyncio.create_task(coroutine)
        except BaseException:
            coroutine.close()
            raise
        self.task_id, self.original_yaml, self.nodes, self.events = task_id, data, nodes, []
        self.progress, self.total, self.current_node = 0, len(active), ""
        self._phase, self.task = "running", task
        task.add_done_callback(self._batch_done)
        return {"task_id": task_id, "total": self.total}

    def request_stop(self):
        if not self.is_running:
            raise ValueError("没有正在运行的任务")
        self._phase = "stopping"

    async def shutdown(self):
        if self.is_running:
            self.request_stop()
        try:
            if self.task and not self.task.done():
                await asyncio.shield(self.task)
        finally:
            await self.checker.stop()

    def _controller(self, config):
        return self.controller_factory(config.get("clash_api_url", "http://127.0.0.1:9097"),
                                       config.get("clash_api_secret", ""))

    def _runner(self, controller, selector, port, config):
        return NodeCheckRunner(controller, self.checker, selector, f"http://127.0.0.1:{port}",
                               mode="fast" if config.get("fast_mode", True) else "browser",
                               source=config.get("source", "both"), fallback=config.get("fallback", True),
                               sleep=self.sleep)

    def _record_progress(self, index, node):
        self.nodes[index] = node
        self.progress += 1
        self.events.append({"type": "progress", "progress": self.progress, "total": self.total, "node": node})

    def _finish_batch(self):
        self.checker.clear_cache()
        stopped = self.stop_requested
        for node in self.nodes:
            if node.get("status") == "pending":
                node["status"] = "⏹ 未检测" if stopped else "❌ 未检测"
                node["ip"] = "❓"
                self.events.append({"type": "update", "node": node})
        self._phase = "idle"
        self.events.append({"type": "stopped" if stopped else "complete", "total": len(self.nodes)})

    def _batch_done(self, task):
        if self.task is task and self.is_running:
            self._finish_batch()

    def _recheck_done(self, task):
        if self.task is task and self.is_running:
            self.checker.clear_cache()
            self._phase = "idle"

    async def _run_batch(self, proxies, config):
        source = config.get("source", "both")
        selector = config.get("selector_name", "GLOBAL")
        self.checker.headless = config.get("headless", True)
        try:
            if not proxies:
                return
            controller = self._controller(config)
            async with controller.testing_session(selector):
                port = await controller.get_running_port()
                runner = self._runner(controller, selector, port, config)
                for i, proxy in enumerate(proxies):
                    if self.stop_requested:
                        break
                    name = proxy["name"]
                    self.current_node = name
                    try:
                        result = await runner.check(name)
                        node = build_node_result(i, name, proxy, result, source)
                    except NodeSwitchError:
                        node = build_node_result(i, name, proxy, failure_aggregate(source, "切换节点失败"),
                                                 source, name_suffix="【❌ 切换失败】")
                        node["status"] = "❌ 切换失败"
                    except Exception as exc:
                        node = build_node_result(i, name, proxy, failure_aggregate(source, str(exc)),
                                                 source, name_suffix="【❌ Error】")
                        node["error"] = str(exc)
                        self.events.append({"type": "error", "node_name": name, "error": str(exc)})
                    self._record_progress(i, node)
        except Exception as exc:
            self.events.append({"type": "error", "node_name": "Clash API", "error": str(exc)})
        finally:
            self._finish_batch()

    async def recheck_node(self, node_id, config):
        if self.is_running:
            raise TaskBusyError("请先停止当前的批量检测任务")
        index = next((i for i, node in enumerate(self.nodes) if node["id"] == node_id), None)
        if index is None:
            raise NodeNotFoundError("节点不存在")
        coroutine = self._run_recheck(index, config)
        try:
            task = asyncio.create_task(coroutine)
        except BaseException:
            coroutine.close()
            raise
        self._phase, self.task = "running", task
        task.add_done_callback(self._recheck_done)
        return await task

    async def _run_recheck(self, index, config):
        node = self.nodes[index]
        name = node.get("original_name", node["name"])
        display_base = node.get("display_base_name", name)
        selector = config.get("selector_name", "GLOBAL")
        source = config.get("source", "both")
        self.checker.headless = config.get("headless", True)
        try:
            controller = self._controller(config)
            async with controller.testing_session(selector):
                port = await controller.get_running_port()
                runner = self._runner(controller, selector, port, config)
                result = await runner.check(name, use_cache=False)
                updated = build_node_result(node["id"], name, node["proxy_config"], result, source,
                                            display_base_name=display_base)
                self.nodes[index] = updated
                self.events.append({"type": "update", "node": updated})
            return {"status": "success", "node": updated}
        finally:
            self.checker.clear_cache()
            self._phase = "idle"


state = AppState()

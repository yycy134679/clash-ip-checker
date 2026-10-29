import asyncio
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, mock_open, patch

import yaml
from fastapi.testclient import TestClient

from core.clash_api import ClashController
from core.ip_checker import IPChecker
from core.results import build_aggregate, dual_suffix, failure_aggregate, source_result
from core.sources.browser import BrowserSource
from routers import api
from schemas import ExportRequest, RecheckRequest, UpdateNodeRequest
from state import AppState
from web import app
import clash_automator


RESULT = {
    "ip": "203.0.113.1", "pure_score": "10%", "source": "ippure",
    "full_string": "【⚪ 机房|原生】", "error": None,
}


def dual_result(
    ping0_ip="203.0.113.1",
    ippure_ip="203.0.113.1",
    ping0_score="20%",
    ippure_score="35%",
):
    result = build_aggregate({
        "ping0": source_result("ping0", {
            "ip": ping0_ip,
            "pure_score": ping0_score,
            "pure_emoji": "🟢",
            "shared_users": "120",
            "shared_emoji": "🟡",
            "ip_attr": "住宅",
            "ip_src": "原生",
            "full_string": "【🟢🟡 住宅|原生】",
        }),
        "ippure": source_result("ippure", {
            "ip": ippure_ip,
            "pure_score": ippure_score,
            "pure_emoji": "🟡",
            "bot_score": "8%",
            "bot_emoji": "🟢",
            "ip_attr": "机房",
            "ip_src": "广播",
            "full_string": "【🟡🟢 机房|广播】",
        }),
    })
    result["full_string"] = dual_suffix(result["source_results"])
    return result


class DetectionTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_and_browser_checks_return_timeout(self):
        checker = IPChecker()

        async def slow(*args, **kwargs):
            await asyncio.sleep(1)

        with patch("core.ip_checker.CHECK_TIMEOUT", 0.02), patch("core.ip_checker.BROWSER_CHECK_TIMEOUT", 0.02):
            with patch.object(checker, "_check_fast_impl", side_effect=slow):
                self.assertEqual((await checker.check_fast())["error"], "Timeout")
            with patch.object(checker, "_check_browser_impl", side_effect=slow):
                self.assertEqual((await checker.check_browser())["error"], "Timeout")

    async def test_browser_has_more_time_than_fast_check(self):
        checker = IPChecker()

        async def slow(*args, **kwargs):
            await asyncio.sleep(0.04)
            return RESULT.copy()

        with patch("core.ip_checker.CHECK_TIMEOUT", 0.02), patch("core.ip_checker.BROWSER_CHECK_TIMEOUT", 0.2):
            with patch.object(checker, "_check_fast_impl", side_effect=slow):
                self.assertEqual((await checker.check_fast())["error"], "Timeout")
            with patch.object(checker, "_check_browser_impl", side_effect=slow):
                self.assertEqual(await checker.check_browser(), RESULT)

    async def test_browser_closes_context_when_selector_wait_is_cancelled(self):
        source = BrowserSource(headless=False)
        page = AsyncMock()
        entered = asyncio.Event()

        async def wait_for_selector(*args, **kwargs):
            entered.set()
            await asyncio.sleep(1)

        page.wait_for_selector.side_effect = wait_for_selector
        context = AsyncMock()
        context.new_page.return_value = page
        source.browser = AsyncMock()
        source.browser.new_context.return_value = context
        task = asyncio.create_task(source.check())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()


class HomepageTests(unittest.TestCase):
    def test_homepage_and_static_assets(self):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("<title>Clash 节点检测器</title>", response.text)
            self.assertEqual(client.get("/static/js/app.js").status_code, 200)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def controller(self):
        controller = ClashController("http://unused.invalid")
        controller.get_config = AsyncMock(return_value={"mode": "rule"})
        controller.get_proxies = AsyncMock(return_value={"GLOBAL": {"now": "原节点"}})
        controller.set_mode = AsyncMock(return_value=True)
        controller.switch_proxy = AsyncMock(return_value=True)
        return controller

    async def test_restores_after_success_and_error(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                controller = self.controller()
                try:
                    async with controller.testing_session("GLOBAL"):
                        if fail:
                            raise ValueError("检测失败")
                except ValueError:
                    pass
                self.assertEqual(controller.set_mode.await_args_list[-1].args, ("rule",))
                controller.switch_proxy.assert_awaited_once_with("GLOBAL", "原节点")

    async def test_snapshot_failure_does_not_change_network(self):
        controller = self.controller()
        controller.get_proxies.return_value = None
        with self.assertRaises(RuntimeError):
            async with controller.testing_session("GLOBAL"):
                self.fail("读取原设置失败时不应检测")
        controller.set_mode.assert_not_awaited()

    async def test_restores_mode_even_if_node_restore_fails(self):
        controller = self.controller()
        controller.switch_proxy.return_value = False
        with self.assertRaisesRegex(RuntimeError, "恢复"):
            async with controller.testing_session("GLOBAL"):
                pass
        self.assertEqual(controller.set_mode.await_args_list[-1].args, ("rule",))

    async def test_restores_after_cancellation(self):
        controller = self.controller()
        self.assertTrue(hasattr(controller, "testing_session"))
        entered = asyncio.Event()

        async def run():
            async with controller.testing_session("GLOBAL"):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(run())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        controller.switch_proxy.assert_awaited_once_with("GLOBAL", "原节点")
        self.assertEqual(controller.set_mode.await_args_list[-1].args, ("rule",))


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    controller = SessionTests.controller

    async def asyncSetUp(self):
        self.state = AppState()
        self.state.nodes = [{"id": 0, "name": "测试节点", "original_name": "测试节点", "proxy_config": {"name": "测试节点"}}]
        self.state.checker.check_sources = AsyncMock(return_value=dual_result())
        self.controller_mock = self.controller()
        self.controller_mock.get_running_port = AsyncMock(return_value=7897)
        self.state_patch = patch.object(api, "state", self.state)
        self.state.controller_factory = lambda *args: self.controller_mock
        self.state.sleep = AsyncMock()
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)

    async def run_batch(self, proxies, config):
        self.state.start_batch({"proxies": proxies}, config)
        await self.state.task

    async def test_batch_restores_and_records_valid_result(self):
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await self.run_batch([{"name": "测试节点"}], {"source": "both"})
        self.assertFalse(self.state.is_running)
        self.assertEqual(self.state.nodes[0]["status"], "✅")
        self.assertEqual(
            self.state.nodes[0]["name"],
            "测试节点【Ping0 20%｜IPPure 35%】",
        )
        self.assertEqual(self.state.nodes[0]["source_results"]["ping0"]["shared_users"], "120")
        self.assertEqual(self.state.nodes[0]["source_results"]["ippure"]["bot_score"], "8%")
        progress = next(event for event in self.state.events if event["type"] == "progress")
        self.assertIn("source_results", progress["node"])
        self.assertEqual(progress["node"]["check_status"], "success")
        self.assertFalse(progress["node"]["ip_mismatch"])
        self.assertEqual(self.controller_mock.switch_proxy.await_args_list[-1].args,
                         ("GLOBAL", "原节点"))

    async def test_batch_reports_source_results_and_ip_mismatch(self):
        self.state.checker.check_sources.return_value = dual_result(
            ping0_ip="203.0.113.1",
            ippure_ip="198.51.100.2",
        )
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await self.run_batch([{"name": "测试节点"}], {"source": "both"})

        node = self.state.nodes[0]
        self.assertEqual(node["check_status"], "ip_mismatch")
        self.assertTrue(node["ip_mismatch"])
        self.assertEqual(node["status"], "⚠️ IP 不一致")
        self.assertEqual(node["source_results"]["ping0"]["ip"], "203.0.113.1")
        self.assertEqual(node["source_results"]["ippure"]["ip"], "198.51.100.2")
        self.assertEqual(node["name"], "测试节点【Ping0 20%｜IPPure 35%】")

    async def test_batch_passes_old_single_source_config(self):
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await self.run_batch(
                [{"name": "测试节点"}],
                {"source": "ping0", "fallback": False},
            )

        self.assertEqual(
            self.state.checker.check_sources.await_args.kwargs,
            {"proxy": "http://127.0.0.1:7897", "mode": "fast", "source": "ping0", "fallback": False},
        )

    async def test_stop_keeps_busy_until_cleanup_and_blocks_new_task(self):
        self.state.start_batch({"proxies": [{"name": "测试节点"}]}, {})
        response = await api.stop_check()
        self.assertEqual(response["status"], "stopping")
        self.assertTrue(self.state.is_running)
        self.assertTrue(self.state.stop_requested)
        with self.assertRaises(api.HTTPException) as error:
            await api.recheck_node(0, RecheckRequest())
        self.assertEqual(error.exception.status_code, 409)
        await self.state.task
        self.state.checker.check_sources.assert_not_awaited()
        self.assertFalse(self.state.is_running)

    async def test_recheck_restores_after_check_exception(self):
        self.state.checker.check_sources.side_effect = ValueError("接口不可用")
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            with self.assertRaises(api.HTTPException):
                await api.recheck_node(0, RecheckRequest())
        self.assertFalse(self.state.is_running)
        self.assertEqual(self.controller_mock.switch_proxy.await_args_list[-1].args,
                         ("GLOBAL", "原节点"))

    async def test_query_failure_is_not_marked_as_success(self):
        self.state.checker.check_sources.return_value = failure_aggregate("both", "All sources failed")
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await self.run_batch([{"name": "测试节点"}], {})
        self.assertEqual(self.state.nodes[0]["status"], "❌ 失败")

    async def test_stop_during_check_waits_until_restore_finishes(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def check(*args, **kwargs):
            entered.set()
            await release.wait()
            return RESULT.copy()

        self.state.checker.check_sources.side_effect = check
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            task = asyncio.create_task(self.run_batch([{"name": "测试节点"}], {}))
            await asyncio.wait_for(entered.wait(), 1)
            await api.stop_check()
            self.assertTrue(self.state.is_running)
            release.set()
            await task
        self.assertEqual(self.state.events[-1]["type"], "stopped")
        self.assertEqual(self.controller_mock.set_mode.await_args_list[-1].args, ("rule",))

    async def test_restore_failure_reaches_user_before_completion(self):
        self.controller_mock.switch_proxy.side_effect = [True, False]
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await self.run_batch([{"name": "测试节点"}], {})
        self.assertIn("手动恢复", self.state.events[-2]["error"])
        self.assertEqual(self.state.events[-1]["type"], "complete")
        self.assertFalse(self.state.is_running)

    async def test_recheck_bypasses_cache_and_replaces_old_suffix(self):
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await self.run_batch([{"name": "测试节点"}], {"source": "both"})

        old_name = self.state.nodes[0]["name"]
        await api.update_node(0, UpdateNodeRequest(name=f"手动节点{old_name[len('测试节点'):]}"))
        self.assertEqual(self.state.nodes[0]["display_base_name"], "手动节点")

        self.state.checker.check_sources.reset_mock()
        self.state.checker.check_sources.return_value = dual_result(
            ping0_score="40%",
            ippure_score="45%",
        )
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            response = await api.recheck_node(0, RecheckRequest(config={"source": "both"}))

        self.assertEqual(
            response["node"]["name"],
            "手动节点【Ping0 40%｜IPPure 45%】",
        )
        self.assertEqual(response["node"]["display_base_name"], "手动节点")
        self.assertEqual(self.state.checker.check_sources.await_args.kwargs["use_cache"], False)
        self.assertEqual(self.state.events[-1]["type"], "update")
        self.assertIn("source_results", self.state.events[-1]["node"])

    async def test_export_updates_proxy_group_references(self):
        self.state.original_yaml = {
            "proxies": [{"name": "测试节点", "type": "ss", "server": "example.com"}],
            "proxy-groups": [{"name": "Proxy", "proxies": ["测试节点", "DIRECT"]}],
        }
        self.state.nodes[0].update({
            "name": "手动节点【Ping0 20%｜IPPure 35%】",
            "proxy_config": self.state.original_yaml["proxies"][0],
        })
        with patch("builtins.open", mock_open()):
            response = await api.export_yaml(ExportRequest(node_ids=[0]))

        exported = yaml.safe_load(response["yaml"])
        self.assertEqual(exported["proxies"][0]["name"], "手动节点【Ping0 20%｜IPPure 35%】")
        self.assertEqual(exported["proxy-groups"][0]["proxies"], [
            "手动节点【Ping0 20%｜IPPure 35%】",
            "DIRECT",
        ])


class CommandLineTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_mode_does_not_launch_browser_and_restores_settings(self):
        controller = SessionTests.controller(self)
        controller.get_running_port = AsyncMock(return_value=7897)
        checker = IPChecker()
        checker.start = AsyncMock()
        checker.stop = AsyncMock()
        with patch.multiple(clash_automator, CLASH_CONFIG_PATH="demo.yaml", FAST_MODE=True, SOURCE="both"), \
             patch.object(clash_automator.os.path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="proxies:\n  - name: demo\n")), \
             patch.object(clash_automator, "ClashController", return_value=controller), \
             patch.object(clash_automator, "IPChecker", return_value=checker), \
             patch.object(clash_automator, "test_single_proxy", new=AsyncMock(return_value=RESULT.copy())), \
             patch.object(clash_automator, "save_config_results") as save:
            await clash_automator.main()
            save.assert_called_once()
            self.assertFalse(save.call_args.kwargs["join_with_space"])
        checker.start.assert_not_awaited()
        checker.stop.assert_awaited_once()
        self.assertEqual(controller.set_mode.await_args_list[-1].args, ("rule",))

    async def test_single_proxy_uses_dual_source_check(self):
        controller = SessionTests.controller(self)
        checker = IPChecker()
        checker.check_sources = AsyncMock(return_value=dual_result())

        result = await clash_automator.test_single_proxy(
            controller,
            checker,
            "测试节点",
            "GLOBAL",
            "http://127.0.0.1:7897",
            fast_mode=True,
            source="both",
            fallback=True,
        )

        checker.check_sources.assert_awaited_once_with(
            proxy="http://127.0.0.1:7897",
            mode="fast",
            source="both",
            fallback=True,
        )
        self.assertEqual(result["check_status"], "success")
        self.assertEqual(result["full_string"], "【Ping0 20%｜IPPure 35%】")

    async def test_single_proxy_prints_both_source_details(self):
        controller = SessionTests.controller(self)
        checker = IPChecker()
        checker.check_sources = AsyncMock(return_value=dual_result())

        with patch.object(clash_automator.asyncio, "sleep", new=AsyncMock()):
            with redirect_stdout(io.StringIO()) as output:
                await clash_automator.test_single_proxy(
                    controller,
                    checker,
                    "测试节点",
                    "GLOBAL",
                    "http://127.0.0.1:7897",
                    fast_mode=True,
                    source="both",
                )

        text = output.getvalue()
        self.assertIn("Ping0: IP: 203.0.113.1 | 评分: 20%", text)
        self.assertIn("IPPure: IP: 203.0.113.1 | 评分: 35%", text)
        self.assertIn("Bot 比例: 8%", text)

    def test_save_config_results_updates_dual_names_and_groups(self):
        config = {
            "proxies": [
                {"name": "测试节点", "type": "ss", "server": "example.com"},
            ],
            "proxy-groups": [
                {"name": "Proxy", "proxies": ["测试节点", "DIRECT"]},
            ],
        }
        suffix = "【Ping0 20%｜IPPure 35%】"
        new_name = f"测试节点{suffix}"

        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "checked.yaml")
            clash_automator.save_config_results(
                config,
                {"测试节点": suffix},
                output_path,
                join_with_space=False,
            )
            with open(output_path, encoding="utf-8") as file:
                exported = yaml.safe_load(file)

        self.assertEqual(exported["proxies"][0]["name"], new_name)
        self.assertEqual(
            exported["proxy-groups"][0]["proxies"],
            [new_name, "DIRECT"],
        )

    def test_save_config_results_keeps_space_for_single_source(self):
        config = {
            "proxies": [
                {"name": "测试节点", "type": "ss", "server": "example.com"},
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            output_path = os.path.join(directory, "checked.yaml")
            clash_automator.save_config_results(
                config,
                {"测试节点": "【Ping0 20%】"},
                output_path,
            )
            with open(output_path, encoding="utf-8") as file:
                exported = yaml.safe_load(file)

        self.assertEqual(exported["proxies"][0]["name"], "测试节点 【Ping0 20%】")


class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_score_uses_backup_instead_of_caching_success(self):
        checker = IPChecker()
        checker.get_simple_ip = AsyncMock(return_value=None)
        checker.ping0.check = AsyncMock(return_value={"ip": "203.0.113.1", "pure_score": "❓"})
        checker.ippure.check = AsyncMock(return_value=RESULT.copy())
        result = await checker.check_fast()
        self.assertEqual(result["source"], "ippure")
        self.assertEqual(result["pure_score"], "10%")


if __name__ == "__main__":
    unittest.main()

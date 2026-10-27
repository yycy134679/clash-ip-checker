import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from core.ip_checker import IPChecker
from core.results import build_aggregate, not_requested, result_suffix, source_result


def ping0_payload(ip="203.0.113.1", score="20%"):
    return {
        "ip": ip,
        "pure_score": score,
        "pure_emoji": "🟢",
        "shared_users": "120",
        "shared_emoji": "🟡",
        "ip_attr": "住宅",
        "ip_src": "原生",
        "full_string": "【🟢🟡 住宅|原生】",
        "error": None,
        "source": "ping0",
    }


def ippure_payload(ip="203.0.113.1", score="35%", bot="8%"):
    return {
        "ip": ip,
        "pure_score": score,
        "pure_emoji": "🟡",
        "bot_score": bot,
        "bot_emoji": "🟢",
        "ip_attr": "机房",
        "ip_src": "广播",
        "full_string": "【🟡🟢 机房|广播】",
        "error": None,
        "source": "ippure",
    }


class DualSourceTests(unittest.IsolatedAsyncioTestCase):
    def make_checker(self):
        checker = IPChecker()
        checker.get_simple_ip = AsyncMock(return_value="203.0.113.1")
        checker.ping0.check = AsyncMock(return_value=ping0_payload())
        checker.ippure.check = AsyncMock(return_value=ippure_payload())
        return checker

    async def test_fast_mode_requests_both_sources_concurrently(self):
        checker = self.make_checker()
        active = 0
        peak = 0

        async def check(proxy=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return ping0_payload()

        async def check_ippure(proxy=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return ippure_payload()

        checker.ping0.check = check
        checker.ippure.check = check_ippure
        result = await checker.check_sources(mode="fast", source="both", use_cache=False)

        self.assertEqual(peak, 2)
        self.assertEqual(result["check_status"], "success")
        self.assertEqual(result["source_results"]["ping0"]["pure_score"], "20%")
        self.assertEqual(result["source_results"]["ippure"]["pure_score"], "35%")
        self.assertEqual(result["pure_score"], "20%")
        self.assertEqual(result["source"], "ping0")
        self.assertEqual(result["bot_score"], "N/A")
        self.assertFalse(result["ip_mismatch"])

    async def test_browser_mode_keeps_ippure_bot_ratio(self):
        checker = self.make_checker()
        checker.browser_source.check = AsyncMock(
            return_value=ippure_payload(bot="12.5%")
        )

        result = await checker.check_sources(mode="browser", source="both", use_cache=False)

        self.assertEqual(result["check_status"], "success")
        self.assertEqual(result["source_results"]["ippure"]["bot_score"], "12.5%")
        checker.browser_source.check.assert_awaited_once()
        checker.ippure.check.assert_not_awaited()

    async def test_one_source_failure_keeps_the_other_result(self):
        for failing_source in ("ping0", "ippure"):
            with self.subTest(source=failing_source):
                checker = self.make_checker()
                getattr(checker, failing_source).check.side_effect = RuntimeError("接口不可用")
                result = await checker.check_sources(
                    mode="fast",
                    source="both",
                    use_cache=False,
                )

                self.assertEqual(result["check_status"], "partial")
                self.assertEqual(result["source_results"][failing_source]["status"], "failed")
                self.assertIn("接口不可用", result["source_results"][failing_source]["error"])
                healthy = "ippure" if failing_source == "ping0" else "ping0"
                self.assertEqual(result["source_results"][healthy]["status"], "success")
                self.assertEqual(result["source"], healthy)

    async def test_top_level_projection_falls_back_to_ippure_fields(self):
        checker = self.make_checker()
        checker.ping0.check.side_effect = RuntimeError("接口不可用")
        checker.ippure.check.return_value = ippure_payload(score="35%", bot="12%")

        result = await checker.check_sources(mode="fast", source="both", use_cache=False)

        self.assertEqual(result["source"], "ippure")
        self.assertEqual(result["ip"], "203.0.113.1")
        self.assertEqual(result["pure_score"], "35%")
        self.assertEqual(result["bot_score"], "12%")
        self.assertEqual(result["bot_emoji"], "🟢")

    async def test_one_source_timeout_does_not_cut_off_the_other(self):
        checker = self.make_checker()

        async def slow_ping0(proxy=None):
            await asyncio.sleep(1)
            return ping0_payload()

        checker.ping0.check = slow_ping0
        with patch("core.ip_checker.DUAL_PING0_TIMEOUT", 0.02):
            result = await checker.check_sources(
                mode="fast",
                source="both",
                use_cache=False,
            )

        self.assertEqual(result["check_status"], "partial")
        self.assertEqual(result["source_results"]["ping0"]["status"], "timeout")
        self.assertEqual(result["source_results"]["ippure"]["status"], "success")
        self.assertEqual(result_suffix(result, "both"), "【Ping0 超时｜IPPure 35%】")

    async def test_both_sources_fail(self):
        checker = self.make_checker()
        checker.ping0.check.side_effect = RuntimeError("Ping0 down")
        checker.ippure.check.side_effect = RuntimeError("IPPure down")

        result = await checker.check_sources(mode="fast", source="both", use_cache=False)

        self.assertEqual(result["check_status"], "failed")
        self.assertEqual(result["ip"], "❓")
        self.assertEqual(result["source_results"]["ping0"]["status"], "failed")
        self.assertEqual(result["source_results"]["ippure"]["status"], "failed")
        self.assertIn("Ping0：Ping0 down", result["error"])
        self.assertIn("IPPure：IPPure down", result["error"])

    async def test_missing_score_is_failure_not_zero(self):
        checker = self.make_checker()
        checker.ping0.check.return_value = ping0_payload(score="❓")

        result = await checker.check_sources(mode="fast", source="both", use_cache=False)

        self.assertEqual(result["check_status"], "partial")
        self.assertEqual(result["source_results"]["ping0"]["status"], "failed")
        self.assertEqual(result["source_results"]["ping0"]["error"], "未获取到评分")
        self.assertEqual(result_suffix(result, "both"), "【Ping0 失败｜IPPure 35%】")

    async def test_zero_score_is_a_valid_result(self):
        checker = self.make_checker()
        checker.ping0.check.return_value = ping0_payload(score="0%")
        checker.ippure.check.return_value = ippure_payload(score="0%")

        result = await checker.check_sources(mode="fast", source="both", use_cache=False)

        self.assertEqual(result["check_status"], "success")
        self.assertEqual(result["source_results"]["ping0"]["pure_score"], "0%")
        self.assertEqual(result["source_results"]["ippure"]["pure_score"], "0%")

    async def test_different_ips_are_both_kept(self):
        checker = self.make_checker()
        checker.ping0.check.return_value = ping0_payload(ip="203.0.113.1")
        checker.ippure.check.return_value = ippure_payload(ip="198.51.100.2")

        result = await checker.check_sources(mode="fast", source="both", use_cache=False)

        self.assertTrue(result["ip_mismatch"])
        self.assertEqual(result["check_status"], "ip_mismatch")
        self.assertEqual(result["source_results"]["ping0"]["ip"], "203.0.113.1")
        self.assertEqual(result["source_results"]["ippure"]["ip"], "198.51.100.2")
        self.assertEqual(result["ip"], "203.0.113.1")

    async def test_cache_is_isolated_by_source_mode_and_ip(self):
        checker = self.make_checker()
        first = await checker.check_sources(mode="fast", source="both")
        first["source_results"]["ping0"]["pure_score"] = "99%"

        second = await checker.check_sources(mode="fast", source="both")
        self.assertEqual(second["source_results"]["ping0"]["pure_score"], "20%")
        checker.ping0.check.assert_awaited_once()
        checker.ippure.check.assert_awaited_once()

        await checker.check_sources(mode="fast", source="ping0")
        checker.ping0.check.assert_awaited_once()

        checker.browser_source.check = AsyncMock(return_value=ippure_payload())
        await checker.check_sources(mode="browser", source="both")
        self.assertEqual(checker.ping0.check.await_count, 2)
        checker.browser_source.check.assert_awaited_once()

        await checker.check_sources(mode="browser", source="both", use_cache=False)
        self.assertEqual(checker.ping0.check.await_count, 3)
        self.assertEqual(checker.browser_source.check.await_count, 2)

    async def test_failed_source_is_retried_on_next_check(self):
        checker = self.make_checker()
        checker.ping0.check.side_effect = [
            RuntimeError("temporary"),
            ping0_payload(),
        ]

        first = await checker.check_sources(mode="fast", source="both")
        second = await checker.check_sources(mode="fast", source="both")

        self.assertEqual(first["check_status"], "partial")
        self.assertEqual(second["check_status"], "success")
        self.assertEqual(checker.ping0.check.await_count, 2)
        checker.ippure.check.assert_awaited_once()

    async def test_mismatched_ips_are_not_cached_as_one_dual_result(self):
        checker = self.make_checker()
        checker.ping0.check.return_value = ping0_payload(ip="203.0.113.1")
        checker.ippure.check.return_value = ippure_payload(ip="198.51.100.2")

        await checker.check_sources(mode="fast", source="both")
        second = await checker.check_sources(mode="fast", source="both")

        self.assertTrue(second["ip_mismatch"])
        checker.ping0.check.assert_awaited_once()
        self.assertEqual(checker.ippure.check.await_count, 2)

    async def test_cancelling_dual_check_waits_for_both_sources_to_clean_up(self):
        checker = self.make_checker()
        both_started = asyncio.Event()
        finished = {"ping0": False, "ippure": False}
        started = 0

        async def request(source):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished[source] = True

        checker.ping0.check = lambda proxy=None: request("ping0")
        checker.ippure.check = lambda proxy=None: request("ippure")
        task = asyncio.create_task(
            checker.check_sources(mode="fast", source="both", use_cache=False)
        )
        await asyncio.wait_for(both_started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertTrue(finished["ping0"])
        self.assertTrue(finished["ippure"])

    async def test_single_source_mode_keeps_legacy_contract(self):
        checker = IPChecker()
        checker.check_fast = AsyncMock(return_value={
            "ip": "203.0.113.1",
            "pure_score": "10%",
            "source": "ippure",
            "full_string": "【⚪ 机房|原生】",
            "error": None,
        })

        result = await checker.check_sources(mode="fast", source="ping0", fallback=True)

        self.assertEqual(result["source_results"]["ping0"]["status"], "failed")
        self.assertEqual(result["source_results"]["ippure"]["status"], "success")
        self.assertEqual(result["check_status"], "partial")
        self.assertEqual(result["source"], "ippure")

    async def test_direct_check_methods_keep_legacy_top_level_fields(self):
        checker = IPChecker()
        checker.get_simple_ip = AsyncMock(return_value="203.0.113.1")
        checker.ping0.check = AsyncMock(return_value=ping0_payload())
        checker.browser_source.check = AsyncMock(
            return_value=ippure_payload(bot="8%")
        )

        fast = await checker.check_fast()
        browser = await checker.check_browser()

        self.assertEqual(fast["source"], "ping0")
        self.assertEqual(fast["pure_score"], "20%")
        self.assertNotIn("source_results", fast)
        self.assertEqual(browser["source"], "ippure")
        self.assertEqual(browser["bot_score"], "8%")
        self.assertNotIn("source_results", browser)

    async def test_aggregate_returns_independent_source_results(self):
        original = source_result("ping0", ping0_payload())
        aggregate = build_aggregate({
            "ping0": original,
            "ippure": not_requested("ippure"),
        })

        aggregate["source_results"]["ping0"]["pure_score"] = "99%"

        self.assertEqual(original["pure_score"], "20%")


if __name__ == "__main__":
    unittest.main()

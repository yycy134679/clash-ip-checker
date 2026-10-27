import asyncio
import re
from copy import deepcopy

import aiohttp

from .results import (
    build_aggregate,
    dual_suffix,
    failed_result,
    source_result,
    timeout_result,
    wrap_legacy_result,
)
from .sources.browser import BrowserSource
from .sources.ippure import IPPureSource
from .sources.ping0 import Ping0Source


CHECK_TIMEOUT = 3
BROWSER_CHECK_TIMEOUT = 40
DUAL_PING0_TIMEOUT = 6
DUAL_IPPURE_TIMEOUT = 5


class IPChecker:
    def __init__(self, headless=True):
        self._headless = headless
        self.ping0 = Ping0Source()
        self.ippure = IPPureSource()
        self.browser_source = BrowserSource(headless=headless)
        self.cache = {}

    def clear_cache(self):
        self.cache.clear()
        print("[IPChecker] Cache cleared.")

    @property
    def headless(self):
        return self._headless

    @headless.setter
    def headless(self, value):
        self._headless = value
        self.browser_source.headless = value

    async def start(self):
        await self.browser_source.start()

    async def stop(self):
        await self.browser_source.stop()

    async def get_simple_ip(self, proxy=None):
        urls = ["http://api.ipify.org", "http://v4.ident.me"]
        for url in urls:
            try:
                timeout = aiohttp.ClientTimeout(total=3)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, proxy=proxy) as resp:
                        if resp.status == 200:
                            ip = (await resp.text()).strip()
                            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                                return ip
            except Exception:
                continue
        return None

    def _cache_get(self, source, mode, ip):
        if not ip:
            return None
        entry = self.cache.get((source, mode, ip))
        return deepcopy(entry) if entry else None

    def _cache_set(self, source, mode, entry):
        if entry.get("status") == "success" and entry.get("ip") not in (None, "", "❓"):
            self.cache[(source, mode, entry["ip"])] = deepcopy(entry)

    async def _run_source(self, source, proxy, mode, use_cache=True, fast_ip=None):
        cached = self._cache_get(source, mode, fast_ip) if use_cache else None
        if cached:
            return cached

        if source == "ping0":
            result = await self.ping0.check(proxy)
        elif mode == "browser":
            result = await self.browser_source.check(proxy)
            if result.get("ip") in (None, "", "❓") and fast_ip:
                result["ip"] = fast_ip
        else:
            result = await self.ippure.check(proxy)

        entry = source_result(source, result)
        if use_cache:
            self._cache_set(source, mode, entry)
        return entry

    async def _run_source_timed(self, source, proxy, mode, timeout, use_cache, fast_ip):
        try:
            return await asyncio.wait_for(
                self._run_source(source, proxy, mode, use_cache, fast_ip),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return timeout_result(source)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return failed_result(source, str(exc))

    async def _check_both(self, proxy, mode, use_cache=True):
        fast_ip = await self.get_simple_ip(proxy)
        timeout = DUAL_IPPURE_TIMEOUT if mode == "fast" else BROWSER_CHECK_TIMEOUT
        tasks = [
            self._run_source_timed(
                "ping0", proxy, mode, DUAL_PING0_TIMEOUT, use_cache, fast_ip
            ),
            self._run_source_timed(
                "ippure", proxy, mode, timeout, use_cache, fast_ip
            ),
        ]
        ping0_result, ippure_result = await asyncio.gather(*tasks)
        result = build_aggregate({"ping0": ping0_result, "ippure": ippure_result})
        result["full_string"] = dual_suffix(result["source_results"])
        return result

    async def check_sources(
        self,
        proxy=None,
        mode="fast",
        source="both",
        fallback=True,
        use_cache=True,
    ):
        """Unified entry for single-source and dual-source checks."""
        if source == "both":
            return await self._check_both(proxy, mode, use_cache)

        if mode == "fast":
            result = await self.check_fast(
                proxy,
                source=source,
                fallback=fallback,
                use_cache=use_cache,
            )
        elif source == "ippure":
            try:
                result = await self.check_browser(proxy=proxy, use_cache=use_cache)
            except Exception as exc:
                result = failed_result("ippure", str(exc))
            if fallback and source_result("ippure", result)["status"] != "success":
                try:
                    backup = await self.check_fast(
                        proxy, source="ping0", fallback=False, use_cache=use_cache
                    )
                except Exception:
                    backup = None
                if backup and backup.get("source") == "ping0" and source_result("ping0", backup)["status"] == "success":
                    result = backup
        else:
            result = await self.check_fast(
                proxy,
                source="ping0",
                fallback=fallback,
                use_cache=use_cache,
            )
        return wrap_legacy_result(result, source)

    async def check_browser(self, url="https://ippure.com/", proxy=None, timeout=20000, use_cache=True):
        try:
            return await asyncio.wait_for(
                self._check_browser_impl(proxy, use_cache=use_cache),
                timeout=BROWSER_CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return self._timeout_result()

    async def _check_browser_impl(self, proxy, use_cache=True):
        current_ip = await self.get_simple_ip(proxy)
        if use_cache:
            cached = self._cache_get("ippure", "browser", current_ip)
            if cached:
                print(f"     [Cache Hit] {current_ip}")
                return cached

        if current_ip:
            print(f"     [New IP] {current_ip}")
        else:
            print("     [Warning] Fast IP check failed. Scanning with browser...")

        result = await self.browser_source.check(proxy)
        if result.get("ip") in (None, "", "❓") and current_ip:
            result["ip"] = current_ip

        entry = source_result("ippure", result)
        if use_cache:
            self._cache_set("ippure", "browser", entry)
        return entry

    async def check_fast(self, proxy=None, source="ping0", fallback=True, use_cache=True):
        """Fast mode. Keep the single-source contract; both returns an aggregate."""
        if source == "both":
            return await self._check_both(proxy, "fast", use_cache)
        try:
            return await asyncio.wait_for(
                self._check_fast_impl(proxy, source, fallback, use_cache),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return self._timeout_result()

    @staticmethod
    def _timeout_result():
        return {
            "pure_emoji": "❓", "shared_emoji": "❓", "ip_attr": "❓", "ip_src": "❓",
            "pure_score": "❓", "shared_users": "N/A", "full_string": "【⏱️ Timeout】",
            "ip": "❓", "error": "Timeout", "source": "timeout"
        }

    async def _check_fast_impl(self, proxy=None, source="ping0", fallback=True, use_cache=True):
        fast_ip = await self.get_simple_ip(proxy)

        async def try_source(current_source):
            entry = await self._run_source(current_source, proxy, "fast", use_cache, fast_ip)
            return entry if entry.get("status") == "success" else None

        result = await try_source(source)
        if result:
            return result

        if fallback:
            print(f"     [Check] {source} failed, falling back...")
            result = await try_source("ippure" if source == "ping0" else "ping0")
            if result:
                return result

        return {
            "pure_emoji": "❓", "shared_emoji": "❓", "ip_attr": "❓", "ip_src": "❓",
            "pure_score": "❓", "shared_users": "N/A", "full_string": "【❌ Check Failed】",
            "ip": "❓", "error": f"All sources failed (Primary: {source})", "source": "failed"
        }

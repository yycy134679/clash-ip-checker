import aiohttp
import urllib.parse
from contextlib import asynccontextmanager

class ClashController:
    def __init__(self, api_url, secret=""):
        self.api_url = api_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json"
        }

    async def switch_proxy(self, selector, proxy_name):
        """Switches the selector to the specified proxy."""
        url = f"{self.api_url}/proxies/{urllib.parse.quote(selector)}"
        payload = {"name": proxy_name}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(url, json=payload, headers=self.headers, timeout=5) as resp:
                    if resp.status == 204:
                        return True
                    else:
                        print(f"Failed to switch to {proxy_name}. Status: {resp.status}")
                        return False
        except Exception as e:
            print(f"API Error switching to {proxy_name}: {e}")
            return False

    async def set_mode(self, mode):
        """Sets the Clash mode (global, rule, direct)."""
        url = f"{self.api_url}/configs"
        payload = {"mode": mode}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, json=payload, headers=self.headers, timeout=5) as resp:
                    if resp.status == 204:
                        print(f"Successfully set mode to: {mode}")
                        return True
                    else:
                        print(f"Failed to set mode logic. Status: {resp.status}")
                        return False
        except Exception as e:
            print(f"API Error setting mode: {e}")
            return False

    async def get_config(self):
        """Read the current mode before changing any network settings."""
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.api_url}/configs", headers=self.headers) as resp:
                resp.raise_for_status()
                return await resp.json()

    @asynccontextmanager
    async def testing_session(self, selector):
        """Restore the original selection and mode on completion, failure or cancellation."""
        config = await self.get_config()
        proxies = await self.get_proxies()
        mode = config.get("mode")
        selection = (proxies or {}).get(selector, {}).get("now")
        if not mode or not selection:
            raise RuntimeError("无法读取原模式或代理组当前节点，未开始检测")

        try:
            if not await self.set_mode("global"):
                raise RuntimeError("无法切换到全局模式，未开始检测")
            yield
        finally:
            errors = []
            try:
                if not await self.switch_proxy(selector, selection):
                    errors.append("恢复原节点失败")
            except Exception as exc:
                errors.append(f"恢复原节点失败: {exc}")
            try:
                if not await self.set_mode(mode):
                    errors.append("恢复原模式失败")
            except Exception as exc:
                errors.append(f"恢复原模式失败: {exc}")
            if errors:
                raise RuntimeError("；".join(errors) + "，请在 Clash 中手动恢复")

    async def get_running_port(self):
        """Fetches the mixed-port or http-port from running instance."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/configs", headers=self.headers) as resp:
                    if resp.status == 200:
                        conf = await resp.json()
                        if conf.get('mixed-port', 0) != 0: return conf['mixed-port']
                        if conf.get('port', 0) != 0: return conf['port']
                        if conf.get('socks-port', 0) != 0: return conf['socks-port']
        except Exception:
            pass
        return 7897 # Default fallback

    async def get_proxies(self):
        """Fetches all proxies."""
        try:
             async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"{self.api_url}/proxies", headers=self.headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('proxies', {})
        except Exception as e:
            print(f"Error fetching proxies: {e}")
            return None

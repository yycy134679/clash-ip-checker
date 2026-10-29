import asyncio


class NodeSwitchError(Exception):
    """The selected Clash node could not be activated."""


class NodeCheckRunner:
    def __init__(self, controller, checker, selector, proxy_url, *, mode="fast",
                 source="both", fallback=True, sleep=None, on_check=None):
        self.controller = controller
        self.checker = checker
        self.selector = selector
        self.proxy_url = proxy_url
        self.mode = mode
        self.source = source
        self.fallback = fallback
        self.sleep = sleep or asyncio.sleep
        self.on_check = on_check

    async def check(self, node_name, *, use_cache=True):
        if not await self.controller.switch_proxy(self.selector, node_name):
            raise NodeSwitchError("切换节点失败")
        await self.sleep(1)
        if self.on_check:
            self.on_check()
        options = {"mode": self.mode, "source": self.source, "fallback": self.fallback}
        if not use_cache:
            options["use_cache"] = False
        return await self.checker.check_sources(proxy=self.proxy_url, **options)

from .base import BaseCheckSource
from ..results import build_source_payload, shared_emoji
from curl_cffi.requests import AsyncSession
import re
from typing import Dict, Optional

class Ping0Source(BaseCheckSource):


    def get_shared_emoji(self, shared_str):
        return shared_emoji(shared_str)

    @staticmethod
    def _result(source_error=None, full_string=""):
        return build_source_payload("ping0", error=source_error, full_string=full_string)

    async def check(self, proxy: Optional[str] = None) -> Dict:
        url = "https://ping0.cc/"
        proxies = {"http": proxy, "https": proxy} if proxy else None
        
        try:
            # The checker enforces the 6-second dual-source limit; keep the
            # transport timeout longer so it reports a timeout instead of a
            # transport error.
            async with AsyncSession(proxies=proxies, impersonate="chrome124", timeout=10) as session:
                resp = await session.get(url)
                
                if resp.status_code != 200:
                    return self._result(
                        f"HTTP {resp.status_code}",
                        f"【❌ HTTP {resp.status_code}】",
                    )
                
                html = resp.text
                
                # Cloudflare detection
                if "<title>Just a moment...</title>" in html or "challenge-platform" in html or "cf-turnstile" in html:
                    print("     [Ping0] Cloudflare blocked")
                    return self._result("Cloudflare 验证拦截", "【❌ 验证拦截】")

                result = self._result()
                
                # 1. IP
                ip_match = re.search(r"window\.ip\s*=\s*'([^']+)'", html)
                if not ip_match:
                    ip_match = re.search(r'href="[^"]*?/ping/([0-9.]+)"', html)
                if ip_match:
                    result["ip"] = ip_match.group(1).strip()
                
                # 2. Type
                type_match = re.search(r'<div class="line line-iptype">.*?<span class="label[^>]*>(.*?)</span>', html, re.DOTALL)
                if type_match:
                    raw_type = type_match.group(1).strip()
                    if "机房" in raw_type or "IDC" in raw_type: result["ip_attr"] = "机房"
                    elif "家庭" in raw_type or "住宅" in raw_type: result["ip_attr"] = "住宅"
                    else: result["ip_attr"] = raw_type
                
                # 3. Score
                score_match = re.search(r'class="riskitem riskcurrent"[^>]*><span class="value">(\d+)%</span>', html)
                if score_match:
                    result["pure_score"] = f"{score_match.group(1)}%"
                
                # 4. Native
                native_match = re.search(r'<div class="line line-nativeip">.*?<span class="label[^>]*>(.*?)</span>', html, re.DOTALL)
                if native_match:
                    raw_native = native_match.group(1).strip()
                    if "广播" in raw_native: result["ip_src"] = "广播"
                    elif "原生" in raw_native: result["ip_src"] = "原生"
                    else: result["ip_src"] = raw_native
                
                # 5. Shared
                shared_match = re.search(r'usecount="([^"]+)"', html)
                if not shared_match:
                    shared_match = re.search(r'class="usecountbar"[^>]*>\s*(.*?)\s*</div>', html, re.DOTALL)
                if shared_match:
                    result["shared_users"] = shared_match.group(1).strip()
                
                return build_source_payload("ping0", values=result, formatted=True)

        except Exception as e:
            print(f"     [Ping0] Error: {e}")
            return self._result(str(e), "【❌ Error】")

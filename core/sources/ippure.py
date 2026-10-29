from .base import BaseCheckSource
from ..results import build_source_payload
from curl_cffi.requests import AsyncSession
from typing import Dict, Optional

class IPPureSource(BaseCheckSource):

    async def check(self, proxy: Optional[str] = None) -> Dict:
        url = "https://my.123169.xyz/v1/info"
        result = build_source_payload("ippure")
        try:
            proxies = {"http": proxy, "https": proxy} if proxy else None
            # The checker enforces the 5-second dual-source limit; keep the
            # transport timeout longer so it reports a timeout instead of a
            # transport error.
            async with AsyncSession(proxies=proxies, impersonate="chrome110", timeout=10) as session:
                resp = await session.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    result["ip"] = data.get("ip", "❓")
                    
                    f_score = data.get("fraudScore")
                    if f_score is not None:
                        result["pure_score"] = f"{f_score}%"
                    
                    is_resi = data.get("isResidential", False)
                    result["ip_attr"] = "住宅" if is_resi else "机房"
                    
                    is_broad = data.get("isBroadcast", False)
                    result["ip_src"] = "广播" if is_broad else "原生"
                    
                    result = build_source_payload("ippure", values=result, formatted=True)
                else:
                    result["error"] = f"API Error {resp.status_code}"
                    result["full_string"] = "【❌ API Error】"
        except Exception as e:
            print(f"     [ippure] curl_cffi error: {e}")
            result["error"] = str(e)
            result["full_string"] = "【❌ Error】"
        return result

import asyncio
import yaml
import os
import sys
from typing import Dict, Any, List

# Import Utils
from utils.config_loader import load_config
from core.ip_checker import IPChecker
from core.clash_api import ClashController
from core.results import failure_aggregate

# --- CONFIGURATION ---
cfg = load_config("config.yaml") or {}

CLASH_CONFIG_PATH = cfg.get('yaml_path', r"YOUR_CLASH_CONFIG_PATH_HERE")
CLASH_API_URL = cfg.get('clash_api_url', "http://127.0.0.1:9097")
CLASH_API_SECRET = cfg.get('clash_api_secret', "")
SELECTOR_NAME = cfg.get('selector_name', "GLOBAL")
OUTPUT_SUFFIX = cfg.get('output_suffix', "_checked")
FAST_MODE = cfg.get('fast_mode', True)
SKIP_KEYWORDS = cfg.get('skip_keywords', ["剩余", "重置", "到期", "有效期", "官网", "网址", "更新", "公告"])
HEADLESS = cfg.get('headless', True)
SOURCE = cfg.get('source', 'both')
FALLBACK = cfg.get('fallback', True)


def format_source_detail(entry: Dict[str, Any]) -> str:
    """Format one source result for terminal output."""
    status = entry.get("status")
    if status == "success":
        parts = [
            f"IP: {entry.get('ip', '❓')}",
            f"评分: {entry.get('pure_score', 'N/A')}",
            f"属性: {entry.get('ip_attr', '❓')}/{entry.get('ip_src', '❓')}",
        ]
        shared = entry.get("shared_users")
        if shared not in (None, "", "N/A", "❓"):
            parts.append(f"共享人数: {shared}")
        bot = entry.get("bot_score")
        if bot not in (None, "", "N/A", "❓"):
            parts.append(f"Bot 比例: {bot}")
        return " | ".join(parts)

    label = {"timeout": "超时", "failed": "失败", "not_requested": "未检测"}.get(status, "失败")
    error = entry.get("error")
    return f"{label}（{error}）" if error else label


async def test_single_proxy(controller: ClashController, checker: IPChecker, proxy_name: str, selector: str, local_proxy: str,
                          fast_mode: bool = FAST_MODE, source: str = SOURCE, fallback: bool = FALLBACK) -> Dict[str, Any]:
    """
    Tests a single proxy: switches to it, waits, and checks IP.
    Returns the result dictionary (or error dict).
    """
    print(f"\nTesting: {proxy_name}")

    # ... switch logic same ...

    # 1. Switch Node
    print(f"  -> Switching {selector} ...")
    switched = await controller.switch_proxy(selector, proxy_name)
    if not switched:
        print("  -> Switch failed, skipping IP check.")
        return failure_aggregate(source, "切换节点失败", name_suffix="【❌ Switch Error】")

    # 2. Wait for switch to take effect
    await asyncio.sleep(1)

    # 3. Check IP
    print(f"  -> Running IP Check ({'Fast Mode' if fast_mode else 'Browser Mode'})...")
    try:
        res = await checker.check_sources(
            proxy=local_proxy,
            mode="fast" if fast_mode else "browser",
            source=source,
            fallback=fallback,
        )
    except Exception as e:
        print(f"     Check error: {e}")
        res = failure_aggregate(source, str(e))

    if not res:
        res = failure_aggregate(source, "检测失败")

    full_str = res['full_string']
    ip_addr = res.get('ip', 'Unknown')
    p_score = res.get('pure_score', 'N/A')
    b_score = res.get('bot_score', 'N/A')
    s_users = res.get('shared_users', 'N/A')

    print(f"  -> Result: {full_str}")

    if source == "both" and res.get("source_results"):
        print(f"  -> Ping0: {format_source_detail(res['source_results']['ping0'])}")
        print(f"  -> IPPure: {format_source_detail(res['source_results']['ippure'])}")
    else:
        details_str = f"  -> Details: IP: {ip_addr} | 污染度: {p_score}"
        if b_score != 'N/A':
            details_str += f" | Bot流量比: {b_score}"
        if s_users != 'N/A':
            details_str += f" | 共享人数: {s_users}"
        print(details_str)

    return res

def save_config_results(
    original_config: dict,
    results_map: Dict[str, str],
    output_path: str,
    join_with_space: bool = True,
):
    """Append results to proxy names and save the new config file."""
    print("\nUpdating config names...")
    new_proxies = []
    name_mapping = {} # Old -> New
    separator = " " if join_with_space else ""

    proxies = original_config.get('proxies', [])
    for proxy in proxies:
        old_name = proxy['name']
        if old_name in results_map:
            new_name = f"{old_name}{separator}{results_map[old_name]}"
            proxy['name'] = new_name
            name_mapping[old_name] = new_name
        new_proxies.append(proxy)

    original_config['proxies'] = new_proxies

    # Update groups
    if 'proxy-groups' in original_config:
        for group in original_config['proxy-groups']:
            if 'proxies' in group:
                new_group_proxies = []
                for p_name in group['proxies']:
                    if p_name in name_mapping:
                        new_group_proxies.append(name_mapping[p_name])
                    else:
                        new_group_proxies.append(p_name)
                group['proxies'] = new_group_proxies

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(original_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"\nSuccess! Saved updated config to: {output_path}")
    except Exception as e:
        print(f"Error saving config: {e}")

async def main():
    print(f"Loading config from: {CLASH_CONFIG_PATH}")
    if not os.path.exists(CLASH_CONFIG_PATH):
        print(f"Error: Config file not found at {CLASH_CONFIG_PATH}")
        return

    try:
        with open(CLASH_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config_data = yaml.full_load(f)
    except Exception as e:
        print(f"Error parsing YAML: {e}")
        return

    proxies = config_data.get('proxies', [])
    if not proxies:
        print("No 'proxies' found in config.")
        return

    print(f"Found {len(proxies)} proxies to test.")

    controller = ClashController(CLASH_API_URL, CLASH_API_SECRET)

    checker = IPChecker(headless=HEADLESS)
    results_map = {}

    try:
        async with controller.testing_session(SELECTOR_NAME):
            mixed_port = await controller.get_running_port()
            local_proxy_url = f"http://127.0.0.1:{mixed_port}"
            if not FAST_MODE:
                await checker.start()

            for i, proxy in enumerate(proxies):
                name = proxy['name']
                if any(kw in name for kw in SKIP_KEYWORDS):
                    print(f"\n[{i+1}/{len(proxies)}] Skipping (Status Node): {name}")
                    continue
                print(f"[{i+1}/{len(proxies)}] Progress...", end="")
                res = await test_single_proxy(
                    controller, checker, name, SELECTOR_NAME, local_proxy_url,
                    fast_mode=FAST_MODE, source=SOURCE, fallback=FALLBACK,
                )
                results_map[name] = res['full_string']
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nProcess interrupted by user. Saving current progress...")
    finally:
        checker.clear_cache()
        await checker.stop()

    # SAVE RESULTS
    base = os.path.basename(CLASH_CONFIG_PATH)
    filename, ext = os.path.splitext(base)
    output_filename = f"{filename}{OUTPUT_SUFFIX}{ext}"
    output_path = os.path.join(os.getcwd(), output_filename)

    save_config_results(
        config_data,
        results_map,
        output_path,
        join_with_space=SOURCE != "both",
    )

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())

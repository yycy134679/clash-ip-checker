import ipaddress
import re
from copy import deepcopy


SOURCES = ("ping0", "ippure")
SOURCE_LABELS = {"ping0": "Ping0", "ippure": "IPPure"}


def score_emoji(percentage_str):
    try:
        value = float(percentage_str.replace('%', ''))
        for threshold, emoji in ((10, '⚪'), (30, '🟢'), (50, '🟡'), (70, '🟠'), (90, '🔴')):
            if value <= threshold:
                return emoji
        return '⚫'
    except Exception:
        return '❓'


def shared_emoji(shared_str):
    try:
        nums = re.findall(r'\d+', shared_str or '')
        if not nums:
            return '❓'
        upper = int(nums[-1]) + (1 if '+' in shared_str else 0)
        for threshold, emoji in ((10, '🟢'), (100, '🟡'), (1000, '🟠'), (10000, '🔴')):
            if upper <= threshold:
                return emoji
        return '⚫'
    except Exception:
        return '❓'


def build_source_payload(source, mode='fast', values=None, error=None, full_string='', formatted=False):
    if mode == 'browser':
        result = {'pure_emoji': '❓', 'bot_emoji': '❓', 'ip_attr': '❓', 'ip_src': '❓',
                  'pure_score': '❓', 'bot_score': '❓', 'full_string': '', 'ip': '❓',
                  'error': None, 'source': source}
    else:
        result = {'ip': '❓', 'ip_attr': '❓', 'ip_src': '❓', 'pure_score': '❓',
                  'shared_users': 'N/A', 'pure_emoji': '❓', 'shared_emoji': '❓',
                  'full_string': '', 'error': None, 'source': source}
    result.update(values or {})
    if formatted:
        result['pure_emoji'] = score_emoji(result['pure_score'])
        if mode == 'browser':
            result['bot_emoji'] = score_emoji(result['bot_score'])
            extra = result['bot_emoji']
        elif source == 'ping0':
            result['shared_emoji'] = shared_emoji(result['shared_users'])
            extra = result['shared_emoji']
        else:
            result['shared_emoji'] = ''
            extra = ''
        attr = result['ip_attr'] if result['ip_attr'] != '❓' else ''
        origin = result['ip_src'] if result['ip_src'] != '❓' else ''
        info = f'{attr}|{origin}'.strip()
        if info == '|' or not info:
            info = '未知'
        result['full_string'] = f"【{result['pure_emoji']}{extra} {info}】"
    if error is not None or full_string:
        result['error'] = error
        result['full_string'] = full_string
    return result


def _empty_source_result(source, status="not_requested", error=None):
    result = build_source_payload(source)
    result["status"] = status
    result["error"] = error
    return result


def not_requested(source):
    return _empty_source_result(source)


def _valid_ip(value):
    try:
        ipaddress.ip_address(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _valid_score(value):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s*", str(value or ""))
    if not match:
        return False
    return 0 <= float(match.group(1)) <= 100


def source_result(source, result=None, status=None, error=None, full_string=None):
    """Validate and copy one source result without changing the source payload."""
    entry = _empty_source_result(source)
    if result:
        entry.update(deepcopy(result))
    entry["source"] = source

    if error is not None:
        entry["error"] = error
    if full_string is not None:
        entry["full_string"] = full_string

    if status is None:
        if entry.get("error"):
            status = "failed"
        elif not _valid_ip(entry.get("ip")):
            status = "failed"
            entry["error"] = entry.get("error") or "未获取到 IP"
        elif not _valid_score(entry.get("pure_score")):
            status = "failed"
            entry["error"] = entry.get("error") or "未获取到评分"
        else:
            status = "success"

    entry["status"] = status
    if status == "success":
        entry["error"] = None
    elif not entry.get("error"):
        entry["error"] = "检测失败"
    return entry


def timeout_result(source):
    return source_result(source, status="timeout", error="超时", full_string="【⏱️ 超时】")


def failed_result(source, error, full_string="【❌ 检测失败】"):
    return source_result(source, status="failed", error=error, full_string=full_string)


def build_aggregate(source_results, legacy_result=None):
    """Build one dual-source result while keeping a legacy top-level projection."""
    entries = {}
    for source in SOURCES:
        value = source_results.get(source)
        entries[source] = deepcopy(value) if value else not_requested(source)

    success = [entry for entry in entries.values() if entry.get("status") == "success"]
    requested = [entry for entry in entries.values() if entry.get("status") != "not_requested"]
    mismatch = (
        len(success) == len(SOURCES)
        and entries["ping0"].get("ip") != entries["ippure"].get("ip")
    )

    if not requested or not success:
        check_status = "failed"
    elif mismatch:
        check_status = "ip_mismatch"
    elif len(success) == len(requested):
        check_status = "success"
    else:
        check_status = "partial"

    errors = []
    for source in SOURCES:
        entry = entries[source]
        if entry.get("status") in ("failed", "timeout"):
            errors.append(f"{SOURCE_LABELS[source]}：{entry.get('error') or '检测失败'}")

    if legacy_result is not None:
        aggregate = deepcopy(legacy_result)
    else:
        preferred = entries["ping0"] if entries["ping0"].get("status") == "success" else entries["ippure"]
        if preferred.get("status") != "success":
            preferred = None
        aggregate = {
            "ip": preferred.get("ip") if preferred else "❓",
            "pure_score": preferred.get("pure_score") if preferred else "❓",
            "pure_emoji": preferred.get("pure_emoji") if preferred else "❓",
            "bot_score": preferred.get("bot_score", "N/A") if preferred else "N/A",
            "bot_emoji": preferred.get("bot_emoji", "❓") if preferred else "❓",
            "shared_users": preferred.get("shared_users") if preferred else "N/A",
            "shared_emoji": preferred.get("shared_emoji") if preferred else "❓",
            "ip_attr": preferred.get("ip_attr") if preferred else "❓",
            "ip_src": preferred.get("ip_src") if preferred else "❓",
            "full_string": preferred.get("full_string") if preferred else "【❌ 检测失败】",
            "source": preferred.get("source") if preferred else "failed",
            "error": None if preferred else "；".join(errors) or "检测失败",
        }

    aggregate["source_results"] = entries
    aggregate["check_status"] = check_status
    aggregate["ip_mismatch"] = mismatch
    if check_status in ("failed", "partial"):
        aggregate["error"] = "；".join(errors) or aggregate.get("error")
    return aggregate


def wrap_legacy_result(result, requested_source):
    """Keep existing single-source calls working and expose them as source results."""
    legacy = deepcopy(result)
    actual = legacy.get("source")
    entries = {source: not_requested(source) for source in SOURCES}

    if actual in SOURCES:
        actual_entry = source_result(actual, legacy)
        entries[actual] = actual_entry
        if requested_source in SOURCES and actual != requested_source:
            entries[requested_source] = failed_result(
                requested_source,
                "主源失败，已降级",
                full_string="【❌ 主源失败】",
            )
    else:
        status = "timeout" if legacy.get("error") == "Timeout" else "failed"
        failed_sources = (requested_source,) if requested_source in SOURCES else SOURCES
        for source in failed_sources:
            entries[source] = source_result(
                source,
                legacy,
                status=status,
                error=legacy.get("error") or "检测失败",
                full_string=legacy.get("full_string") or "【❌ 检测失败】",
            )

    return build_aggregate(entries, legacy_result=legacy)


def failure_aggregate(requested_source, error, name_suffix=None):
    sources = SOURCES if requested_source == "both" else (requested_source,)
    entries = {source: not_requested(source) for source in SOURCES}
    for source in sources:
        entries[source] = failed_result(source, error)
    aggregate = build_aggregate(entries)
    if name_suffix:
        aggregate["full_string"] = name_suffix
    return aggregate


def _source_suffix_value(entry):
    status = entry.get("status")
    if status == "success":
        return entry.get("pure_score") or "❓"
    if status == "timeout":
        return "超时"
    if status == "failed":
        return "失败"
    return "未检测"


def dual_suffix(source_results):
    ping0 = _source_suffix_value(source_results.get("ping0") or not_requested("ping0"))
    ippure = _source_suffix_value(source_results.get("ippure") or not_requested("ippure"))
    return f"【Ping0 {ping0}｜IPPure {ippure}】"


def result_suffix(result, requested_source):
    if result.get("source_results") and requested_source == "both":
        return dual_suffix(result["source_results"])
    return result.get("full_string") or "【❌ 检测失败】"


def status_label(result, requested_source):
    if requested_source == "both" and result.get("check_status"):
        labels = {
            "success": "✅",
            "partial": "⚠️ 部分成功",
            "failed": "❌ 失败",
            "ip_mismatch": "⚠️ IP 不一致",
        }
        return labels.get(result["check_status"], "❌ 失败")

    if result.get("ip") in (None, "", "❓") or not _valid_score(result.get("pure_score")):
        return "❌ 失败"
    if result.get("source") != requested_source:
        return "⚠️ 降级"
    return "✅"


def build_node_result(
    node_id,
    original_name,
    proxy,
    result,
    requested_source,
    display_base_name=None,
    name_suffix=None,
):
    aggregate = result if result.get("source_results") else wrap_legacy_result(result, requested_source)
    base_name = display_base_name or original_name
    suffix = name_suffix if name_suffix is not None else result_suffix(aggregate, requested_source)
    return {
        "id": node_id,
        "original_name": original_name,
        "display_base_name": base_name,
        "name": f"{base_name}{suffix}",
        "ip": aggregate.get("ip", "❓"),
        "risk": aggregate.get("pure_score", "❓"),
        "bot": aggregate.get("bot_score", "N/A"),
        "shared": aggregate.get("shared_users", "N/A"),
        "type": aggregate.get("ip_attr", "❓"),
        "native": aggregate.get("ip_src", "❓"),
        "source": aggregate.get("source", "unknown"),
        "source_results": aggregate["source_results"],
        "check_status": aggregate.get("check_status", "failed"),
        "ip_mismatch": aggregate.get("ip_mismatch", False),
        "status": status_label(aggregate, requested_source),
        "error": aggregate.get("error"),
        "proxy_config": proxy,
    }

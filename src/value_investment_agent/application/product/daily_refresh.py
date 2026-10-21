"""Check immutable registered inputs before acquiring another daily refresh."""
from datetime import datetime
import json
from pathlib import Path
import hashlib
import re

from ..hotspot.current_registry import load_price_conditions
from .quote_bridge import execute_quote_bridge_for_symbol

PUBLIC_NOTES = frozenset({
    '公告增量采集或复核未完成；保留研究门禁，其他已核验证券继续。',
    '本次更新尚未完成；继续显示历史已验证快照。',
    '当前价格条件采集存在缺项；未通过验证的证券不会升级为当前触发。',
    '行情采集未完成（网络或来源不可用）；本次继续使用已登记行情。',
    '刷新后完整输入未通过最近完成交易日及来源校验；不发布新快照。',
    '刷新后快照生成失败，Web 保留上一验证版本。',
    '采集或登记不完整：未发布新快照，Web 保留上一验证版本，不能称为本次新数据。',
    '部分证券数据未能更新；已核验证券可用，缺项不代表今日已刷新。',
})


def read_latest_run(root: Path) -> dict | None:
    """Read local update status without executing commands or exposing bootstrap secrets."""
    try:
        value = json.loads((root / '.tmp/daily-workbench-latest-run.json').read_text(encoding='utf-8-sig'))
        if (value['schema_version'] != 'daily-workbench-run-v1' or value['action'] != 'no_order'
                or value['status'] not in {'SUCCESS', 'PARTIAL', 'BLOCKED'}):
            return None
        fields = ('schema_version', 'action', 'mode', 'started_at', 'finished_at', 'status',
                  'exit_code', 'published', 'publication_id', 'retained_publication_id', 'notes')
        result = {key: value.get(key) for key in fields}
        notes = value.get('notes')
        result['notes'] = [note for note in notes if isinstance(note, str) and note in PUBLIC_NOTES] if isinstance(notes, list) else []
        if isinstance(value.get('marketwide_screen'), dict):
            result['screening'] = _screening_summary(root, value['marketwide_screen'])
        if isinstance(value.get('value_research_priority'), dict):
            result['research_priority'] = _priority_summary(root, value['value_research_priority'])
        if isinstance(notes, list) and len(result['notes']) != len(notes):
            result['notes'].append('部分运行说明仅保留在本机回执；请检查本次更新状态。')
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _priority_summary(root, binding):
    """Expose verified scheduling counts, never raw facts or investment ranks."""
    unavailable = {'status': 'UNVERIFIED', 'scope': 'RESEARCH_SCHEDULING_ONLY'}
    try:
        digest = binding['sha256']
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            return unavailable
        path = (root / binding['path']).resolve()
        if (not path.is_relative_to((root / 'runtime/daily-marketwide').resolve())
                or path.name != 'research-priority-v2.json' or path.stat().st_size > 10_000_000):
            return unavailable
        raw = path.read_bytes()
        if len(raw) > 10_000_000 or hashlib.sha256(raw).hexdigest() != digest:
            return unavailable
        value = json.loads(raw)
        from ..research.value_research_queue import _canonical_hash
        if (value['schema_version'] != 'value-research-priority-v2'
                or value['action'] != 'no_order' or value['admission'] != 'RESEARCH_QUEUE_ONLY'
                or value['content_sha256'] != _canonical_hash({k: v for k, v in value.items() if k != 'content_sha256'})):
            return unavailable
        deep, enrichment = value['deep_research_priority'], value['evidence_enrichment_work_queue']
        rows = deep + enrichment
        if (len(rows) > 6000 or len({row['symbol'] for row in rows}) != len(rows)
                or any(type(value[key]) is not int or not 0 <= value[key] <= len(queue)
                       for key, queue in (('selected_deep_research_count', deep), ('selected_enrichment_count', enrichment)))):
            return unavailable
        result = {'status': 'VERIFIED_RESEARCH_PRIORITY', 'scope': 'RESEARCH_SCHEDULING_ONLY',
            'as_of': value['as_of'], 'deep_research_count': len(deep), 'enrichment_count': len(enrichment),
            'selected_deep_research_count': value['selected_deep_research_count'],
            'selected_enrichment_count': value['selected_enrichment_count'],
            'formal_eligibility': False, 'action': 'no_order'}
        if isinstance(binding.get('execution'), dict):
            result['execution'] = _enrichment_execution_summary(root, path.parent, binding['execution'], value)
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable


def _enrichment_execution_summary(root, folder, binding, queue):
    unavailable = {'status': 'UNVERIFIED'}
    try:
        path = (root / binding['path']).resolve()
        if not path.is_relative_to(folder) or path.name != 'execution.json' or path.stat().st_size > 500_000:
            return unavailable
        raw = path.read_bytes()
        if len(raw) > 500_000 or hashlib.sha256(raw).hexdigest() != binding['sha256']:
            return unavailable
        value = json.loads(raw)
        rows = value['items']
        candidates = {row['symbol']: row for row in queue['evidence_enrichment_work_queue']}
        if (value['schema_version'] != 'value-enrichment-execution-v1' or value['action'] != 'no_order'
                or value['queue_content_sha256'] != queue['content_sha256'] or value['formal_eligibility'] is not False
                or value['new_fact_approvals'] != 0 or not 0 <= len(rows) <= 3
                or type(value['attempted_count']) is not int or value['attempted_count'] != len(rows)
                or len({row['symbol'] for row in rows}) != len(rows)
                or any(row['symbol'] not in candidates or row['formal_eligibility'] is not False for row in rows)):
            return unavailable
        return {'status': 'VERIFIED_RESEARCH_EXECUTION', 'attempted_count': len(rows),
            'reevaluated_count': sum('QUALITY_REEVALUATED' in row['transitions'] for row in rows),
            'data_gap_count': sum(row['state'] == 'DATA_UNAVAILABLE' for row in rows),
            'items': [{'symbol': row['symbol'], 'company_name': candidates[row['symbol']]['company_name'],
                'state': row['state'], 'extracted_candidates': row.get('extracted_candidates'),
                'matched_candidates': row.get('matched_candidates')} for row in rows],
            'formal_eligibility': False, 'action': 'no_order'}
    except (OSError, ValueError, TypeError, KeyError):
        return unavailable


def _screening_summary(root, binding):
    """Display a pinned research scan separately from the decision publication."""
    unavailable = {'status': 'UNVERIFIED', 'scope': 'RESEARCH_LEADS_NOT_ACTIONS'}
    try:
        name, digest = binding['manifest_path'], binding['manifest_sha256']
        if not isinstance(name, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            return unavailable
        base = (root / 'runtime/daily-marketwide').resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(base) or path.name != 'manifest.json' or path.is_symlink():
            return unavailable
        if path.stat().st_size > 512_000:
            return unavailable
        raw = path.read_bytes()
        if len(raw) > 512_000 or hashlib.sha256(raw).hexdigest() != digest:
            return unavailable
        summary = json.loads(raw)['summary']
        if (summary['action'] != 'no_order' or summary['input_mode'] != 'LIVE_COLLECTION'
                or summary['rule_version'] != 'm2-evidence-screen-v3'):
            return unavailable
        health = summary['data_health']
        counts = summary['channel_counts']
        lead_count = summary.get('lead_count', summary.get('deduplicated_lead_count'))
        if lead_count is None:
            lead_count = summary['legacy_comparison']['new_candidate_count']
        if any(type(n) is not int or n < 0 for n in [health['universe_count'], lead_count, *counts.values()]):
            return unavailable
        return {'status': 'VERIFIED_RESEARCH_SCAN', 'scope': 'RESEARCH_LEADS_NOT_ACTIONS',
            'as_of': summary['as_of'], 'quote_date_verification': summary['quote_date_verification'],
            'universe_count': health['universe_count'], 'lead_count': lead_count,
            'channel_counts': counts, 'data_status': health['status'],
            'blockers': health.get('blockers', []), 'formal_eligibility': False, 'action': 'no_order'}
    except (OSError, ValueError, TypeError, KeyError):
        return unavailable


def refresh_readiness(root: Path, *, now: datetime, symbols: list[str]) -> dict:
    """Reuse only complete, hash-verified latest-session observations, not eligibility."""
    prices = load_price_conditions(root, now=now, research_version=None)
    rows, active, selected = {}, set(), set()
    try:
        registry = json.loads((root / "config/current-price-conditions.json").read_bytes())
        active = {row["symbol"] for row in registry["items"]}
        selected = set(registry.get("selected_symbols", active))
        rows = {row["symbol"]: row["price_action_plan"] for row in prices["items"]
                if not row["price_action_plan"].get("candidate_lifecycle")}
        dates = {rows[symbol]["market_trade_date"] for symbol in active if symbol in rows}
        prices_ready = (bool(active) and active == selected and active <= rows.keys() and len(dates) == 1
                        and all(rows[symbol].get("daily_selection") for symbol in active))
        if not active and not selected and prices.get("status") == "CURRENT_EMPTY_SELECTION":
            dates = {prices["selection_trade_date"]}
            from zoneinfo import ZoneInfo
            # Only reuse on the collection session; later days must rescreen.
            prices_ready = prices["selection_trade_date"] == now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    except (OSError, ValueError, KeyError, TypeError):
        prices_ready, dates = False, set()
    quotes = {}
    for symbol in symbols:
        try:
            quotes[symbol] = execute_quote_bridge_for_symbol(root, symbol, today=now)
        except (OSError, ValueError, KeyError, TypeError):
            quotes[symbol] = {"status": "QUOTE_READ_FAILED", "quote": None,
                              "reason": "该证券行情读取失败；不升级资格，其他证券继续核验。"}
    valid = {"QUOTE_VERIFIED_FOR_RESEARCH_INPUT", "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
             "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY",
             "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY"}
    quote_valid = {symbol: (
        row.get("quote_verification_status", row["status"]) in valid and (row.get("quote") or {}).get("quote_date")
        == (row.get("quote") or {}).get("latest_completed_session")
        and bool((row.get("quote") or {}).get("quote_date")))
        for symbol, row in quotes.items()}
    quote_ready = bool(symbols) and all(quote_valid.values())
    price_rows = [dict(symbol=symbol, status="VERIFIED" if symbol in rows else "MISSING_OR_INVALID",
                      market_trade_date=rows.get(symbol, {}).get("market_trade_date"),
                      sources=rows.get(symbol, {}).get("current_reference_close"),
                      missing=[] if symbol in rows else ["CURRENT_PRICE_CASE_UNAVAILABLE"])
                  for symbol in sorted(selected)]
    quote_rows = [dict(symbol=symbol, status="VERIFIED" if quote_valid[symbol] else "MISSING_OR_INVALID",
                      market_trade_date=(row.get("quote") or {}).get("quote_date"),
                      latest_completed_session=(row.get("quote") or {}).get("latest_completed_session"),
                      sources=row.get("sources", []),
                      reason=row.get("reason"), missing=[] if quote_valid[symbol] else [row["status"]])
                  for symbol, row in quotes.items()]
    integrity_ok = "CURRENT_PRICE_REGISTRY_UNAVAILABLE" not in prices.get("blockers", [])
    return dict(action="no_order", prices_ready=bool(prices_ready), quotes_ready=quote_ready,
                market_trade_dates=sorted(dates), quotes=quotes,
                price_securities=price_rows, quote_securities=quote_rows,
                publication_ready=integrity_ok and (bool(rows) or any(quote_valid.values())
                    or (prices.get("status") == "CURRENT_EMPTY_SELECTION" and bool(prices_ready))),
                core_integrity_ok=integrity_ok,
                blockers=prices.get("blockers", []))

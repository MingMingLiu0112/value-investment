"""Check immutable registered inputs before acquiring another daily refresh."""
from datetime import datetime
import json
from pathlib import Path

from ..hotspot.current_registry import load_price_conditions
from .quote_bridge import execute_quote_bridge_for_symbol

PUBLIC_NOTES = frozenset({
    '本次更新尚未完成；继续显示历史已验证快照。',
    '当前价格条件采集存在缺项；未通过验证的证券不会升级为当前触发。',
    '行情采集未完成（网络或来源不可用）；本次继续使用已登记行情。',
    '刷新后完整输入未通过最近完成交易日及来源校验；不发布新快照。',
    '刷新后快照生成失败，Web 保留上一验证版本。',
    '采集或登记不完整：未发布新快照，Web 保留上一验证版本，不能称为本次新数据。',
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
        if isinstance(notes, list) and len(result['notes']) != len(notes):
            result['notes'].append('部分运行说明仅保留在本机回执；请检查本次更新状态。')
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None


def refresh_readiness(root: Path, *, now: datetime, symbols: list[str]) -> dict:
    """Reuse only complete, hash-verified latest-session observations, not eligibility."""
    prices = load_price_conditions(root, now=now, research_version=None)
    try:
        registry = json.loads((root / "config/current-price-conditions.json").read_bytes())
        active = {row["symbol"] for row in registry["items"]}
        rows = {row["symbol"]: row["price_action_plan"] for row in prices["items"]
                if not row["price_action_plan"].get("candidate_lifecycle")}
        dates = {rows[symbol]["market_trade_date"] for symbol in active if symbol in rows}
        prices_ready = (len(active) == 5 and active <= rows.keys() and len(dates) == 1
                        and all(rows[symbol].get("daily_selection") for symbol in active))
    except (OSError, ValueError, KeyError, TypeError):
        prices_ready, dates = False, set()
    quotes = {symbol: execute_quote_bridge_for_symbol(root, symbol, today=now) for symbol in symbols}
    valid = {"QUOTE_VERIFIED_FOR_RESEARCH_INPUT", "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
             "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY"}
    quote_ready = bool(symbols) and all(
        row["status"] in valid and (row.get("quote") or {}).get("quote_date")
        == (row.get("quote") or {}).get("latest_completed_session")
        and (row.get("quote") or {}).get("quote_date") in dates
        for row in quotes.values())
    return dict(action="no_order", prices_ready=bool(prices_ready), quotes_ready=quote_ready,
                market_trade_dates=sorted(dates), quotes=quotes)

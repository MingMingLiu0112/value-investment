"""Compose the daily research-status rows from the registered real inputs.

The section answers one question per registered symbol: does the registered
research cutoff still cover the verified close, or must the company be
re-researched before any price comparison? It reuses the shared quote bridge,
never admits a price, never re-registers research and never invents an event.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from .common import load_json_object
from .quote_bridge import execute_quote_bridge_for_symbol


SCHEMA_VERSION = "daily-research-status-v1"
POINTER_PATH = "config/current-quote-bridge.json"
_EXECUTION_ERRORS = (OSError, ValueError, KeyError, TypeError, IndexError,
                     AttributeError, UnicodeError, json.JSONDecodeError)


def registered_quote_symbols(root: Path) -> list[str]:
    """Symbols with a registered quote binding; an unreadable pointer registers nothing."""
    try:
        payload = load_json_object(root / POINTER_PATH, "quote bridge pointer")
    except _EXECUTION_ERRORS:
        return []
    quotes = payload.get("quotes")
    if not isinstance(quotes, dict):
        return []
    return sorted(symbol for symbol in quotes if isinstance(symbol, str))


def _row(execution: Mapping[str, Any], name: str | None) -> dict[str, Any]:
    symbol = str(execution.get("symbol") or "")
    quote = execution.get("quote")
    quote = quote if isinstance(quote, dict) else {}
    research_day = execution.get("research_day")
    quote_date = quote.get("quote_date")
    research_day = research_day if isinstance(research_day, str) else None
    quote_date = quote_date if isinstance(quote_date, str) else None
    comparable = research_day is not None and quote_date is not None
    return {
        "symbol": symbol,
        "name": name or symbol,
        "research_day": research_day,
        "quote_date": quote_date,
        "bridge_status": execution.get("status"),
        "price_admitted": execution.get("price_admitted") is True,
        "needs_re_research": bool(comparable and quote_date > research_day),
        "research_covers_close": bool(comparable and quote_date <= research_day),
        "reason": execution.get("reason"),
        "next_step": execution.get("next_step"),
    }


def build_daily_research_status(root: Path, *, today: datetime,
                                names: Mapping[str, str] | None = None) -> dict[str, Any]:
    """One row per registered symbol; a per-symbol failure stays isolated."""
    names = names or {}
    rows: list[dict[str, Any]] = []
    for symbol in registered_quote_symbols(root):
        try:
            execution = execute_quote_bridge_for_symbol(root, symbol, today=today)
            rows.append(_row(execution, names.get(symbol)))
        except _EXECUTION_ERRORS as error:
            rows.append({"symbol": symbol, "name": names.get(symbol, symbol),
                         "research_day": None, "quote_date": None,
                         "bridge_status": "EXECUTION_FAILED", "price_admitted": False,
                         "needs_re_research": False, "research_covers_close": False,
                         "reason": f"价格桥接执行失败：{type(error).__name__}",
                         "next_step": None})
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "no_order",
        "status": ("NO_REGISTERED_QUOTES" if not rows
                   else "RE_RESEARCH_REQUIRED" if any(row["needs_re_research"] for row in rows)
                   else "REGISTERED"),
        "registered_count": len(rows),
        "verified_close_count": sum(1 for row in rows if row["quote_date"]),
        "needs_re_research_count": sum(1 for row in rows if row["needs_re_research"]),
        "admitted_count": sum(1 for row in rows if row["price_admitted"]),
        "rows": rows,
    }

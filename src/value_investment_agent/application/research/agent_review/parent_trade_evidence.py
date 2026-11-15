"""Replay standalone parent balance evidence without assigning forecast cash."""

from datetime import datetime
from pathlib import Path
import json

from .task_execution_v1 import _hash
from ...product.common import require_inside
from ....infrastructure.filings import parent_trade_balances as trade


def replay_parent_trade_evidence(*, root: Path, context: dict, selection: dict,
                                 cutoff: datetime) -> dict:
    if set(selection) != {"symbol", "diagnostic", "issuer_name",
                          "fiscal_year", "available_at"}:
        raise ValueError("PARENT_TRADE_SELECTION_INVALID")
    symbol = selection["symbol"]
    if symbol != context.get("symbol") or selection["issuer_name"] != context.get("issuer_name"):
        raise ValueError("PARENT_TRADE_CONTEXT_ISSUER_CHANGED")
    available = datetime.fromisoformat(selection["available_at"])
    if cutoff.utcoffset() is None or available.utcoffset() is None or available > cutoff:
        raise ValueError("PARENT_TRADE_SOURCE_NOT_AVAILABLE")
    ref = selection["diagnostic"]
    path = require_inside(root / "runtime", root / ref["path"], "parent trade diagnostic")
    raw = path.read_bytes()
    if _hash(raw) != ref["sha256"]:
        raise ValueError("PARENT_TRADE_DIAGNOSTIC_HASH_CHANGED")
    receipt = json.loads(raw)
    if (set(receipt) != {"symbol", "diagnostic", "sources"} or receipt["symbol"] != symbol
            or len(receipt["sources"]) != 3):
        raise ValueError("PARENT_TRADE_SOURCE_IDENTITY_INVALID")
    reports = [
        trade.read_parent_trade_balances(
            require_inside(root / "runtime", root / source["path"], "parent trade PDF"),
            expected_sha256=source["sha256"], issuer_name=selection["issuer_name"],
            balance_periods=tuple(source["balance_periods"]), cash_periods=tuple(source["cash_periods"]),
        )
        for source in receipt["sources"]
    ]
    year = selection["fiscal_year"]
    result = trade.reconcile_parent_trade_intervals(*reports, fiscal_year=year)
    if result != receipt["diagnostic"]:
        raise ValueError("PARENT_TRADE_DIAGNOSTIC_CHANGED")
    balances = "、".join(f"{period} {value}" for period, value in zip(
        result["periods"], result["cash_direction_balance_proxy_cny"], strict=True))
    text = ("母公司营运资金历史证据：三项余额的现金方向代理（人民币元）为"
            + balances
            + "。余额方向反转；不得直接年化、替代现金流分解或将缺失预测填零。")
    last_digest = reports[-1]["source_sha256"]
    return dict(id=f"official:parent-trade:{symbol}:{ref['sha256']}",
                source_id="official:" + last_digest, pdf_sha256=last_digest,
                available_at=available.isoformat(), period=f"{year+1}-06-30",
                physical_page=reports[-1]["trade_balances"]["应付账款"]["physical_page"],
                scope="ISSUER_PARENT_STANDALONE_BALANCE_PROXY", unit="TEXT",
                field="parent_trade_working_capital_balance_history",
                text=text, text_sha256=_hash(text.encode("utf-8")),
                kind="HISTORICAL_BALANCE_PROXY_NOT_CASH_OR_FORECAST")

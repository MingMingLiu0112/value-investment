"""Low-memory, auditable all-A-share initial screening."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


EASTMONEY_SOURCE = (
    "AkShare / Eastmoney all-A market snapshot",
    "https://quote.eastmoney.com/center/gridlist.html#hs_a_board",
    "market-screen-v1-eastmoney",
)
TENCENT_SOURCE = (
    "AkShare / Tencent all-A market snapshot",
    "https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj",
    "market-screen-v1-tencent",
)


@dataclass(frozen=True)
class MarketCandidate:
    symbol: str
    name: str
    sector: str
    board: str
    current_price: Decimal
    pe: Decimal
    pb: Decimal | None
    market_cap: Decimal
    score: Decimal
    status: str = "initial_screen_pending_financial_review"


def _number(value) -> Decimal | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    return number if number.is_finite() else None


def _value(row: dict, *names: str):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def board_for_symbol(symbol: str) -> str:
    """Classify listing board from the A-share code, independently of industry."""
    if symbol.startswith(("688", "689")):
        return "科创板"
    if symbol.startswith(("300", "301")):
        return "创业板"
    if symbol.startswith(("4", "8", "92")):
        return "北交所"
    if symbol.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "主板"
    return "待板块映射"


def screen_rows(rows: list[dict], sectors: dict[str, str], require_pb: bool = True) -> list[MarketCandidate]:
    """Apply a conservative public-data initial screen without trade signals."""
    candidates: list[MarketCandidate] = []
    for row in rows:
        symbol = str(_value(row, "代码", "symbol", "code") or "").zfill(6)
        name = str(_value(row, "名称", "name") or "").strip()
        if len(symbol) != 6 or not symbol.isdigit() or not name or "ST" in name.upper():
            continue
        price = _number(_value(row, "最新价", "current_price"))
        pe = _number(_value(row, "市盈率-动态", "动态市盈率", "pe"))
        pb = _number(_value(row, "市净率", "pb"))
        market_cap = _number(_value(row, "总市值", "market_cap"))
        required_values = (price, pe, market_cap) if not require_pb else (price, pe, pb, market_cap)
        if not all(value is not None and value > 0 for value in required_values):
            continue
        # This deliberately favours established, reasonably priced companies.
        # It is only an enrichment queue, never an investment recommendation.
        if pe > Decimal("25") or market_cap < Decimal("5000000000"):
            continue
        if require_pb and (pb is None or pb > Decimal("3")):
            continue
        pe_weight = Decimal("45") if require_pb else Decimal("65")
        cap_weight = Decimal("20") if require_pb else Decimal("35")
        score = min(Decimal("1"), (Decimal("25") - pe) / Decimal("25")) * pe_weight
        if require_pb:
            score += min(Decimal("1"), (Decimal("3") - pb) / Decimal("3")) * Decimal("35")
        score += min(Decimal("1"), market_cap / Decimal("100000000000")) * cap_weight
        score = score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sector = sectors.get(symbol, str(_value(row, "行业", "industry", "sector") or "待行业映射"))
        status = "initial_screen_pending_financial_review" if require_pb else "initial_screen_pending_pb_financial_review"
        candidates.append(MarketCandidate(symbol, name, sector, board_for_symbol(symbol), price, pe, pb, market_cap, score, status))
    return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.sector, candidate.symbol))


class AllAMarketAdapter:
    """Fetch the full A-share snapshot once, then optionally map industries."""

    def fetch(self, include_industry: bool = True) -> tuple[list[dict], dict[str, str], list[MarketCandidate], bytes, datetime, tuple[str, str, str]]:
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError("AkShare is not installed") from error
        fetched_at = datetime.now(timezone.utc)
        source = EASTMONEY_SOURCE
        fallback_reason: str | None = None
        industry_mapping_error: str | None = None
        try:
            frame = ak.stock_zh_a_spot_em()
            rows = frame.to_dict("records")
        except Exception as eastmoney_error:
            fallback_reason = str(eastmoney_error)
            frame = ak.stock_zh_a_spot_tx()
            rows = self._tencent_rows(frame.to_dict("records"))
            sectors = {}
            candidates = screen_rows(rows, sectors, require_pb=False)
            source = TENCENT_SOURCE
        else:
            if include_industry:
                try:
                    sectors = self._industry_map(ak)
                except Exception as error:
                    # Industry classification must not discard an otherwise
                    # complete all-market quote snapshot or silently switch
                    # it to a source with different valuation coverage.
                    sectors = {}
                    industry_mapping_error = str(error)
            else:
                sectors = {}
            candidates = screen_rows(rows, sectors)
        universe = []
        for row in rows:
            symbol = str(_value(row, "代码", "symbol", "code") or "").zfill(6)
            name = str(_value(row, "名称", "name") or "").strip()
            if len(symbol) == 6 and symbol.isdigit() and name:
                universe.append({"symbol": symbol, "name": name, "sector": sectors.get(symbol, "待行业映射")})
        raw = json.dumps({
            "rows": rows, "candidate_count": len(candidates), "source": source[0],
            "industry_mapping_count": len(sectors),
            "industry_mapping_error": industry_mapping_error,
            "fallback_reason": fallback_reason,
        }, ensure_ascii=False, default=str).encode()
        return universe, sectors, candidates, raw, fetched_at, source

    @staticmethod
    def _tencent_rows(rows: list[dict]) -> list[dict]:
        board_labels = {
            "GP-A-KCB": "科创板",
            "GP-A-CYB": "创业板",
        }
        converted: list[dict] = []
        for row in rows:
            code = str(row.get("code", ""))[-6:]
            stock_type = str(row.get("stock_type", ""))
            converted.append({
                "代码": code,
                "名称": row.get("name"),
                "最新价": row.get("zxj"),
                "市盈率-动态": row.get("pe_ttm"),
                "总市值": _number(row.get("zsz")) * Decimal("100000000") if _number(row.get("zsz")) is not None else None,
                "板块": board_labels.get(stock_type, "主板" if stock_type.startswith("GP-A") else "待板块映射"),
            })
        return converted

    @staticmethod
    def _industry_map(ak) -> dict[str, str]:
        sectors: dict[str, str] = {}
        try:
            boards = ak.stock_board_industry_name_em().to_dict("records")
        except Exception:
            return sectors
        for board in boards:
            board_name = str(_value(board, "板块名称", "name") or "").strip()
            if not board_name:
                continue
            try:
                members = ak.stock_board_industry_cons_em(symbol=board_name).to_dict("records")
            except Exception:
                continue
            for member in members:
                symbol = str(_value(member, "代码", "symbol", "code") or "").zfill(6)
                if len(symbol) == 6 and symbol.isdigit():
                    sectors.setdefault(symbol, board_name)
        return sectors

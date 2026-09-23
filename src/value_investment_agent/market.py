"""Low-memory, auditable all-A-share initial screening.

LEGACY_VALUE_SCREEN

The PE<=25 / PB<=3 / market-cap>=5bn selection in this module is retained for
historical comparison and enrichment only. M2 must not use its score as a
candidate priority.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


LEGACY_VALUE_SCREEN = True


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
SINA_VALUATION_SOURCE = (
    "AkShare / Sina all-A valuation snapshot",
    "https://vip.stock.finance.sina.com.cn/mkt/#hs_a",
    "market-screen-v2-sina-valuation",
)
TENCENT_SINA_SOURCE = (
    "Tencent all-A market snapshot + Sina valuation cross-check",
    "https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj | https://vip.stock.finance.sina.com.cn/mkt/#hs_a",
    "market-screen-v2-tencent-sina-cross-check",
)
EASTMONEY_INDUSTRY_SOURCE = "AkShare / Eastmoney industry-board mapping"
SINA_SHENWAN_INDUSTRY_SOURCE = "AkShare / Sina Shenwan level-1 industry mapping"
MIN_UNIVERSE_SIZE = 4000


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
    # SZSE official stock list confirms this renamed security on 2026-09-07.
    if symbol == "302132" or symbol.startswith(("300", "301")):
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
        if rejection_reason(row, require_pb):
            continue
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


def rejection_reason(row: dict, require_pb: bool = True) -> str | None:
    symbol = str(_value(row, '代码', 'symbol', 'code') or '').zfill(6)
    name = str(_value(row, '名称', 'name') or '').strip()
    if not (len(symbol) == 6 and symbol.isdigit() and name):
        return 'invalid_identity'
    if board_for_symbol(symbol) == '待板块映射':
        return 'unmapped_board'
    if 'ST' in name.upper():
        return 'risk_warning_st'
    proof = row.get('price_cross_check') or {}
    if proof.get('status') in {'conflict', 'missing'}:
        return 'price_conflict' if proof['status'] == 'conflict' else 'price_cross_check_missing'
    price = _number(_value(row, '最新价', 'current_price'))
    pe = _number(_value(row, '市盈率-动态', '动态市盈率', 'pe'))
    pb = _number(_value(row, '市净率', 'pb'))
    cap = _number(_value(row, '总市值', 'market_cap'))
    required = (price, pe, cap, pb) if require_pb else (price, pe, cap)
    if not all(x is not None and x > 0 for x in required):
        return 'missing_or_nonpositive_inputs'
    if pe > Decimal('25'): return 'pe_above_25'
    if cap < Decimal('5000000000'): return 'market_cap_below_5bn'
    if require_pb and pb > Decimal('3'): return 'pb_above_3'
    return None


def validate_snapshot(rows: list[dict]) -> None:
    codes = [str(_value(r,'代码','symbol','code') or '').zfill(6) for r in rows]
    if len(rows) < MIN_UNIVERSE_SIZE:
        raise ValueError(f'Market response truncated: {len(rows)} rows; expected at least {MIN_UNIVERSE_SIZE}')
    if len(set(codes)) != len(codes):
        raise ValueError('Duplicate market codes: refuse an overlapping/paginated snapshot')


def market_coverage_audit(rows: list[dict], require_pb: bool) -> dict:
    outcomes, boards, candidate_boards = Counter(), Counter(), Counter()
    decisions = []
    for r in rows:
        code = str(_value(r,'代码','symbol','code') or '').zfill(6)
        board = board_for_symbol(code)
        reason = rejection_reason(r,require_pb) or 'candidate'
        outcomes[reason] += 1
        boards[board] += 1
        if reason == 'candidate': candidate_boards[board] += 1
        decisions.append({'symbol':code,'name':_value(r,'名称','name'),'board':board,'outcome':reason})
    return {'received_rows':len(rows),'unique_symbols':len({d['symbol'] for d in decisions}),
        'board_counts':dict(boards),'candidate_board_counts':dict(candidate_boards),
        'outcome_counts':dict(outcomes),'decisions':decisions,
        'official_universe_reconciled':False,
        'coverage_status':'provider_snapshot_not_yet_reconciled_to_exchange_security_lists',
        'screen_rule_version':'public-value-screen-v1-pe25-pb3-cap5bn'}


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
        industry_mapping_source: str | None = None
        industry_rows: list[dict] = []
        try:
            frame = ak.stock_zh_a_spot_em()
            rows = frame.to_dict("records")
            validate_snapshot(rows)
        except Exception as eastmoney_error:
            fallback_reason = f"{type(eastmoney_error).__name__}: {eastmoney_error}"
            frame = ak.stock_zh_a_spot_tx()
            rows = self._tencent_rows(frame.to_dict("records"))
            validate_snapshot(rows)
            sectors = {}
            source = TENCENT_SOURCE
            try:
                rows, cross_check = self._merge_tencent_with_sina(rows, self._sina_rows())
                source = TENCENT_SINA_SOURCE
            except Exception as sina_error:
                cross_check = {"sina_status": "unavailable", "sina_error": f"{type(sina_error).__name__}: {sina_error}"}
                fallback_reason += f"; Sina valuation fallback unavailable: {cross_check['sina_error']}"
        if include_industry:
            try:
                sectors = self._industry_map(ak)
                if len(sectors) < 4000:
                    raise RuntimeError(f"Eastmoney industry coverage is incomplete: {len(sectors)}")
                industry_mapping_source = EASTMONEY_INDUSTRY_SOURCE
            except Exception as eastmoney_industry_error:
                try:
                    sectors = self._sina_shenwan_industry_map()
                    if len(sectors) < 4000:
                        raise RuntimeError(f"Sina Shenwan industry coverage is incomplete: {len(sectors)}")
                    industry_mapping_source = SINA_SHENWAN_INDUSTRY_SOURCE
                    industry_mapping_error = f"Eastmoney fallback: {type(eastmoney_industry_error).__name__}: {eastmoney_industry_error}"
                except Exception as sina_industry_error:
                    sectors = {}
                    industry_mapping_error = (
                        f"Eastmoney: {type(eastmoney_industry_error).__name__}: {eastmoney_industry_error}; "
                        f"Sina Shenwan: {type(sina_industry_error).__name__}: {sina_industry_error}"
                    )
        else:
            sectors = {}
        industry_rows = [
            {"symbol": symbol, "sector": sector}
            for symbol, sector in sorted(sectors.items())
        ]
        candidates = screen_rows(rows, sectors, require_pb=source != TENCENT_SOURCE)
        universe = []
        for row in rows:
            symbol = str(_value(row, "代码", "symbol", "code") or "").zfill(6)
            name = str(_value(row, "名称", "name") or "").strip()
            if len(symbol) == 6 and symbol.isdigit() and name:
                universe.append({"symbol": symbol, "name": name, "sector": sectors.get(symbol, "待行业映射")})
        mapped_candidate_count = sum(1 for candidate in candidates if candidate.symbol in sectors)
        raw = json.dumps({
            "rows": rows, "candidate_count": len(candidates), "source": source[0],
            "industry_mapping_count": mapped_candidate_count,
            "industry_mapping_source": industry_mapping_source,
            "industry_mapping_error": industry_mapping_error,
            "industry_rows": industry_rows,
            "fallback_reason": fallback_reason,
            "valuation_cross_check": cross_check if 'cross_check' in locals() else None,
            "coverage_audit": market_coverage_audit(rows, source != TENCENT_SOURCE),
        }, ensure_ascii=False, default=str).encode()
        return universe, sectors, candidates, raw, fetched_at, source

    @staticmethod
    def _sina_rows() -> list[dict]:
        """Fetch Sina's raw all-A payload, retaining fields AkShare omits.

        AkShare's public convenience method deliberately drops PB, PE and
        market-cap columns.  This reads the same documented endpoint once and
        archives the full response in the market-screen evidence document.
        """
        try:
            import akshare.stock.stock_zh_a_sina as sina
            from akshare.utils import demjson
            import requests
        except ImportError as error:
            raise RuntimeError("AkShare Sina market dependencies are unavailable") from error

        count_response = requests.get(sina.zh_sina_a_stock_count_url, timeout=20)
        count_response.raise_for_status()
        # This endpoint returns a JSON-style quoted number on some routes.
        count = int(str(count_response.text).strip().strip('"'))
        if count < 4000:
            raise RuntimeError(f"Sina all-A count is unexpectedly incomplete: {count}")
        page_size = int(sina.zh_sina_a_stock_payload["num"])
        rows: list[dict] = []
        for page in range(1, math.ceil(count / page_size) + 1):
            params = dict(sina.zh_sina_a_stock_payload, page=str(page))
            expected = min(page_size, count - (page - 1) * page_size)
            for attempt in range(3):
                response = requests.get(sina.zh_sina_a_stock_url, params=params, timeout=20)
                response.raise_for_status()
                page_rows = demjson.decode(response.text)
                if isinstance(page_rows, list) and len(page_rows) == expected:
                    break
                if attempt == 2:
                    actual = len(page_rows) if isinstance(page_rows, list) else 'invalid'
                    raise RuntimeError(f'Sina page {page} incomplete after 3 attempts: expected {expected}, received {actual}')
                time.sleep(attempt + 1)
            rows.extend(page_rows)
        if len(rows) != count:
            raise RuntimeError(f"Sina all-A snapshot is incomplete: {len(rows)} rows")
        codes = [str(row.get('code',row.get('symbol','')))[-6:] for row in rows]
        if len(set(codes)) != count:
            raise RuntimeError('Sina pagination contains duplicate or missing securities')
        return rows

    @staticmethod
    def _merge_tencent_with_sina(tencent_rows: list[dict], sina_rows: list[dict]) -> tuple[list[dict], dict]:
        """Enrich Tencent coverage only when the independent price agrees."""
        sina_by_symbol = {
            str(row.get("code", row.get("symbol", "")))[-6:].zfill(6): row
            for row in sina_rows
            if str(row.get("code", row.get("symbol", "")))[-6:].isdigit()
        }
        merged: list[dict] = []
        matched = enriched = conflicts = missing = 0
        conflict_examples: list[dict] = []
        for row in tencent_rows:
            result = dict(row)
            symbol = str(_value(row, "代码", "symbol", "code") or "").zfill(6)
            sina = sina_by_symbol.get(symbol)
            result['pe_source_values'] = dict(result.get('pe_source_values') or {})
            if sina is not None:
                result['pe_source_values']['sina_per'] = sina.get('per')
            primary_price = _number(_value(row, "最新价", "current_price"))
            sina_price = _number(sina.get("trade")) if sina else None
            result['price_cross_check'] = {'status':'missing','tencent_price':str(primary_price),
                'sina_price':str(sina_price),'sina_url':SINA_VALUATION_SOURCE[1]}
            if sina is None:
                missing += 1
            elif primary_price is None or primary_price <= 0 or sina_price is None or sina_price <= 0:
                missing += 1
            elif abs(primary_price - sina_price) > max(Decimal("0.03"), primary_price * Decimal("0.02")):
                conflicts += 1
                result['price_cross_check']['status'] = 'conflict'
                if len(conflict_examples) < 100:
                    conflict_examples.append({"symbol": symbol, "tencent_price": str(primary_price), "sina_price": str(sina_price)})
            else:
                matched += 1
                result['price_cross_check']['status'] = 'matched'
                pb = _number(sina.get("pb"))
                if pb is not None and pb > 0:
                    result["pb"] = pb
                    enriched += 1
                sina_pe = _number(sina.get("per"))
                if _number(_value(result, "市盈率-动态", "市盈率(动态)", "动态市盈率", "pe")) is None and sina_pe is not None:
                    result["pe"] = sina_pe
                    result['pe_basis'] = 'sina_per_unspecified'
                sina_cap = _number(sina.get("mktcap"))
                if _number(_value(result, "总市值", "market_cap")) is None and sina_cap is not None:
                    result["market_cap"] = sina_cap * Decimal("10000")
            merged.append(result)
        reconciled = matched + conflicts
        if reconciled < 4000 or enriched < 3500:
            raise RuntimeError(
                f"Sina cross-check coverage is insufficient: reconciled={reconciled}, pb_enriched={enriched}"
            )
        return merged, {
            "sina_status": "accepted",
            "sina_row_count": len(sina_rows),
            "matched_prices": matched,
            "reconciled_prices": reconciled,
            "pb_enriched": enriched,
            "missing_or_invalid": missing,
            "price_conflicts": conflicts,
            "price_conflict_examples": conflict_examples,
            "price_tolerance": "max(CNY 0.03, 2% of Tencent price)",
        }

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
                "pe": row.get("pe_ttm"),
                "pe_basis": "ttm",
                "pe_source_values": {"tencent_pe_ttm": row.get("pe_ttm")},
                "总市值": _number(row.get("zsz")) * Decimal("100000000") if _number(row.get("zsz")) is not None else None,
                "板块": board_labels.get(stock_type, "主板" if stock_type.startswith("GP-A") else "待板块映射"),
            })
        return converted

    @staticmethod
    def _industry_map(ak) -> dict[str, str]:
        sectors: dict[str, str] = {}
        boards = ak.stock_board_industry_name_em().to_dict("records")
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

    @staticmethod
    def _sina_shenwan_industry_map() -> dict[str, str]:
        """Return the full Sina-maintained Shenwan level-1 classification."""
        try:
            from akshare.stock_feature.stock_classify_sina import stock_classify_sina
        except ImportError as error:
            raise RuntimeError("AkShare Sina classification adapter is unavailable") from error
        frame = stock_classify_sina("申万行业")
        sectors: dict[str, str] = {}
        for row in frame.to_dict("records"):
            symbol = str(row.get("code", "")).zfill(6)
            sector = str(row.get("class", "")).strip()
            if len(symbol) == 6 and symbol.isdigit() and sector:
                sectors[symbol] = sector
        return sectors

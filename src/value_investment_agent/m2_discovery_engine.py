"""Fail-closed M2 screening engine.

The engine consumes immutable provider snapshots and produces a replayable
opportunity receipt.  It never turns a candidate into a valuation, order,
position or BUY signal.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .financial_institutions import provisional_financial_type
from .financial_quality import evaluate_financial_quality
from .m2_market_data import parse_eastmoney_dividends, parse_sina_industry, parse_tencent_board
from .m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CHANNEL_CYCLICAL,
    CHANNEL_DIVIDEND,
    CHANNEL_QUALITY,
    CHANNEL_VALUE,
    CHANNELS,
    CANDIDATE_CLASS_LEAD,
    DATA_COMPLETE,
    DATA_MISSING,
    DATA_PARTIAL,
    DATA_UNSUPPORTED,
    EVALUATION_BUDGET_EXCLUDED,
    EVALUATION_CONFLICT,
    EVALUATION_DATA_GAP,
    EVALUATION_NOT_EVALUATED,
    EVALUATION_PASS,
    EVALUATION_REJECTED,
    EVALUATION_UNSUPPORTED,
    M2_RULE_VERSION,
    M2_SCHEMA_VERSION,
    PRIORITY_A,
    PRIORITY_B,
    PRIORITY_C,
    PROFILE_SUPPORTED,
    PROFILE_UNKNOWN,
    PROFILE_UNSUPPORTED,
    CandidateReason,
    ChannelEvaluation,
    ChannelResult,
    DataHealth,
    DiscoveryRunReceipt,
    DividendEvidence,
    EvidenceReference,
    ExcludedSecurity,
    FinancialEvidence,
    LegacyComparison,
    SecurityQuote,
    UniverseRecord,
    UniverseSnapshot,
    candidate_signature,
    coverage_signature,
)


FINANCIAL_MODEL_TYPES = frozenset({"bank", "insurer", "broker", "financial_group"})
CYCLICAL_SECTORS = frozenset(
    {
        "煤炭",
        "钢铁",
        "有色金属",
        "石油石化",
        "基础化工",
        "建筑材料",
        "工程机械",
        "汽车",
        "房地产",
        "交通运输",
        "农林牧渔",
        "纺织服饰",
        "轻工制造",
        "商贸零售",
        "电力设备",
        "环保",
    }
)


@dataclass(frozen=True)
class M2ScreeningPolicy:
    rule_version: str = M2_RULE_VERSION
    quality_min_score: Decimal = Decimal("60")
    quality_min_coverage: Decimal = Decimal("0.5")
    dividend_min_yield: Decimal = Decimal("0.025")
    dividend_min_market_cap: Decimal = Decimal("2_000_000_000")
    value_max_pe: Decimal = Decimal("15")
    value_min_market_cap: Decimal = Decimal("2_000_000_000")
    value_min_implied_roe: Decimal = Decimal("0.03")
    cyclical_min_market_cap: Decimal = Decimal("2_000_000_000")
    max_per_channel: int = 50
    price_tolerance: Decimal = Decimal("0.02")
    minimum_quote_count: int = 5000
    minimum_match_ratio: Decimal = Decimal("0.98")

    def as_policy(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "quality_min_score": str(self.quality_min_score),
            "quality_min_coverage": str(self.quality_min_coverage),
            "dividend_min_yield": str(self.dividend_min_yield),
            "dividend_min_market_cap": str(self.dividend_min_market_cap),
            "value_max_pe": str(self.value_max_pe),
            "value_min_market_cap": str(self.value_min_market_cap),
            "value_min_implied_roe": str(self.value_min_implied_roe),
            "cyclical_min_market_cap": str(self.cyclical_min_market_cap),
            "max_per_channel": self.max_per_channel,
            "price_tolerance": str(self.price_tolerance),
            "minimum_quote_count": self.minimum_quote_count,
            "minimum_match_ratio": str(self.minimum_match_ratio),
        }


def _decimal(value: object, field: str = "value") -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    return number if number.is_finite() else None


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return date.fromisoformat(text)


def _universe_from_payload(payload: Mapping[str, Any]) -> tuple[UniverseRecord, ...]:
    records = []
    for item in payload.get("records") or []:
        data = dict(item)
        records.append(
            UniverseRecord(
                symbol=str(data.get("symbol") or "").zfill(6),
                name=str(data.get("name") or "").strip(),
                board=str(data.get("board") or "").strip(),
                exchange=str(data.get("exchange") or "").strip(),
                listed_on=str(data.get("listed_on") or "").strip(),
                official_industry=data.get("official_industry"),
                security_type=str(data.get("security_type") or "").strip(),
            )
        )
    if not records:
        raise ValueError("Official universe payload contains no records")
    if len({item.symbol for item in records}) != len(records):
        raise ValueError("Official universe payload contains duplicate symbols")
    return tuple(records)


def build_universe_snapshot(
    official_payload: Mapping[str, Any],
    *,
    evidence_refs: Iterable[EvidenceReference] = (),
) -> UniverseSnapshot:
    fetched_at = official_payload.get("fetched_at")
    as_of = _date(fetched_at) if fetched_at else date.today()
    return UniverseSnapshot(
        schema_version=M2_SCHEMA_VERSION,
        as_of=as_of,
        complete=bool(official_payload.get("complete")),
        scope=str(official_payload.get("scope") or "沪深A股、科创板境内存托凭证、北交所股票"),
        records=_universe_from_payload(official_payload),
        evidence_refs=tuple(evidence_refs),
    )


def _board(symbol: str, official: Mapping[str, UniverseRecord] | None) -> str:
    if official and symbol in official:
        return official[symbol].board
    if symbol.startswith(("688", "689")):
        return "科创板"
    if symbol.startswith(("300", "301")) or symbol == "302132":
        return "创业板"
    if symbol.startswith(("4", "8", "92")):
        return "北交所"
    if symbol.startswith(("000", "001", "002", "003", "600", "601", "603", "605")):
        return "主板"
    return "待板块映射"


def merge_market_snapshots(
    tencent_rows: Iterable[Mapping[str, Any]],
    sina_rows: Iterable[Mapping[str, Any]],
    official_by_symbol: Mapping[str, UniverseRecord],
    *,
    quote_date: str,
    price_tolerance: Decimal,
) -> tuple[dict[str, SecurityQuote], list[str]]:
    """Merge quotes with explicit conflict detection and no synthetic defaults."""
    tencent = {str(row["symbol"]): dict(row) for row in tencent_rows}
    sina = {str(row["symbol"]): dict(row) for row in sina_rows}
    merged: dict[str, SecurityQuote] = {}
    conflicts: list[str] = []
    for symbol in sorted(set(tencent) | set(sina)):
        t = tencent.get(symbol)
        s = sina.get(symbol)
        price_t = _decimal(t.get("current_price")) if t else None
        price_s = _decimal(s.get("current_price")) if s else None
        price_conflict = False
        if price_t is not None and price_s is not None and price_s > 0:
            spread = abs(price_t - price_s) / max(price_t, price_s)
            if spread > price_tolerance:
                price_conflict = True
                conflicts.append(symbol)
        primary = t or s
        if primary is None:
            continue
        current_price = price_t if price_t is not None else price_s
        pe_ttm = _decimal((t or {}).get("pe_ttm"))
        if pe_ttm is None:
            pe_ttm = _decimal((s or {}).get("pe_ttm"))
        pb = _decimal((t or {}).get("pb"))
        if pb is None:
            pb = _decimal((s or {}).get("pb"))
        market_cap = _decimal((t or {}).get("market_cap"))
        if market_cap is None:
            market_cap = _decimal((s or {}).get("market_cap"))
        official = official_by_symbol.get(symbol)
        if primary.get("name"):
            name = str(primary["name"]).strip()
        elif official is not None:
            name = official.name
        else:
            name = symbol
        merged[symbol] = SecurityQuote(
            symbol=symbol,
            name=name,
            industry=(str((s or {}).get("industry")) if s and s.get("industry") else None),
            board=_board(symbol, official_by_symbol),
            stock_type=str((t or {}).get("stock_type") or "A股"),
            current_price=current_price,
            pe_ttm=pe_ttm if pe_ttm is not None and pe_ttm > 0 else None,
            pb=pb if pb is not None and pb > 0 else None,
            market_cap=market_cap if market_cap is not None and market_cap > 0 else None,
            quote_date=quote_date,
            source_names=tuple(
                source for source in ("Tencent", "Sina") if (t if source == "Tencent" else s)
            ),
            price_conflict=price_conflict,
            trading_state=str((t or {}).get("state") or "").strip(),
        )
    return merged, conflicts


def _latest_points(points: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        symbol = str(point.get("symbol") or "").zfill(6)
        if len(symbol) != 6 or not symbol.isdigit():
            continue
        by_symbol[symbol].append(dict(point))
    return dict(by_symbol)


def build_financial_evidence(
    points: Iterable[Mapping[str, Any]],
    names: Mapping[str, str],
    sectors: Mapping[str, str | None],
    *,
    evaluation_date: date,
) -> dict[str, FinancialEvidence]:
    result: dict[str, FinancialEvidence] = {}
    for symbol, symbol_points in _latest_points(points).items():
        evaluation = evaluate_financial_quality(
            symbol,
            names.get(symbol),
            sectors.get(symbol),
            symbol_points,
            evaluation_date=evaluation_date,
        )
        details = evaluation.calculation_details
        values = details.get("values") or {} if isinstance(details, dict) else {}
        result[symbol] = FinancialEvidence(
            symbol=symbol,
            model_type=str(evaluation.model_type),
            quality_status=str(evaluation.quality_status),
            total_score=evaluation.total_score,
            coverage_ratio=evaluation.coverage_ratio,
            period=str(details.get("period")) if details.get("period") else None,
            metrics={str(key): str(value) for key, value in values.items()},
            reasons=tuple(str(item) for item in evaluation.reasons),
            source_ids={
                str(key): str(value) for key, value in (details.get("source_ids") or {}).items()
            },
            evidence_date=str(max(
                (str(point.get("fetched_at") or point.get("created_at") or "") for point in symbol_points),
                default="",
            )),
        )
    return result


def build_dividend_evidence(
    rows: Iterable[Mapping[str, Any]],
    *,
    fetched_at: datetime,
    raw_sha256: str,
    known_at: date,
) -> dict[str, DividendEvidence]:
    result: dict[str, DividendEvidence] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").zfill(6)
        cash_dps = _decimal(row.get("cash_dps"))
        declared_yield = _decimal(row.get("declared_yield"))
        if cash_dps is None or declared_yield is None:
            continue
        declaration_date = (
            _date(row["declaration_date"]) if row.get("declaration_date") else None
        )
        if declaration_date is not None and declaration_date > known_at:
            continue
        result[symbol] = DividendEvidence(
            symbol=symbol,
            name=str(row.get("name") or "").strip(),
            fiscal_year=str(row.get("fiscal_year") or ""),
            cash_dps=cash_dps,
            declared_yield=declared_yield,
            status=str(row.get("status") or "unknown"),
            declaration_date=str(row.get("declaration_date")) if row.get("declaration_date") else None,
            ex_dividend_date=str(row.get("ex_dividend_date")) if row.get("ex_dividend_date") else None,
            source_name="AkShare / Eastmoney annual cash dividend plan snapshot",
            source_url="https://data.eastmoney.com/yjfp/",
            fetched_at=fetched_at.isoformat(),
            raw_sha256=raw_sha256,
        )
    return result


def _financial_type(quote: SecurityQuote) -> str | None:
    return provisional_financial_type(quote.name, quote.industry)


def _profile_status(quote: SecurityQuote) -> str:
    if _financial_type(quote):
        return PROFILE_UNSUPPORTED
    return PROFILE_SUPPORTED if quote.industry else PROFILE_UNKNOWN


def _metric(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _evidence_refs(
    run_refs: Mapping[str, EvidenceReference],
    *keys: str,
) -> tuple[EvidenceReference, ...]:
    return tuple(run_refs[key] for key in keys if key in run_refs)


def build_channel_results(
    quotes: Mapping[str, SecurityQuote],
    financial: Mapping[str, FinancialEvidence],
    dividends: Mapping[str, DividendEvidence],
    *,
    official_universe: Mapping[str, UniverseRecord] | None = None,
    run_refs: Mapping[str, EvidenceReference],
    policy: M2ScreeningPolicy,
    quote_date: str,
) -> dict[str, ChannelResult]:
    def eligible(symbol: str) -> bool:
        return official_universe is None or symbol in official_universe

    quality_candidates: list[CandidateReason] = []
    quality_missing: list[ExcludedSecurity] = []
    for fin in sorted(financial.values(), key=lambda item: (item.total_score is None, -(item.total_score or Decimal("-1")))):
        if not eligible(fin.symbol):
            continue
        if fin.model_type in FINANCIAL_MODEL_TYPES:
            continue
        quote = quotes.get(fin.symbol)
        if quote is None:
            quality_missing.append(ExcludedSecurity(
                fin.symbol, fin.symbol, "financial evidence exists but no same-session quote", PROFILE_UNKNOWN, quote_date,
            ))
            continue
        if fin.quality_status != "已验证" or fin.total_score is None or fin.total_score < policy.quality_min_score:
            continue
        if fin.coverage_ratio is None or fin.coverage_ratio < policy.quality_min_coverage:
            quality_missing.append(ExcludedSecurity(
                fin.symbol, quote.name, "financial coverage below quality gate", _profile_status(quote), quote_date,
            ))
            continue
        data_status = DATA_COMPLETE if not quote.price_conflict else DATA_PARTIAL
        tier = PRIORITY_A if fin.total_score >= Decimal("75") and data_status == DATA_COMPLETE else PRIORITY_B
        quality_candidates.append(CandidateReason(
            symbol=fin.symbol,
            name=quote.name,
            channel=CHANNEL_QUALITY,
            reasons=(
                f"{fin.period or 'latest'} 财务质量已通过 {policy.quality_min_score} 分门禁",
                "盈利、现金转换、资产负债与增长证据来自同一报告期",
                "仅进入深研队列，不生成估值、仓位或 BUY",
            ),
            metrics={
                "quality_score": _metric(fin.total_score),
                "coverage_ratio": _metric(fin.coverage_ratio),
                "pe_ttm": _metric(quote.pe_ttm),
                "pb": _metric(quote.pb),
                "market_cap": _metric(quote.market_cap),
                "industry": quote.industry,
            },
            evidence_refs=_evidence_refs(run_refs, "tencent", "sina", "financial"),
            evidence_date=quote_date,
            data_status=data_status,
            profile_status=_profile_status(quote),
            priority_tier=tier,
            candidate_class=CANDIDATE_CLASS_LEAD,
        ))

    dividend_candidates: list[CandidateReason] = []
    dividend_excluded: list[ExcludedSecurity] = []
    for dividend in sorted(
        dividends.values(),
        key=lambda item: (-item.declared_yield, -(item.cash_dps)),
    ):
        if not eligible(dividend.symbol):
            continue
        quote = quotes.get(dividend.symbol)
        if quote is None:
            continue
        profile = _profile_status(quote)
        if profile == PROFILE_UNSUPPORTED:
            dividend_excluded.append(ExcludedSecurity(
                dividend.symbol, quote.name, "financial-institution profile is not routed to a supported M2 valuation model", profile, quote_date,
            ))
            continue
        if quote.market_cap is None or quote.market_cap < policy.dividend_min_market_cap:
            continue
        if dividend.declared_yield < policy.dividend_min_yield:
            continue
        data_status = DATA_COMPLETE if not quote.price_conflict else DATA_PARTIAL
        tier = PRIORITY_A if dividend.declared_yield >= Decimal("0.05") and data_status == DATA_COMPLETE else PRIORITY_B
        dividend_candidates.append(CandidateReason(
            symbol=dividend.symbol,
            name=quote.name,
            channel=CHANNEL_DIVIDEND,
            reasons=(
                f"FY{dividend.fiscal_year} 已披露每股现金分红约 {dividend.cash_dps:.4f} 元，参考股息率约 {dividend.declared_yield * 100:.2f}%",
                "该通道只识别现金回报候选；FCF 覆盖、派息历史与可持续性尚未验证",
                "高股息不等于好公司，周期顶点和股价暴跌必须单独检查",
            ),
            metrics={
                "cash_dps": _metric(dividend.cash_dps),
                "declared_yield": _metric(dividend.declared_yield),
                "pe_ttm": _metric(quote.pe_ttm),
                "pb": _metric(quote.pb),
                "market_cap": _metric(quote.market_cap),
                "industry": quote.industry,
                "dividend_status": dividend.status,
            },
            evidence_refs=_evidence_refs(run_refs, "tencent", "sina", "dividend"),
            evidence_date=quote_date,
            data_status=data_status,
            profile_status=profile,
            priority_tier=tier,
            candidate_class=CANDIDATE_CLASS_LEAD,
        ))

    value_candidates: list[CandidateReason] = []
    value_excluded: list[ExcludedSecurity] = []
    value_rows = [
        quote for quote in quotes.values()
        if eligible(quote.symbol)
        and quote.pe_ttm is not None and 0 < quote.pe_ttm <= policy.value_max_pe
        and quote.pb is not None and quote.pb > 0
        and quote.market_cap is not None and quote.market_cap >= policy.value_min_market_cap
        and "ST" not in quote.name.upper()
    ]
    for quote in sorted(value_rows, key=lambda item: Decimal("1") / item.pe_ttm, reverse=True):
        implied_roe = quote.pb / quote.pe_ttm
        if implied_roe < policy.value_min_implied_roe:
            continue
        profile = _profile_status(quote)
        if profile == PROFILE_UNSUPPORTED:
            value_excluded.append(ExcludedSecurity(
                quote.symbol, quote.name, "financial-institution profile excluded from general value channel", profile, quote_date,
            ))
            continue
        data_status = DATA_COMPLETE if not quote.price_conflict else DATA_PARTIAL
        value_candidates.append(CandidateReason(
            symbol=quote.symbol,
            name=quote.name,
            channel=CHANNEL_VALUE,
            reasons=(
                f"TTM 市盈率 {quote.pe_ttm:.2f}、市净率 {quote.pb:.2f}，市场隐含 ROE 约 {implied_roe * 100:.1f}%",
                "这是多指标便宜度候选，不是单一低 PE 结论",
                "FCF Yield、EV/EBIT、正常化收益与资产负债表证据仍需补足",
            ),
            metrics={
                "pe_ttm": _metric(quote.pe_ttm),
                "pb": _metric(quote.pb),
                "earnings_yield": _metric(Decimal("1") / quote.pe_ttm),
                "implied_roe": _metric(implied_roe),
                "market_cap": _metric(quote.market_cap),
                "industry": quote.industry,
                "fcf_yield": None,
                "ev_ebit": None,
            },
            evidence_refs=_evidence_refs(run_refs, "tencent", "sina"),
            evidence_date=quote_date,
            data_status=data_status,
            profile_status=profile,
            priority_tier=PRIORITY_B if data_status == DATA_COMPLETE else PRIORITY_C,
            candidate_class=CANDIDATE_CLASS_LEAD,
        ))

    cyclical_candidates: list[CandidateReason] = []
    cyclical_excluded: list[ExcludedSecurity] = []
    cyclical_rows = [
        quote for quote in quotes.values()
        if eligible(quote.symbol)
        and quote.industry in CYCLICAL_SECTORS
        and quote.pe_ttm is not None and quote.pe_ttm > 0
        and quote.pb is not None and quote.pb > 0
        and quote.market_cap is not None and quote.market_cap >= policy.cyclical_min_market_cap
    ]
    for quote in sorted(cyclical_rows, key=lambda item: Decimal("1") / item.pe_ttm, reverse=True):
        profile = _profile_status(quote)
        if profile == PROFILE_UNSUPPORTED:
            cyclical_excluded.append(ExcludedSecurity(
                quote.symbol, quote.name, "financial-institution profile excluded from cyclical screening", profile, quote_date,
            ))
            continue
        data_status = DATA_COMPLETE if not quote.price_conflict else DATA_PARTIAL
        cyclical_candidates.append(CandidateReason(
            symbol=quote.symbol,
            name=quote.name,
            channel=CHANNEL_CYCLICAL,
            reasons=(
                f"申万行业 {quote.industry}，当前 TTM 市盈率 {quote.pe_ttm:.2f}、市净率 {quote.pb:.2f}",
                "周期正常化利润、中周期成本与供需证据尚未取得",
                "当前低 PE 不自动等于低估，必须先完成周期背景复核",
            ),
            metrics={
                "pe_ttm": _metric(quote.pe_ttm),
                "pb": _metric(quote.pb),
                "market_cap": _metric(quote.market_cap),
                "industry": quote.industry,
                "normalized_earnings": None,
                "current_vs_normalized_roe": None,
            },
            evidence_refs=_evidence_refs(run_refs, "tencent", "sina"),
            evidence_date=quote_date,
            data_status=data_status,
            profile_status=profile,
            priority_tier=PRIORITY_C,
            candidate_class=CANDIDATE_CLASS_LEAD,
        ))

    def bounded(items: list[CandidateReason]) -> tuple[CandidateReason, ...]:
        return tuple(items[: policy.max_per_channel])

    full_candidates = {
        CHANNEL_QUALITY: quality_candidates,
        CHANNEL_DIVIDEND: dividend_candidates,
        CHANNEL_VALUE: value_candidates,
        CHANNEL_CYCLICAL: cyclical_candidates,
    }

    def name_for(symbol: str) -> str:
        record = (official_universe or {}).get(symbol)
        if record is not None:
            return record.name
        quote = quotes.get(symbol)
        if quote is not None:
            return quote.name
        return symbol

    def profile_for(symbol: str) -> str:
        quote = quotes.get(symbol)
        if quote is not None:
            return _profile_status(quote)
        fin = financial.get(symbol)
        if fin is not None and fin.model_type in FINANCIAL_MODEL_TYPES:
            return PROFILE_UNSUPPORTED
        record = (official_universe or {}).get(symbol)
        if record is not None and record.official_industry:
            return PROFILE_SUPPORTED
        return PROFILE_UNKNOWN

    def evaluation(
        channel: str,
        symbol: str,
        status: str,
        reason: str,
    ) -> ChannelEvaluation:
        return ChannelEvaluation(
            symbol=symbol,
            name=name_for(symbol),
            channel=channel,
            status=status,
            reason=reason,
            profile_status=profile_for(symbol),
            evidence_date=quote_date,
        )

    def candidate_reason_for(
        channel_candidates: list[CandidateReason],
        symbol: str,
    ) -> str:
        for candidate in channel_candidates:
            if candidate.symbol == symbol:
                return "；".join(candidate.reasons)
        return ""

    if official_universe is not None:
        evaluation_symbols = set(official_universe)
    else:
        evaluation_symbols = set(quotes) | set(financial) | set(dividends)
        for candidates in full_candidates.values():
            evaluation_symbols.update(candidate.symbol for candidate in candidates)

    quality_excluded_by_symbol = {
        item.symbol: item.reason for item in quality_missing
    }
    dividend_excluded_by_symbol = {
        item.symbol: item.reason for item in dividend_excluded
    }
    value_excluded_by_symbol = {
        item.symbol: item.reason for item in value_excluded
    }
    cyclical_excluded_by_symbol = {
        item.symbol: item.reason for item in cyclical_excluded
    }

    evaluations: dict[str, list[ChannelEvaluation]] = {
        channel: [] for channel in CHANNELS
    }
    for symbol in sorted(evaluation_symbols):
        quote = quotes.get(symbol)
        fin = financial.get(symbol)
        dividend = dividends.get(symbol)

        if profile_for(symbol) == PROFILE_UNSUPPORTED:
            quality_status = EVALUATION_UNSUPPORTED
            quality_reason = "金融画像需专用模型，不进入通用 Quality 通道"
        elif fin is None:
            quality_status = EVALUATION_DATA_GAP
            quality_reason = "当前快照缺少同一报告期、可验证的财务质量证据"
        elif fin.model_type in FINANCIAL_MODEL_TYPES:
            quality_status = EVALUATION_UNSUPPORTED
            quality_reason = f"{fin.model_type} 金融画像需专用模型，不进入通用 Quality 通道"
        elif quote is None:
            quality_status = EVALUATION_DATA_GAP
            quality_reason = quality_excluded_by_symbol.get(symbol, "有财务证据但没有同一会话报价")
        elif fin.quality_status != "已验证" or fin.total_score is None or fin.total_score < policy.quality_min_score:
            quality_status = EVALUATION_REJECTED
            quality_reason = f"财务质量状态为 {fin.quality_status or 'UNKNOWN'}，未通过 {policy.quality_min_score} 分门禁"
        elif fin.coverage_ratio is None or fin.coverage_ratio < policy.quality_min_coverage:
            quality_status = EVALUATION_REJECTED
            quality_reason = quality_excluded_by_symbol.get(symbol, f"财务证据覆盖不足 {policy.quality_min_coverage}")
        elif any(candidate.symbol == symbol for candidate in quality_candidates):
            quality_status = EVALUATION_CONFLICT if quote.price_conflict else EVALUATION_PASS
            quality_reason = candidate_reason_for(quality_candidates, symbol)
        else:
            quality_status = EVALUATION_REJECTED
            quality_reason = "未满足 Quality 通道的全部数据与质量门禁"
        evaluations[CHANNEL_QUALITY].append(
            evaluation(CHANNEL_QUALITY, symbol, quality_status, quality_reason)
        )

        if dividend is None:
            dividend_status = EVALUATION_NOT_EVALUATED
            dividend_reason = "当前快照没有该证券的现金分红预案或已宣告记录"
        elif quote is None:
            dividend_status = EVALUATION_DATA_GAP
            dividend_reason = "有分红证据但没有同一会话报价"
        elif profile_for(symbol) == PROFILE_UNSUPPORTED:
            dividend_status = EVALUATION_UNSUPPORTED
            dividend_reason = dividend_excluded_by_symbol.get(symbol, "金融画像不进入通用现金回报通道")
        elif quote.market_cap is None or quote.market_cap < policy.dividend_min_market_cap:
            dividend_status = EVALUATION_REJECTED
            dividend_reason = f"总市值低于现金回报通道下限 {policy.dividend_min_market_cap}"
        elif dividend.declared_yield < policy.dividend_min_yield:
            dividend_status = EVALUATION_REJECTED
            dividend_reason = f"参考股息率低于 {policy.dividend_min_yield}"
        elif any(candidate.symbol == symbol for candidate in dividend_candidates):
            dividend_status = EVALUATION_CONFLICT if quote.price_conflict else EVALUATION_PASS
            dividend_reason = candidate_reason_for(dividend_candidates, symbol)
        else:
            dividend_status = EVALUATION_REJECTED
            dividend_reason = "未满足现金回报通道的全部数据与质量门禁"
        evaluations[CHANNEL_DIVIDEND].append(
            evaluation(CHANNEL_DIVIDEND, symbol, dividend_status, dividend_reason)
        )

        if quote is None:
            value_status = EVALUATION_DATA_GAP
            value_reason = "当前快照没有可用于 Value 通道的报价"
        elif profile_for(symbol) == PROFILE_UNSUPPORTED:
            value_status = EVALUATION_UNSUPPORTED
            value_reason = value_excluded_by_symbol.get(symbol, "金融画像不进入通用 Value 通道")
        elif "ST" in quote.name.upper():
            value_status = EVALUATION_REJECTED
            value_reason = "ST/风险警示证券不进入通用 Value 通道"
        elif quote.pe_ttm is None or quote.pb is None or quote.market_cap is None:
            value_status = EVALUATION_DATA_GAP
            value_reason = "PE、PB 或总市值缺失，无法完成 Value 通道校验"
        elif quote.market_cap < policy.value_min_market_cap:
            value_status = EVALUATION_REJECTED
            value_reason = f"总市值低于 Value 通道下限 {policy.value_min_market_cap}"
        elif quote.pe_ttm > policy.value_max_pe:
            value_status = EVALUATION_REJECTED
            value_reason = f"TTM PE {quote.pe_ttm} 高于 {policy.value_max_pe}"
        elif quote.pb / quote.pe_ttm < policy.value_min_implied_roe:
            value_status = EVALUATION_REJECTED
            value_reason = f"市场隐含 ROE 低于 {policy.value_min_implied_roe}"
        elif any(candidate.symbol == symbol for candidate in value_candidates):
            value_status = EVALUATION_CONFLICT if quote.price_conflict else EVALUATION_PASS
            value_reason = candidate_reason_for(value_candidates, symbol)
        else:
            value_status = EVALUATION_REJECTED
            value_reason = "未满足 Value 通道的全部数据与质量门禁"
        evaluations[CHANNEL_VALUE].append(
            evaluation(CHANNEL_VALUE, symbol, value_status, value_reason)
        )

        if quote is None:
            cyclical_status = EVALUATION_DATA_GAP
            cyclical_reason = "当前快照没有可用于周期通道的报价"
        elif profile_for(symbol) == PROFILE_UNSUPPORTED:
            cyclical_status = EVALUATION_UNSUPPORTED
            cyclical_reason = cyclical_excluded_by_symbol.get(symbol, "金融画像不进入周期通道")
        elif quote.industry is None:
            cyclical_status = EVALUATION_NOT_EVALUATED
            cyclical_reason = "申万行业映射缺失，周期适用性未知"
        elif quote.industry not in CYCLICAL_SECTORS:
            cyclical_status = EVALUATION_NOT_EVALUATED
            cyclical_reason = f"行业 {quote.industry} 不在当前周期通道适用清单"
        elif quote.pe_ttm is None or quote.pb is None or quote.market_cap is None:
            cyclical_status = EVALUATION_DATA_GAP
            cyclical_reason = "PE、PB 或总市值缺失，无法完成周期通道校验"
        elif quote.market_cap < policy.cyclical_min_market_cap:
            cyclical_status = EVALUATION_REJECTED
            cyclical_reason = f"总市值低于周期通道下限 {policy.cyclical_min_market_cap}"
        elif any(candidate.symbol == symbol for candidate in cyclical_candidates):
            cyclical_status = EVALUATION_CONFLICT if quote.price_conflict else EVALUATION_PASS
            cyclical_reason = candidate_reason_for(cyclical_candidates, symbol)
        else:
            cyclical_status = EVALUATION_REJECTED
            cyclical_reason = "未满足周期通道的全部数据与质量门禁"
        evaluations[CHANNEL_CYCLICAL].append(
            evaluation(CHANNEL_CYCLICAL, symbol, cyclical_status, cyclical_reason)
        )

    for channel, channel_candidates in full_candidates.items():
        by_symbol = {item.symbol: item for item in evaluations[channel]}
        for symbol in [item.symbol for item in channel_candidates[policy.max_per_channel :]]:
            item = by_symbol[symbol]
            by_symbol[symbol] = ChannelEvaluation(
                symbol=item.symbol,
                name=item.name,
                channel=item.channel,
                status=EVALUATION_BUDGET_EXCLUDED,
                reason=(
                    f"已通过通道规则，但超出单通道展示预算 {policy.max_per_channel}；"
                    "仍保留在覆盖率分母，未静默删除"
                ),
                profile_status=item.profile_status,
                evidence_date=item.evidence_date,
            )
        evaluations[channel] = [by_symbol[symbol] for symbol in sorted(by_symbol)]

    return {
        CHANNEL_QUALITY: ChannelResult(
            CHANNEL_QUALITY,
            "Quality / Business Quality",
            bounded(quality_candidates),
            (),
            tuple(quality_missing),
            policy.rule_version,
            tuple(evaluations[CHANNEL_QUALITY]),
        ),
        CHANNEL_DIVIDEND: ChannelResult(
            CHANNEL_DIVIDEND,
            "Dividend / Cash Return",
            bounded(dividend_candidates),
            tuple(dividend_excluded),
            (),
            policy.rule_version,
            tuple(evaluations[CHANNEL_DIVIDEND]),
        ),
        CHANNEL_VALUE: ChannelResult(
            CHANNEL_VALUE,
            "Value / Earnings Yield + Implied ROE",
            bounded(value_candidates),
            tuple(value_excluded),
            (),
            policy.rule_version,
            tuple(evaluations[CHANNEL_VALUE]),
        ),
        CHANNEL_CYCLICAL: ChannelResult(
            CHANNEL_CYCLICAL,
            "Cyclical / Normalized Earnings Pending",
            bounded(cyclical_candidates),
            tuple(cyclical_excluded),
            (),
            policy.rule_version,
            tuple(evaluations[CHANNEL_CYCLICAL]),
        ),
    }


def build_data_health(
    universe: UniverseSnapshot,
    quotes: Mapping[str, SecurityQuote],
    financial: Mapping[str, FinancialEvidence],
    dividends: Mapping[str, DividendEvidence],
    *,
    price_conflict_count: int,
    policy: M2ScreeningPolicy,
) -> DataHealth:
    expected = {record.symbol for record in universe.records}
    received = set(quotes)
    matched = expected & received
    missing = expected - received
    extra = received - expected
    unsupported = sum(
        1 for quote in quotes.values() if _financial_type(quote) is not None
    )
    blockers: list[str] = []
    status = "COMPLETE"
    if not universe.complete:
        status = "PARTIAL"
        blockers.append("official universe is marked incomplete")
    if len(received) < policy.minimum_quote_count:
        status = "PARTIAL"
        blockers.append(f"quote coverage below {policy.minimum_quote_count}")
    match_ratio = Decimal(len(matched)) / Decimal(len(expected)) if expected else Decimal("0")
    if match_ratio < policy.minimum_match_ratio:
        status = "PARTIAL"
        blockers.append("official universe overlap below minimum match ratio")
    if missing:
        blockers.append(f"{len(missing)} official symbols have no quote snapshot")
    if extra:
        blockers.append(f"{len(extra)} quote symbols are not in the official universe")
    if price_conflict_count:
        blockers.append(f"{price_conflict_count} symbols have conflicting provider prices")
    return DataHealth(
        universe_count=len(expected),
        quote_count=len(received),
        matched_quote_count=len(matched),
        missing_quote_count=len(missing),
        extra_quote_count=len(extra),
        price_conflict_count=price_conflict_count,
        industry_mapping_count=sum(1 for quote in quotes.values() if quote.industry),
        financial_evidence_count=len(financial),
        dividend_evidence_count=len(dividends),
        unsupported_financial_count=unsupported,
        status=status,
        blockers=tuple(blockers),
    )


def build_legacy_comparison(
    quotes: Mapping[str, SecurityQuote],
    channel_results: Mapping[str, ChannelResult],
    policy: M2ScreeningPolicy,
    official_symbols: set[str] | frozenset[str] = frozenset(),
) -> LegacyComparison:
    from .market import screen_rows

    rows = []
    for quote in quotes.values():
        if official_symbols and quote.symbol not in official_symbols:
            continue
        if quote.price_conflict or "ST" in quote.name.upper():
            continue
        if any(value is None for value in (quote.current_price, quote.pe_ttm, quote.pb, quote.market_cap)):
            continue
        rows.append({
            "代码": quote.symbol,
            "名称": quote.name,
            "最新价": quote.current_price,
            "市盈率-动态": quote.pe_ttm,
            "市净率": quote.pb,
            "总市值": quote.market_cap,
        })
    legacy = screen_rows(rows, {}, require_pb=True)
    legacy_symbols = tuple(item.symbol for item in legacy)
    new_symbols = {
        candidate.symbol
        for channel in channel_results.values()
        for candidate in channel.candidates
    }
    overlap = len(set(legacy_symbols) & new_symbols)
    return LegacyComparison(
        legacy_candidate_count=len(legacy_symbols),
        legacy_candidates=legacy_symbols,
        new_candidate_count=len(new_symbols),
        overlap_count=overlap,
        note=(
            "Legacy PE<=25 / PB<=3 / market-cap>=5bn is retained only as a shadow baseline. "
            "It never ranks M2 candidates and has no independent evidence of quality or normalized earnings."
        ),
    )


def build_discovery_receipt(
    *,
    run_id: str,
    generated_at: datetime,
    official_payload: Mapping[str, Any],
    tencent_payload: Mapping[str, Any],
    sina_payload: Mapping[str, Any],
    dividend_payload: Mapping[str, Any],
    financial_points: Iterable[Mapping[str, Any]],
    quote_date: str,
    run_refs: Mapping[str, EvidenceReference],
    policy: M2ScreeningPolicy | None = None,
) -> DiscoveryRunReceipt:
    policy = policy or M2ScreeningPolicy()
    universe = build_universe_snapshot(
        official_payload,
        evidence_refs=_evidence_refs(run_refs, "official"),
    )
    official_by_symbol = {record.symbol: record for record in universe.records}
    tencent_rows = parse_tencent_board(tencent_payload)
    sina_rows = parse_sina_industry(sina_payload)
    quotes, conflicts = merge_market_snapshots(
        tencent_rows,
        sina_rows,
        official_by_symbol,
        quote_date=quote_date,
        price_tolerance=policy.price_tolerance,
    )
    official_quotes = {
        symbol: quote
        for symbol, quote in quotes.items()
        if symbol in official_by_symbol
    }
    names = {record.symbol: record.name for record in universe.records}
    names.update({symbol: quote.name for symbol, quote in official_quotes.items() if quote.name})
    sectors = {symbol: quote.industry for symbol, quote in official_quotes.items()}
    financial = {
        symbol: evidence
        for symbol, evidence in build_financial_evidence(
        financial_points,
        names,
        sectors,
        evaluation_date=generated_at.date(),
        ).items()
        if symbol in official_by_symbol
    }
    dividends = {
        symbol: evidence
        for symbol, evidence in build_dividend_evidence(
        parse_eastmoney_dividends(dividend_payload),
        fetched_at=generated_at,
        raw_sha256=str(run_refs["dividend"].sha256),
        known_at=generated_at.date(),
        ).items()
        if symbol in official_by_symbol
    }
    channel_results = build_channel_results(
        official_quotes,
        financial,
        dividends,
        official_universe=official_by_symbol,
        run_refs=run_refs,
        policy=policy,
        quote_date=quote_date,
    )
    health = build_data_health(
        universe,
        quotes,
        financial,
        dividends,
        price_conflict_count=len(conflicts),
        policy=policy,
    )
    legacy = build_legacy_comparison(
        official_quotes,
        channel_results,
        policy,
        official_symbols=frozenset(official_by_symbol),
    )
    return DiscoveryRunReceipt(
        schema_version=M2_SCHEMA_VERSION,
        run_id=run_id,
        rule_version=policy.rule_version,
        generated_at=generated_at,
        as_of=generated_at.date(),
        action=ACTION_NO_ORDER,
        universe=universe,
        data_health=health,
        channel_results=channel_results,
        legacy_comparison=legacy,
        evidence_refs=tuple(run_refs.values()),
        coverage_signature=coverage_signature(channel_results),
        candidate_signature=candidate_signature(channel_results),
    )

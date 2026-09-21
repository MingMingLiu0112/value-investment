"""Auditable financial-quality scoring with conservative evidence gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .financial_institutions import provisional_financial_type


GENERAL_FIELDS = (
    "roe", "gross_margin", "net_margin", "operating_cash_flow_to_net_income",
    "cash", "interest_bearing_debt", "debt_ratio", "revenue_yoy", "net_income_yoy",
)


@dataclass(frozen=True)
class FinancialQualityResult:
    symbol: str
    model_type: str
    quality_status: str
    total_score: Decimal | None
    coverage_ratio: Decimal
    profitability_score: Decimal | None
    cash_flow_score: Decimal | None
    balance_sheet_score: Decimal | None
    growth_score: Decimal | None
    reasons: list[str]
    calculation_details: dict

    def database_row(self) -> dict:
        return asdict(self)


def _accepted(point: dict | None) -> bool:
    if not point or point.get("validation_status") != "verified":
        return False
    metadata = point.get("metadata") or {}
    if (point.get('field_name') == 'interest_bearing_debt'
            and metadata.get('complete_debt_verified') is not True):
        return False
    # This historical proxy omits noncurrent leases and financing payables.
    # Retain its evidence, but do not treat input validation as scope validation.
    if point.get('field_name') == 'interest_bearing_debt' and metadata.get('derivation_formula') == (
        'short_term_borrowings + current_portion_long_term_debt + long_term_borrowings + bonds_payable'
    ):
        return False
    return metadata.get("automatic_cross_source_verification") is True and not metadata.get('evidence_quarantine')


def _score(value: Decimal, thresholds: tuple[tuple[Decimal, Decimal], ...]) -> Decimal:
    for minimum, points in thresholds:
        if value >= minimum:
            return points
    return Decimal("0")


def _institution_result(symbol: str, model_type: str, points: list[dict]) -> FinancialQualityResult:
    from .institution_metrics import FIELDS
    fields = list(FIELDS.get(model_type, {'分部ROE': 'segment_roe', '分部净资产': 'segment_equity'}).values())
    relevant = [p for p in points if p['field_name'] in fields]
    period = max((str(p['period_label']) for p in relevant), default='')
    current = {p['field_name']: p for p in relevant if str(p['period_label']) == period}
    confirmed = [f for f in fields if _accepted(current.get(f))]
    missing = [f for f in fields if f not in current]
    labels = {"bank": "银行", "insurer": "保险", "broker": "证券公司", "financial_group": "金融控股/多元金融"}
    return FinancialQualityResult(
        symbol=symbol,
        model_type=model_type,
        quality_status="专用指标已验证，估值另评" if len(confirmed) == len(fields) else "待专用指标验证",
        total_score=None,
        coverage_ratio=Decimal(len(confirmed)) / Decimal(len(fields)),
        profitability_score=None,
        cash_flow_score=None,
        balance_sheet_score=None,
        growth_score=None,
        reasons=[f"{labels[model_type]}专用指标已取得 {len(current)}/{len(fields)}，交叉验证 {len(confirmed)}/{len(fields)}；缺值：{', '.join(missing) or '无'}；资本/风险指标不等于投资价值评分"],
        calculation_details={"required_model": f"{model_type}_specialized_v1", "period": period,
            "required_fields":fields,"available_fields":sorted(current),"accepted_fields":confirmed},
    )


def evaluate_financial_quality(symbol: str, name: str | None, sector: str | None, points: list[dict], *, evaluation_date: date | None = None) -> FinancialQualityResult:
    """Score a general enterprise only after complete, same-period evidence exists.

    The score ranks research priority, not expected returns.  Missing, stale or
    mismatched evidence yields a transparent pending state instead of a partial
    score that could look more certain than it is.
    """
    model_type = provisional_financial_type(name, sector)
    if model_type:
        return _institution_result(symbol, model_type, points)

    relevant = [p for p in points if p['field_name'] in GENERAL_FIELDS]
    annual = [p for p in relevant if str(p['period_label']).endswith('-12-31')]
    # Annual fundamentals and the latest interim report are independent views.
    pool = annual or relevant
    latest = {}
    for point in sorted(pool, key=lambda p: (str(p['period_label']), str(p.get('created_at', '')))):
        latest[point['field_name']] = point
    accepted = {field: point for field, point in latest.items() if _accepted(point)}
    coverage = (Decimal(len(accepted)) / Decimal(len(GENERAL_FIELDS))).quantize(Decimal("0.0001"))
    missing = [field for field in GENERAL_FIELDS if field not in accepted]
    periods = {str(point["period_label"]) for point in accepted.values()}
    if missing:
        return FinancialQualityResult(
            symbol, "general_enterprise", "待补证", None, coverage, None, None, None, None,
            [f"缺少自动双源验证字段：{', '.join(missing)}"],
            {"required_fields": list(GENERAL_FIELDS), "accepted_fields": sorted(accepted), "source_ids": {
                field: str(point.get("source_id", "")) for field, point in accepted.items()
            }},
        )
    if len(periods) != 1:
        return FinancialQualityResult(
            symbol, "general_enterprise", "待同报告期补证", None, coverage, None, None, None, None,
            ["核心财务指标不属于同一报告期，禁止混合计算质量评分"],
            {"periods": sorted(periods), "source_ids": {field: str(point.get("source_id", "")) for field, point in accepted.items()}},
        )

    period = next(iter(periods))
    if not period.endswith('-12-31'):
        return FinancialQualityResult(
            symbol, "general_enterprise", "中期跟踪，不套年度评分", None, coverage, None, None, None, None,
            ["ROE和现金流采用当期披露值；半年/季度数据不与年度阈值混算，也不直接倍乘年化"],
            {"period": period, "required_fields": list(GENERAL_FIELDS)},
        )
    today = evaluation_date if evaluation_date is not None else date.today()
    required_year = today.year - (1 if today.month >= 5 else 2)
    if int(period[:4]) < required_year:
        return FinancialQualityResult(
            symbol, "general_enterprise", "年度报告过期，待更新", None, coverage, None, None, None, None,
            [f"评分数据为{period}；当前至少需要{required_year}年年报，不沿用过期年度分数"],
            {"period": period, "required_year": required_year},
        )
    values = {}
    invalid = []
    for field, point in accepted.items():
        try:
            value = Decimal(str(point['value']))
            if not value.is_finite() or (field in ('cash', 'interest_bearing_debt', 'debt_ratio') and value < 0):
                invalid.append(field)
            else:
                values[field] = value
        except (InvalidOperation, ValueError, TypeError, KeyError):
            invalid.append(field)
    if invalid:
        return FinancialQualityResult(
            symbol, 'general_enterprise', '财务数值异常，待核验', None, coverage,
            None, None, None, None, ['指标存在非有限数值或不允许的负数，禁止评分'],
            {'period': period, 'invalid_fields': sorted(invalid)},
        )
    for field in ('cash', 'interest_bearing_debt'):
        if accepted[field].get('unit') == 'CNY 100M':
            values[field] *= Decimal('100000000')
    profitability = (
        _score(values["roe"], ((Decimal("15"), Decimal("15")), (Decimal("10"), Decimal("10"))))
        + _score(values["gross_margin"], ((Decimal("25"), Decimal("10")), (Decimal("15"), Decimal("5"))))
        + _score(values["net_margin"], ((Decimal("10"), Decimal("10")), (Decimal("5"), Decimal("5"))))
    )
    cash_flow = (
        _score(values["operating_cash_flow_to_net_income"], ((Decimal("100"), Decimal("15")), (Decimal("80"), Decimal("8"))))
        + (Decimal("10") if values["cash"] >= values["interest_bearing_debt"] else Decimal("0"))
    )
    balance_sheet = _score(values["debt_ratio"], ((Decimal("0"), Decimal("0")),))
    if values["debt_ratio"] <= Decimal("40"):
        balance_sheet = Decimal("20")
    elif values["debt_ratio"] <= Decimal("60"):
        balance_sheet = Decimal("10")
    growth = (
        _score(values["revenue_yoy"], ((Decimal("5"), Decimal("10")), (Decimal("0"), Decimal("5"))))
        + _score(values["net_income_yoy"], ((Decimal("5"), Decimal("10")), (Decimal("0"), Decimal("5"))))
    )
    total = profitability + cash_flow + balance_sheet + growth
    return FinancialQualityResult(
        symbol, "general_enterprise", "已验证", total, coverage, profitability, cash_flow, balance_sheet, growth, [],
        {
            "period": periods.pop(),
            "formula_version": "financial-quality-general-v1",
            "pillar_weights": {"profitability": 35, "cash_flow": 25, "balance_sheet": 20, "growth": 20},
            "source_ids": {field: str(point.get("source_id", "")) for field, point in accepted.items()},
            "values": {field: str(value) for field, value in values.items()},
        },
    )

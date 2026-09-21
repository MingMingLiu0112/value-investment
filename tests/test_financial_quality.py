from decimal import Decimal
import pytest

from value_investment_agent.financial_quality import evaluate_financial_quality


def point(field: str, value: str, period: str = "2025-12-31") -> dict:
    return {
        "field_name": field, "value": Decimal(value), "period_label": period,
        "validation_status": "verified", "metadata": {"automatic_cross_source_verification": True,
            **({'complete_debt_verified': True} if field == 'interest_bearing_debt' else {})},
        "source_id": f"source-{field}",
    }


def general_points() -> list[dict]:
    return [
        point("roe", "16"), point("gross_margin", "30"), point("net_margin", "12"),
        point("operating_cash_flow_to_net_income", "105"), point("cash", "120"),
        point("interest_bearing_debt", "100"), point("debt_ratio", "35"),
        point("revenue_yoy", "8"), point("net_income_yoy", "9"),
    ]


def test_verified_general_enterprise_receives_pillar_scores() -> None:
    result = evaluate_financial_quality("600001", "样例制造", "制造业", general_points())

    assert result.quality_status == "已验证"
    assert result.total_score == Decimal("100")
    assert result.coverage_ratio == Decimal("1.0000")
    assert result.profitability_score == Decimal("35")


@pytest.mark.parametrize('field,value', [('roe', 'NaN'), ('cash', 'Infinity'),
    ('net_income_yoy', '-Infinity'), ('debt_ratio', '-1'), ('cash', '-1'),
    ('interest_bearing_debt', '-1'), ('roe', None), ('roe', True)])
def test_invalid_verified_numeric_values_block_scores(field, value):
    points = general_points()
    next(p for p in points if p['field_name'] == field)['value'] = value
    result = evaluate_financial_quality('600001', '样例制造', '制造业', points)
    assert result.total_score is None
    assert result.quality_status == '财务数值异常，待核验'
    assert result.calculation_details['invalid_fields'] == [field]


def test_negative_profit_growth_is_valid_data_not_a_missing_value():
    points = general_points()
    next(p for p in points if p['field_name'] == 'net_income_yoy')['value'] = Decimal('-10')
    result = evaluate_financial_quality('600001', '样例制造', '制造业', points)
    assert result.total_score == Decimal('90')


def test_missing_or_unverified_fields_never_receive_partial_score() -> None:
    points = general_points()[:-1]
    result = evaluate_financial_quality("600001", "样例制造", "制造业", points)

    assert result.quality_status == "待补证"
    assert result.total_score is None
    assert "net_income_yoy" in result.reasons[0]


def test_mixed_periods_are_blocked() -> None:
    points = general_points()
    points[-1] = point("net_income_yoy", "9", "2024-12-31")
    result = evaluate_financial_quality("600001", "样例制造", "制造业", points)

    assert result.quality_status == "待同报告期补证"
    assert result.total_score is None


def test_bank_never_uses_general_enterprise_score() -> None:
    result = evaluate_financial_quality("600036", "招商银行", "银行", general_points())

    assert result.model_type == "bank"
    assert result.quality_status == "待专用指标验证"
    assert result.total_score is None


def test_interim_roe_is_not_compared_to_annual_thresholds() -> None:
    points = [dict(p, period_label='2026-06-30') for p in general_points()]
    result = evaluate_financial_quality('600001', '样例制造', '制造业', points)
    assert result.total_score is None
    assert result.quality_status == '中期跟踪，不套年度评分'


def test_latest_interim_does_not_hide_annual_score():
    points = general_points() + [dict(p, period_label='2026-06-30', value=Decimal('1')) for p in general_points()]
    result = evaluate_financial_quality('600001', '样例制造', '制造业', points)
    assert result.total_score == Decimal('100')
    assert result.calculation_details['period'] == '2025-12-31'


def test_incomplete_new_annual_does_not_fall_back_to_old_complete_year():
    points = [dict(p, period_label='2024-12-31') for p in general_points()] + [point('roe', '16')]
    result = evaluate_financial_quality('600001', '样例制造', '制造业', points)
    assert result.total_score is None


def test_old_annual_report_cannot_generate_current_score():
    points = [dict(p, period_label='2000-12-31') for p in general_points()]
    result = evaluate_financial_quality('600001', '样例制造', '制造业', points)
    assert result.quality_status == '年度报告过期，待更新'
    assert result.total_score is None

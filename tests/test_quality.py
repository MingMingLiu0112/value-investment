from datetime import datetime, timedelta, timezone
from decimal import Decimal

from value_investment_agent.quality import evaluate


def point(value: str, age_hours: int = 0, status: str = 'verified') -> dict:
    now = datetime.now(timezone.utc)
    return {
        'field_name': 'current_price', 'value': Decimal(value), 'created_at': now,
        'fetched_at': now - timedelta(hours=age_hours), 'validation_status': status,
    }


def test_missing_price_blocks_signal() -> None:
    result = evaluate('600519', [], 30, Decimal('0.03'))
    assert result.status == '缺失'
    assert result.signal == '待数据'


def test_stale_price_blocks_signal() -> None:
    result = evaluate('600519', [point('1500', 31)], 30, Decimal('0.03'))
    assert result.status == '异常'
    assert '价格数据已过期' in result.reasons


def test_conflicting_sources_blocks_signal() -> None:
    result = evaluate('600519', [point('1000'), point('1100')], 30, Decimal('0.03'))
    assert result.status == '异常'
    assert '双源价格差异超阈值' in result.reasons


def test_fresh_price_requires_fair_value() -> None:
    result = evaluate('600519', [point('1500')], 30, Decimal('0.03'))
    assert result.status == '待估值'
    assert result.signal == '待数据'


def test_automatic_cross_source_evidence_can_pass_the_quality_gate() -> None:
    now = datetime.now(timezone.utc)
    automatic = {'automatic_cross_source_verification': True}
    result = evaluate('600519', [
        {'field_name': 'current_price', 'value': Decimal('50'), 'created_at': now, 'fetched_at': now,
         'validation_status': 'verified', 'human_reviewed': False, 'metadata': automatic},
        {'field_name': 'fair_value', 'value': Decimal('100'), 'created_at': now, 'fetched_at': now,
         'validation_status': 'verified', 'human_reviewed': False, 'metadata': automatic},
    ], 30, Decimal('0.03'))

    assert result.signal == '建仓候选'
    assert result.target_weight == Decimal('0.10')

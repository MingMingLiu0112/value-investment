from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from value_investment_agent.historical_fees import (
    CURRENT_SSE_REVIEWED_ON, CURRENT_SSE_VERSION, CURRENT_SSE_EVIDENCE,
    CURRENT_SSE_ARCHIVE, current_sse_components, statutory_components, verify_current_sse_policy,
)
from value_investment_agent.virtual_account import current_sse_research_fee, replay


def test_current_statutory_buy_sell_components_and_no_duplicate_exchange_charges():
    buy = current_sse_components(CURRENT_SSE_REVIEWED_ON, 'buy', Decimal('10000'))
    sell = current_sse_components(CURRENT_SSE_REVIEWED_ON, 'sell', Decimal('10000'))
    assert buy['version'] == CURRENT_SSE_VERSION
    assert buy['stamp_duty_unrounded_cny'] == 0
    assert sell['stamp_duty_unrounded_cny'] == Decimal('5')
    assert buy['csdc_transfer_unrounded_cny'] == Decimal('0.1')
    assert sell['statutory_subtotal_unrounded_cny'] == Decimal('5.1')
    assert current_sse_research_fee('buy', 100, Decimal('100'), CURRENT_SSE_REVIEWED_ON) == Decimal('5.10')
    assert current_sse_research_fee('sell', 100, Decimal('100'), CURRENT_SSE_REVIEWED_ON) == Decimal('10.10')
    assert buy['full_cost_verified'] is False


@pytest.mark.parametrize('day', [date(2025, 12, 31), date(2026, 9, 15), date(2026, 9, 17)])
def test_reviewed_scope_does_not_silently_cover_other_sessions(day):
    with pytest.raises(ValueError, match='reviewed session'):
        current_sse_components(day, 'buy', Decimal('10000'))


def test_historical_scope_remains_frozen():
    with pytest.raises(ValueError, match='2015-2025'):
        statutory_components(CURRENT_SSE_REVIEWED_ON, 'SSE', 'buy', Decimal('10000'))


def test_pinned_official_sources_exist_and_changed_bytes_are_rejected(tmp_path):
    root = Path(__file__).resolve().parents[1]
    policy = verify_current_sse_policy(root)
    assert policy['valid_session'] == '2026-09-16'
    assert policy['broker_invoice_verified'] is False
    for key in CURRENT_SSE_EVIDENCE:
        path = tmp_path / CURRENT_SSE_ARCHIVE / (key + '.html')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / CURRENT_SSE_ARCHIVE / path.name).read_bytes())
    verify_current_sse_policy(tmp_path)
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='source changed'):
        verify_current_sse_policy(tmp_path)


def test_reviewed_date_fee_runs_through_bounded_ledger_without_admitting_a_model():
    from value_investment_agent.virtual_account import ORDER_TERMS_VERSION
    bars = [{"date": day, "open": "100", "close": "100", "execution_ready": True,
             "price_limit_down": "90", "price_limit_up": "110"}
            for day in ('2026-09-15', '2026-09-16')]
    decision = {'state': 'proposed_entry', 'decision_id': 'synthetic-current-fee-test', 'quantity': 100,
                'execution_terms': {'version': ORDER_TERMS_VERSION, 'valid_session': '2026-09-16',
                                    'limit_price': '101', 'cash_budget_cny': '10100',
                                    'liquidity_budget_cny': '20000', 'liquidity_as_of': '2026-09-15',
                                    'slippage_bps': '10', 'basis_id': 'synthetic-only'}}
    account, rows = replay(bars, {'2026-09-15': decision}, fee_calculator=current_sse_research_fee)
    assert rows[1]['fill']['price'] == '100.10'
    assert rows[1]['fill']['fee_cny'] == '5.10'
    assert account.cash == Decimal('989984.90')
    assert replay(bars, {}, account, fee_calculator=current_sse_research_fee)[1] == []


@pytest.mark.parametrize('quantity,price', [(True, Decimal('100')), (0, Decimal('100')), (100, Decimal('NaN'))])
def test_invalid_cost_inputs_fail(quantity, price):
    with pytest.raises(ValueError):
        current_sse_research_fee('buy', quantity, price, CURRENT_SSE_REVIEWED_ON)

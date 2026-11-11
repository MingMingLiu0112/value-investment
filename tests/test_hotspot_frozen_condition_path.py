"""Synthetic path counterexamples; not historical strategy validation."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from value_investment_agent.domain.hotspot.shadow_observation import (
    _frozen_condition, evaluate_frozen_condition_path,
)
from value_investment_agent.domain.hotspot.price_action_plan import RULE_VERSION

CHINA = ZoneInfo('Asia/Shanghai')
NOW = datetime(2026, 10, 20, 16, tzinfo=CHINA)


def inputs():
    times = ['2026-10-16 14:00:00', '2026-10-16 15:00:00'] + [
        '2026-10-19 ' + clock for clock in ('10:30:00', '11:30:00', '14:00:00', '15:00:00')]
    bars = [dict(time=stamp, open='10', high='11', low='9', close='10', volume='100') for stamp in times]
    prior = dict(symbol='600519', action='no_order', rule_version=RULE_VERSION,
        market_trade_date='2026-10-19', observed_at='2026-10-19T16:00:00+08:00',
        case_sha256='synthetic-prior', entry_trigger_price='11', invalidation_price='9',
        frozen_price_condition=_frozen_condition(dict(bars={'60m': bars}, market_trade_date='2026-10-19')))
    today = [dict(time='2026-10-20 ' + clock, open='10', high='10.8', low='9.2', close='10', volume='100')
             for clock in ('10:30:00', '11:30:00', '14:00:00', '15:00:00')]
    current = dict(symbol='600519', action='no_order', market_trade_date='2026-10-20',
                   case_sha256='synthetic-current', bars={'60m': today}, source_bindings={})
    return prior, current


def evaluate(prior, current):
    return evaluate_frozen_condition_path(prior, current, observed_at=NOW)


def trigger(row, volume='120'):
    row.update(open='10.5', high='11.3', low='10.4', close='11.2', volume=volume)


def invalidate(row):
    row.update(open='9.5', high='9.8', low='8.7', close='8.8')


def test_first_trigger_and_later_invalidation_keep_original_protection():
    prior, current = inputs()
    original = deepcopy(prior)
    trigger(current['bars']['60m'][0])
    invalidate(current['bars']['60m'][2])
    result = evaluate(prior, current)
    assert result['status'] == 'INVALIDATED_AFTER_TRIGGER'
    assert result['first_valid_trigger']['time'].endswith('10:30:00')
    assert result['invalidation_at'].endswith('14:00:00')
    assert result['original_condition']['invalidation_price'] == '9'
    assert prior == original
    assert result['hypothetical_fills'] is result['profit'] is None
    assert result['personal_sell_permission'] is result['formal_eligibility'] is False
    assert result['action'] == 'no_order'


def test_invalidation_latches_no_later_resurrection():
    prior, current = inputs()
    invalidate(current['bars']['60m'][0])
    trigger(current['bars']['60m'][1])
    result = evaluate(prior, current)
    assert result['status'] == 'INVALIDATED_BEFORE_TRIGGER'
    assert result['first_valid_trigger'] is None


@pytest.mark.parametrize('volume', ['119.99', '100'])
def test_price_cross_without_frozen_volume_cannot_confirm(volume):
    prior, current = inputs()
    trigger(current['bars']['60m'][0], volume)
    result = evaluate(prior, current)
    assert result['status'] == 'NOT_TRIGGERED'
    assert result['first_valid_trigger'] is None
    assert result['trace'][0]['reason'] == 'PRICE_ABOVE_TRIGGER_VOLUME_INSUFFICIENT'


def test_thresholds_are_strict_price_and_inclusive_existing_volume():
    prior, current = inputs()
    trigger(current['bars']['60m'][0])
    current['bars']['60m'][0]['close'] = '11'
    assert evaluate(prior, current)['first_valid_trigger'] is None
    current['bars']['60m'][0]['close'] = '11.2'
    assert evaluate(prior, current)['status'] == 'TRIGGER_OBSERVED'


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'unordered', 'zero_volume', 'missing_volume', 'future'])
def test_incomplete_or_invalid_path_cannot_confirm(defect):
    prior, current = inputs()
    rows = current['bars']['60m']
    trigger(rows[0])
    if defect == 'missing':
        rows.pop(2)
    elif defect == 'duplicate':
        rows.append(deepcopy(rows[-1]))
    elif defect == 'unordered':
        rows.reverse()
    elif defect == 'zero_volume':
        rows[-1]['volume'] = '0'
    elif defect == 'missing_volume':
        rows[-1].pop('volume')
    if defect == 'future':
        result = evaluate_frozen_condition_path(prior, current,
            observed_at=NOW.replace(hour=14, minute=30))
    else:
        result = evaluate(prior, current)
    assert result['status'] == 'NOT_ASSESSABLE'
    assert result['first_valid_trigger'] is None


def test_same_bar_bounds_cannot_establish_event_order():
    prior, current = inputs()
    trigger(current['bars']['60m'][0])
    current['bars']['60m'][0]['low'] = '8.5'
    result = evaluate(prior, current)
    assert result['status'] == 'NOT_ASSESSABLE'
    assert result['ambiguous_at'].endswith('10:30:00')
    assert result['first_valid_trigger'] is None
    assert result['invalidation_at'] is None


def test_later_ambiguous_bar_preserves_earlier_fact_but_not_overall_confirmation():
    prior, current = inputs()
    trigger(current['bars']['60m'][0])
    trigger(current['bars']['60m'][1])
    current['bars']['60m'][1]['low'] = '8.5'
    result = evaluate(prior, current)
    assert result['status'] == 'NOT_ASSESSABLE'
    assert result['first_valid_trigger']['time'].endswith('10:30:00')
    assert result['ambiguous_at'].endswith('11:30:00')
    assert result['formal_eligibility'] is False


def test_late_prior_source_and_expired_plan_do_not_become_forward_evidence():
    prior, current = inputs()
    prior['observed_at'] = '2026-10-20T09:00:00+08:00'
    assert evaluate(prior, current)['reason'] == 'PRIOR_CONDITION_NOT_KNOWN_BEFORE_TARGET_SESSION'
    prior['observed_at'] = '2026-10-19T16:00:00+08:00'
    current['market_trade_date'] = '2026-10-21'
    assert evaluate(prior, current)['reason'] == 'TARGET_IS_NOT_THE_SEALED_NEXT_EXCHANGE_SESSION'


def test_legacy_baseline_not_backfilled_and_changed_frozen_basis_rejected():
    prior, current = inputs()
    legacy = deepcopy(prior)
    legacy.pop('frozen_price_condition')
    assert evaluate(legacy, current)['status'] == 'NOT_ASSESSABLE'
    prior['frozen_price_condition']['mean_volume'] = '1'
    with pytest.raises(ValueError, match='basis changed'):
        evaluate(prior, current)


def test_current_source_not_available_and_wrong_symbol_fail_closed():
    prior, current = inputs()
    current['verified_available_at'] = '2026-10-20T16:01:00+08:00'
    assert evaluate(prior, current)['reason'] == 'CURRENT_SOURCE_NOT_AVAILABLE_AT_OBSERVATION'
    current['symbol'] = '000001'
    with pytest.raises(ValueError, match='identity mismatch'):
        evaluate(prior, current)


def test_retained_real_pair_replay_not_forward_or_shadow():
    import json
    import os
    from pathlib import Path
    from value_investment_agent.infrastructure.hotspot.current_price_case import load_current_price_case
    from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
    from value_investment_agent.domain.hotspot.shadow_observation import make_shadow_baseline
    root = os.environ.get('HOTSPOT_RETAINED_PAIR_ROOT')
    if root is None:
        pytest.skip('Explicit read-only retained real two-date source root required')
    root = Path(root)
    cases = []
    for name, digest in (
        ('300750-2026-10-22-33fb0e21b19e42c298afea658cf277fe',
         '7403915e9a25adab62fadfc881c14d6ec24efa552aec7a3d66a3cc542d40d5fd'),
        ('300750-2026-10-23-0562d041ff2a473581ec1fd21b17fafc',
         '7318349de7a62e54a463690b1e8cb939b874e5f2bf7634396b1e6beb9ff4a0f1'),
    ):
        path = Path('runtime/hotspot-current-price-cases') / name / 'case.json'
        stored = json.loads((root / path).read_bytes())
        bundle = json.loads((root / stored['current_reference_close']['bundle_path']).read_bytes())
        known = max(datetime.fromisoformat(value) for value in [bundle['finished_at'],
            *(row['fetched_at'] for row in stored['source_bindings'].values())])
        cases.append(load_current_price_case(root=root, symbol='300750', case_path=path,
                                            expected_sha256=digest, now=known))
    prior, current = cases
    plan = project_current_price_action_plan(prior)
    baseline = make_shadow_baseline({**prior, 'data_available_at': plan['data_available_at']}, plan,
        observed_at=datetime.fromisoformat(prior['verified_available_at']))
    result = evaluate_frozen_condition_path(baseline, current,
        observed_at=datetime.fromisoformat(current['verified_available_at']))
    # Source-asof reconstruction: no claim the plan was actually sealed then.
    assert result['original_condition']['entry_trigger_price'] == '232.830'
    assert result['original_condition']['invalidation_price'] == '218.450'
    assert result['status'] == 'NOT_TRIGGERED'
    assert any(row['reason'] == 'PRICE_ABOVE_TRIGGER_VOLUME_INSUFFICIENT' for row in result['trace'])
    assert result['first_valid_trigger'] is result['invalidation_at'] is None
    assert result['action'] == 'no_order' and result['real_trade'] is False

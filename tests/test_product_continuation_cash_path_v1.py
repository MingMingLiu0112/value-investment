"""TEST_ONLY hypotheses plus opt-in retained-public-source cold calculation."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.domain.valuation.finite_advantage_cash_path_v1 import SCOPE
from value_investment_agent.domain.valuation.product_continuation_cash_path_v1 import (
    build_product_continuation_cash_path,
)


def capital(year):
    return dict(year=year, scope=SCOPE, rationale='TEST_ONLY net maintenance balanced, not no maintenance',
        funding_treatment='NET_NEEDS_DEDUCTED_HERE_NOT_IN_UPSTREAM_MAPPING',
        maintenance_basis='EXPLICIT_NET_GAP_ASSUMPTION', net_maintenance_gap_cny='0',
        project_cash_cny='0', maintenance_project_overlap_cny='0', operating_wc_increase_cny='0',
        fund_call_cny='0', other_noncash_adjustment_cny='0', net_financing_cny='0')


def distribution(year, terminal=False):
    return dict(year=year, payout_ratio='1' if terminal else '.9', newly_withheld_fraction='0',
        release_fraction='0', reserve_transfer_fraction='0' if terminal else '.1',
        reserve_policy_rationale='TEST_ONLY explicit reserve policy, not inferred from a large reserve stock',
        capacity_mapping_rationale='TEST_ONLY owner funds mapping, not parent legal earnings')


def drivers():
    return dict(moutai_volume_growth='0', moutai_realization_growth='0',
        series_volume_growth='0', series_realization_growth='0', other_revenue_growth='0', cost_ratio='.1')


def terminal():
    return dict(method='STABLE_PRODUCT_PROFIT_ZERO_GROWTH_FULL_PAYOUT',
        rationale='TEST_ONLY flat products, margins, finance balance and attribution remain sustainable',
        operating_continuation='FINAL_PRODUCT_LEVELS_AND_EARNINGS_BRIDGE_CONSTANT',
        distribution_constraint_rationale='TEST_ONLY lawful stable payout assumption, not approval',
        capital_cash_row=capital(11), distribution_row=distribution(11, terminal=True))


@pytest.fixture
def inputs():
    rows = [dict(year=year, opening_product_reference_revenue_cny=dict(moutai='800', series='180', other='20'),
        product_revenue_cny=dict(moutai='800', series='180', other='20'), drivers=drivers(), revenue='1000',
        cost='100', expenses=dict(taxes_surcharges='20', selling='30', administration='40', research='10'),
        other_pre_tax_balance='20', legacy_pre_tax_profit='820', effective_tax_rate='.25',
        parent_share='.98', net_parent_nonrecurring_difference='2', legacy_ex_parent='600.7') for year in range(1, 6)]
    return dict(opening_state=dict(scope=SCOPE, currency='CNY', book_equity_cny='10000', cash_cny='3000',
        unremitted_assets_cny='0', distribution_capacity_cny='5000', cash_floor_cny='1000',
        uncalled_fund_commitment_cny='0', selected_project_budget_cny='0', ordinary_shares='100'),
        first_five_product_rows=rows, continuation_policy=[drivers() for _ in range(5)],
        capital_cash_rows=[capital(year) for year in range(1, 11)],
        distribution_rows=[distribution(year) for year in range(1, 11)],
        cost_of_equity='.08', incremental_cash_yield='.01', terminal_policy=terminal())


def test_flat_product_cash_and_ri_ddm_replay(inputs):
    before = deepcopy(inputs)
    result = build_product_continuation_cash_path(**inputs)
    assert result['valuation']['usable']
    assert len(result['operating_rows']) == len(result['cash_rows']) == 10
    assert all(D(row['legacy_ex_parent']) == D('600.7') for row in result['operating_rows'])
    assert D(result['cash_rows'][0]['incremental_cash_income_cny']) == 0
    assert D(result['cash_rows'][1]['incremental_cash_income_cny']) == D('.6007')
    assert abs(D(result['valuation']['ri_ddm_residual_cny'])) < D('1e-24')
    assert result['action'] == 'no_order' and not result['formal_eligibility']
    assert not result['economic_approval'] and not result['primary_valuation_changed']
    assert result['normalized_parent_profit_cny'] is None
    assert inputs == before
    json.dumps(result, allow_nan=False)


def test_terminal_uses_actual_closing_cash_not_last_profit(inputs):
    result = build_product_continuation_cash_path(**inputs)
    with localcontext() as context:
        context.prec = 48
        expected = D('600.7') + D('.01') * (D(result['cash_rows'][-1]['closing_cash_cny']) - D('3000'))
        assert D(result['terminal']['next_profit_cny']) == expected
        assert expected > D(result['cash_rows'][-1]['profit_cny'])
        assert D(result['terminal']['terminal_equity_cash_value_cny']) == expected/D('.08')
        assert D(result['terminal']['next_cash_cny']) == D(result['cash_rows'][-1]['closing_cash_cny'])
        assert D(result['terminal']['terminal_ri_cny']) != 0


def test_low_total_roe_does_not_trigger_forced_profit_recovery_or_collapse(inputs):
    inputs['incremental_cash_yield'] = '0'
    result = build_product_continuation_cash_path(**inputs)
    assert result['valuation']['usable']
    assert all(D(row['profit_cny']) == D('600.7') for row in result['cash_rows'])
    assert D(result['terminal']['first_year_ri_cny']) < 0


@pytest.mark.parametrize('challenge', ['realization', 'cost'])
def test_explicit_operating_counter_evidence_reduces_earnings_and_value(inputs, challenge):
    baseline = build_product_continuation_cash_path(**inputs)
    for row in inputs['continuation_policy']:
        row['moutai_realization_growth' if challenge == 'realization' else 'cost_ratio'] = '-.01' if challenge == 'realization' else '.12'
    result = build_product_continuation_cash_path(**inputs)
    assert result['valuation']['usable']
    assert D(result['operating_rows'][-1]['legacy_ex_parent']) < D('600.7')
    assert D(result['valuation']['equity_value_cny']) < D(baseline['valuation']['equity_value_cny'])
    assert result['operating_rows'][0] == baseline['operating_rows'][0]


def test_volume_and_realization_apply_to_product_not_whole_group(inputs):
    row = inputs['continuation_policy'][0]
    row.update(moutai_volume_growth='.1', moutai_realization_growth='-.1')
    result = build_product_continuation_cash_path(**inputs)
    first = result['operating_rows'][5]
    assert D(first['product_revenue_cny']['moutai']) == 792
    assert D(first['product_revenue_cny']['series']) == 180
    assert D(first['revenue']) == 992
    assert D(first['other_pre_tax_balance']) == 20


@pytest.mark.parametrize('field', ['legacy_ex_parent', 'revenue', 'cost', 'legacy_pre_tax_profit', 'other_pre_tax_balance'])
def test_original_product_row_tamper_rejected(inputs, field):
    inputs['first_five_product_rows'][2][field] = '999'
    with pytest.raises(ValueError, match='mismatch'):
        build_product_continuation_cash_path(**inputs)


def test_broken_original_product_continuity_rejected(inputs):
    # A fully recomputed but different product split cannot silently restart Y3.
    row = inputs['first_five_product_rows'][2]
    for field in ('opening_product_reference_revenue_cny', 'product_revenue_cny'):
        row[field].update(moutai='790', series='190')
    with pytest.raises(ValueError, match='continuity'):
        build_product_continuation_cash_path(**inputs)


@pytest.mark.parametrize('bad', [None, True, .1, 'NaN', 'Infinity'])
def test_invalid_driver_numbers_rejected(inputs, bad):
    inputs['continuation_policy'][0]['moutai_volume_growth'] = bad
    with pytest.raises(ValueError):
        build_product_continuation_cash_path(**inputs)


def test_no_default_or_optimized_horizon(inputs):
    inputs['continuation_policy'].append(drivers())
    with pytest.raises(ValueError, match='five'):
        build_product_continuation_cash_path(**inputs)


@pytest.mark.parametrize('challenge', ['gap', 'wc_offset', 'withheld', 'reserve', 'project', 'fund'])
def test_terminal_cash_challenges_reject_without_altering_payout(inputs, challenge):
    tp = inputs['terminal_policy']
    if challenge in ('gap', 'wc_offset'):
        tp['capital_cash_row']['net_maintenance_gap_cny'] = '5'
        if challenge == 'wc_offset':
            tp['capital_cash_row']['operating_wc_increase_cny'] = '-5'
    elif challenge == 'withheld':
        for row in inputs['distribution_rows']:
            row['newly_withheld_fraction'] = '.1'
    elif challenge == 'reserve':
        tp['distribution_row']['reserve_transfer_fraction'] = '.1'
    else:
        inputs['opening_state']['selected_project_budget_cny' if challenge == 'project' else 'uncalled_fund_commitment_cny'] = '5'
    result = build_product_continuation_cash_path(**inputs)
    assert not result['valuation']['usable']
    assert result['valuation']['equity_value_cny'] is None
    assert result['terminal']['terminal_ri_cny'] is None


def test_no_terminal_support_does_not_price_implicit_continuation(inputs):
    inputs['terminal_policy'] = None
    result = build_product_continuation_cash_path(**inputs)
    assert len(result['cash_rows']) == 10
    assert result['valuation']['equity_value_cny'] is None


def test_cash_failure_stops_unfunded_rows_without_cutting_dividends(inputs):
    inputs['opening_state']['cash_cny'] = '1000'
    inputs['distribution_rows'][0]['newly_withheld_fraction'] = '.2'
    result = build_product_continuation_cash_path(**inputs)
    assert len(result['cash_rows']) == 1
    assert not result['cash_rows'][0]['checks']['cash_floor']
    assert D(result['cash_rows'][0]['distribution_cny']) == D('540.63')
    assert result['valuation']['equity_value_cny'] is None


def test_scope_mismatch_and_missing_reserve_rationale_are_not_assumed_away(inputs):
    inputs['capital_cash_rows'][0]['scope'] = 'GROUP_DA_TO_PARENT_CASH'
    with pytest.raises(ValueError, match='scope'):
        build_product_continuation_cash_path(**inputs)
    inputs['capital_cash_rows'][0]['scope'] = SCOPE
    inputs['terminal_policy']['distribution_row']['reserve_policy_rationale'] = ''
    with pytest.raises(ValueError, match='rationale'):
        build_product_continuation_cash_path(**inputs)


def test_caller_precision_does_not_change_any_result(inputs):
    inputs['capital_cash_rows'][0]['net_maintenance_gap_cny'] = '5.1234567890123456789'
    with localcontext() as context:
        context.prec = 28
        expected = build_product_continuation_cash_path(**inputs)
    with localcontext() as context:
        context.prec = 6
        actual = build_product_continuation_cash_path(**inputs)
        assert context.prec == 6
    assert actual == expected


def test_retained_public_source_three_scenarios():
    """Explicit opt-in; cold PDF/statement replay, never current-pointer writes."""
    raw_root = os.environ.get('PRODUCT_CONTINUATION_REAL_ROOT')
    if not raw_root:
        pytest.skip('Set PRODUCT_CONTINUATION_REAL_ROOT to retained public source root')
    from datetime import datetime, timezone
    from hashlib import sha256
    from value_investment_agent.application.product.source_native_candidate_v2 import verify_source_native_candidate
    from value_investment_agent.application.product.incremental_validity import read_bound_json
    from value_investment_agent.application.research.product_operating_research import build_product_operating_research
    from value_investment_agent.m1_valuation_package_builder import build_descriptor

    root = Path(raw_root).resolve()
    relative = 'runtime/product-operating-research/20261025T071814444248Z/proposal/candidate/candidate.json'
    binding = '2e53d50d988a737272d7a95b822c8e0e9998d3749c1432cac7f6c12d92fe8ed0'
    now = datetime.now(timezone.utc)
    candidate = verify_source_native_candidate(root=root, path=root/relative, expected_sha256=binding, now=now)
    _, package = read_bound_json(root, candidate['source_package_binding'], 'real product package')
    _, ledger = read_bound_json(root, candidate['native_cash_ledger_binding'], 'real product ledger')
    facts = build_descriptor(package, root=root).facts
    refs = [dict(path=relative, sha256=binding), candidate['source_package_binding'],
            candidate['native_cash_ledger_binding'], *candidate['source_bindings']]
    def check_sources():
        for ref in refs:
            assert sha256((root/ref['path']).read_bytes()).hexdigest() == ref['sha256']
    check_sources()
    generated = build_product_operating_research(root=root, package=package, ledger=ledger, facts=facts, evaluation_at=now)
    assert generated['status'] == 'CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED'
    summaries = []
    for scenario in generated['scenarios']:
        old = ledger['cases']['TIMING_DELAY'][scenario['scenario']]
        opening = dict(scope=SCOPE, currency='CNY', book_equity_cny=str(facts.operating_inputs['start_book_equity']),
            cash_cny=ledger['history']['ttm']['cash_end'], unremitted_assets_cny='0',
            distribution_capacity_cny=ledger['history']['ttm']['parent_retained_profit_end'],
            cash_floor_cny=old['cash_floor'], uncalled_fund_commitment_cny=ledger['history']['known_uncalled_fund_commitment']['amount_cny'],
            selected_project_budget_cny=old['project_budget'], ordinary_shares=str(facts.operating_inputs['ordinary_shares']))
        cap, dist = [capital(y) for y in range(1, 11)], [distribution(y) for y in range(1, 11)]
        with localcontext() as context:
            context.prec = 48
            for y in range(5):
                cap[y]['project_cash_cny'] = str(D(old['project_budget'])/5)
            cap[0]['fund_call_cny'] = opening['uncalled_fund_commitment_cny']
        dist[0]['newly_withheld_fraction'] = '.1'
        dist[1]['release_fraction'] = '1'
        continuation = [dict(drivers(), cost_ratio=scenario['operating_rows'][-1]['drivers']['cost_ratio']) for _ in range(5)]
        args = dict(opening_state=opening, first_five_product_rows=scenario['operating_rows'],
            continuation_policy=continuation, capital_cash_rows=cap, distribution_rows=dist,
            cost_of_equity=ledger['plan']['ke'], incremental_cash_yield=ledger['plan']['incremental_parent_cash_yield'], terminal_policy=terminal())
        result = build_product_continuation_cash_path(**args)
        assert result['valuation']['usable']
        for new, source in zip(result['cash_rows'][:5], old['annual_rows']):
            assert abs(D(new['profit_cny'])-D(source['profit'])) < D('1e-24')
            assert abs(D(new['closing_cash_cny'])-D(source['cash_close'])) < D('1e-24')
        assert D(result['valuation']['terminal_value_pv_share']) > D('.5')
        adverse = deepcopy(args)
        adverse['continuation_policy'] = [dict(row, moutai_realization_growth='-.01',
            cost_ratio=str(D(row['cost_ratio'])+D('.005'))) for row in continuation]
        challenged = build_product_continuation_cash_path(**adverse)
        assert challenged['valuation']['usable']
        assert D(challenged['valuation']['equity_value_cny']) < D(result['valuation']['equity_value_cny'])
        summaries.append(dict(scenario=scenario['scenario'], profit_y10_cny=result['cash_rows'][-1]['profit_cny'],
            terminal_profit_cny=result['terminal']['next_profit_cny'], valuation=result['valuation'],
            challenge_valuation=challenged['valuation']))
    check_sources()
    print(json.dumps(dict(scope='ACTUAL_PUBLIC_SOURCE_COLD_REPLAY_UNAPPROVED_RESEARCH', candidate_binding=dict(path=relative, sha256=binding), rows=summaries)))

from copy import deepcopy
from decimal import Decimal

import pytest

from value_investment_agent.domain.valuation.distribution_capacity_review import explain_distribution_capacity
from value_investment_agent.application.product.consumed_economic_path import _distribution_diagnostics
from test_pending_candidate_alignment import real_candidate


def row(**changes):
    result = dict(year=1, profit='100', target_distribution='85', distribution='85',
        accessible_profit='90', mandatory_cash='10', cash_distribution_limit='95',
        capacity_distribution_limit='100', closing_cash='20', closing_unremitted='10',
        funding_shortfall='0')
    result.update(changes)
    return result


def test_target_met_can_still_need_opening_resources():
    source = [row()]
    original = deepcopy(source)
    result = explain_distribution_capacity(source)
    year = result['years'][0]
    assert year['status'] == 'TARGET_MET'
    assert year['net_period_resources'] == '80'
    assert year['distribution_support_from_opening_resources'] == '5'
    assert year['binding_constraints'] == ['TARGET_POLICY']
    assert Decimal(year['distribution_coverage_ratio']) < 1
    assert result['summary']['opening_resources_used_years'] == [1]
    assert source == original


@pytest.mark.parametrize('cash,capacity,expected', [('60','100','CASH_LIMIT'), ('95','60','DISTRIBUTABLE_CAPACITY')])
def test_distinguishes_cash_from_distribution_capacity(cash, capacity, expected):
    result = explain_distribution_capacity([row(distribution='60', cash_distribution_limit=cash,
        capacity_distribution_limit=capacity)])
    assert result['years'][0]['binding_constraints'] == [expected]
    assert result['years'][0]['target_reduction'] == '25'
    assert result['summary']['target_reduced_years'] == [1]


def test_ties_and_zero_distribution_do_not_invent_coverage():
    year = explain_distribution_capacity([row(target_distribution='0', distribution='0',
        cash_distribution_limit='0', capacity_distribution_limit='0', mandatory_cash='120',
        closing_cash='-5', funding_shortfall='5')])['years'][0]
    assert year['binding_constraints'] == ['TARGET_POLICY','CASH_LIMIT','DISTRIBUTABLE_CAPACITY']
    assert year['distribution_coverage_ratio'] is None
    assert year['operating_resource_deficit'] == '30'
    assert year['distribution_support_from_opening_resources'] == '0'
    assert year['status'] == 'FUNDING_SHORTFALL'


def test_working_capital_release_and_model_year_sequence():
    result = explain_distribution_capacity([row(mandatory_cash='-10'), row(year=2)])
    assert result['years'][0]['net_period_resources'] == '100'
    assert result['summary']['cumulative_distribution'] == '170'
    assert result['summary']['opening_resources_used_years'] == [2]


@pytest.mark.parametrize('change', [dict(profit='NaN'), dict(distribution='Infinity'),
    dict(distribution=True), dict(accessible_profit=None), dict(distribution='86'),
    dict(cash_distribution_limit='-1'), dict(year=2), dict(year=True)])
def test_invalid_or_inconsistent_ledger_is_rejected(change):
    with pytest.raises(ValueError):
        explain_distribution_capacity([row(**change)])


def review():
    return dict(candidate_binding={'path':'candidate.json','sha256':'a'*64},
        policy_binding={'path':'policy.json','sha256':'b'*64},
        input_descriptor_sha256='c'*64, valuation_at='2026-06-30',
        scenarios=[dict(scenario=s, ledger={'rows':[row()]}) for s in ('bear','base','bull')])


def test_projection_keeps_identity_and_does_not_partially_publish_bad_scenario():
    source = review()
    good = _distribution_diagnostics(source)
    assert good['candidate_binding'] == source['candidate_binding']
    assert good['assumption_binding'] == source['policy_binding']
    assert good['action'] == 'no_order' and not good['formal_eligibility']
    source['scenarios'][-1]['ledger']['rows'][0]['distribution'] = '999'
    bad = _distribution_diagnostics(source)
    assert bad['status'] == 'UNASSESSABLE' and bad['scenarios'] == []
    assert source['scenarios'][0]['ledger']['rows'][0]['distribution'] == '85'


def test_real_candidate_is_replayed_then_consumed(real_candidate):
    _, analysis, _, _ = real_candidate
    review = analysis['joint_capital_review']
    result = review['distribution_diagnostics']
    assert result['status'] == 'CONDITIONAL_DIAGNOSTICS'
    assert result['candidate_binding'] == review['candidate_binding']
    assert result['input_descriptor_sha256'] == review['input_descriptor_sha256']
    for source, scenario in zip(review['scenarios'], result['scenarios']):
        assert scenario['scenario'] == source['scenario']
        assert len(scenario['years']) == len(source['ledger']['rows']) == 10
        assert scenario['summary']['target_reduced_years'] == []
        assert scenario['summary']['funding_shortfall_years'] == []
        for raw, year in zip(source['ledger']['rows'],scenario['years']):
            assert year['distribution'] == raw['distribution']
            assert year['profit'] == raw['profit']
    bear, base, bull = result['scenarios']
    assert bear['summary']['opening_resources_used_years'] == [1]
    assert base['summary']['opening_resources_used_years'] == []
    assert Decimal(bear['summary']['minimum_distribution_coverage_ratio']) < 1
    assert Decimal(base['summary']['minimum_distribution_coverage_ratio']) > 1
    assert Decimal(bull['summary']['minimum_distribution_coverage_ratio']) > 1
    assert not analysis['action_admitted']
    assert not analysis['current_alignment']['currentpricecomparison']

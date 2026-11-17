"""One bounded diagnostic: TEST_ONLY arithmetic and opt-in retained JS2 originals."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import json
from pathlib import Path

import pytest

from test_source_native_economic_review_v1 import public_js2
from value_investment_agent.domain.valuation.joint_adverse_cash_v1 import (
    EX_PARENT_LABEL, diagnose_joint_adverse_cash,
)
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.source_native_candidate_v2 import verify_source_native_candidate
from value_investment_agent.application.research.operating_earnings_bridge import extract_statement
from value_investment_agent.domain.valuation.source_native_cash_v1 import replay_timing_delay_inputs


CODE = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    # TEST_ONLY numbers: no real issuer, source authentication or approval.
    return dict(annual_profit_fact=dict(label=EX_PARENT_LABEL, periods=['FY2025', 'FY2024'],
        values=['95', '100'], scope='CONSOLIDATED_AFTER_TAX_PARENT', unit='CNY', currency='CNY'),
        profit_anchor='1000', opening_book='3000', project_budget='50',
        plan=dict(horizon=5, explicit_retention='.10', incremental_parent_cash_yield='.01',
            TIMING_DELAY=dict(withheld_years=[1], withheld_fraction='.10'),
            known_uncalled_fund_commitment=dict(amount_cny='100')),
        history=dict(unit='CNY', scope='standalone parent, NOT consolidated free cash',
            periods=dict(FY2025=dict(operating_outflows='100')),
            ttm=dict(cash_end='1000', parent_equity_end='2000', parent_retained_profit_end='1000'),
            known_uncalled_fund_commitment=dict(amount_cny='100')))


def test_exact_plan_and_persistent_owned_assets_without_valuation(inputs):
    before = deepcopy(inputs)
    result = diagnose_joint_adverse_cash(**inputs)
    assert inputs == before
    assert result['status'] == 'FIVE_YEAR_CONDITIONAL_PLAN_FEASIBLE'
    assert result['disclosed_annual_growth'] == D('-.05')
    assert result['terminal_status'] == 'UNSUPPORTED_NO_RELEASE_NO_FULL_PAYOUT_TERMINAL'
    assert result['action'] == 'no_order'
    assert result['first_policy_failure_year'] is None
    assert result['not_computed_years'] == []
    with localcontext() as context:
        context.prec = 48
        c, b, u, re = D('1000'), D('3000'), D(0), D('1000')
        for t, row in enumerate(result['rows'], 1):
            p = D('1000') * D('.95')**t + D('.01')*(c-D('1000'))
            assert row['P'] == p
            assert row['newly_withheld'] == p/10 and row['released'] == 0
            assert row['M'] == p-p/10
            assert row['U'] == u+p/10
            assert row['D'] == D('.9')*p
            assert row['C'] == c+row['M']-10-(100 if t == 1 else 0)-row['D']
            assert abs(row['B']-(b+p-row['D'])) < D('1e-35')
            assert row['retained_profit'] == re+row['M']-D('.1')*row['M']-row['D']
            # h == retention makes M == planned D: operating pressure does NOT
            # additionally lower C under this mapping. Do not invent that effect.
            assert row['C'] == D('1000')-100-10*t
            assert abs(row['ownership_bridge_residual']) < D('1e-35')
            assert row['cash_bridge_residual'] == 0
            c, b, u, re = row['C'], row['B'], row['U'], row['retained_profit']
    assert result['outstanding_unremitted_assets'] == u > 0
    encoded = json.dumps(result, default=str)
    for forbidden in ('fair_value', 'entry_price', 'formal_eligibility', 'dividend_paid', 'cost_of_equity'):
        assert forbidden not in encoded


def test_cash_failure_keeps_planned_dividend_not_an_automatic_cut(inputs):
    inputs['history']['ttm']['cash_end'] = '200'
    inputs['history']['periods']['FY2025']['operating_outflows'] = '200'
    result = diagnose_joint_adverse_cash(**inputs)
    row, = result['rows']
    assert result['first_cash_failure_year'] == result['first_policy_failure_year'] == 1
    assert result['first_retained_profit_failure_year'] is None
    assert result['not_computed_years'] == [2, 3, 4, 5]
    assert row['D'] > row['cash_capacity']
    assert row['C'] == 90 < row['cash_floor']
    assert row['status'] == 'UNFUNDED_PLAN'
    assert result['status'] == 'INHERITED_PAYOUT_INFEASIBLE'


def test_retained_profit_failure_independent_of_cash(inputs):
    inputs['history']['ttm']['parent_retained_profit_end'] = '0'
    result = diagnose_joint_adverse_cash(**inputs)
    assert result['first_retained_profit_failure_year'] == 1
    assert result['first_cash_failure_year'] is None
    assert result['rows'][0]['retained_profit'] < 0
    assert result['rows'][0]['C'] > result['rows'][0]['cash_floor']


def test_unsupported_negative_profit_does_not_invent_funding(inputs):
    inputs['profit_anchor'] = '.0001'
    result = diagnose_joint_adverse_cash(**inputs)
    assert result['status'] == 'UNSUPPORTED'
    assert result['unsupported_reason'] == 'NONPOSITIVE_PROFIT_OR_EQUITY_NO_SUPPORTED_CASH_MAPPING'
    assert result['not_computed_years'] == [2, 3, 4, 5]


@pytest.mark.parametrize('values', [['100', '100'], ['101', '100'], ['0', '100'],
    ['-1', '100'], ['95', '0'], ['NaN', '100'], [True, '100'], [95.0, '100'], ['95']])
def test_no_unobserved_growth_or_missing_comparison(inputs, values):
    inputs['annual_profit_fact']['values'] = values
    with pytest.raises(ValueError):
        diagnose_joint_adverse_cash(**inputs)


@pytest.mark.parametrize('key,value', [('periods', ['H12026', 'H12025']),
    ('label', 'reported parent profit'), ('unit', 'CNY_10000'), ('currency', 'USD'),
    ('scope', 'STANDALONE_PARENT')])
def test_profit_definition_scope_and_period_are_not_interchangeable(inputs, key, value):
    inputs['annual_profit_fact'][key] = value
    with pytest.raises(ValueError):
        diagnose_joint_adverse_cash(**inputs)


@pytest.mark.parametrize('damage', ['horizon', 'boolean_year', 'retention', 'withholding',
    'yield', 'call', 'negative_project', 'missing_parent_re', 'annual_basis', 'group_cash'])
def test_no_silent_change_to_inherited_mapping_or_budget(inputs, damage):
    if damage == 'horizon': inputs['plan']['horizon'] = True
    elif damage == 'boolean_year': inputs['plan']['TIMING_DELAY']['withheld_years'] = [True]
    elif damage == 'retention': inputs['plan']['explicit_retention'] = '.25'
    elif damage == 'withholding': inputs['plan']['TIMING_DELAY']['withheld_fraction'] = '.20'
    elif damage == 'yield': inputs['plan']['incremental_parent_cash_yield'] = '0'
    elif damage == 'call': inputs['plan']['known_uncalled_fund_commitment']['amount_cny'] = '99'
    elif damage == 'negative_project': inputs['project_budget'] = '-1'
    elif damage == 'missing_parent_re': del inputs['history']['ttm']['parent_retained_profit_end']
    elif damage == 'annual_basis': inputs['history']['periods']['FY2024'] = dict(operating_outflows='100')
    elif damage == 'group_cash': inputs['history']['scope'] = 'consolidated free cash'
    with pytest.raises((ValueError, KeyError)):
        diagnose_joint_adverse_cash(**inputs)


def test_precision_does_not_depend_on_callers_context(inputs):
    normal = diagnose_joint_adverse_cash(**inputs)
    with localcontext() as context:
        context.prec = 6
        assert diagnose_joint_adverse_cash(**inputs) == normal


def test_discount_rate_cannot_repair_a_cash_failure(inputs):
    inputs['history']['ttm']['cash_end'] = '200'
    inputs['history']['periods']['FY2025']['operating_outflows'] = '200'
    inputs['plan']['ke'] = '.01'
    result = diagnose_joint_adverse_cash(**inputs)
    inputs['plan']['ke'] = '.99'
    assert diagnose_joint_adverse_cash(**inputs) == result
    assert result['first_cash_failure_year'] == 1


def test_real_js2_bound_sources_recompute_the_joint_counterexample(public_js2, tmp_path):
    root, ref, _ = public_js2
    candidate = verify_source_native_candidate(root=root, path=root/ref['path'],
        expected_sha256=ref['sha256'], now=datetime.now(timezone.utc))
    refs = [ref, *candidate['source_bindings']]
    before = {r['path']: sha256_file(root/r['path']) for r in refs}
    package = json.loads((root/candidate['source_package_binding']['path']).read_bytes())
    ledger = json.loads((root/candidate['native_cash_ledger_binding']['path']).read_bytes())
    forbidden_plan = deepcopy(ledger['plan'])
    forbidden_plan['TIMING_DELAY']['withheld_years'] = [1, 2, 3, 4, 5]
    with pytest.raises(ValueError, match='Unsupported native timing'):
        replay_timing_delay_inputs(plan=forbidden_plan, scenarios=ledger['cases']['TIMING_DELAY'],
            opening_book=package['facts']['operating_inputs']['start_book_equity'], history=ledger['history'])
    specifications = json.loads((CODE/'docs/current/two-company-earnings-bridge-20261024/sources.json').read_bytes())
    specs = deepcopy(specifications['companies']['600519'])
    profit_sources = package['research_case']['financial_summary']['historical_profit_reconciliation']['source_rows']
    for spec, source in zip(specs, (profit_sources[0], profit_sources[1])):
        assert spec['sha256'] == source['sha256']
        spec['path'] = source['path']  # Same official bytes in existing content-addressed closure.
        spec['fields'] = ['ex_parent_profit']
    annual, interim = [extract_statement(root=root, spec=spec)['rows']['ex_parent_profit'] for spec in specs]
    with localcontext() as context:
        context.prec = 48
        anchor = D(annual['values'][0])+D(interim['values'][0])-D(interim['values'][1])
    assert anchor == D(package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'])
    result = diagnose_joint_adverse_cash(annual_profit_fact=annual, profit_anchor=anchor,
        plan=ledger['plan'], history=ledger['history'],
        opening_book=package['facts']['operating_inputs']['start_book_equity'],
        project_budget=ledger['cases']['TIMING_DELAY']['base']['project_budget'])
    assert len(result['rows']) == 5 and result['not_computed_years'] == []
    assert result['first_cash_failure_year'] == result['first_policy_failure_year'] == 5
    assert result['first_retained_profit_failure_year'] is None
    assert result['rows'][-1]['status'] == 'UNFUNDED_PLAN'
    assert result['rows'][-1]['retained_profit'] > 0
    assert result['status'] == 'INHERITED_PAYOUT_INFEASIBLE'
    with localcontext() as context:
        context.prec = 48
        c0 = D(ledger['history']['ttm']['cash_end'])
        budget = D(ledger['cases']['TIMING_DELAY']['base']['project_budget'])
        call = D(ledger['plan']['known_uncalled_fund_commitment']['amount_cny'])
        opening_re = D(ledger['history']['ttm']['parent_retained_profit_end'])
        # The inherited 48-digit operation order rounds M and D separately.
        # Compare identities at sub-cent precision, not Decimal bit equality.
        assert abs(result['rows'][-1]['C']-(c0-budget-call)) < D('1e-34')
        for row in result['rows']:
            assert abs(row['C']-(c0-budget/5*row['year']-call)) < D('1e-34')
            assert abs(row['ownership_bridge_residual']) < D('1e-34')
        assert abs(result['outstanding_unremitted_assets']-
            sum(row['P'] for row in result['rows'])/10) < D('1e-34')
        assert abs(result['rows'][-1]['retained_profit']-
            (opening_re-D('.09')*sum(row['P'] for row in result['rows']))) < D('1e-34')
    assert all(row['released'] == 0 for row in result['rows'])
    assert ledger['cases']['TIMING_DELAY']['base']['annual_rows'][1]['released'] != '0'
    assert before == {r['path']: sha256_file(root/r['path']) for r in refs}
    assert all(before[r['path']] == r['sha256'] for r in refs)
    receipt = dict(source_scope='REAL_RETAINED_PUBLIC_NOT_HISTORICAL_PIT_PROOF',
        annual_profit_fact=annual, interim_profit_fact=interim, source_bindings=refs,
        source_spec_binding=dict(path='docs/current/two-company-earnings-bridge-20261024/sources.json',
            sha256=sha256_file(CODE/'docs/current/two-company-earnings-bridge-20261024/sources.json')),
        extractor_binding=dict(path='src/value_investment_agent/application/research/operating_earnings_bridge.py',
            sha256=sha256_file(CODE/'src/value_investment_agent/application/research/operating_earnings_bridge.py')),
        implementation=dict(path='src/value_investment_agent/domain/valuation/joint_adverse_cash_v1.py',
            sha256=sha256_file(CODE/'src/value_investment_agent/domain/valuation/joint_adverse_cash_v1.py')),
        result=result, action='no_order')
    (tmp_path/'joint-adverse-cash.json').write_text(json.dumps(receipt, default=str,
        ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

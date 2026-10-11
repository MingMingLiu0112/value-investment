"""Synthetic path contracts; no issuer, approval or price admission evidence."""
import json
from decimal import Decimal

import pytest

from test_research_review_packet import inputs
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.neutral_valuation_proposal import build_neutral_valuation_proposal


def proposal_inputs(root):
    _, package_path = inputs(root)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'] = str(
        Decimal(package['facts']['operating_inputs']['start_book_equity']) * Decimal('0.20'))
    package['source_contract']['fact_anchors'].append(dict(
        field='ttm_ex_nonrecurring_parent_profit_cny', source_id='facts', physical_page=1,
        source_value=package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'],
        unit='CNY', scope='consolidated_parent_profit_ex_nonrecurring',
        period_end=package['point_in_time']['report_period']))
    package_path.write_text(json.dumps(package), encoding='utf-8')
    rationale = root / 'runtime/rationale.md'
    rationale.write_text('Synthetic continuity proposal; duration and dividends are unapproved.', encoding='utf-8')
    policy = dict(schema_version='finite-earnings-path-proposal-v1', action='no_order',
        symbol=package['symbol'], source_package_sha256=sha256_file(package_path),
        profit_anchor_field='ttm_ex_nonrecurring_parent_profit_cny', profit_basis='synthetic disclosed proxy',
        income_growth={'bear': '-0.05', 'base': '0', 'bull': '0.05'},
        rationale_bindings=[dict(path='runtime/rationale.md', sha256=sha256_file(rationale))],
        choices=[dict(id='continuity', growth_years=10, fade_years=5,
            rationale='Synthetic earnings persistence; not proven.', countercase='Persistence may fail.')],
        economic_review_items=['Review persistence.'], assurance_limits=['No actual approval.'])
    policy_path = root / 'runtime/policy.json'
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    return package_path, policy_path


def run(root, package, policy):
    return build_neutral_valuation_proposal(root=root, package_path=package,
        package_sha256=sha256_file(package), policy_path=policy, policy_sha256=sha256_file(policy),
        output_path=root / 'runtime/proposal.json')


def test_new_path_is_consumed_by_same_model_without_upgrading_research(tmp_path):
    package, policy = proposal_inputs(tmp_path)
    before = package.read_bytes()
    result = run(tmp_path, package, policy)
    assert package.read_bytes() == before
    assert result['status'] == 'NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW'
    assert result['decision_changed'] is result['g3_approved'] is result['price_admitted'] is False
    assert result['research_date_advanced'] is False and result['position_guidance'] is None
    assert result['normalized_profit'] is None
    row = result['choices'][0]
    assert row['valuation']['status'] == 'conditional_research_only'
    assert row['valuation']['model_version'] == result['baseline_valuation']['model_version']
    for scenario in row['annual_arithmetic'].values():
        assert scenario['date_bridge']['basis_to_valuation_factor'] == '1'
        assert Decimal(scenario['date_bridge']['model_per_share_difference_cny']) == 0
        assert scenario['date_bridge']['basis_origin_per_share_cny'] == scenario['date_bridge']['valuation_date_per_share_cny']
        assert len(scenario['forecast_years']) == 15
        years = scenario['forecast_years']
        for year in years:
            assert abs(Decimal(year['opening_book_equity_cny']) + Decimal(year['net_income_assumption_cny'])
                       - Decimal(year['dividend_assumption_cny']) - Decimal(year['closing_book_equity_cny'])) < Decimal('0.01')
        assert abs(Decimal(scenario['dividend_crosscheck_difference_cny'])) < Decimal('0.01')
    assert row['actual_calculation_inputs']['scenarios']['base']['retention']
    assert (tmp_path / 'runtime/proposal.md').is_file()
    with pytest.raises(FileExistsError):
        run(tmp_path, package, policy)


@pytest.mark.parametrize('change', ['other-package', 'other-symbol', 'unbounded', 'rationale', 'missing-anchor'])
def test_invalid_proposal_cannot_write_or_change_the_package(tmp_path, change):
    package, policy_path = proposal_inputs(tmp_path)
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    if change == 'other-package':
        policy['source_package_sha256'] = '0' * 64
    elif change == 'other-symbol':
        policy['symbol'] = '000001'
    elif change == 'unbounded':
        policy['choices'][0]['growth_years'] = 1000
    elif change == 'missing-anchor':
        policy['profit_anchor_field'] = 'missing'
    else:
        (tmp_path / 'runtime/rationale.md').write_text('changed', encoding='utf-8')
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    before = package.read_bytes()
    with pytest.raises(ValueError):
        run(tmp_path, package, policy_path)
    assert package.read_bytes() == before
    assert not (tmp_path / 'runtime/proposal.json').exists()


def test_dated_annual_details_reconcile_to_same_model_values(tmp_path):
    package_path, policy = proposal_inputs(tmp_path)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    package['facts']['valuation_timing'] = dict(basis_at='2026-06-30T23:59:59+08:00',
        valuation_at='2026-09-22T16:00:00+08:00', evidence_refs=[dict(id='facts')])
    package['dependencies']['model_version'] = 'residual-income-equity-shared-dated-v2'
    package_path.write_text(json.dumps(package), encoding='utf-8')
    data = json.loads(policy.read_text(encoding='utf-8'))
    data['source_package_sha256'] = sha256_file(package_path)
    policy.write_text(json.dumps(data), encoding='utf-8')
    result = run(tmp_path, package_path, policy)
    row = result['choices'][0]
    for name, annual in row['annual_arithmetic'].items():
        bridge = annual['date_bridge']
        origin = Decimal(bridge['basis_origin_per_share_cny'])
        dated = Decimal(bridge['valuation_date_per_share_cny'])
        assert dated > origin
        assert dated == Decimal(row['valuation'][f'{name}_value'])
        assert dated == Decimal(annual['per_share_value'])
        assert abs(dated - origin * Decimal(bridge['basis_to_valuation_factor'])) < Decimal('1e-20')
        assert Decimal(bridge['model_per_share_difference_cny']) == 0
        assert Decimal(bridge['equity_transport_difference_cny']) == 0
        assert bridge['basis_at'].startswith('2026-06-30')
        assert bridge['valuation_at'].startswith('2026-09-22')
        assert abs(Decimal(annual['dividend_crosscheck_difference_cny'])) < Decimal('0.01')
        assert annual['annual_schedule_scope'].startswith('basis_origin')
    assert result['g3_approved'] is result['research_date_advanced'] is False
    assert '日期因子' in (tmp_path/'runtime/proposal.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('change', ['shares', 'equity', 'undeclared', 'unit', 'scope', 'value', 'source', 'period'])
def test_only_declared_cny_parent_profit_is_accepted_as_earnings(tmp_path, change):
    package_path, policy_path = proposal_inputs(tmp_path)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    declaration = package['source_contract']['fact_anchors'][-1]
    if change in ('shares', 'equity'):
        field = 'ordinary_shares' if change == 'shares' else 'start_book_equity'
        package['research_case']['financial_summary'][field] = package['facts']['operating_inputs'][field]
        policy['profit_anchor_field'] = field
        # Even a fabricated CNY label cannot turn shares/equity into profit.
        declaration['field'] = field
        declaration['source_value'] = package['research_case']['financial_summary'][field]
    elif change == 'undeclared':
        package['source_contract']['fact_anchors'].pop()
    elif change == 'unit':
        declaration['unit'] = 'shares'
    elif change == 'scope':
        declaration['scope'] = 'parent_company_profit'
    elif change == 'value':
        declaration['source_value'] = '1'
    elif change == 'source':
        declaration['source_id'] = 'unbound'
    elif change == 'period':
        declaration['period_end'] = '2025-12-31'
    package_path.write_text(json.dumps(package), encoding='utf-8')
    policy['source_package_sha256'] = sha256_file(package_path)
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    before = package_path.read_bytes()
    with pytest.raises(ValueError, match='earnings anchor'):
        run(tmp_path, package_path, policy_path)
    assert package_path.read_bytes() == before
    assert not (tmp_path/'runtime/proposal.json').exists()
    assert not (tmp_path/'runtime/proposal.md').exists()


@pytest.mark.parametrize('change', [None, 'unit', 'scope', 'amount', 'inline-drift', 'missing-rows'])
def test_bound_ttm_components_supply_actual_financial_declaration(tmp_path, change):
    package_path, policy_path = proposal_inputs(tmp_path)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    package['source_contract']['fact_anchors'].pop()
    anchor = package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny']
    original = package['sources'][0]
    rows = [dict(period=period, currency='CNY', statement_scope='consolidated',
        profit_basis='attributable_to_parent', source_id=original['id'], sha256=original['sha256'],
        ex_nonrecurring_profit_cny=amount) for period, amount in
        [('FY2025', anchor), ('H1_2026', '10'), ('H1_2025', '10')]]
    reconciliation = dict(symbol=package['symbol'], report_period=package['point_in_time']['report_period'],
        formula='FY2025 + H1_2026 - H1_2025', source_rows=rows,
        ttm_ex_nonrecurring_parent_profit_cny=anchor)
    if change == 'unit':
        rows[0]['currency'] = 'shares'
    elif change == 'scope':
        rows[0]['profit_basis'] = 'consolidated_including_minority'
    elif change == 'amount':
        rows[0]['ex_nonrecurring_profit_cny'] = str(Decimal(anchor) + 1)
    elif change == 'missing-rows':
        rows.pop()
    path = tmp_path/'runtime/profit-reconciliation.json'
    path.write_text(json.dumps(reconciliation), encoding='utf-8')
    package['sources'].append(dict(id='synthetic-reconciliation', kind='research_artifact',
        parser_version='historical-profit-reconciliation-v1', local_path='runtime/profit-reconciliation.json',
        location='runtime/profit-reconciliation.json',
        sha256=sha256_file(path)))
    package['research_case']['financial_summary']['historical_profit_reconciliation'] = reconciliation
    if change == 'inline-drift':
        rows[1]['ex_nonrecurring_profit_cny'] = '20'
    package_path.write_text(json.dumps(package), encoding='utf-8')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['source_package_sha256'] = sha256_file(package_path)
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    if change is None:
        result = run(tmp_path, package_path, policy_path)
        assert result['choices'][0]['actual_calculation_inputs']['profit_anchor_unit'] == 'CNY'
    else:
        with pytest.raises(ValueError, match='earnings anchor'):
            run(tmp_path, package_path, policy_path)
        assert not (tmp_path/'runtime/proposal.json').exists()

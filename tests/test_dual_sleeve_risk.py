"""Isolated synthetic arithmetic only; no real investment policy or portfolio."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from test_portfolio_risk_assessment import _policy, _snapshot, _holding, _attributes, GENERATED_AT
from value_investment_agent.portfolio_contracts import PortfolioInputBundle
from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk, CORE, HOTSPOT
from value_investment_agent.application.product.dual_sleeve_risk import run_dual_sleeve_review
from value_investment_agent.application.product.common import sha256_file, write_new_json


def synthetic_input():
    bundle = PortfolioInputBundle(policy=_policy(investable_assets_cny=Decimal('10000'),
        minimum_cash_cny=Decimal('1000'), emergency_cash_cny=Decimal('100'), liquidity_needs_cny=Decimal('100')),
        snapshot=_snapshot(namespace='SIMULATED', cash_cny=Decimal('9000'),
            holdings=(_holding(market_value_cny=Decimal('1000')),)))
    bundle = replace(bundle, snapshot=replace(bundle.snapshot,
        holdings=(replace(bundle.snapshot.holdings[0], cost_basis_cny=Decimal('900')),)))
    sleeve = dict(cash_cny='4400', risk_budget_cny='500', max_single_security_fraction='1',
        max_industry_fraction='1', max_factor_fraction='1', single_trade_risk_fraction=None,
        single_security_risk_cny=None, realized_pnl_cny=None, financing_allowed=False,
        risk_tools_allowed=False, confirmed_at=GENERATED_AT.isoformat(), evidence_ref='synthetic-policy')
    request = dict(sleeve=HOTSPOT, symbol='600519', entry_price_cny='10', stop_price_cny='9',
        gap_stress_cny='0.1', entry_slippage_cny='0.01', exit_slippage_cny='0.01',
        buy_fee_fraction='0.001', sell_fee_fraction='0.001', minimum_buy_fee_cny='1',
        minimum_sell_fee_cny='1', lot_size=100, max_trade_notional_cny='10000',
        quote_as_of=bundle.snapshot.as_of.isoformat(), available_at=GENERATED_AT.isoformat(),
        valid_until=(GENERATED_AT+timedelta(hours=1)).isoformat(), liquidity_verified=True,
        limit_up=False, limit_down=False, research_version_sha256='a'*64, evidence_ref='synthetic-quote')
    return dict(schema_version='dual-sleeve-risk-input-v1', action='no_order', namespace='SIMULATED',
        portfolio=bundle.as_policy(), shared_budget=dict(core_value_budget='0.5',
            tactical_hotspot_budget='0.3', cash_floor='0.2', cross_sleeve_single_stock_cap='0.8',
            cross_sleeve_sector_cap='0.8', policy_scope='SYNTHETIC_POLICY_ONLY', action='no_order'),
        sleeves={CORE: sleeve, HOTSPOT: dict(sleeve, cash_cny='2600',
            single_trade_risk_fraction='0.1', single_security_risk_cny='300')},
        cash_reserve_cny='2000', allocations=[
            dict(sleeve=CORE, symbol='600519', quantity='60', sellable_quantity='60',
                committed_risk_cny='30', evidence_ref='synthetic-core'),
            dict(sleeve=HOTSPOT, symbol='600519', quantity='40', sellable_quantity='0',
                committed_risk_cny='40', evidence_ref='synthetic-satellite')],
        security_attributes=[_attributes(common_factors=('consumer',)).as_policy()], hotspot_request=request)


def review(payload):
    return review_dual_sleeve_risk(payload, generated_at=GENERATED_AT, allow_synthetic=True)


def test_partition_reuses_existing_aggregate_engine_and_distinguishes_core_risk():
    result = review(synthetic_input())
    assert result['namespace'] == 'SIMULATED' and result['trade_eligible'] is False
    assert result['aggregate']['total_assets_cny'] == '10000'
    assert result['aggregate']['existing_risk_assessment']['total_assets_cny'] == '10000'
    assert [r['quantity'] for r in result['aggregate']['duplicated_security_exposure']['600519']] == ['60', '40']
    assert result['sleeves'][CORE]['unrealized_pnl_cny'] == '60'
    assert result['sleeves'][HOTSPOT]['unrealized_pnl_cny'] == '40'
    assert result['sleeves'][CORE]['mechanical_stop_required'] is False
    assert result['sleeves'][CORE]['exit_basis'] == 'FUNDAMENTAL_THESIS_AND_LIQUIDITY_REVIEW'
    assert result['sleeves'][HOTSPOT]['contract_sleeve'] == 'TACTICAL_HOTSPOT'
    assert result['sleeves'][CORE]['realized_pnl_cny'] is None
    assert result['position_guidance'] is result['expected_return'] is None


def test_loss_sizing_includes_fees_slippage_lot_and_gap_without_stop_guarantee():
    result = review(synthetic_input())['hotspot_quantity_review']
    assert result['review_quantity'] == 200
    assert Decimal(result['cash_required_cny']) == Decimal('2004.002')
    assert Decimal(result['stressed_loss_cny']) == Decimal('227.780')
    assert Decimal(result['stressed_loss_cny']) <= Decimal(result['planned_risk_limit_cny'])
    assert result['t_plus_one'] and not result['same_day_exit_available']
    assert not result['stop_execution_guaranteed'] and not result['trade_eligible']
    assert Decimal(result['full_capital_at_risk_cny']) > Decimal(result['stressed_loss_cny'])


@pytest.mark.parametrize('change', ['cash', 'quantity', 'duplicate', 'budget', 'namespace', 'scope'])
def test_double_reservation_or_namespace_policy_mixing_rejected(change):
    payload = synthetic_input()
    if change == 'cash': payload['sleeves'][HOTSPOT]['cash_cny'] = '3000'
    if change == 'quantity': payload['allocations'][1]['quantity'] = '41'
    if change == 'duplicate': payload['allocations'].append(deepcopy(payload['allocations'][0]))
    if change == 'budget': payload['shared_budget']['cash_floor'] = '0.4'
    if change == 'namespace': payload['namespace'] = 'ACTUAL'
    if change == 'scope': payload['shared_budget']['policy_scope'] = 'USER_CONFIRMED'
    with pytest.raises(ValueError): review(payload)


@pytest.mark.parametrize('field,value', [('committed_risk_cny', None), ('committed_risk_cny', '500')])
def test_unknown_or_exhausted_hotspot_risk_cannot_borrow_core(field, value):
    payload = synthetic_input()
    payload['allocations'][1][field] = value
    before = deepcopy(payload)
    result = review(payload)
    assert result['hotspot_quantity_review']['review_quantity'] is None
    assert result['sleeves'][CORE]['available_risk_cny'] == '470'
    assert payload == before


@pytest.mark.parametrize('field,value', [('limit_up', True), ('limit_down', True),
    ('liquidity_verified', False), ('valid_until', '2026-09-21T12:00:00+00:00'),
    ('available_at', '2026-09-23T12:00:00+00:00'), ('quote_as_of', '2026-09-21')])
def test_execution_or_time_uncertainty_blocks_quantity(field, value):
    payload = synthetic_input()
    payload['hotspot_request'][field] = value
    assert review(payload)['hotspot_quantity_review']['review_quantity'] is None


def test_user_caps_and_minimum_fee_reduce_quantity_without_default_policy():
    payload = synthetic_input()
    payload['hotspot_request']['minimum_buy_fee_cny'] = '1000'
    assert review(payload)['hotspot_quantity_review']['review_quantity'] == 0
    payload = synthetic_input()
    payload['sleeves'][HOTSPOT]['max_single_security_fraction'] = '0.3'
    assert review(payload)['hotspot_quantity_review']['review_quantity'] == 0
    payload = synthetic_input()
    payload['hotspot_request']['gap_stress_cny'] = '20'
    assert review(payload)['hotspot_quantity_review']['review_quantity'] == 0


def test_new_cash_use_preserves_existing_ips_cash_reserve():
    payload = synthetic_input()
    payload['portfolio']['policy']['minimum_cash_cny'] = '8500'
    assert review(payload)['hotspot_quantity_review']['review_quantity'] == 0


@pytest.mark.parametrize('cap,quantity', [('15', 0), ('25', 100), ('40', 200)])
def test_new_cyclical_exposure_respects_aggregate_ips_cap_across_sleeves(cap, quantity):
    payload = synthetic_input()
    payload['security_attributes'][0]['cyclical'] = True
    payload['portfolio']['policy']['max_cyclical_exposure_pct'] = cap
    result = review(payload)
    sizing = result['hotspot_quantity_review']
    assert sizing['review_quantity'] == quantity
    existing = sum((Decimal(row['market_value_cny']) for sleeve in (CORE, HOTSPOT)
        for row in result['sleeves'][sleeve]['holdings']), Decimal(0))
    assert existing + Decimal(sizing['cash_required_cny']) <= Decimal('10000')*Decimal(cap)/100
    assert result['action'] == 'no_order' and sizing['trade_eligible'] is False


def test_noncyclical_purchase_does_not_consume_cyclical_headroom():
    payload = synthetic_input()
    payload['portfolio']['policy']['max_cyclical_exposure_pct'] = '1'
    assert review(payload)['hotspot_quantity_review']['review_quantity'] == 200


def test_cross_sleeve_overlap_cap_and_cash_floor_fail_closed():
    payload = synthetic_input()
    payload['shared_budget']['cross_sleeve_single_stock_cap'] = '0.09'
    result = review(payload)
    assert 'shared:single_security_cap:600519' in result['blockers']
    assert result['hotspot_quantity_review']['status'] == 'BLOCKED'
    assert result['hotspot_quantity_review']['review_quantity'] is None
    assert result['aggregate']['duplicated_security_exposure']['600519'][0]['quantity'] == '60'
    assert result['aggregate']['duplicated_security_exposure']['600519'][1]['quantity'] == '40'
    assert result['action'] == 'no_order' and result['trade_eligible'] is False

    payload = synthetic_input()
    payload['cash_reserve_cny'] = '1000'
    payload['sleeves'][CORE]['cash_cny'] = '5400'
    result = review(payload)
    assert 'shared:cash_floor_violation' in result['blockers']
    assert result['hotspot_quantity_review']['review_quantity'] is None
    assert result['sleeves'][HOTSPOT]['cash_cny'] == '2600'


def test_semantic_content_ignores_run_dates_paths_but_not_economic_input(tmp_path):
    source = tmp_path/'.tmp/input.json'
    write_new_json(source, synthetic_input())
    args = dict(root=tmp_path, input_path=source, input_sha256=sha256_file(source), synthetic=True,
        generated_at=GENERATED_AT)
    first = run_dual_sleeve_review(**args)
    second = run_dual_sleeve_review(**dict(args, generated_at=GENERATED_AT+timedelta(minutes=1)))
    assert first['semantic_content'] == second['semantic_content']
    from value_investment_agent.application.product.dual_sleeve_risk import semantic_content
    assert semantic_content(dict(path='run/a', sha256='a'*64)) == semantic_content(dict(path='run/b', sha256='a'*64))
    payload = synthetic_input()
    payload['hotspot_request']['gap_stress_cny'] = '0.2'
    source2 = tmp_path/'.tmp/input2.json'
    write_new_json(source2, payload)
    third = run_dual_sleeve_review(**dict(args, input_path=source2, input_sha256=sha256_file(source2)))
    assert first['semantic_content'] != third['semantic_content']


def test_unconnected_report_can_write_fresh_root_binding(tmp_path):
    output = tmp_path/'runtime/dual/report.json'
    report = run_dual_sleeve_review(root=tmp_path, output_path=output, generated_at=GENERATED_AT)
    assert report['status'] == 'NOT_CONNECTED'
    assert json.loads(output.read_text(encoding='utf-8')) == report
    with pytest.raises(FileExistsError):
        run_dual_sleeve_review(root=tmp_path, output_path=output, generated_at=GENERATED_AT)


def test_core_sizing_rejected_and_synthetic_permission_is_explicit():
    payload = synthetic_input()
    payload['hotspot_request']['sleeve'] = CORE
    with pytest.raises(ValueError, match='core has no mechanical stop'): review(payload)
    with pytest.raises(ValueError, match='isolated permission'):
        review_dual_sleeve_risk(synthetic_input(), generated_at=GENERATED_AT)


def test_missing_or_unconfirmed_private_data_produces_no_amounts():
    result = run_dual_sleeve_review(root=Path(__file__).resolve().parents[1], generated_at=GENERATED_AT)
    assert result['status'] == 'NOT_CONNECTED'
    assert result['sleeves'] is result['aggregate'] is result['hotspot_quantity_review'] is None
    payload = synthetic_input()
    payload['portfolio']['policy'].update(confirmation_status='DRAFT', confirmed_at=None)
    assert review(payload)['sleeves'] is None
    payload = synthetic_input()
    payload['sleeves'][CORE]['cash_cny'] = None
    assert review(payload)['hotspot_quantity_review'] is None


def test_explicit_cash_only_snapshot_can_be_reviewed_without_fake_holdings():
    payload = synthetic_input()
    payload['portfolio']['snapshot']['cash_cny'] = '10000'
    payload['portfolio']['snapshot']['holdings'] = []
    payload['allocations'] = []
    payload['security_attributes'] = []
    payload['hotspot_request'] = None
    payload['sleeves'][CORE]['cash_cny'] = '5000'
    payload['sleeves'][HOTSPOT]['cash_cny'] = '3000'
    result = review(payload)
    assert result['aggregate']['total_assets_cny'] == '10000'
    assert result['aggregate']['duplicated_security_exposure'] == {}
    assert result['sleeves'][CORE]['holdings'] == []
    assert result['sleeves'][HOTSPOT]['used_funds_cny'] == '0'


def test_pinned_synthetic_io_isolated_and_append_only(tmp_path):
    source = tmp_path/'.tmp/input.json'
    output = tmp_path/'.tmp/report.json'
    write_new_json(source, synthetic_input())
    args = dict(root=tmp_path, input_path=source, input_sha256=sha256_file(source), output_path=output,
        synthetic=True, generated_at=GENERATED_AT)
    assert run_dual_sleeve_review(**args)['namespace'] == 'SIMULATED'
    original = output.read_bytes()
    with pytest.raises(FileExistsError): run_dual_sleeve_review(**args)
    assert output.read_bytes() == original
    with pytest.raises(ValueError, match='hash mismatch'):
        run_dual_sleeve_review(**dict(args, input_sha256='b'*64))
    with pytest.raises(ValueError, match='isolated synthetic'):
        run_dual_sleeve_review(**dict(args, input_path=tmp_path/'outside.json'))
    with pytest.raises(ValueError, match='private_root'):
        run_dual_sleeve_review(**dict(args, synthetic=False))


def test_cli_no_private_input_reports_blocked_without_writes(tmp_path, monkeypatch, capsys):
    script = Path(__file__).resolve().parents[1]/'scripts/current/review_dual_sleeve_risk.py'
    spec = importlib.util.spec_from_file_location('dual_sleeve_cli_test', script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', [str(script)])
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'NOT_CONNECTED'
    assert not list(tmp_path.iterdir())

"""TEST_ONLY source-bound proposal intake; no issuer or economic admission."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import shutil
import subprocess
import types

import pytest

from test_neutral_valuation_proposal import proposal_inputs
from test_joint_capital_cash_path_v2 import inputs as cash_inputs
from value_investment_agent.application.product import neutral_valuation_proposal as subject
from value_investment_agent.application.product.common import sha256_file, encode_json_bytes


ROOT = Path(subject.__file__).resolve().parents[4]


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def case(tmp_path):
    package_path, policy_path = proposal_inputs(tmp_path)
    package = json.loads(package_path.read_bytes())
    anchor = D(package['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'])
    raw = cash_inputs()
    with localcontext() as context:
        context.prec = 48
        factor = anchor / D('400')
        historical = {key: (format(D(value)*factor, 'f') if key not in ('scope', 'currency') else value)
            for key, value in raw['historical'].items()}
    observations, declared = {}, dict(scope=historical['scope'], currency='CNY')
    for field, value in historical.items():
        if field in ('scope', 'currency'):
            continue
        scope = ('consolidated_parent' if field in ('parent_profit', 'nonrecurring') else
            historical['scope'] if field in ('opening_cash', 'opening_distribution_capacity', 'cash_floor') else 'consolidated')
        observations[field] = dict(value=value, unit='CNY', scope=scope)
        declared[field] = dict(**observations[field], source_id='TEST_ONLY-cash',
            field_path=['historical', field], rationale='Synthetic same-scope observation.')
    choice = dict(id='cash', rationale='Explicit ten-year cash hypothesis.',
        countercase='Upstream access and capital needs may differ.', joint_drivers={},
        terminal_policy={}, cost_of_equity={}, scenario_bindings={})
    scenario_nodes = {}
    for name, growth, cost in (('bear', '0', '0.12'), ('base', '0.01', '0.10'), ('bull', '0.02', '0.09')):
        drivers = deepcopy(raw['drivers'])
        for row in drivers['years']:
            row['revenue_growth'] = growth
            row['target_payout_ratio'] = '0.3' if row['year'] == 1 else '0.8'
        choice['joint_drivers'][name] = drivers
        choice['terminal_policy'][name] = deepcopy(raw['terminal_policy'])
        choice['cost_of_equity'][name] = cost
        choice['scenario_bindings'][name] = dict(source_id='TEST_ONLY-cash', field_path=['scenarios', name])
        scenario_nodes[name] = dict(drivers=drivers, terminal_policy=choice['terminal_policy'][name], cost_of_equity=cost)
    observation_path = tmp_path/'runtime/observations.json'
    save(observation_path, dict(historical=observations, scenarios=scenario_nodes))
    now = datetime.now(timezone.utc).isoformat()
    policy = dict(schema_version=subject.JOINT_CASH_SCHEMA, action='no_order', symbol=package['symbol'],
        source_package_sha256=sha256_file(package_path), generated_at=now,
        assumption_scope='RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST',
        profit_anchor_field='ttm_ex_nonrecurring_parent_profit_cny', profit_basis='TEST_ONLY historical proxy',
        rationale_bindings=[dict(id='TEST_ONLY-cash', path='runtime/observations.json',
            sha256=sha256_file(observation_path), available_at=now)],
        joint_historical=declared, choices=[choice], economic_review_items=['Review capital access.'],
        assurance_limits=['Source equality is not economic approval.'])
    save(policy_path, policy)
    for name in subject._JOINT_CASH_IMPLEMENTATIONS:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    return tmp_path, package_path, policy_path, observation_path


def run(case, output='cash-proposal'):
    root, package, policy, _ = case
    return subject.build_neutral_valuation_proposal(root=root, package_path=package,
        package_sha256=sha256_file(package), policy_path=policy, policy_sha256=sha256_file(policy),
        output_path=root/f'runtime/{output}.json')


def update_package(case, change):
    package_path, policy_path = case[1:3]
    package = json.loads(package_path.read_bytes())
    change(package)
    save(package_path, package)
    policy = json.loads(policy_path.read_bytes())
    policy['source_package_sha256'] = sha256_file(package_path)
    save(policy_path, policy)


@pytest.mark.parametrize('legacy', ['absent', 'relocated'])
def test_v2_bound_historical_anchor_does_not_require_legacy_reconciliation(case, monkeypatch, legacy):
    def remove_legacy(package):
        package['source_contract']['fact_anchors'] = [row for row in package['source_contract']['fact_anchors']
            if row.get('field') not in subject._PROFIT_FIELDS]
        summary = package['research_case']['financial_summary']
        summary.pop('historical_profit_reconciliation', None)
        if legacy == 'relocated':
            summary['historical_profit_reconciliation'] = dict(
                report_period=package['point_in_time']['report_period'],
                review_report=dict(path='retired-layout/missing-reconciliation.json', sha256='0'*64))
    update_package(case, remove_legacy)
    def forbidden(*args, **kwargs):
        pytest.fail('v2 must not call the legacy profit-anchor locator')
    monkeypatch.setattr(subject, '_profit_anchor', forbidden)
    result = run(case)
    policy = json.loads(case[2].read_bytes())
    with localcontext() as context:
        context.prec = 48
        expected = D(policy['joint_historical']['parent_profit']['value']) - D(policy['joint_historical']['nonrecurring']['value'])
    assert D(result['choices'][0]['actual_calculation_inputs']['profit_anchor']) == expected


@pytest.mark.parametrize('fault', ['mismatch', 'missing', 'zero', 'negative', 'nan', 'unsupported', 'reported_scope'])
def test_v2_history_must_match_a_positive_case_anchor_with_correct_semantics(case, fault):
    field = 'ttm_ex_nonrecurring_parent_profit_cny'
    def change(package):
        summary = package['research_case']['financial_summary']
        if fault == 'mismatch': summary[field] = str(D(summary[field])+1)
        elif fault == 'missing': summary.pop(field)
        elif fault in ('zero', 'negative', 'nan'):
            summary[field] = {'zero':'0', 'negative':'-1', 'nan':'NaN'}[fault]
        elif fault == 'reported_scope':
            summary['ttm_reported_parent_profit_cny'] = summary[field]
    update_package(case, change)
    policy = json.loads(case[2].read_bytes())
    if fault == 'unsupported': policy['profit_anchor_field'] = 'ordinary_shares'
    elif fault == 'reported_scope': policy['profit_anchor_field'] = 'ttm_reported_parent_profit_cny'
    save(case[2], policy)
    with pytest.raises(ValueError, match='anchor'):
        run(case)
    assert not (case[0]/'runtime/cash-proposal.json').exists()
    assert not (case[0]/'runtime/cash-proposal.md').exists()


def test_actual_annual_retention_and_cash_distributions_reach_dispatcher(case):
    before = [p.read_bytes() for p in case[1:]]
    result = run(case)
    assert before == [p.read_bytes() for p in case[1:]]
    assert result['schema_version'] == result['input_mode'] == subject.JOINT_CASH_SCHEMA
    assert result['cash_funding_status'] == 'PASS'
    assert all(result[k] is False for k in ('assumptions_approved', 'g3_approved',
        'model_validity_approved', 'price_admitted', 'research_date_advanced', 'decision_changed'))
    assert result['normalized_profit'] is result['position_guidance'] is None
    assert {b['path'] for b in result['implementation_bindings']} == set(subject._JOINT_CASH_IMPLEMENTATIONS)
    row = result['choices'][0]
    assert row['valuation']['model_version'] == 'residual-income-equity-path-v2'
    assert row['valuation']['confidence'] == '低'
    for name in ('bear', 'base', 'bull'):
        actual = row['actual_calculation_inputs']['scenarios'][name]
        ledger = row['joint_capital_ledgers'][name]
        arithmetic = row['annual_arithmetic'][name]
        assert 'retention' not in actual
        assert actual['forecast_retentions'] == ledger['forecast_retentions']
        assert len(actual['forecast_roe']) == len(actual['forecast_retentions']) == 10
        assert len(set(actual['forecast_retentions'])) > 1
        for cash, annual in zip(ledger['rows'], arithmetic['forecast_years'], strict=True):
            assert abs(D(cash['distribution'])-D(annual['dividend_assumption_cny'])) < D('.01')
            assert abs(D(cash['profit'])-D(annual['net_income_assumption_cny'])) < D('.01')
        assert abs(D(arithmetic['cash_distribution_crosscheck']['difference_cny'])) < D('.01')
    assert (case[0]/'runtime/cash-proposal.md').is_file()
    with pytest.raises(FileExistsError):
        run(case)


@pytest.mark.parametrize('fault', ['extra_policy', 'missing_history', 'extra_history', 'unit', 'scope',
    'value', 'unbound_history', 'unbound_scenario', 'driver_drift', 'terminal_drift', 'cost_drift',
    'missing_terminal', 'extra_driver', 'extra_year', 'nine_years', 'wrong_year', 'float', 'nan',
    'funding', 'terminal_funding', 'growth', 'cost_range', 'cost_float', 'future', 'future_source',
    'hash', 'implementation', 'duplicate_choice', 'anchor'])
def test_invalid_policy_or_binding_fails_without_outputs(case, fault):
    root, _, path, observations = case
    policy = json.loads(path.read_bytes())
    choice = policy['choices'][0]
    driver = choice['joint_drivers']['base']
    if fault == 'extra_policy': policy['approved'] = True
    elif fault == 'missing_history': policy['joint_historical'].pop('da')
    elif fault == 'extra_history': policy['joint_historical']['symbol'] = '600519'
    elif fault in ('unit', 'scope', 'value'):
        policy['joint_historical']['revenue'][fault] = {'unit':'USD', 'scope':'parent', 'value':'1'}[fault]
    elif fault == 'unbound_history': policy['joint_historical']['revenue'].pop('field_path')
    elif fault == 'unbound_scenario': choice['scenario_bindings']['base']['source_id'] = 'missing'
    elif fault == 'driver_drift': driver['years'][5]['revenue_growth'] = '0.04'
    elif fault == 'terminal_drift': choice['terminal_policy']['base']['rationale'] = 'Resealed policy only.'
    elif fault == 'cost_drift': choice['cost_of_equity']['base'] = '0.11'
    elif fault == 'missing_terminal': choice['terminal_policy']['base'].pop('reserve_ratio')
    elif fault == 'extra_driver': driver['retention'] = '0.1'
    elif fault == 'extra_year': driver['years'][0]['extra'] = '0'
    elif fault == 'nine_years': driver['years'].pop()
    elif fault == 'wrong_year': driver['years'][0]['year'] = True
    elif fault == 'float': driver['new_operating_return'] = 0.08
    elif fault == 'nan': driver['new_operating_return'] = 'NaN'
    elif fault == 'funding': driver['years'][0]['commitment_cash_cny'] = '1000000000000000000000000'
    elif fault == 'terminal_funding': choice['terminal_policy']['base']['commitment_cash_cny'] = '1000000000000000000000000'
    elif fault == 'growth': choice['terminal_policy']['base']['target_payout_ratio'] = '0'
    elif fault == 'cost_range': choice['cost_of_equity']['base'] = '0.9'
    elif fault == 'cost_float': choice['cost_of_equity']['base'] = 0.1
    elif fault == 'future': policy['generated_at'] = '2099-01-01T00:00:00+00:00'
    elif fault == 'future_source': policy['rationale_bindings'][0]['available_at'] = '2099-01-01T00:00:00+00:00'
    elif fault == 'hash': observations.write_bytes(observations.read_bytes()+b' ')
    elif fault == 'implementation':
        target = root/subject._JOINT_CASH_IMPLEMENTATIONS[0]
        target.write_bytes(target.read_bytes()+b'\n')
    elif fault == 'duplicate_choice': policy['choices'].append(deepcopy(choice))
    elif fault == 'anchor':
        policy['joint_historical']['parent_profit']['value'] = '1'
        data = json.loads(observations.read_bytes())
        data['historical']['parent_profit']['value'] = '1'
        save(observations, data)
        policy['rationale_bindings'][0]['sha256'] = sha256_file(observations)
    save(path, policy)
    with pytest.raises(ValueError):
        run(case)
    assert not (root/'runtime/cash-proposal.json').exists()
    assert not (root/'runtime/cash-proposal.md').exists()


def test_growth_equal_to_required_return_is_rejected(case):
    _, _, path, _ = case
    policy = json.loads(path.read_bytes())
    # Derive the exact compiler growth so equality cannot pass a rounded test.
    choice = policy['choices'][0]
    from value_investment_agent.domain.valuation.joint_capital_cash_path_v2 import compile_joint_capital_cash_path
    historical = {k:(v['value'] if isinstance(v, dict) else v) for k,v in policy['joint_historical'].items()}
    package = json.loads(case[1].read_bytes())
    ledger = compile_joint_capital_cash_path(start_book=package['facts']['operating_inputs']['start_book_equity'],
        historical=historical, drivers=choice['joint_drivers']['base'], terminal_policy=choice['terminal_policy']['base'])
    choice['cost_of_equity']['base'] = format(ledger['terminal_growth'], 'f')
    save(path, policy)
    with pytest.raises(ValueError, match='exceed terminal growth'):
        run(case)


@pytest.mark.parametrize('target', ['observation', 'implementation'])
def test_final_recheck_rejects_drift_during_shared_valuation(case, monkeypatch, target):
    from value_investment_agent.valuation_models.residual_income_path_v2 import (
        ResidualIncomeContractDispatcher, ResidualIncomePathScenarioInputs,
    )
    original = ResidualIncomeContractDispatcher.value
    changed = False
    def value(self, facts, research_case):
        nonlocal changed
        result = original(self, facts, research_case)
        if not changed and any(isinstance(s, ResidualIncomePathScenarioInputs) for s in facts.scenario_inputs.values()):
            path = case[3] if target == 'observation' else case[0]/subject._JOINT_CASH_IMPLEMENTATIONS[0]
            path.write_bytes(path.read_bytes()+b' ')
            changed = True
        return result
    monkeypatch.setattr(ResidualIncomeContractDispatcher, 'value', value)
    with pytest.raises(ValueError, match='source changed during calculation'):
        run(case)
    assert not (case[0]/'runtime/cash-proposal.json').exists()


def test_inconsistent_compiler_retention_cannot_be_hidden_by_ri(case, monkeypatch):
    from value_investment_agent.domain.valuation import joint_capital_cash_path_v2 as domain
    original = domain.compile_joint_capital_cash_path
    def compile_path(**kwargs):
        ledger = original(**kwargs)
        ledger['forecast_retentions'] = (D('0.1'),)*10
        return ledger
    monkeypatch.setattr(domain, 'compile_joint_capital_cash_path', compile_path)
    with pytest.raises(ValueError, match='annual RI and cash path differ'):
        run(case)
    assert not (case[0]/'runtime/cash-proposal.json').exists()


@pytest.mark.parametrize('year', [True, 1.0])
def test_source_year_type_cannot_match_policy_integer_by_python_equality(case, year):
    _, _, path, observations = case
    source = json.loads(observations.read_bytes())
    source['scenarios']['base']['drivers']['years'][0]['year'] = year
    save(observations, source)
    policy = json.loads(path.read_bytes())
    policy['rationale_bindings'][0]['sha256'] = sha256_file(observations)
    save(path, policy)
    with pytest.raises(ValueError, match='source-bound drivers/terminal/cost'):
        run(case)


def test_dated_values_crosscheck_distributions_at_origin(case):
    _, package_path, policy_path, _ = case
    package, policy = (json.loads(p.read_bytes()) for p in (package_path, policy_path))
    package['facts']['valuation_timing'] = dict(basis_at='2026-06-30T23:59:59+08:00',
        valuation_at='2026-09-22T16:00:00+08:00', evidence_refs=[dict(id='facts')])
    package['dependencies']['model_version'] = 'residual-income-equity-shared-dated-v2'
    save(package_path, package)
    policy['source_package_sha256'] = sha256_file(package_path)
    save(policy_path, policy)
    result = run(case)
    for arithmetic in result['choices'][0]['annual_arithmetic'].values():
        assert D(arithmetic['conditional_equity_value_cny']) > D(arithmetic['basis_origin_equity_value_cny'])
        assert abs(D(arithmetic['cash_distribution_crosscheck']['difference_cny'])) < D('.01')


@pytest.mark.parametrize('joint', [False, True])
def test_legacy_json_and_report_bytes_match_head_implementation(tmp_path, monkeypatch, joint):
    package, policy = proposal_inputs(tmp_path)
    if joint:
        from test_joint_capital_path import policy_inputs
        policy_inputs(tmp_path, package, policy)
    source = subprocess.run(['git', '-C', str(ROOT), 'show',
        'HEAD:src/value_investment_agent/application/product/neutral_valuation_proposal.py'],
        check=True, capture_output=True).stdout.decode('utf-8')
    predecessor = types.ModuleType(subject.__package__ + '._test_only_predecessor')
    predecessor.__file__ = subject.__file__
    predecessor.__package__ = subject.__package__
    exec(compile(source, subject.__file__, 'exec'), predecessor.__dict__)
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
            return value if tz is None else value.astimezone(tz)
    monkeypatch.setattr(subject, 'datetime', FixedClock)
    predecessor.datetime = FixedClock
    kwargs = dict(root=tmp_path, package_path=package, package_sha256=sha256_file(package),
        policy_path=policy, policy_sha256=sha256_file(policy))
    old = predecessor.build_neutral_valuation_proposal(**kwargs, output_path=tmp_path/'runtime/old.json')
    new = subject.build_neutral_valuation_proposal(**kwargs, output_path=tmp_path/'runtime/new.json')
    assert encode_json_bytes(old) == encode_json_bytes(new)
    assert (tmp_path/'runtime/old.json').read_bytes() == (tmp_path/'runtime/new.json').read_bytes()
    assert (tmp_path/'runtime/old.md').read_bytes() == (tmp_path/'runtime/new.md').read_bytes()

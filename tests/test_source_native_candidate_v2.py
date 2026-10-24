"""Versioned native review intake; no real approvals, registries or schedules."""
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import json
import os
from pathlib import Path
import shutil

import pytest

from test_pending_research_candidate import candidate_inputs, run as finite_seed
from value_investment_agent.application.product import source_native_candidate_v2 as native
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.domain.valuation.source_native_cash_v1 import replay_timing_delay_inputs


CODE_ROOT = Path(__file__).resolve().parents[1]
REAL_PACKAGE = 'runtime/public-research/600519-js2-native-input-20261024/compile-20261023T231832356628Z/package.json'


def store(root, path, value):
    target = root/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return dict(path=path, sha256=sha256_file(target))


def install_implementations(root):
    for name in native.IMPLEMENTATIONS:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE_ROOT/name, target)


def test_only_ledger(book, basis):
    """Independent simple cash bookkeeping, not a model or official evidence."""
    plan = dict(horizon=5, ke='.10', explicit_retention='.10', incremental_parent_cash_yield='0',
        TIMING_DELAY=dict(withheld_fraction='.10', withheld_years=[1]),
        known_uncalled_fund_commitment=dict(amount_cny='0'))
    history = dict(unit='CNY', scope='standalone parent, NOT consolidated free cash',
        ttm=dict(cash_end=str(book*10), parent_equity_end=str(book),
        parent_retained_profit_end=str(book)), periods={'FY2025':dict(operating_outflows=str(book*2))},
        known_uncalled_fund_commitment=dict(amount_cny='0'))
    cases = {}
    with localcontext() as ctx:
        ctx.prec = 48
        for name in ('bear', 'base', 'bull'):
            opening, cash, delayed, parent, re = book, book*10, D(0), book, book
            rows = []
            for year in range(1,6):
                profit = book/10
                held = profit/10 if year == 1 else D(0)
                release = delayed if year == 2 else D(0)
                funds = profit-held+release
                appropriation = funds/10
                dividend = profit*D('.9')
                rows.append(dict(year=year, legacy_profit_before_new_cash_cost=str(profit),
                    incremental_parent_cash_income='0', permanent_after_tax_cash_expense='0',
                    profit=str(profit), opening_book=str(opening), opening_parent_cash=str(cash),
                    opening_delayed_asset=str(delayed), newly_withheld=str(held), released=str(release),
                    parent_net_funds=str(funds), assumed_parent_standalone_profit=str(funds),
                    statutory_appropriation=str(appropriation), dividend_planned=str(dividend),
                    dividend_paid=str(dividend), actual_retention='.1', cash_capacity=str(cash+funds-book),
                    retained_profit_capacity=str(re+funds-appropriation), project_cash='0', fund_capital_call='0',
                    fund_asset_at_cost='0', cash_close=str(cash+funds-dividend),
                    delayed_close=str(delayed+held-release), roe=str(profit/opening),
                    book_close=str(opening+profit-dividend), parent_equity_close=str(parent+funds-dividend),
                    parent_retained_profit_close=str(re+funds-appropriation-dividend), cash_bridge_residual='0'))
                opening += profit-dividend
                cash += funds-dividend
                delayed += held-release
                parent += funds-dividend
                re += funds-appropriation-dividend
            cases[name] = dict(branch='TIMING_DELAY', blockers=[], annual_rows=rows,
                cash_floor=str(book), project_budget='0', terminal_appropriation='0', terminal_growth='0',
                terminal_retention='0', terminal_funding_gap='0', terminal_parent_funds=str(profit),
                terminal_assumed_dividend=str(profit), terminal_profit=str(profit), terminal_cash=str(cash),
                terminal_delayed_asset=str(delayed), terminal_book=str(opening), parent_retained_profit_end=str(re),
                terminal_incremental_cash_income='0', terminal_roe=str(profit/opening))
    return dict(action='no_order', financial_basis=basis, plan=plan, history=history,
                cases=dict(TIMING_DELAY=cases))


@pytest.fixture
def synthetic_native(tmp_path, synthetic_pending_candidate_clock):
    # Only obtain a valid TEST_ONLY source-contract template. JS2 values never
    # pass through the finite compiler and all subsequent replay uses native v2.
    package_path, policy, request = candidate_inputs(tmp_path)
    finite_seed(tmp_path, package_path, policy, request)
    package = json.loads((tmp_path/'runtime/pending/package.json').read_bytes())
    assert package['symbol'] == '600887'  # A second company, not a 600519 branch.
    package['name'] = 'TEST_ONLY_SECOND_COMPANY'
    package['facts']['confidence'] = '\u4f4e'
    package['facts']['confidence_evidence'] = None
    book = D(package['facts']['operating_inputs']['start_book_equity'])
    ledger = test_only_ledger(book, package['point_in_time']['valuation_date'])
    ledger_ref = store(tmp_path, 'runtime/TEST_ONLY-cash-ledger.json', ledger)
    source_ref = dict(id='TEST_ONLY-native-cash', **ledger_ref)
    package['sources'].append(dict(id=source_ref['id'], kind='research_artifact',
        local_path=ledger_ref['path'], location=ledger_ref['path'], sha256=ledger_ref['sha256'],
        source_available_at=package['point_in_time']['available_at'],
        availability_basis='TEST_ONLY_FIXED_CLOCK_NOT_HISTORICAL_PIT'))
    package['facts']['evidence_refs'].append(source_ref)
    package['research_case']['evidence_refs'].append(source_ref)
    package['research_case']['financial_summary']['TEST_ONLY_native_economic_review'] = dict(
        scope='CONDITIONAL_RESEARCH_NOT_G3', branch='TIMING_DELAY', source_result_sha256=ledger_ref['sha256'],
        joint_assumptions=ledger['plan'], historical_cash_bridge=ledger['history'])
    scenarios = replay_timing_delay_inputs(plan=ledger['plan'], scenarios=ledger['cases']['TIMING_DELAY'],
        history=ledger['history'], opening_book=book)
    package['facts']['scenario_inputs'] = scenarios
    assumptions, bindings = [], []
    for field in ['cost_of_equity', 'retention', 'terminal_roe', 'terminal_growth',
                  *[f'forecast_roes_{i}' for i in range(5)]]:
        path = field.replace('forecast_roes_', 'forecast_roes.')
        values = {name: row['forecast_roes'][int(field.rsplit('_',1)[1])]
            if field.startswith('forecast_roes_') else row[field] for name,row in scenarios.items()}
        assumptions.append(dict(name=field, unit='ratio', **values, basis='TEST_ONLY_CASH_HYPOTHESIS',
            rationale='TEST_ONLY not an issuer forecast', confidence='low', sensitivity='high',
            evidence_refs=[source_ref]))
        bindings += [dict(assumption_name=field, scenario=name, field_path=path,
            expected_value=value, evidence_refs=[source_ref]) for name,value in values.items()]
    package['assumptions'] = dict(assumptions=assumptions, evidence_refs=[source_ref], blockers=['TEST_ONLY G3 missing'])
    package['assumption_bindings'] = bindings
    package_ref = store(tmp_path, 'runtime/TEST_ONLY-native-package.json', package)
    install_implementations(tmp_path)
    return tmp_path, package_ref, ledger_ref


def prepare(case):
    root, package, ledger = case
    return native.prepare_source_native_candidate(root=root, package_binding=package, ledger_binding=ledger,
        output_dir=root/'runtime/native-v2', now=datetime.now(timezone.utc))


def test_second_company_cold_replay_preserves_inputs_and_existing_packet(synthetic_native, monkeypatch):
    root, package_ref, _ = synthetic_native
    before = (root/package_ref['path']).read_bytes()
    candidate = prepare(synthetic_native)
    assert candidate['schema_version'] == native.SCHEMA
    assert candidate['symbol'] == '600887'
    assert (root/'runtime/native-v2/package.json').read_bytes() == before
    path = root/'runtime/native-v2/candidate.json'
    assert native.verify_source_native_candidate(root=root, path=path, expected_sha256=sha256_file(path)) == candidate
    # Model only the exact dispatcher change requested of Root. No G3/Gate,
    # model, signing or candidate verification is replaced by a permissive stub.
    from value_investment_agent.application.product import pending_research_candidate as frozen
    from value_investment_agent.application.product.research_reviews import prepare_pending_review_intake
    with pytest.raises(ValueError, match='pending candidate admission boundary mismatch'):
        frozen.verify_pending_research_candidate(root=root, path=path, expected_sha256=sha256_file(path))
    monkeypatch.setattr(frozen, 'verify_pending_research_candidate', native.verify_review_candidate)
    intake = prepare_pending_review_intake(root=root, candidate_path=path, candidate_sha256=sha256_file(path))
    assert len(intake['groups']) == 5 and intake['valuation_artifact_sha256']
    assert intake['whole_model_decision'] is None and intake['research_admitted'] is False
    assert candidate['candidate_valuation']['confidence'] == '\u4f4e'
    assert candidate['execution_status'] == 'NO_ACTION'
    assert candidate['primary_registered'] is False


@pytest.mark.parametrize('change', ['cash_missing', 'roe_drift', 'unbound_ledger', 'raw_drift', 'future', 'narrative', 'future_ledger'])
def test_source_input_rejections(synthetic_native, change):
    root, package_ref, ledger_ref = synthetic_native
    package = json.loads((root/package_ref['path']).read_bytes())
    if change == 'cash_missing':
        ledger = json.loads((root/ledger_ref['path']).read_bytes())
        del ledger['cases']['TIMING_DELAY']['base']['annual_rows'][0]['fund_capital_call']
        ledger_ref = store(root, ledger_ref['path'], ledger)
        for item in package['sources']:
            if item['id'] == 'TEST_ONLY-native-cash': item['sha256'] = ledger_ref['sha256']
        for ref in package['facts']['evidence_refs']:
            if ref['id'] == 'TEST_ONLY-native-cash': ref['sha256'] = ledger_ref['sha256']
        package['research_case']['financial_summary']['TEST_ONLY_native_economic_review']['source_result_sha256'] = ledger_ref['sha256']
    elif change == 'future_ledger':
        ledger = json.loads((root/ledger_ref['path']).read_bytes())
        ledger['generated_at'] = '2099-01-01T00:00:00+00:00'
        ledger_ref = store(root, ledger_ref['path'], ledger)
    elif change == 'roe_drift': package['facts']['scenario_inputs']['base']['forecast_roes'][0] = '.99'
    elif change == 'unbound_ledger': package['sources'] = [s for s in package['sources'] if s['id'] != 'TEST_ONLY-native-cash']
    elif change == 'future': package['point_in_time']['computed_at'] = '2099-01-01T00:00:00+00:00'
    elif change == 'narrative': package['research_case']['financial_summary']['TEST_ONLY_native_economic_review']['joint_assumptions']['ke'] = '.99'
    else: (root/ledger_ref['path']).write_bytes(b'TEST_ONLY drift')
    package_ref = store(root, package_ref['path'], package)
    with pytest.raises((ValueError, KeyError)):
        native.prepare_source_native_candidate(root=root, package_binding=package_ref, ledger_binding=ledger_ref,
            output_dir=root/'runtime/rejected-native')
    assert not (root/'runtime/rejected-native/candidate.json').exists()


@pytest.mark.parametrize('change', ['authority', 'valuation', 'research_date', 'missing_source',
    'implementation', 'workbench', 'unknown_schema'])
def test_resealed_candidate_cannot_change_consumption_or_authority(synthetic_native, change):
    root, _, _ = synthetic_native
    candidate = prepare(synthetic_native)
    path = root/'runtime/native-v2/candidate.json'
    if change == 'authority': candidate['g3_approved'] = True
    elif change == 'valuation': candidate['candidate_valuation']['base_value'] = '1'
    elif change == 'research_date': candidate['candidate_research_as_of'] = '2026-06-30'
    elif change == 'missing_source': candidate['source_bindings'].pop()
    elif change == 'implementation': candidate['implementation_bindings'][0]['sha256'] = '0'*64
    elif change == 'unknown_schema': candidate['schema_version'] = 'source-native-pending-research-candidate-v999'
    else:
        work = root/'runtime/native-v2/workbench.json'
        payload = json.loads(work.read_bytes())
        payload['valuation']['base_value'] = '1'
        work.write_text(json.dumps(payload), encoding='utf-8')
        for ref in candidate['source_bindings']:
            if ref['path'] == work.relative_to(root).as_posix(): ref['sha256'] = sha256_file(work)
    path.write_text(json.dumps(candidate), encoding='utf-8')
    with pytest.raises(ValueError):
        native.verify_review_candidate(root=root, path=path, expected_sha256=sha256_file(path))


def test_legacy_dispatch_retains_original_verifier(synthetic_native):
    root, _, _ = synthetic_native
    path = root/'runtime/pending/candidate.json'
    args = dict(root=root, path=path, expected_sha256=sha256_file(path))
    assert native.verify_review_candidate(**args) == native._verify_frozen_v1(**args)


def test_cash_replay_does_not_use_sealed_expected_prices(synthetic_native):
    root, package_ref, ledger_ref = synthetic_native
    package = json.loads((root/package_ref['path']).read_bytes())
    ledger = json.loads((root/ledger_ref['path']).read_bytes())
    expected = replay_timing_delay_inputs(plan=ledger['plan'], scenarios=ledger['cases']['TIMING_DELAY'],
        history=ledger['history'], opening_book=package['facts']['operating_inputs']['start_book_equity'])
    for case in ledger['cases']['TIMING_DELAY'].values():
        case['value_basis_per_share'] = '999999999999'
        case['scenario_inputs'] = dict(expected_numbers='NOT_CONSUMED')
        case['existing_RI_output'] = dict(expected_numbers='NOT_CONSUMED')
    actual = replay_timing_delay_inputs(plan=ledger['plan'], scenarios=ledger['cases']['TIMING_DELAY'],
        history=ledger['history'], opening_book=package['facts']['operating_inputs']['start_book_equity'])
    assert actual == expected


@pytest.mark.parametrize('field,value', [('unit', 'CNY10000'), ('scope', 'consolidated')])
def test_cash_history_scope_cannot_be_silently_reinterpreted(synthetic_native, field, value):
    root, package_ref, ledger_ref = synthetic_native
    package = json.loads((root/package_ref['path']).read_bytes())
    ledger = json.loads((root/ledger_ref['path']).read_bytes())
    ledger['history'][field] = value
    with pytest.raises(ValueError, match='unit/ownership scope mismatch'):
        replay_timing_delay_inputs(plan=ledger['plan'], scenarios=ledger['cases']['TIMING_DELAY'],
            history=ledger['history'], opening_book=package['facts']['operating_inputs']['start_book_equity'])


@pytest.mark.parametrize('role', ['package', 'ledger', 'catalog_source'])
@pytest.mark.parametrize('stage', ['serialize', 'model_context'])
def test_direct_cold_replay_rejects_last_stage_source_drift(synthetic_native, monkeypatch, role, stage):
    root, package_ref, ledger_ref = synthetic_native
    package = json.loads((root/package_ref['path']).read_bytes())
    path = root/(package_ref['path'] if role == 'package' else ledger_ref['path']
        if role == 'ledger' else next(source['local_path'] for source in package['sources']
            if source.get('local_path') and source['local_path'] != ledger_ref['path']))
    function = '_serialize_outcome' if stage == 'serialize' else 'build_research_review_model_context'
    original = getattr(native, function)
    calls = []
    def change_after_native_calculation(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(native, function, change_after_native_calculation)
    with pytest.raises(ValueError, match='hash mismatch|source changed during replay'):
        native.replay_source_native_inputs(root=root, package_binding=package_ref,
            ledger_binding=ledger_ref, now=datetime.now(timezone.utc))
    assert calls == [True]


def test_direct_cold_replay_returns_original_receipt_and_closure_identity(synthetic_native):
    root, package_ref, ledger_ref = synthetic_native
    replay = native.replay_source_native_inputs(root=root, package_binding=package_ref,
        ledger_binding=ledger_ref, now=datetime.now(timezone.utc))
    assert replay['workbench']['research_receipt']['input_sha256']['valuation_package'] == package_ref['sha256']
    assert [ref for ref in replay['source_bindings'] if ref['path'] == package_ref['path']] == [package_ref]
    assert [ref for ref in replay['source_bindings'] if ref['path'] == ledger_ref['path']] == [ledger_ref]


def test_real_js2_native_candidate_cold_replay(tmp_path, monkeypatch):
    source_root = os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    if not source_root:
        pytest.skip('Explicit public retained source root required; no network or private lookup')
    source = Path(source_root)
    original = source/REAL_PACKAGE
    package = json.loads(original.read_bytes())
    # Copy exact bound public bytes into an isolated fixture root; no restamping.
    paths = {REAL_PACKAGE, *[row['local_path'] for row in package['sources']]}
    for name in paths:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
        assert sha256_file(source/name) == sha256_file(target)
    install_implementations(tmp_path)
    sealed_receipt = json.loads((original.parent/'receipt.json').read_bytes())
    package_ref = sealed_receipt['package_binding']
    assert package_ref == dict(path=REAL_PACKAGE, sha256='7f447dbb3f9958e687c88c454f17525e9f8d5d22bcbefa99fcd287a0ac4f349b')
    assert sha256_file(original) == package_ref['sha256']
    ledger = next(row for row in package['sources'] if row['id'] == 'js2-sealed-result')
    ledger_ref = dict(path=ledger['local_path'], sha256=ledger['sha256'])
    result = prepare((tmp_path, package_ref, ledger_ref))
    assert result['model_context']['input_descriptor_sha256'] == sealed_receipt['input_descriptor_sha256']
    assert result['candidate_valuation']['base_value'] == '929.145098627591685335814533390435112363613340182'
    assert result['candidate_valuation']['valuation_date'] == '2026-06-30'
    assert result['candidate_research_as_of'] == package['point_in_time']['research_as_of']
    assert result['execution_status'] == 'NO_ACTION' and not result['research_admitted']
    assert (tmp_path/'runtime/native-v2/package.json').read_bytes() == original.read_bytes()
    packet = json.loads((tmp_path/'runtime/native-v2/consumed-review.json').read_bytes())
    assert packet['input_descriptor_sha256'] == result['model_context']['input_descriptor_sha256']
    assert len(result['review_groups']) == 5
    from value_investment_agent.application.product import pending_research_candidate as frozen
    from value_investment_agent.application.product.research_review_wizard import preview_pending_review_response
    monkeypatch.setattr(frozen, 'verify_pending_research_candidate', native.verify_review_candidate)
    path = tmp_path/'runtime/native-v2/candidate.json'
    preview = preview_pending_review_response(root=tmp_path, candidate_path=path, candidate_sha256=sha256_file(path))
    assert preview['status'] == 'READ_ONLY_PREVIEW_NOT_APPROVED'
    assert len(preview['review_questions']) == 5
    assert preview['draft']['whole_model_approval'] is None
    materials = native.project_source_native_review_materials(root=tmp_path,
        candidate_binding=dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256_file(path)))
    assert materials['point_in_time'] == package['point_in_time']
    assert materials['scenarios']['base']['per_share_value'] == result['candidate_valuation']['base_value']
    assert len(materials['scenarios']['base']['cash_ledger']) == 5
    assert materials['primary_registered'] is False and materials['research_admitted'] is False


# Helper is not a pytest test; it creates clearly labelled synthetic inputs.
test_only_ledger.__test__ = False

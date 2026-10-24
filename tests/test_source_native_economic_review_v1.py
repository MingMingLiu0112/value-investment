"""Economic read model: actual kernels, TEST_ONLY variants, opt-in retained JS2."""
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import json
import os
from pathlib import Path
import shutil

import pytest

from test_source_native_candidate_v2 import synthetic_native, prepare, store
from value_investment_agent.application.product import source_native_economic_review_v1 as review
from value_investment_agent.application.product.common import sha256_file

CODE = Path(__file__).resolve().parents[1]


def implementations(root):
    for name in review.IMPLEMENTATIONS:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE/name, target)


def binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


@pytest.fixture
def sample(synthetic_native):
    root, _, _ = synthetic_native
    implementations(root)
    candidate = prepare(synthetic_native)
    return root, binding(root, root/'runtime/native-v2/candidate.json'), candidate


def snapshot(root):
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in root.rglob('*') if p.is_file()}


def test_second_company_uses_kernels_and_never_creates_approval(sample):
    root, ref, candidate = sample
    before = snapshot(root)
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref)
    assert result['symbol'] == '600887'
    assert result['confidence'] == 'LOW'
    assert result['g3_status'] == 'NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE'
    assert result['current_g3_status'] == 'NOT_QUERIED'
    assert result['share_basis']['current_shares'] is None
    assert result['share_basis']['corporate_action_comparability'] == 'NOT_ASSESSED'
    assert len(result['five_groups']) == 5
    joint = result['joint_adverse_cash']
    assert joint['status'] == 'UNSUPPORTED' and joint['reason']
    assert joint['rows'] == []
    assert set(joint) == {'status', 'reason', 'rows', 'scope', 'action'}
    assert all(group['approval_status'] == 'PENDING_NOT_APPROVED' for group in result['five_groups'])
    for row in result['scenarios']:
        assert row['original']['candidate_per_historical_share_cny'] == candidate['candidate_valuation'][row['scenario']+'_value']
        assert row['original']['matches_candidate_at_recorded_precision'] is True
        assert row['ke_plus_200bp']['status'] == 'CONDITIONAL_KERNEL_SENSITIVITY'
        assert D(row['ke_plus_200bp']['challenged_ke']) - D(row['ke_plus_200bp']['original_ke']) == D('.02')
        assert D(row['ke_plus_200bp']['result']['per_historical_share_cny']) < D(row['original']['per_historical_share_cny'])
        assert row['ke_plus_200bp']['alternative_candidate_verified'] is False
        assert len(row['annual_cash_rows']) == 5
        assert row['first_year_boundary']['status'] == 'CASH_ONLY_FIRST_YEAR_IDENTITY'
        assert row['first_year_boundary']['boundary_within_zero_one'] is False
    for key in ('approval_changed', 'research_admitted', 'price_admitted', 'formal_eligibility',
                'strategy_approved', 'canonical_written', 'registered_current_case_changed'):
        assert result[key] is False
    assert result['normalized_parent_profit_cny'] is None
    assert result['action'] == 'no_order'
    json.dumps(result, allow_nan=False)
    assert snapshot(root) == before


@pytest.mark.parametrize('damage', ['candidate', 'original_package', 'cash_ledger', 'implementation'])
def test_drift_of_any_consumed_component_rejected(sample, damage):
    root, ref, candidate = sample
    path = dict(candidate=ref['path'], original_package=candidate['source_package_binding']['path'],
        cash_ledger=candidate['native_cash_ledger_binding']['path'], implementation=review.IMPLEMENTATIONS[0])[damage]
    target = root/path
    target.write_bytes(target.read_bytes()+b'\nTEST_ONLY_DRIFT')
    with pytest.raises(ValueError): review.build_source_native_economic_review(root=root, candidate_binding=ref)


@pytest.mark.parametrize('damage', ['original', 'document'])
def test_final_read_catches_source_drift_after_projection(sample, monkeypatch, damage):
    root, ref, candidate = sample
    document = store(root, 'docs/TEST_ONLY-economic.md', dict(note='EDITORIAL_ONLY'))
    compute = review._first_year_boundary
    changed = False
    def after_computation(plan, case):
        nonlocal changed
        result = compute(plan, case)
        if not changed:
            path = root/(candidate['source_package_binding']['path'] if damage == 'original' else document['path'])
            path.write_bytes(path.read_bytes()+b'\nTEST_ONLY_FINAL_DRIFT')
            changed = True
        return result
    # Pure projection instrumentation only; kernels/validators run unchanged.
    monkeypatch.setattr(review, '_first_year_boundary', after_computation)
    with pytest.raises(ValueError):
        review.build_source_native_economic_review(root=root, candidate_binding=ref, review_document_binding=document)


def test_editorial_numbers_do_not_drive_arithmetic(sample):
    root, ref, _ = sample
    doc1 = store(root, 'docs/TEST_ONLY-first.md', dict(value='999999999'))
    doc2 = store(root, 'docs/TEST_ONLY-second.md', dict(value='-888888'))
    one = review.build_source_native_economic_review(root=root, candidate_binding=ref, review_document_binding=doc1)
    two = review.build_source_native_economic_review(root=root, candidate_binding=ref, review_document_binding=doc2)
    assert one['scenarios'] == two['scenarios']
    assert one['editorial_review']['binding'] != two['editorial_review']['binding']


def test_unusable_model_or_schema_does_not_fall_back_to_valuation(sample):
    root, ref, _ = sample
    old = root/'runtime/pending/candidate.json'
    result = review.build_source_native_economic_review(root=root, candidate_binding=binding(root, old))
    assert result['status'] == 'NOT_APPLICABLE' and result['scenarios'] == []
    path = root/'runtime/TEST_ONLY-unknown.json'
    path.write_text(json.dumps(dict(schema_version='source-native-pending-research-candidate-v999')), encoding='utf-8')
    with pytest.raises(ValueError, match='Unsupported'):
        review.build_source_native_economic_review(root=root, candidate_binding=binding(root, path))
    for now in (datetime.now(), datetime(2020, 1, 1, tzinfo=timezone.utc)):
        with pytest.raises(ValueError): review.build_source_native_economic_review(root=root, candidate_binding=ref, now=now)


@pytest.mark.parametrize('stage', ['valuation', 'cash'])
def test_ke_challenge_kernel_rejection_is_explicit_unsupported(sample, monkeypatch, stage):
    root, ref, _ = sample
    kernel = review._shared_scenario_calculation
    def rejects_only_challenge(facts, scenario):
        if scenario.cost_of_equity != facts.scenario_inputs['base'].cost_of_equity:
            raise ValueError('TEST_ONLY unsupported challenge')
        return kernel(facts, scenario)
    # Failure injection, never a fabricated positive or bypassed source validator.
    if stage == 'valuation':
        monkeypatch.setattr(review, '_shared_scenario_calculation', rejects_only_challenge)
    else:
        cash_kernel = review.replay_timing_delay_inputs
        def cash_challenge(**kwargs):
            if D(kwargs['plan']['ke']) != D('.10'):
                raise ValueError('TEST_ONLY unsupported cash challenge')
            return cash_kernel(**kwargs)
        monkeypatch.setattr(review, 'replay_timing_delay_inputs', cash_challenge)
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref)
    assert all(row['ke_plus_200bp']['status'] == 'UNSUPPORTED' for row in result['scenarios'])
    assert all(row['ke_plus_200bp']['alternative_candidate_verified'] is False for row in result['scenarios'])


def test_saved_report_prices_are_not_copied(synthetic_native):
    root, package_ref, ledger_ref = synthetic_native
    ledger = json.loads((root/ledger_ref['path']).read_bytes())
    old_sha = ledger_ref['sha256']
    for case in ledger['cases']['TIMING_DELAY'].values():
        case.update(existing_RI_output=dict(conditional_equity_value_cny='99999999999999'),
            terminal_DDM_PV_fraction='0.123456', value_basis_per_share='999999999')
    ledger_ref = store(root, ledger_ref['path'], ledger)
    package = json.loads((root/package_ref['path']).read_bytes())
    def replace_sha(value):
        if isinstance(value, dict): return {k:replace_sha(v) for k,v in value.items()}
        if isinstance(value, list): return [replace_sha(v) for v in value]
        return ledger_ref['sha256'] if value == old_sha else value
    package_ref = store(root, package_ref['path'], replace_sha(package))
    implementations(root)
    candidate = prepare((root, package_ref, ledger_ref))
    result = review.build_source_native_economic_review(root=root,
        candidate_binding=binding(root, root/'runtime/native-v2/candidate.json'))
    for row in result['scenarios']:
        assert row['original']['candidate_per_historical_share_cny'] == candidate['candidate_valuation'][row['scenario']+'_value']
        assert D(row['original']['ddm_terminal_fraction']) != D('0.123456')


@pytest.fixture
def public_js2(tmp_path_factory):
    source_root = os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    if not source_root:
        pytest.skip('Explicit retained public root required; no network/private discovery')
    source = Path(source_root)
    tmp_path = tmp_path_factory.mktemp('js2')
    candidate_name = 'runtime/source-native-pending/3bb7bfe05c3f4c7d9a52d34b07588087/candidate.json'
    candidate = json.loads((source/candidate_name).read_bytes())
    assert sha256_file(source/candidate_name) == 'bfba1fb08f316cd4791e2f8d36490a86345e969d1f2c97663fb7a1e42aa912d8'
    for ref in [dict(path=candidate_name, sha256=sha256_file(source/candidate_name)), *candidate['source_bindings']]:
        target = tmp_path/ref['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/ref['path'], target)
        assert sha256_file(target) == ref['sha256']
    implementations(tmp_path)
    spec = tmp_path/review.JOINT_SOURCE_SPEC
    spec.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CODE/review.JOINT_SOURCE_SPEC, spec)
    doc = tmp_path/'docs/current/600519-native-economic-review-20261024.md'
    doc.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CODE/'docs/current/600519-native-economic-review-20261024.md', doc)
    return tmp_path, binding(tmp_path, tmp_path/candidate_name), binding(tmp_path, doc)


def test_real_js2_actual_inputs_and_independent_checked_quantities(public_js2):
    root, ref, document = public_js2
    before = snapshot(root)
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref,
        review_document_binding=document)
    base = next(row for row in result['scenarios'] if row['scenario'] == 'base')
    assert result['symbol'] == '600519'
    assert result['share_basis']['ordinary_shares'] == '1250081601'
    assert result['share_basis']['financial_basis'] == '2026-06-30'
    assert result['point_in_time']['research_as_of'] == '2026-10-24'
    candidate = json.loads((root/ref['path']).read_bytes())
    ledger = json.loads((root/candidate['native_cash_ledger_binding']['path']).read_bytes())
    case = ledger['cases']['TIMING_DELAY']['base']
    with localcontext() as context:
        context.prec = 48
        # Independent test-only cash-flow arithmetic, not report-value bands or
        # another production valuation engine. No saved existing_RI_output used.
        cost, shares = D(ledger['plan']['ke']), D(result['share_basis']['ordinary_shares'])
        explicit = sum((D(row['dividend_paid'])/(1+cost)**row['year'] for row in case['annual_rows']), D(0))
        terminal = D(case['terminal_assumed_dividend'])/cost/(1+cost)**len(case['annual_rows'])
        assert abs(D(base['original']['per_historical_share_cny'])-(explicit+terminal)/shares) < D('1E-30')
        assert abs(D(base['original']['per_historical_share_cny'])-D(candidate['candidate_valuation']['base_value'])) < D('1E-30')
        assert abs(D(base['original']['ddm_terminal_fraction'])-terminal/(explicit+terminal)) < D('1E-40')
        terminal_ri = (D(case['terminal_profit'])-cost*D(case['terminal_book']))/cost/(1+cost)**len(case['annual_rows'])
        assert abs(D(base['original']['ri_terminal_fraction'])-terminal_ri/(explicit+terminal)) < D('1E-40')
        stressed = cost+D('.02')
        challenged_pv = sum((D(row['dividend_paid'])/(1+stressed)**row['year'] for row in case['annual_rows']), D(0))
        challenged_pv += D(case['terminal_assumed_dividend'])/stressed/(1+stressed)**len(case['annual_rows'])
        assert abs(D(base['ke_plus_200bp']['result']['per_historical_share_cny'])-challenged_pv/shares) < D('1E-30')
        boundary = base['first_year_boundary']
        first = case['annual_rows'][0]
        floor = D(case['cash_floor'])
        assert abs(D(boundary['original_cash_above_floor_cny'])-(D(first['cash_close'])-floor)) < D('1E-30')
        cash_at_boundary = (D(first['opening_parent_cash'])
            +(D(ledger['plan']['explicit_retention'])-D(boundary['cash_only_delay_boundary_fraction']))*D(first['profit'])
            -D(first['project_cash'])-D(first['fund_capital_call']))
        assert abs(cash_at_boundary-floor) < D('1E-30')
    assert all(item['status'] == 'UNSUPPORTED' for item in result['unsupported_challenges'])
    persistent = next(item for item in result['unsupported_challenges']
                      if item['id'] == 'PERSISTENT_UPSTREAM_RESTRICTION')
    assert '降低分配可缓解有限期现金约束' in persistent['reason']
    assert '当前模型不输出此分支估值' in persistent['reason']
    assert '不按零价值' in persistent['reason']
    assert set(persistent) == {'id', 'status', 'reason'}
    assert result['normalized_parent_profit_cny'] is None
    assert result['g3_status'] == 'NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE'
    joint = result['joint_adverse_cash']
    assert joint['status'] == 'INHERITED_PAYOUT_INFEASIBLE', joint
    assert joint['scope'] == review.JOINT_SCOPE and joint['action'] == 'no_order'
    assert joint['first_cash_failure_year'] == joint['first_policy_failure_year'] == 5
    assert joint['first_retained_profit_failure_year'] is None
    assert len(joint['rows']) == 5
    assert joint['rows'][-1]['cash_constraint_failed'] is True
    assert joint['rows'][-1]['retained_constraint_failed'] is False
    assert D(joint['profit_anchor']) == D('81367067677.44')
    assert all(isinstance(row['P'], str) for row in joint['rows'])
    assert not any('valuation' in key or 'approved' in key for key in joint)
    json.dumps(result)
    assert snapshot(root) == before
    print(json.dumps(dict(schema_version=result['schema_version'], candidate_binding=ref,
        confidence=result['confidence'], g3_status=result['g3_status'],
        historical_shares=result['share_basis'], first_year_boundary=boundary,
        ddm_terminal_fraction=base['original']['ddm_terminal_fraction'],
        ri_terminal_fraction=base['original']['ri_terminal_fraction'],
        ke_plus_200bp_value=base['ke_plus_200bp']['result']['per_historical_share_cny'],
        action=result['action']), ensure_ascii=True))


@pytest.mark.parametrize('change', [
    'id', 'hash', 'url', 'period', 'published', 'future_available',
    'reviewed', 'amount', 'anchor', 'duplicate_catalog',
])
def test_joint_cold_evidence_mismatch_has_no_numeric_projection(public_js2, change):
    """TEST_ONLY mutations of copied real inputs, not newly authorized candidates."""
    root, ref, _ = public_js2
    candidate = json.loads((root/ref['path']).read_bytes())
    package = json.loads((root/candidate['source_package_binding']['path']).read_bytes())
    ledger = json.loads((root/candidate['native_cash_ledger_binding']['path']).read_bytes())
    summary = package['research_case']['financial_summary']
    row = summary['historical_profit_reconciliation']['source_rows'][0]
    source = next(item for item in package['sources'] if item['id'] == row['source_id'])
    if change == 'id': row['source_id'] = 'cninfo:wrong'
    elif change == 'hash': row['sha256'] = '0'*64
    elif change == 'url': row['source_url'] += '?other=1'
    elif change == 'period': row['period'] = 'FY2024'
    elif change == 'published': source['published_at'] = '2026-04-18T00:00:00+08:00'
    elif change == 'future_available': source['source_available_at'] = '2099-01-01T00:00:00+00:00'
    elif change == 'reviewed': row['reviewed_at'] = '2099-01-01T00:00:00+00:00'
    elif change == 'amount': row['ex_nonrecurring_profit_cny'] = '1'
    elif change == 'anchor': summary['ttm_ex_nonrecurring_parent_profit_cny'] = '1'
    elif change == 'duplicate_catalog': package['sources'].append(dict(source))
    before = snapshot(root)
    result = review._joint_adverse_review(root, package, ledger, datetime.now(timezone.utc), [])
    assert result['status'] == 'UNSUPPORTED' and result['reason'].startswith('Joint diagnostic failed closed:')
    assert result['rows'] == []
    assert set(result) == {'status', 'reason', 'rows', 'scope', 'action'}
    assert snapshot(root) == before


def test_optional_cold_extraction_failure_preserves_parent_valuation(public_js2, monkeypatch):
    root, ref, _ = public_js2
    def unavailable(**kwargs):
        raise ValueError('TEST_ONLY unreadable official statement')
    monkeypatch.setattr(review, 'research_from_retained_sources', unavailable)
    before = snapshot(root)
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref)
    candidate = json.loads((root/ref['path']).read_bytes())
    assert result['joint_adverse_cash']['status'] == 'UNSUPPORTED'
    assert result['joint_adverse_cash']['rows'] == []
    assert 'TEST_ONLY unreadable' in result['joint_adverse_cash']['reason']
    assert result['research_admitted'] is result['price_admitted'] is result['approval_changed'] is False
    for scenario in result['scenarios']:
        assert scenario['original']['candidate_per_historical_share_cny'] == candidate['candidate_valuation'][scenario['scenario']+'_value']
    assert snapshot(root) == before


@pytest.mark.parametrize('target', ['spec', 'domain', 'extractor', 'pdf', 'original'])
def test_joint_final_closure_rejects_drift_after_cold_calculation(public_js2, monkeypatch, target):
    root, ref, _ = public_js2
    original = review.diagnose_joint_adverse_cash
    targets = dict(spec=review.JOINT_SOURCE_SPEC,
        domain='src/value_investment_agent/domain/valuation/joint_adverse_cash_v1.py',
        extractor='src/value_investment_agent/application/research/operating_earnings_bridge.py',
        pdf='src/value_investment_agent/infrastructure/filings/pdf_text.py')
    def drift(**kwargs):
        result = original(**kwargs)
        name = kwargs['annual_profit_fact']['path'] if target == 'original' else targets[target]
        path = root/name
        path.write_bytes(path.read_bytes()+b'\nTEST_ONLY_FINAL_CLOSURE_DRIFT')
        return result
    monkeypatch.setattr(review, 'diagnose_joint_adverse_cash', drift)
    with pytest.raises(ValueError):
        review.build_source_native_economic_review(root=root, candidate_binding=ref)


def test_joint_spec_must_match_executing_root_without_weakening_parent(public_js2):
    root, ref, _ = public_js2
    spec = root/review.JOINT_SOURCE_SPEC
    spec.write_bytes(spec.read_bytes()+b'\n')
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref)
    assert result['joint_adverse_cash']['status'] == 'UNSUPPORTED'
    assert 'differs from executing root' in result['joint_adverse_cash']['reason']
    assert result['joint_adverse_cash']['rows'] == []
    assert len(result['scenarios']) == 3 and result['approval_changed'] is False


def test_synthetic_company_with_spec_but_no_official_reconciliation_is_unsupported(sample):
    root, ref, _ = sample
    spec = root/review.JOINT_SOURCE_SPEC
    spec.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CODE/review.JOINT_SOURCE_SPEC, spec)
    before = snapshot(root)
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref)
    joint = result['joint_adverse_cash']
    assert joint['status'] == 'UNSUPPORTED' and joint['reason']
    assert set(joint) == {'status', 'reason', 'rows', 'scope', 'action'}
    assert joint['rows'] == []
    assert len(result['scenarios']) == 3 and result['approval_changed'] is False
    assert snapshot(root) == before

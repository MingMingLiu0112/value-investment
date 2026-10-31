"""New intake tests: native parent/model/packet, TEST_ONLY product-reader seam."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import test_source_native_candidate_v2 as seed
from test_product_continuation_cash_path_v1 import inputs as kernel_fixture
from value_investment_agent.application.research import product_continuation_candidate as intake
from value_investment_agent.application.product.common import sha256_file


@pytest.mark.parametrize('flag', ['--pending-review-candidate-sha256','--signed-review-response-sha256',
    '--review-trust-root-sha256','--previous-review-response-sha256'])
def test_existing_cli_rejects_review_hashes_in_continuation_mode(flag, tmp_path):
    code = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable,'-B',str(code/'scripts/current/run_company_research.py'),
        '--symbol','600519','--continuation-request','runtime/nonexistent.json',
        '--continuation-request-sha256','0'*64,'--output',str(tmp_path/'unused'),flag,'1'*64],
        capture_output=True,text=True)
    assert result.returncode == 2
    assert 'excludes market/approval modes' in result.stderr
    assert not (tmp_path/'unused').exists()


def store(root, path, value):
    return seed.store(root, path, value)


@pytest.fixture
def case(tmp_path, monkeypatch, synthetic_pending_candidate_clock):
    original_factory = seed.test_only_ledger
    def bounded_ledger(book, basis):
        ledger = original_factory(book, basis)
        with localcontext() as ctx:
            ctx.prec = 48
            shift, floor = book*D('9.5'), book*D('.1')
            ledger['history']['ttm']['cash_end'] = str(book*D('.5'))
            ledger['history']['periods']['FY2025']['operating_outflows'] = str(floor*2)
            for item in ledger['cases']['TIMING_DELAY'].values():
                item['cash_floor'] = str(floor)
                item['terminal_cash'] = str(D(item['terminal_cash'])-shift)
                for row in item['annual_rows']:
                    for key in ('opening_parent_cash', 'cash_close'):
                        row[key] = str(D(row[key])-shift)
                    row['cash_capacity'] = str(D(row['cash_capacity'])-shift+book-floor)
        return ledger
    monkeypatch.setattr(seed, 'test_only_ledger', bounded_ledger)
    root, package_ref, ledger_ref = seed.synthetic_native.__wrapped__(tmp_path, synthetic_pending_candidate_clock)
    parent = seed.native.prepare_source_native_candidate(root=root, package_binding=package_ref,
        ledger_binding=ledger_ref, output_dir=root/'runtime/parent')
    parent_ref = dict(path='runtime/parent/candidate.json', sha256=sha256_file(root/'runtime/parent/candidate.json'))
    for name in intake.IMPLEMENTATIONS:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(intake.CODE_ROOT/name, target)
    package = json.loads((root/package_ref['path']).read_bytes())
    with localcontext() as ctx:
        ctx.prec = 48
        book = D(package['facts']['operating_inputs']['start_book_equity'])
        factor = book/D('6007')
        rows = kernel_fixture.__wrapped__()['first_five_product_rows']
        for row in rows:
            for key in ('revenue', 'cost', 'other_pre_tax_balance', 'legacy_pre_tax_profit', 'net_parent_nonrecurring_difference', 'legacy_ex_parent'):
                row[key] = str(D(row[key])*factor)
            for field in ('opening_product_reference_revenue_cny', 'product_revenue_cny', 'expenses'):
                row[field] = {key: str(D(value)*factor) for key, value in row[field].items()}
    observation = store(root, 'runtime/TEST_ONLY-product-reader.json', rows)
    def source_reader(**kwargs):
        # TEST_ONLY source parsing seam only: native parent, model and packet are real.
        values = json.loads((root/observation['path']).read_bytes())
        return dict(status='CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED', source_bindings=[observation],
            scenarios=[dict(scenario=name, operating_rows=deepcopy(values)) for name in ('bear', 'base', 'bull')])
    monkeypatch.setattr(intake, 'build_product_operating_research', source_reader)
    stamp = datetime.now(timezone.utc).isoformat()
    cash = dict(schema_version='finite-advantage-cash-research-policy-v1', generated_at=stamp, symbol=parent['symbol'],
        candidate_binding=parent_ref, confidence='LOW', action='no_order', maintenance_rationale='TEST_ONLY balance, not zero maintenance',
        capacity_rationale='TEST_ONLY research proxy', cash_mapping_rationale='TEST_ONLY owner funds, not parent profit',
        terminal_distribution_rationale='TEST_ONLY lawful cessation/availability assumption, not actual authorization')
    policy = dict(schema_version='product-continuation-research-policy-v1', generated_at=stamp, symbol=parent['symbol'],
        candidate_binding=parent_ref, confidence='LOW', action='no_order', center='FLAT_YEAR5_PRODUCT_LEVELS_AND_COST_RATIOS',
        continuation_years=5, terminal_rationale='TEST_ONLY conditional stable product contribution',
        rationale='TEST_ONLY flat product extension, not evidence of permanent economics',
        cash_return_rationale='TEST_ONLY retained cash earns explicit incremental yield',
        strongest_counter_evidence='TEST_ONLY maintenance or remittance can defeat full payout',
        counter_evidence=['TEST_ONLY operating continuation is uncertain'])
    return dict(root=root, source_candidate_binding=parent_ref,
        cash_policy_binding=store(root, 'runtime/TEST_ONLY-cash-policy.json', cash),
        continuation_policy_binding=store(root, 'runtime/TEST_ONLY-center-policy.json', policy),
        output_dir=root/'runtime/center'), observation


def prepare(case):
    return intake.prepare_product_continuation_candidate(**case[0])


def verify(case, candidate):
    args = case[0]
    path = args['output_dir']/'candidate.json'
    return intake.verify_product_continuation_candidate(root=args['root'], path=path, expected_sha256=sha256_file(path))


def test_native_typed_ten_year_candidate_and_original_five_group_packet(case):
    args, _ = case
    before = (args['root']/args['source_candidate_binding']['path']).read_bytes()
    candidate = prepare(case)
    assert candidate['schema_version'] == intake.SCHEMA
    assert candidate['source_candidate_binding'] == args['source_candidate_binding']
    assert candidate['status'] == 'PENDING_REVIEW' and candidate['execution_status'] == 'NO_ACTION'
    assert not candidate['research_admitted'] and not candidate['price_admitted']
    assert candidate['position_guidance'] is None
    assert verify(case, candidate) == candidate
    package = json.loads((args['output_dir']/'package.json').read_bytes())
    assert package['research_case']['research_version'] == package['package_version']
    assert package['research_case']['research_version'] != package['research_case']['financial_summary']['product_ten_year_research']['antecedent_research_version']
    assert package['quote'] is None and package['human_research_approval'] is None
    assert all(len(row['forecast_roes']) == 10 for row in package['facts']['scenario_inputs'].values())
    assert sum(item['name'].startswith('forecast_roes_') for item in package['assumptions']['assumptions']) == 10
    assert len(candidate['review_groups']) == 5
    packet = json.loads((args['output_dir']/'consumed-review.json').read_bytes())
    assert len(packet['assumptions']) == 14
    assert (args['root']/args['source_candidate_binding']['path']).read_bytes() == before


def test_ten_year_candidate_consumed_by_existing_supplement_and_unsigned_materials(case):
    from value_investment_agent.application.product import pending_candidate_supplement as supplement
    from value_investment_agent.application.product.source_native_review_adapter_v2 import prepare_pending_review_intake
    from value_investment_agent.application.product.economic_review_materials import project_product_continuation_review
    from value_investment_agent.application.research.value_research_analysis import load_current_value_research_analysis
    candidate = prepare(case)
    root, target = case[0]['root'], case[0]['output_dir']
    store(root, supplement.PUBLIC_INPUTS_PATH, dict(schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={candidate['symbol']: dict(path=target.relative_to(root).as_posix()+'/candidate.json',
            sha256=sha256_file(target/'candidate.json'))}))
    loaded = supplement.load_current_pending_candidate_supplement(root=root, symbol=candidate['symbol'])
    assert loaded['candidate'] == candidate and loaded['position_guidance'] is None
    intake_result = prepare_pending_review_intake(root=root, candidate_path=target/'candidate.json',
        candidate_sha256=loaded['candidate_binding']['sha256'])
    assert intake_result['status'] == 'AWAITING_HUMAN_RESPONSES'
    assert not intake_result['research_admitted'] and not intake_result['price_admitted']
    assert all(group['response'] is None for group in intake_result['groups'])
    now = datetime.now(timezone.utc)
    analysis = load_current_value_research_analysis(root=root, symbol=candidate['symbol'], now=now)
    assert analysis['arithmetic_complete'] and not analysis['action_admitted']
    review = project_product_continuation_review(root=root, supplement=loaded, now=now)
    assert review['primary_approved'] is False and review['price_draft'] is None
    assert review['position_guidance'] is None
    assert all(len(row['cash_rows']) == 10 for row in review['scenarios'])


@pytest.mark.parametrize('change', ['missing_year', 'wrong_year', 'cash_shortfall', 'distribution', 'currency', 'shares', 'scope'])
def test_cash_or_scope_failure_cannot_be_hidden_by_terminal(case, monkeypatch, change):
    original = intake.build_product_continuation_cash_path
    def changed(**kwargs):
        if change == 'missing_year': kwargs['capital_cash_rows'].pop()
        elif change == 'wrong_year': kwargs['capital_cash_rows'][7]['year'] = 9
        elif change == 'currency': kwargs['opening_state']['currency'] = 'USD'
        elif change == 'shares': kwargs['opening_state']['ordinary_shares'] = '0'
        elif change == 'scope': kwargs['opening_state']['scope'] = 'CONSOLIDATED_CASH_IS_PARENT_CASH'
        elif change == 'cash_shortfall': kwargs['opening_state']['cash_cny'] = '0'
        else: kwargs['distribution_rows'][0]['payout_ratio'] = '2'
        return original(**kwargs)
    monkeypatch.setattr(intake, 'build_product_continuation_cash_path', changed)
    with pytest.raises((ValueError, KeyError)):
        prepare(case)
    assert not (case[0]['output_dir']/'candidate.json').exists()


@pytest.mark.parametrize('change', ['price_admitted', 'primary_registered', 'action', 'valuation', 'extra', 'parent', 'mode'])
def test_resealed_candidate_cannot_grant_authority_or_change_identity(case, change):
    candidate = prepare(case)
    if change in ('price_admitted', 'primary_registered'):
        candidate[change] = True
    elif change == 'action':
        candidate['action'] = 'buy'
    elif change == 'valuation':
        candidate['candidate_valuation']['base_value'] = '1'
    elif change == 'extra':
        candidate['g3_approved'] = True
    elif change == 'parent':
        candidate['source_candidate_binding']['sha256'] = '0'*64
    else:
        candidate['input_mode'] = 'SOURCE_NATIVE_EXACT_INPUT_V1'
    store(case[0]['root'], 'runtime/center/candidate.json', candidate)
    with pytest.raises(ValueError):
        verify(case, candidate)


@pytest.mark.parametrize('change', ['ledger', 'roe', 'terminal', 'packet', 'workbench'])
def test_resealed_derived_files_cannot_replace_cold_inputs(case, change):
    candidate = prepare(case)
    root, target = case[0]['root'], case[0]['output_dir']
    field, filename = ('native_cash_ledger_binding', 'cash-ledger.json') if change in ('ledger', 'terminal') else (
        ('source_package_binding', 'package.json') if change == 'roe' else ('review_packet_binding', 'consumed-review.json'))
    if change == 'workbench':
        filename = 'workbench.json'
    value = json.loads((target/filename).read_bytes())
    if change == 'ledger':
        value['centers']['base']['cash_rows'][7]['profit_cny'] = '1'
    elif change == 'terminal':
        value['centers']['base']['terminal']['next_profit_cny'] = '1'
    elif change == 'roe':
        value['facts']['scenario_inputs']['base']['forecast_roes'][8] = '.99'
    elif change == 'packet':
        value['research_admitted'] = True
    else:
        value['valuation']['base_value'] = '1'
    ref = store(root, 'runtime/center/'+filename, value)
    if change != 'workbench':
        candidate[field] = ref
    candidate['source_bindings'] = [ref if item['path'] == ref['path'] else item for item in candidate['source_bindings']]
    store(root, 'runtime/center/candidate.json', candidate)
    with pytest.raises(ValueError):
        verify(case, candidate)


def test_explicit_parent_not_current_and_readonly_verify(case, monkeypatch):
    candidate = prepare(case)
    import value_investment_agent.application.product.pending_candidate_supplement as supplement
    monkeypatch.setattr(supplement, 'load_current_pending_candidate_supplement', lambda **kw: pytest.fail('current pointer must not be read'))
    root = case[0]['root']
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert verify(case, candidate) == candidate
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_changed_research_input_recomputes_without_rewriting_old_candidate(case):
    args = case[0]
    old = prepare(case)
    root, target = args['root'], args['output_dir']
    prior = dict(path=(target/'candidate.json').relative_to(root).as_posix(), sha256=sha256_file(target/'candidate.json'))
    before = {p.name:p.read_bytes() for p in target.iterdir()}
    path = root/args['continuation_policy_binding']['path']
    policy = json.loads(path.read_bytes())
    policy['rationale'] += ' TEST_ONLY revised evidence interpretation.'
    new_policy = store(root, args['continuation_policy_binding']['path'], policy)
    with pytest.raises(ValueError):
        verify(case, old)
    request = dict(schema_version='product-continuation-refresh-request-v1', symbol=old['symbol'],
        source_candidate_binding=args['source_candidate_binding'], cash_policy_binding=args['cash_policy_binding'],
        continuation_policy_binding=new_policy, previous_candidate_binding=prior,
        reason='TEST_ONLY real contract input change, not a new announcement', action='no_order')
    ref = store(root, 'runtime/refresh-request.json', request)
    result = intake.refresh_product_continuation_candidate(root=root, request_binding=ref, output_dir=root/'runtime/refreshed')
    assert [r['dependency'] for r in result['changed_inputs']] == ['continuation_policy_binding']
    assert result['previous_scope'] == 'HASH_BOUND_HISTORY_NOT_REVERIFIED_AS_CURRENT'
    assert not result['approval_changed'] and not result['current_pointer_changed'] and not result['new_announcement_claimed']
    assert before == {p.name:p.read_bytes() for p in target.iterdir()}
    new = intake.verify_product_continuation_candidate(root=root, path=root/result['current_candidate_binding']['path'],
        expected_sha256=result['current_candidate_binding']['sha256'])
    assert new['model_context']['input_descriptor_sha256'] != old['model_context']['input_descriptor_sha256']
    assert new['candidate_valuation']['base_value'] == old['candidate_valuation']['base_value']


@pytest.mark.parametrize('change', ['symbol', 'future', 'wrong_parent', 'wrong_schema', 'no_economic_reason'])
def test_policy_identity_and_time_fail_closed_before_candidate(case, change):
    args = case[0]
    root = args['root']
    policy = json.loads((root/args['continuation_policy_binding']['path']).read_bytes())
    if change == 'symbol': policy['symbol'] = '000544'
    elif change == 'future': policy['generated_at'] = '2099-01-01T00:00:00+00:00'
    elif change == 'wrong_parent': policy['candidate_binding']['sha256'] = '0'*64
    elif change == 'no_economic_reason': policy['rationale'] = ''
    else: policy['schema_version'] = 'unknown-v99'
    args['continuation_policy_binding'] = store(root, args['continuation_policy_binding']['path'], policy)
    with pytest.raises(ValueError):
        prepare(case)
    assert not (args['output_dir']/'candidate.json').exists()


def test_late_observation_drift_and_execution_drift_rejected(case):
    candidate = prepare(case)
    args, observation = case
    path = args['root']/observation['path']
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):
        verify(case, candidate)
    path.write_bytes(path.read_bytes()[:-1])
    impl = args['root']/intake.IMPLEMENTATIONS[0]
    impl.write_bytes(impl.read_bytes()+b'\n')
    with pytest.raises(ValueError, match='implementation'):
        verify(case, candidate)


def test_final_source_recheck_after_actual_typed_run(case, monkeypatch):
    candidate = prepare(case)
    actual_project = intake.project_research_review_packet
    def packet_then_drift(*args, **kwargs):
        result = actual_project(*args, **kwargs)
        root = case[0]['root']
        source = root/case[1]['path']
        source.write_bytes(source.read_bytes()+b' ')
        return result
    monkeypatch.setattr(intake, 'project_research_review_packet', packet_then_drift)
    with pytest.raises(ValueError, match='source identity/hash drift'):
        verify(case, candidate)


def test_same_bytes_different_package_path_rejected(case):
    candidate = prepare(case)
    root, target = case[0]['root'], case[0]['output_dir']
    alternate = root/'runtime/alternate-package.json'
    alternate.write_bytes((target/'package.json').read_bytes())
    candidate['source_package_binding'] = dict(path='runtime/alternate-package.json', sha256=sha256_file(alternate))
    store(root, 'runtime/center/candidate.json', candidate)
    with pytest.raises(ValueError, match='file identity mismatch'):
        verify(case, candidate)


def test_actual_public_originals_in_isolated_project(tmp_path_factory):
    """Optional real PDFs, real reader/kernel/service; no mocked financial inputs."""
    real = os.environ.get('PRODUCT_CANDIDATE_REAL_ROOT')
    if not real:
        pytest.skip('Set PRODUCT_CANDIDATE_REAL_ROOT to the retained public-source root')
    tmp_path = tmp_path_factory.getbasetemp()/'r'
    tmp_path.mkdir()
    real = Path(real).resolve()
    parent_path = 'runtime/product-operating-research/20261025T071814444248Z/proposal/candidate/candidate.json'
    parent_hash = '2e53d50d988a737272d7a95b822c8e0e9998d3749c1432cac7f6c12d92fe8ed0'
    assert sha256_file(real/parent_path) == parent_hash
    parent = json.loads((real/parent_path).read_bytes())
    refs = [dict(path=parent_path, sha256=parent_hash), *parent['source_bindings']]
    for ref in refs:
        source = (real/ref['path']).resolve()
        assert source.is_relative_to(real) and source.relative_to(real).as_posix() == ref['path']
        assert Path(ref['path']).parts[0] in ('runtime', 'docs', 'src', 'config')
        assert not any(part.lower() in ('private', 'accounts', 'secrets') for part in Path(ref['path']).parts)
        assert sha256_file(source) == ref['sha256']
        destination = tmp_path/ref['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for name in intake.IMPLEMENTATIONS:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(intake.CODE_ROOT/name, target)
    policies = {}
    for kind in ('product-operating', 'finite-advantage-cash', 'product-continuation'):
        relative = 'config/research-assumptions/600519-'+kind+'-v1.json'
        target = tmp_path/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real/relative, target)
        policies[kind] = dict(path=relative, sha256=sha256_file(target))
    current_policy = json.loads((real/policies['product-continuation']['path']).read_bytes())
    if current_policy.get('shareholder_cash_source_binding') is not None:
        ref = current_policy['shareholder_cash_source_binding']
        spec = json.loads((real/ref['path']).read_bytes())
        refs_to_copy = [ref, *[dict(path=s['path'],sha256=s['sha256']) for s in spec['companies'][parent['symbol']]]]
        for ref in refs_to_copy:
            assert sha256_file(real/ref['path']) == ref['sha256']
            target = tmp_path/ref['path']
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(real/ref['path'],target)
    candidate = intake.prepare_product_continuation_candidate(root=tmp_path,
        source_candidate_binding=dict(path=parent_path, sha256=parent_hash),
        cash_policy_binding=policies['finite-advantage-cash'], continuation_policy_binding=policies['product-continuation'],
        output_dir=tmp_path/'runtime/real-ten-year')
    assert candidate['status'] == 'PENDING_REVIEW' and candidate['execution_status'] == 'NO_ACTION'
    assert not candidate['research_admitted'] and not candidate['price_admitted']
    assert len(candidate['review_groups']) == 5
    assert intake.verify_product_continuation_candidate(root=tmp_path, path=tmp_path/'runtime/real-ten-year/candidate.json',
        expected_sha256=sha256_file(tmp_path/'runtime/real-ten-year/candidate.json')) == candidate
    for ref in refs:
        assert sha256_file(real/ref['path']) == ref['sha256']
    print(json.dumps(dict(scope='ACTUAL_PUBLIC_ORIGINALS_ISOLATED_NATIVE_CANDIDATE_NOT_APPROVED',
        source_candidate_binding=candidate['source_candidate_binding'], candidate_binding=dict(
            path=str(tmp_path/'runtime/real-ten-year/candidate.json'), sha256=sha256_file(tmp_path/'runtime/real-ten-year/candidate.json')),
        candidate_valuation={key: candidate['candidate_valuation'][key] for key in (
            'symbol', 'valuation_date', 'bear_value', 'base_value', 'bull_value', 'confidence', 'status')}, action='no_order')))

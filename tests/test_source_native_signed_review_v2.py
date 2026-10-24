"""TEST_ONLY signed native chain; public JS2 is never human-approved here."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from test_source_native_candidate_v2 import synthetic_native, store, prepare
from test_human_research_approval import _receipt
from value_investment_agent.application.product import source_native_signed_review_v2 as signed
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench, current_recommendation_type
from value_investment_agent.application.product.source_native_candidate_v2 import prepare_source_native_candidate
from value_investment_agent.human_research_approval import resolve_human_research_approval
from value_investment_agent.research_run_contract import canonical_contract_payload
from value_investment_agent.operations.authorization.trust_root_registry import (
    _use_test_trust_registry, trust_root_fingerprint,
)

CODE = Path(__file__).resolve().parents[1]


@pytest.fixture(params=['600887', '600519'])
def native_signed(synthetic_native, request):
    root, package_ref, ledger_ref = synthetic_native
    if request.param != '600887':
        package = json.loads((root/package_ref['path']).read_bytes())
        # A second synthetic issuer, not a relabelled real JS2 approval.
        def issuer(value):
            if isinstance(value, dict):
                return {k: issuer(v) for k, v in value.items()}
            if isinstance(value, list):
                return [issuer(v) for v in value]
            return request.param if value == '600887' else value
        package = issuer(package)
        identities = json.loads((CODE/'src/value_investment_agent/domain/research/issuer_identity_registry.json').read_bytes())
        registered = identities['cninfo'][request.param]
        for source in package['sources']:
            if source.get('kind') == 'official_issuer_filing':
                source['issuer_identity'] = dict(venue='CNINFO', security_code=request.param,
                    issuer_name=registered['issuer_names'][0], organization_id=registered['organization_id'])
        package_ref = store(root, 'runtime/TEST_ONLY-native-package-second.json', package)
    for name in signed.IMPLEMENTATIONS:
        target = root/'src/value_investment_agent'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE/'src/value_investment_agent'/name, target)
    now = datetime.now(timezone.utc)
    candidate = prepare_source_native_candidate(root=root, package_binding=package_ref,
        ledger_binding=ledger_ref, output_dir=root/'runtime/native-signed-candidate', now=now)
    path = root/'runtime/native-signed-candidate/candidate.json'
    ref = dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
    response = signed.prepare_native_signed_review_response(root=root, candidate_path=path,
        candidate_sha256=ref['sha256'])
    reviewed = datetime.now(timezone.utc)
    response.update(reviewer_id='TEST_ONLY_NATIVE_REVIEWER', reviewed_at=reviewed.isoformat(), sequence=1)
    for group in response['groups']:
        group.update(response='VERIFIED', response_reason='TEST_ONLY independent conditional input check',
            confirmed_scope='TEST_ONLY whole-model research, no market permission')
    wb = json.loads((path.parent/'workbench.json').read_bytes())
    restored = verify_current_decision_workbench(wb)
    ctx = response['model_context']
    approval = replace(_receipt(decision='APPROVED_CONDITIONAL_LOW_CONFIDENCE', price_assessment_eligible=False),
        symbol=candidate['symbol'], security_id=candidate['symbol'], profile_id=ctx['profile_id'],
        valuation_artifact_sha256=response['valuation_artifact_sha256'], valuation_model_id=ctx['model_id'],
        valuation_model_version=ctx['model_version'], research_case_sha256=ctx['research_case_sha256'],
        facts_artifact_sha256=ctx['facts_sha256'], assumption_set_sha256=ctx['assumptions_sha256'],
        reviewed_at=reviewed, review_as_of=reviewed.date(), reviewer_id=response['reviewer_id'],
        evidence_refs=tuple(json.loads((root/package_ref['path']).read_bytes())['facts']['evidence_refs']),
        **{field: restored.dependencies[role].artifact_id for role, field in (
            ('valuation', 'valuation_artifact_id'), ('research_case', 'research_case_id'),
            ('financial_facts', 'facts_artifact_id'), ('valuation_assumptions', 'assumption_set_id'))})
    response['whole_model_approval'] = approval.as_policy()
    key = Ed25519PrivateKey.generate()
    trust = dict(schema_version='research-review-transport-trust-root-v1', reviewer_id=response['reviewer_id'],
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        scopes=['human_group_research', 'human_whole_model'], symbols=[candidate['symbol']],
        valid_from=(reviewed-timedelta(days=1)).isoformat(), valid_until=(reviewed+timedelta(days=1)).isoformat())
    registry = root/'TEST_ONLY-registry.json'
    write_new_json(registry, dict(schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(trust)]))
    return dict(root=root, path=path, ref=ref, response=response, key=key, trust=trust,
        registry=registry, candidate=candidate, package_ref=package_ref)


def consume_args(f, suffix='', purpose=signed.PURPOSE):
    root = f['root']
    response_path, trust_path = root/f'TEST_ONLY-response{suffix}.json', root/f'TEST_ONLY-trust{suffix}.json'
    f['response']['trust_root_binding'] = dict(path=trust_path.relative_to(root).as_posix(), sha256='')
    write_new_json(trust_path, f['trust'])
    f['response']['trust_root_binding']['sha256'] = sha256_file(trust_path)
    write_new_json(response_path, dict(payload=f['response'], signature=f['key'].sign(
        purpose+canonical_contract_payload(f['response']).encode('utf-8')).hex()))
    return dict(root=root, candidate_path=f['path'],
        candidate_sha256=f['ref']['sha256'], response_path=response_path, response_sha256=sha256_file(response_path),
        trust_root_path=trust_path, trust_root_sha256=sha256_file(trust_path),
        output_dir=root/signed.CONSUMPTIONS/f'TEST_ONLY-consumed{suffix}')


def consume(f, suffix='', purpose=signed.PURPOSE):
    return signed.consume_native_signed_review_response(**consume_args(f, suffix, purpose))


def run(f, result):
    return signed.run_native_reviewed_research(root=f['root'], candidate_binding=f['ref'],
        consumption_binding=result['consumption_binding'])


def test_signed_native_full_service_serialization_and_real_cold_di(native_signed):
    f = native_signed
    original = f['path'].read_bytes()
    with _use_test_trust_registry(f['registry']):
        result = consume(f)
        wb = run(f, result)
        wb = json.loads(json.dumps(wb))
        cold = verify_current_decision_workbench(wb,
            human_approval_provenance_verifier=lambda a: signed.verify_native_human_approval_provenance(f['root'], a))
        approval = cold.dependency_objects['human_approval']
        assert approval.verified_transport is not None
        assert approval.price_assessment_eligible is False
        decision = resolve_human_research_approval(approval, cold.dependency_objects['valuation'],
            model_id=f['response']['model_context']['model_id'],
            research_case_payload=cold.dependencies['research_case'].envelope.payload_object(),
            facts_payload=cold.dependencies['financial_facts'].envelope.payload_object(),
            assumptions_payload=cold.dependencies['valuation_assumptions'].envelope.payload_object(),
            require_authenticated_provenance=True)
        assert decision.approved and decision.valuation_bound and decision.dependencies_bound
        assert not decision.price_assessment_eligible
        assert wb['input_descriptor_sha256'] == wb['native_review']['derived_run_input_sha256']
        assert wb['input_descriptor_sha256'] != f['response']['model_context']['input_descriptor_sha256']
        assert cold.recommendation.action == 'no_order'
        assert wb['native_review']['formal_eligibility'] is False
        assert wb['valuation'] == f['candidate']['candidate_valuation']
        assert wb['price_bridge']['current_price'] is None
        assert wb['price_bridge']['quote_date'] is None
        assert wb['price_bridge']['bridge_status'] == 'PENDING_EXTERNAL_DATA'
        assert current_recommendation_type(cold.recommendation) == 'NO_ACTION'
        assert not (f['root']/'runtime/research-review-responses').exists()
        assert f['path'].read_bytes() == original
        wb_path = f['root']/'TEST_ONLY-reviewed-workbench.json'
        write_new_json(wb_path, wb)
        code = '''import json,sys
from pathlib import Path
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
from value_investment_agent.application.product.source_native_signed_review_v2 import verify_native_human_approval_provenance
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
root, registry, workbench = map(Path,sys.argv[1:])
with _use_test_trust_registry(registry):
    restored=verify_current_decision_workbench(json.loads(workbench.read_bytes()),human_approval_provenance_verifier=lambda a:verify_native_human_approval_provenance(root,a))
    assert restored.dependency_objects['human_approval'].verified_transport is not None
    assert restored.recommendation.action=='no_order'
print('TEST_ONLY_COLD_PROCESS_PASS')
'''
        proc = subprocess.run([sys.executable, '-B', '-c', code, str(f['root']), str(f['registry']), str(wb_path)],
            cwd=CODE, env=dict(os.environ, PYTHONPATH=str(CODE/'src')), capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == 'TEST_ONLY_COLD_PROCESS_PASS'


@pytest.mark.parametrize('change', ['purpose', 'sequence_bool', 'unknown', 'group', 'price',
    'candidate', 'context', 'valuation', 'identity', 'scope', 'future', 'unbound', 'artifact_id',
    'group_missing', 'group_reordered', 'extra', 'nested_transport', 'expired', 'wrong_symbol', 'bad_signature',
    'fabricated_evidence', 'id_only_evidence'])
def test_native_signed_rejects_invalid_contract_before_completion(native_signed, change):
    f = native_signed
    if change == 'sequence_bool': f['response']['sequence'] = True
    if change == 'unknown': f['response']['schema_version'] = 'source-native-research-review-response-v999'
    if change == 'group': f['response']['groups'][0]['response'] = 'INSUFFICIENT'
    if change == 'price': f['response']['whole_model_approval']['price_assessment_eligible'] = True
    if change == 'candidate': f['response']['candidate_binding']['sha256'] = '0'*64
    if change == 'context': f['response']['model_context']['facts_sha256'] = '0'*64
    if change == 'valuation': f['response']['valuation_artifact_sha256'] = '0'*64
    if change == 'identity': f['response']['reviewer_id'] = 'IMPOSTOR'
    if change == 'scope': f['trust']['scopes'] = ['human_group_research']
    if change == 'future': f['response']['reviewed_at'] = (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    if change == 'artifact_id': f['response']['whole_model_approval']['facts_artifact_id'] = 'wrong-id'
    if change == 'group_missing': f['response']['groups'].pop()
    if change == 'group_reordered': f['response']['groups'].reverse()
    if change == 'extra': f['response']['unknown_authority'] = True
    if change == 'nested_transport': f['response']['whole_model_approval']['authenticated_transport_binding'] = {}
    if change == 'expired': f['trust']['valid_until'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    if change == 'wrong_symbol': f['trust']['symbols'] = ['000001']
    if change == 'bad_signature': f['key'] = Ed25519PrivateKey.generate()
    if change == 'fabricated_evidence': f['response']['whole_model_approval']['evidence_refs'][0]['id'] = 'fabricated'
    if change == 'id_only_evidence': f['response']['whole_model_approval']['evidence_refs'] = [dict(id='approval-pdf')]
    if change in {'scope', 'expired', 'wrong_symbol'}:
        f['registry'].write_text(json.dumps(dict(schema_version='authorization-trust-root-registry-v1',
            pinned_trust_root_sha256=[trust_root_fingerprint(f['trust'])])), encoding='utf-8')
    with _use_test_trust_registry(f['registry']):
        with pytest.raises(ValueError):
            if change == 'unbound':
                with _use_test_trust_registry(f['root']/'missing-registry.json'):
                    consume(f)
            else:
                consume(f, purpose=b'old-v1-purpose' if change == 'purpose' else signed.PURPOSE)
    assert not list((f['root']/signed.NAMESPACE).glob('*/*.json'))


def test_native_completion_missing_or_source_drift_blocks_cold_read(native_signed):
    f = native_signed
    with _use_test_trust_registry(f['registry']):
        result = consume(f)
        wb = run(f, result)
        original = f['root']/f['package_ref']['path']
        original.write_bytes(original.read_bytes()+b'\nTEST_ONLY_DRIFT')
        with pytest.raises(ValueError): run(f, result)
        with pytest.raises(ValueError):
            verify_current_decision_workbench(wb,
                human_approval_provenance_verifier=lambda a: signed.verify_native_human_approval_provenance(f['root'], a))


def test_native_commit_interruption_has_no_authority(native_signed, monkeypatch):
    f = native_signed
    args = consume_args(f)
    write = signed.write_new_json
    def interrupt(path, payload):
        if path.parent.parent.name == Path(signed.NAMESPACE).name:
            raise OSError('TEST_ONLY journal interruption')
        return write(path, payload)
    with _use_test_trust_registry(f['registry']):
        monkeypatch.setattr(signed, 'write_new_json', interrupt)
        with pytest.raises(OSError, match='interruption'):
            signed.consume_native_signed_review_response(**args)
        receipt = args['output_dir']/'receipt.json'
        assert receipt.exists()
        ref = dict(path=receipt.relative_to(f['root']).as_posix(), sha256=sha256_file(receipt))
        with pytest.raises(ValueError, match='no completed'):
            signed.run_native_reviewed_research(root=f['root'], candidate_binding=f['ref'], consumption_binding=ref)
        monkeypatch.setattr(signed, 'write_new_json', write)
        with pytest.raises(FileExistsError): signed.consume_native_signed_review_response(**args)
        # A new explicit transaction can consume the still-current signed response;
        # the orphan output is never silently repaired or treated as authoritative.
        result = signed.consume_native_signed_review_response(**dict(args,
            output_dir=f['root']/signed.CONSUMPTIONS/'TEST_ONLY-new-transaction'))
        assert run(f, result)['native_review']['price_admitted'] is False


def test_native_same_predecessor_two_contenders_only_one_commit(native_signed):
    f = native_signed
    args = consume_args(f)
    def contender(index):
        try:
            return signed.consume_native_signed_review_response(**dict(args,
                output_dir=f['root']/signed.CONSUMPTIONS/f'TEST_ONLY-race-{index}'))
        except ValueError as error:
            return str(error)
    with _use_test_trust_registry(f['registry']):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender, [1, 2]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(list((f['root']/signed.NAMESPACE).glob('*/*.json'))) == 1


@pytest.mark.parametrize('damage', ['completion', 'receipt', 'trust', 'implementation', 'response', 'frozen_source_validator'])
def test_native_cold_read_rejects_bound_component_drift(native_signed, damage):
    f = native_signed
    with _use_test_trust_registry(f['registry']):
        result = consume(f)
        wb = run(f, result)
        if damage == 'completion':
            next((f['root']/signed.NAMESPACE).glob('*/*.json')).unlink()
        else:
            paths = dict(receipt=f['root']/result['consumption_binding']['path'],
                trust=f['root']/'TEST_ONLY-trust.json', response=f['root']/'TEST_ONLY-response.json',
                frozen_source_validator=f['root']/'src/value_investment_agent/application/product/source_bound_inputs.py',
                implementation=f['root']/'src/value_investment_agent'/signed.IMPLEMENTATIONS[0])
            path = paths[damage]
            path.write_bytes(path.read_bytes()+b'\nTEST_ONLY_DRIFT')
        with pytest.raises(ValueError):
            verify_current_decision_workbench(wb,
                human_approval_provenance_verifier=lambda a: signed.verify_native_human_approval_provenance(f['root'], a))


def test_native_final_source_drift_after_service_rejected(native_signed, monkeypatch):
    f = native_signed
    with _use_test_trust_registry(f['registry']):
        result = consume(f)
        serialize = signed._serialize_outcome
        def change_after_service(outcome):
            value = serialize(outcome)
            source = f['root']/f['package_ref']['path']
            source.write_bytes(source.read_bytes()+b'\nTEST_ONLY_LAST_READ_DRIFT')
            return value
        # Only the pure formatter is instrumented to simulate source I/O drift;
        # all native, signature, service, gate and provenance validators are real.
        monkeypatch.setattr(signed, '_serialize_outcome', change_after_service)
        with pytest.raises(ValueError): run(f, result)


def test_native_journal_replay_and_supersession(native_signed):
    f = native_signed
    with _use_test_trust_registry(f['registry']):
        first = consume(f)
        wb = run(f, first)
        with pytest.raises(ValueError, match='replay|predecessor'): consume(f, '-replay')
        first_response = dict(path='TEST_ONLY-response.json', sha256=sha256_file(f['root']/'TEST_ONLY-response.json'))
        reviewed = datetime.now(timezone.utc)
        f['response'].update(sequence=2, previous_response_binding=first_response, reviewed_at=reviewed.isoformat())
        f['response']['whole_model_approval'].update(reviewed_at=reviewed.isoformat(), review_as_of=reviewed.date().isoformat())
        second = consume(f, '-second')
        assert run(f, second)['native_review']['consumption_binding'] == second['consumption_binding']
        with pytest.raises(ValueError, match='current completed head'): run(f, first)
        with pytest.raises(ValueError, match='current completed head'):
            verify_current_decision_workbench(wb,
                human_approval_provenance_verifier=lambda a: signed.verify_native_human_approval_provenance(f['root'], a))


@pytest.mark.parametrize('damage', ['duplicate_json', 'invalid_json', 'output_scope', 'bad_journal_key'])
def test_native_parse_and_write_scope_fail_closed(native_signed, damage):
    f = native_signed
    args = consume_args(f)
    if damage in {'duplicate_json', 'invalid_json'}:
        path = args['response_path']
        if damage == 'duplicate_json':
            data = path.read_text(encoding='utf-8')
            path.write_text('{"payload":null,'+data[1:], encoding='utf-8')
        else:
            path.write_text('{"payload":NaN}', encoding='utf-8')
        args['response_sha256'] = sha256_file(path)
    if damage == 'output_scope': args['output_dir'] = f['root']/'runtime/TEST_ONLY-forbidden-outside-namespace'
    if damage == 'bad_journal_key': args['candidate_sha256'] = '../outside-namespace'
    with _use_test_trust_registry(f['registry']):
        with pytest.raises(ValueError): signed.consume_native_signed_review_response(**args)
    assert not list((f['root']/signed.NAMESPACE).glob('*/*.json'))
    assert not (f['root']/'runtime/TEST_ONLY-forbidden-outside-namespace').exists()


def test_native_json_alone_cannot_restore_authenticated_approval(native_signed):
    f = native_signed
    with _use_test_trust_registry(f['registry']):
        result = consume(f)
        wb = json.loads(json.dumps(run(f, result)))
        # No DI must not recover an approved authenticated state from JSON.
        try:
            cold = verify_current_decision_workbench(wb)
        except ValueError:
            return
        approval = cold.dependency_objects['human_approval']
        assert approval.verified_transport is None
        decision = resolve_human_research_approval(approval, cold.dependency_objects['valuation'],
            model_id=f['response']['model_context']['model_id'],
            research_case_payload=cold.dependencies['research_case'].envelope.payload_object(),
            facts_payload=cold.dependencies['financial_facts'].envelope.payload_object(),
            assumptions_payload=cold.dependencies['valuation_assumptions'].envelope.payload_object(),
            require_authenticated_provenance=True)
        assert not decision.approved

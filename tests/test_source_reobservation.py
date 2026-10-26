"""Synthetic metadata repair contracts; none grants real investment eligibility."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from test_pending_candidate_replay import stale, write, binding
from value_investment_agent.application.product import source_reobservation as revision
from value_investment_agent.application.product import pending_research_candidate as candidate_module
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.m1_valuation_package_builder import build_descriptor


@pytest.fixture
def repair_inputs(stale, monkeypatch):
    root, candidate_path, old = stale
    implementation = root / revision.IMPLEMENTATION
    implementation.write_bytes((Path(__file__).resolve().parents[1] / revision.IMPLEMENTATION).read_bytes())
    monkeypatch.setattr(candidate_module, 'datetime', datetime)
    package_path = candidate_path.parent / 'package.json'
    package = json.loads(package_path.read_bytes())
    reference = root / 'runtime/reference/evidence.json'
    write(reference, dict(symbol='000001', research_approved=False, scope='synthetic unrelated issuer'))
    upstream = root / 'runtime/reference/upstream.json'
    write(upstream, dict(TEST_ONLY=True, risk_free='0.02'))
    script = root / 'scripts/reference_recipe.py'
    script.parent.mkdir(exist_ok=True)
    script.write_text('# synthetic retained recipe, never executed\n', encoding='utf-8')
    manifest = root / 'runtime/reference/manifest.json'
    write(manifest, dict(inputs={'runtime/reference/upstream.json': sha256_file(upstream)},
        script_sha256=sha256_file(script), outputs={'evidence.json': sha256_file(reference)}))
    source = dict(id='reference', kind='valuation_reference', location='runtime/reference/evidence.json',
        local_path='runtime/reference/evidence.json', sha256=sha256_file(reference),
        retrieved_at='2026-09-23T00:53:00+00:00', source_available_at=old['generated_at'],
        availability_basis='old-producer-default')
    package['sources'].append(source)
    write(package_path, package)
    request_path = root / 'runtime/schedule.json'
    write(request_path, dict(schema_version='research-schedule-request-v1', symbol=old['symbol'],
        source_id='CNINFO', period=package['point_in_time']['report_period'],
        research_question_id='source-repair', blocker_id='no-active-evidence-stop',
        reopen_condition_met=False, new_evidence_ids=[]))
    registry_path = root / 'runtime/cases.json'
    write(registry_path, dict(schema_version='daily-trade-assistant-cases-v1', action='no_order',
        cases={old['symbol']: dict(package=package_path.relative_to(root).as_posix(),
            package_sha256=sha256_file(package_path), schedule_request='runtime/schedule.json',
            schedule_request_sha256=sha256_file(request_path))}))
    kwargs = dict(root=root, case_registry_binding=binding(root, registry_path), symbol=old['symbol'],
        policy_binding=old['economic_policy_binding'], source_ids=['reference'],
        reference_manifest_binding=binding(root, manifest), reference_script_binding=binding(root, script),
        output_dir=root / 'runtime/reobserved')
    return kwargs, package, candidate_path


def _verify(kwargs):
    return revision.verify_source_reobservation(root=kwargs['root'],
        binding=binding(kwargs['root'], kwargs['output_dir'] / 'manifest.json'))


def test_new_metadata_version_is_reproducible_and_enters_real_unsigned_review(repair_inputs):
    kwargs, old_package, old_candidate = repair_inputs
    root = kwargs['root']
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    started = datetime.now(timezone.utc)
    result = revision.prepare_source_reobservation(**kwargs)
    receipt = json.loads((kwargs['output_dir'] / 'acquisition-receipt.json').read_bytes())
    assert started <= datetime.fromisoformat(receipt['observed_at']) <= datetime.now(timezone.utc)
    assert receipt['observations'][0]['prior_source'] == old_package['sources'][-1]
    package_path = root / result['package_binding']['path']
    package = json.loads(package_path.read_bytes())
    assert package['facts']['operating_inputs'] == old_package['facts']['operating_inputs']
    assert package['facts']['scenario_inputs'] == old_package['facts']['scenario_inputs']
    assert package['point_in_time']['report_period'] == old_package['point_in_time']['report_period']
    assert package['point_in_time']['valuation_date'] == old_package['point_in_time']['valuation_date']
    assert package['source_contract']['schema_version'] == old_package['source_contract']['schema_version']
    assert package['quote'] is None
    for source in package['sources']:
        if source['id'] == 'reference':
            assert source['retrieved_at'] == source['source_available_at'] == receipt['observed_at']
            assert source['sha256'] == old_package['sources'][-1]['sha256']
    assert _verify(kwargs) == result
    with pytest.raises(ValueError, match='retrieval precedes'):
        build_descriptor(old_package, root=root)
    output = kwargs['output_dir'] / 'pending-candidate'
    run = revision.run_reobserved_candidate(root=root,
        binding=binding(root, kwargs['output_dir'] / 'manifest.json'), choice_id='continuity')
    path = output / 'candidate.json'
    actual = candidate_module.verify_pending_research_candidate(root=root, path=path, expected_sha256=sha256_file(path))
    intake = json.loads((output / 'review-intake.json').read_bytes())
    assert run['candidate_binding'] == binding(root, path)
    assert intake['status'] == 'AWAITING_HUMAN_RESPONSES'
    assert actual['model_context_scope'] == 'ACTUALLY_CONSUMED'
    assert actual['research_admitted'] is actual['price_admitted'] is actual['approval_changed'] is False
    assert actual['position_guidance'] is None
    assert json.loads((output / 'consumed-review.json').read_bytes())['gate']['results']['G3_估值门'] is False
    assert all(p.read_bytes() == data for p, data in before.items())
    assert old_candidate.read_bytes() == before[old_candidate]
    with pytest.raises(FileExistsError):
        revision.prepare_source_reobservation(**kwargs)
    upstream = root / 'runtime/reference/upstream.json'
    upstream.write_bytes(upstream.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='source drift'):
        candidate_module.verify_pending_research_candidate(root=root, path=path, expected_sha256=sha256_file(path))


@pytest.mark.parametrize('change', ['source', 'recipe', 'upstream', 'manifest', 'policy', 'symbol', 'unknown-source', 'outside'])
def test_drift_and_invalid_scope_fail_before_output(repair_inputs, change):
    kwargs, _, _ = repair_inputs
    root = kwargs['root']
    paths = dict(source='runtime/reference/evidence.json', recipe='scripts/reference_recipe.py',
        upstream='runtime/reference/upstream.json', manifest='runtime/reference/manifest.json',
        policy=kwargs['policy_binding']['path'])
    if change in paths:
        path = root / paths[change]
        path.write_bytes(path.read_bytes() + b'\nchanged\n')
    elif change == 'symbol':
        kwargs['symbol'] = '000002'
    elif change == 'unknown-source':
        kwargs['source_ids'] = ['does-not-exist']
    else:
        kwargs['output_dir'] = root.parent / 'outside-source-revision'
    with pytest.raises((ValueError, KeyError)):
        revision.prepare_source_reobservation(**kwargs)
    assert not kwargs['output_dir'].exists()


@pytest.mark.parametrize('change', [None, 'raw', 'issuer', 'http-status'])
def test_quote_response_verification_is_real_and_never_promotes_price(repair_inputs, change):
    from test_quote_session_collection import Session
    from test_quote_sessions import NOW
    from value_investment_agent.quote_session_collection import collect_session_bundle

    kwargs, package, _ = repair_inputs
    root = kwargs['root']
    bundle = collect_session_bundle(['600519' if change == 'issuer' else kwargs['symbol']],
        session=Session(), clock=lambda: NOW)
    if change in ('raw', 'http-status'):
        identity = bundle['references'][kwargs['symbol']]['document_refs']['tencent']
        bundle['documents'][identity]['raw_base64' if change == 'raw' else 'http_status'] = (
            'Y2hhbmdlZA==' if change == 'raw' else 500)
    bundle_path = root / 'runtime/quote/bundle.json'
    write(bundle_path, bundle)
    package['sources'].append(dict(id='quote-archive', kind='quote_session',
        location='runtime/quote/bundle.json', local_path='runtime/quote/bundle.json', sha256=sha256_file(bundle_path),
        retrieved_at='2026-09-23T00:56:34+00:00', source_available_at=package['point_in_time']['computed_at'],
        availability_basis='old-producer-default'))
    registry_path = root / kwargs['case_registry_binding']['path']
    registry = json.loads(registry_path.read_bytes())
    package_path = root / registry['cases'][kwargs['symbol']]['package']
    write(package_path, package)
    registry['cases'][kwargs['symbol']]['package_sha256'] = sha256_file(package_path)
    write(registry_path, registry)
    kwargs['case_registry_binding'] = binding(root, registry_path)
    kwargs['source_ids'].append('quote-archive')
    if change:
        with pytest.raises(ValueError):
            revision.prepare_source_reobservation(**kwargs)
        assert not kwargs['output_dir'].exists()
    else:
        result = revision.prepare_source_reobservation(**kwargs)
        receipt = json.loads((root / result['receipt_binding']['path']).read_bytes())
        proof = receipt['observations'][-1]['verification']
        assert proof['historical_session'] == '2026-09-07'
        assert receipt['price_admitted'] is False
        assert json.loads((root / result['package_binding']['path']).read_bytes())['quote'] is None


def test_stricter_contract_cannot_be_downgraded_for_the_legacy_producer(repair_inputs):
    kwargs, package, _ = repair_inputs
    root = kwargs['root']
    registry_path = root / kwargs['case_registry_binding']['path']
    registry = json.loads(registry_path.read_bytes())
    path = root / registry['cases'][kwargs['symbol']]['package']
    package['source_contract']['schema_version'] = 'source-bound-research-inputs-v2'
    write(path, package)
    registry['cases'][kwargs['symbol']]['package_sha256'] = sha256_file(path)
    write(registry_path, registry)
    kwargs['case_registry_binding'] = binding(root, registry_path)
    with pytest.raises(ValueError, match='never downgrade'):
        revision.prepare_source_reobservation(**kwargs)
    assert not kwargs['output_dir'].exists()


@pytest.mark.parametrize('change', ['economics', 'policy', 'time', 'admission', 'registry-schedule'])
def test_rehashed_successor_tampering_is_rejected(repair_inputs, change):
    kwargs, _, _ = repair_inputs
    root = kwargs['root']
    result = revision.prepare_source_reobservation(**kwargs)
    role = ('policy_binding' if change == 'policy' else 'receipt_binding'
        if change == 'admission' else 'case_registry_binding' if change == 'registry-schedule' else 'package_binding')
    path = root / result[role]['path']
    data = json.loads(path.read_bytes())
    if change == 'economics':
        data['facts']['scenario_inputs']['base']['cost_of_equity'] = '0.01'
    elif change == 'policy':
        data['choices'][0]['growth_years'] = 20
    elif change == 'time':
        data['sources'][-2]['retrieved_at'] = '2026-09-01T00:00:00+00:00'
    elif change == 'admission':
        data['approval_changed'] = True
    else:
        alternative = root / 'runtime/alternative-schedule.json'
        request = json.loads((root / 'runtime/schedule.json').read_bytes())
        request['reopen_condition_met'] = True
        write(alternative, request)
        data['cases'][kwargs['symbol']].update(schedule_request='runtime/alternative-schedule.json',
            schedule_request_sha256=sha256_file(alternative))
    write(path, data)
    result[role] = binding(root, path)
    write(kwargs['output_dir'] / 'manifest.json', result)
    with pytest.raises(ValueError):
        _verify(kwargs)


def test_midread_change_does_not_create_a_revision(repair_inputs, monkeypatch):
    kwargs, _, _ = repair_inputs
    original = revision._observations

    def changing(*args, **kw):
        result = original(*args, **kw)
        target = kwargs['root'] / 'runtime/reference/evidence.json'
        target.write_bytes(target.read_bytes() + b'\n')
        return result

    monkeypatch.setattr(revision, '_observations', changing)
    with pytest.raises(ValueError):
        revision.prepare_source_reobservation(**kwargs)
    assert not kwargs['output_dir'].exists()


def test_later_shared_registry_update_does_not_change_the_retained_revision(repair_inputs):
    kwargs, _, _ = repair_inputs
    root = kwargs['root']
    original = root / kwargs['case_registry_binding']['path']
    original_bytes = original.read_bytes()
    result = revision.prepare_source_reobservation(**kwargs)
    receipt = json.loads((root / result['receipt_binding']['path']).read_bytes())
    snapshot = root / receipt['case_registry_binding']['path']
    assert snapshot.parent == kwargs['output_dir']
    assert snapshot.read_bytes() == original_bytes
    assert receipt['observed_case_registry'] == dict(
        original_path=kwargs['case_registry_binding']['path'],
        observed_sha256=kwargs['case_registry_binding']['sha256'])
    original.write_bytes(original_bytes + b'\n')
    assert _verify(kwargs) == result
    snapshot.write_bytes(original_bytes + b'\n')
    with pytest.raises(ValueError, match='binding drift'):
        _verify(kwargs)

"""Synthetic exact-input replay and isolated Web publication contracts."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from test_pending_research_candidate import candidate_inputs, run
from value_investment_agent.application.product import pending_candidate_replay as replay
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.pending_research_candidate import verify_pending_research_candidate
from value_investment_agent.application.product.pending_replay_publication import (
    POINTER_PATH, POINTER_SCHEMA, load_current_pending_replay,
    prepare_pending_replay_publication, verify_pending_replay_publication,
)
from value_investment_agent.application.product.research_reviews import prepare_pending_review_intake
from value_investment_agent.application.product.user_research_workflow import selected_review_candidate


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return dict(path=path, sha256=sha256_file(path))


def binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


@pytest.fixture
def stale(tmp_path, synthetic_pending_candidate_clock):
    code_root = Path(__file__).resolve().parents[1]
    for name in replay.IMPLEMENTATIONS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((code_root / name).read_bytes())
    producer = tmp_path / replay.GENERATOR
    current_bytes = producer.read_bytes()
    producer.write_bytes(current_bytes + b'\n# synthetic retained producer\n')
    package, policy, request = candidate_inputs(tmp_path)
    inputs = json.loads(package.read_text(encoding='utf-8'))
    inputs['facts']['valuation_timing'] = dict(basis_at='2026-06-30T23:59:59+08:00',
        valuation_at='2026-09-22T16:00:00+08:00', evidence_refs=[dict(id='facts')])
    inputs['dependencies']['model_version'] = 'residual-income-equity-shared-dated-v2'
    write(package, inputs)
    policy_data = json.loads(policy.read_text(encoding='utf-8'))
    policy_data['source_package_sha256'] = sha256_file(package)
    policy_data['human_review_groups'] = [dict(id='ECONOMICS',
        question='Does historical profitability persist?', support='Synthetic facts only.',
        countercase='Persistence is unproven.', impact='Conditional economics remain unapproved.',
        field_paths=['facts.scenario_inputs'])]
    write(policy, policy_data)
    candidate = run(tmp_path, package, policy, request)
    path = tmp_path / 'runtime/pending/candidate.json'
    verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))
    producer.write_bytes(current_bytes)
    return tmp_path, path, candidate


def prepare(stale):
    root, path, _ = stale
    return replay.prepare_pending_candidate_replay(root=root, predecessor_path=path,
        predecessor_sha256=sha256_file(path), output_dir=root / 'runtime/replay')


def publish(root, result):
    publication = prepare_pending_replay_publication(root=root,
        candidate_binding=result['candidate_binding'], output_path=root / 'runtime/replay/publication.json')
    candidate = json.loads((root / result['candidate_binding']['path']).read_text(encoding='utf-8'))
    write(root / POINTER_PATH, dict(schema_version=POINTER_SCHEMA, action='no_order',
        publications={candidate['symbol']: publication['publication_binding']}))
    return publication


def test_real_application_replay_freezes_entire_package_and_keeps_old_receipt_invalid(stale):
    root, old_path, old = stale
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='implementation drift'):
        verify_pending_research_candidate(root=root, path=old_path, expected_sha256=sha256_file(old_path))
    result = prepare(stale)
    path = root / result['candidate_binding']['path']
    candidate = replay.verify_pending_candidate_replay(root=root, binding=result['candidate_binding'])
    assert candidate == verify_pending_research_candidate(root=root, path=path,
        expected_sha256=result['candidate_binding']['sha256'])
    assert all(p.read_bytes() == original for p, original in before.items())
    assert (path.parent / 'package.json').read_bytes() == (old_path.parent / 'package.json').read_bytes()
    assert candidate['candidate_research_as_of'] == old['candidate_research_as_of']
    assert candidate['model_context'] == old['model_context']
    assert candidate['candidate_valuation'] == old['candidate_valuation']
    assert candidate['generated_at'] != old['generated_at']
    assert candidate['research_date_advanced'] is candidate['valuation_date_advanced'] is False
    assert candidate['predecessor_binding'] == binding(root, old_path)
    assert len(candidate['implementation_bindings']) == len(replay.IMPLEMENTATIONS)
    for flag in replay.BOUNDARY_FLAGS:
        assert candidate[flag] is False
    assert candidate['position_guidance'] is None
    assert candidate['schedule_gate']['allowed'] is True
    packet = json.loads((path.parent / 'consumed-review.json').read_text(encoding='utf-8'))
    assert packet['gate']['results']['G3_估值门'] is False
    intake = prepare_pending_review_intake(root=root, candidate_path=path,
        candidate_sha256=result['candidate_binding']['sha256'])
    assert intake['status'] == 'AWAITING_HUMAN_RESPONSES'
    assert not (root / 'runtime/research-evidence-stop-consumptions').exists()
    assert not (root / 'runtime/research-evidence-stop-resolutions').exists()
    with pytest.raises(FileExistsError):
        prepare(stale)
    with pytest.raises(ValueError, match='implementation drift'):
        verify_pending_research_candidate(root=root, path=old_path, expected_sha256=sha256_file(old_path))


@pytest.mark.parametrize('change', ['receipt', 'source', 'policy', 'not-stale', 'approved', 'context', 'values'])
def test_predecessor_drift_or_admission_never_creates_a_successor(stale, change):
    root, path, candidate = stale
    digest = sha256_file(path)
    if change == 'receipt':
        path.write_bytes(path.read_bytes() + b'\n')
    elif change == 'source':
        (root / 'runtime/original.md').write_text('changed source', encoding='utf-8')
    elif change == 'policy':
        policy = root / candidate['economic_policy_binding']['path']
        policy.write_bytes(policy.read_bytes() + b'\n')
    elif change == 'not-stale':
        candidate['implementation_bindings'][0]['sha256'] = sha256_file(root / replay.GENERATOR)
        write(path, candidate)
        digest = sha256_file(path)
    else:
        if change == 'approved':
            candidate['research_admitted'] = True
        elif change == 'context':
            candidate['model_context']['facts_sha256'] = '0' * 64
        else:
            candidate['candidate_valuation']['base_value'] = '999999'
        write(path, candidate)
        digest = sha256_file(path)
    with pytest.raises(ValueError):
        replay.prepare_pending_candidate_replay(root=root, predecessor_path=path,
            predecessor_sha256=digest, output_dir=root / 'runtime/replay')
    assert not (root / 'runtime/replay').exists()


def test_current_scheduler_stop_is_retained_without_reopen_or_candidate(stale):
    root, _, old = stale
    stop = dict(stop_id='exact-review-stop', symbol=old['symbol'], source_id='LOCAL_VERIFIED_RESEARCH',
        period=old['financial_period'], research_question_id='consumed_input_review_handoff',
        blocker_id='exact_version_review_candidate_missing', reviewed_evidence_ids=['facts'],
        reopen_condition='Independent authorization, not a replay')
    ledger = root / 'config/research-evidence-stop-ledger-v1.json'
    write(ledger, dict(schema_version='research-evidence-stop-ledger-v1', stops=[stop]))
    before = ledger.read_bytes()
    with pytest.raises(ValueError, match='blocked by current scheduler'):
        prepare(stale)
    assert ledger.read_bytes() == before
    assert not (root / 'runtime/replay/candidate.json').exists()
    assert not (root / 'runtime/research-evidence-stop-consumptions').exists()


@pytest.mark.parametrize('change', ['valuation', 'descriptor', 'implementation', 'source'])
def test_drift_during_actual_replay_is_not_resealed(stale, monkeypatch, change):
    root, _, _ = stale
    actual = replay.build_current_workbench_for_symbol

    def changed(**kwargs):
        result = actual(**kwargs)
        if change == 'valuation':
            result['result']['valuation']['base_value'] = '999999'
        elif change == 'descriptor':
            result['result']['input_descriptor_sha256'] = '0' * 64
        else:
            target = root / (replay.IMPLEMENTATIONS[1] if change == 'implementation' else 'runtime/original.md')
            target.write_bytes(target.read_bytes() + b'\nchanged\n')
        return result

    monkeypatch.setattr(replay, 'build_current_workbench_for_symbol', changed)
    with pytest.raises(ValueError):
        prepare(stale)
    assert not (root / 'runtime/replay/candidate.json').exists()


def test_web_registry_integrates_only_verified_supplement_without_old_publication_bypass(stale):
    root, _, old = stale
    result = prepare(stale)
    assert load_current_pending_replay(root=root, symbol=old['symbol']) is None
    publication = publish(root, result)
    assert verify_pending_replay_publication(root=root,
        binding=publication['publication_binding'])['candidate_binding'] == result['candidate_binding']
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    loaded = load_current_pending_replay(root=root, symbol=old['symbol'])
    assert loaded['publication_binding'] == publication['publication_binding']
    assert loaded['candidate']['candidate_valuation'] == old['candidate_valuation']
    assert loaded['scope'] == 'UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY'
    assert loaded['research_admitted'] is loaded['price_admitted'] is loaded['canonical_written'] is False
    assert load_current_pending_replay(root=root, symbol='600741') is None
    write(root / 'config/user-research-workflow-v1.json', dict(schema_version='user-research-workflow-v1',
        action='no_order', review_candidates={old['symbol']: result['candidate_binding']}))
    with pytest.raises(ValueError, match='not bound to current publication'):
        selected_review_candidate(root=root, symbol=old['symbol'], published={'source_bindings': []})
    assert all(p.read_bytes() == original for p, original in before.items())
    assert not (root / 'canonical.xlsx').exists()
    assert not (root / 'config/current-trial-workbook.json').exists()


@pytest.mark.parametrize('change', ['package', 'packet', 'implementation', 'lineage', 'scope', 'future', 'foreign'])
def test_web_adapter_rejects_drift_even_after_envelope_rehash(stale, change):
    root, _, old = stale
    result = prepare(stale)
    published = publish(root, result)
    path = root / result['candidate_binding']['path']
    publication_path = root / published['publication_binding']['path']
    if change in ('package', 'packet', 'implementation'):
        target = root / replay.IMPLEMENTATIONS[-1] if change == 'implementation' else path.parent / (
            'package.json' if change == 'package' else 'consumed-review.json')
        target.write_bytes(target.read_bytes() + b'\n')
    elif change in ('lineage', 'scope', 'future'):
        payload = json.loads(publication_path.read_text(encoding='utf-8'))
        if change == 'lineage':
            payload['predecessor_binding']['sha256'] = '0' * 64
        elif change == 'scope':
            payload['research_admitted'] = True
        else:
            payload['generated_at'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        write(publication_path, payload)
        write(root / POINTER_PATH, dict(schema_version=POINTER_SCHEMA, action='no_order',
            publications={old['symbol']: binding(root, publication_path)}))
    else:
        write(root / POINTER_PATH, dict(schema_version=POINTER_SCHEMA, action='no_order',
            publications={'600741': published['publication_binding']}))
    with pytest.raises(ValueError):
        load_current_pending_replay(root=root, symbol='600741' if change == 'foreign' else old['symbol'])


def test_rehashed_successor_cannot_claim_date_advancement(stale):
    root, _, _ = stale
    result = prepare(stale)
    path = root / result['candidate_binding']['path']
    data = json.loads(path.read_text(encoding='utf-8'))
    data['research_date_advanced'] = True
    write(path, data)
    # Generic legacy validation does not interpret the successor extension.
    verify_pending_research_candidate(root=root, path=path, expected_sha256=sha256_file(path))
    with pytest.raises(ValueError, match='exact predecessor/successor contract'):
        replay.verify_pending_candidate_replay(root=root, binding=binding(root, path))


@pytest.mark.parametrize('field', ['scenarios', 'assumptions', 'research-date', 'valuation-date'])
def test_resealed_package_economic_changes_are_rejected(stale, field):
    root, _, _ = stale
    result = prepare(stale)
    path = root / result['candidate_binding']['path']
    package_path = path.parent / 'package.json'
    old_hash = sha256_file(package_path)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    if field == 'scenarios':
        package['facts']['scenario_inputs']['base']['cost_of_equity'] = '0.01'
    elif field == 'assumptions':
        package['assumptions']['assumptions'][0]['base'] = '0.01'
    elif field == 'research-date':
        package['point_in_time']['research_as_of'] = '2026-10-21'
    else:
        package['point_in_time']['valuation_date'] = '2026-10-21'
    write(package_path, package)
    candidate = json.loads(path.read_text(encoding='utf-8'))
    source = next(item for item in candidate['source_bindings']
                  if item['path'] == package_path.relative_to(root).as_posix())
    assert source['sha256'] == old_hash
    source['sha256'] = sha256_file(package_path)
    write(path, candidate)
    with pytest.raises(ValueError):
        replay.verify_pending_candidate_replay(root=root, binding=binding(root, path))


def test_replay_output_cannot_escape_runtime_or_overwrite_predecessor(stale):
    root, old_path, _ = stale
    before = old_path.read_bytes()
    for target in (root / 'config/replay', old_path.parent):
        with pytest.raises((ValueError, FileExistsError)):
            replay.prepare_pending_candidate_replay(root=root, predecessor_path=old_path,
                predecessor_sha256=sha256_file(old_path), output_dir=target)
    assert old_path.read_bytes() == before


def test_legacy_availability_conflict_is_not_repaired_by_rewriting_dates(stale):
    root, path, candidate = stale
    package_path = path.parent / 'package.json'
    package = json.loads(package_path.read_text(encoding='utf-8'))
    source = package['sources'][0]
    source['retrieved_at'] = '2026-09-21T00:00:00+08:00'
    source['source_available_at'] = '2026-10-11T00:00:00+08:00'
    source['availability_basis'] = 'current_candidate_acquisition'
    write(package_path, package)
    for item in candidate['source_bindings']:
        if item['path'] == package_path.relative_to(root).as_posix():
            item['sha256'] = sha256_file(package_path)
    write(path, candidate)
    before = package_path.read_bytes()
    with pytest.raises(ValueError, match='retrieval precedes observed availability'):
        prepare((root, path, candidate))
    assert package_path.read_bytes() == before
    assert not (root / 'runtime/replay').exists()


@pytest.mark.parametrize('timestamp', ['backdated', 'future', 'naive'])
def test_rehashed_replay_receipt_cannot_fake_its_actual_availability(stale, timestamp):
    root, _, old = stale
    result = prepare(stale)
    path = root / result['candidate_binding']['path']
    candidate = json.loads(path.read_text(encoding='utf-8'))
    if timestamp == 'backdated':
        candidate['generated_at'] = old['generated_at']
    else:
        at = datetime.now(timezone.utc) + timedelta(days=1)
        if timestamp == 'naive':
            at = at.replace(tzinfo=None)
        candidate['generated_at'] = at.isoformat()
    write(path, candidate)
    with pytest.raises(ValueError):
        replay.verify_pending_candidate_replay(root=root, binding=binding(root, path))

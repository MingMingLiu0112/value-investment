"""Isolated official-response replay; synthetic originals never grant approval."""
from datetime import date, datetime, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

import pytest

from test_d2_source_bound_package_contract import source_package
from value_investment_agent import disclosures
from value_investment_agent.application.product import daily_event_observation as collector
from value_investment_agent.application.product import event_scan_supplement as service


def read(path):
    return json.loads(path.read_bytes())


def save(root, path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return dict(path=path.relative_to(root).as_posix(), sha256=service.sha256_file(path))


@pytest.fixture
def inputs(source_package, monkeypatch):
    root, package = source_package
    package['model_validity_input'] = dict(model_id=package['dependencies']['model_version'],
        valid_from='2026-09-22', events=[], blockers=['pending_complete_event_materiality_review'])
    base = save(root, root / 'runtime/base/package.json', package)

    def pdf(url, path):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with path.open('wb') as stream:
            writer.write(stream)
        return service.sha256_file(path)

    def request(parameters, *, raw_response_sink):
        rows = []
        if parameters['seDate'].startswith('2026-09-01'):
            rows = [dict(secCode=package['symbol'], orgId='TEST_ONLY_org', announcementId='123',
                announcementTitle='TEST_ONLY pre-model filing', adjunctUrl='finalpage/2026-09-20/123.PDF',
                announcementTime=int(datetime(2026, 9, 20, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()*1000))]
        payload = dict(totalAnnouncement=len(rows), announcements=rows, hasMore=False)
        if not parameters['seDate']:
            payload = dict(totalAnnouncement=1, announcements=[dict(secCode=package['symbol'], orgId='TEST_ONLY_org')])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method='POST', request=parameters,
            page=int(parameters['pageNum']), acquired_at=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body)))
        return payload

    monkeypatch.setattr(disclosures, '_request_json', request)
    monkeypatch.setattr(collector, 'download_disclosure_pdf', pdf)
    windows = []
    for index, (start, end) in enumerate([('2026-09-01', '2026-09-21'), ('2026-09-22', '2026-09-23')]):
        folder = root / f'runtime/window-{index}'
        observation = collector.collect_daily_event_observation(root=root, symbol=package['symbol'],
            issuer_name='TEST_ONLY', start=date.fromisoformat(start), end=date.fromisoformat(end),
            output_dir=folder, retain_raw_index=True)
        windows.append(save(root, folder / 'observation.json', observation))
    monkeypatch.setattr(disclosures, '_request_json', lambda *a, **k: pytest.fail('replay must be offline'))
    return root, package, dict(root=root, package_binding=base, observation_bindings=windows,
        coverage_from=date(2026, 9, 1), review_cutoff=date(2026, 9, 23), output_dir=root / 'runtime/new-version')


def test_new_context_preserves_old_economics_and_replays_unsigned_handoff(inputs):
    root, original, kwargs = inputs
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    started = datetime.now(timezone.utc)
    result = service.prepare_event_scan_supplement(**kwargs)
    package = read(root / result['package_binding']['path'])
    handoff = read(root / result['handoff_binding']['path'])
    descriptor = read(root / result['descriptor_binding']['path'])
    scan = read(root / result['scan_binding']['path'])
    assert package['point_in_time']['research_as_of'] == started.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
    assert datetime.fromisoformat(package['point_in_time']['available_at']) >= started
    assert package['point_in_time']['valuation_date'] == original['point_in_time']['valuation_date']
    assert package['assumptions'] == original['assumptions']
    assert package['facts']['scenario_inputs'] == original['facts']['scenario_inputs']
    assert package['facts']['operating_inputs'] == original['facts']['operating_inputs']
    assert package['facts']['verified'] is False
    assert package['quote'] is None and package['valuation_approval'] is None
    assert result['announcement_count'] == result['pre_model_announcement_count'] == 1
    assert scan['announcements'][0]['pre_model'] is True
    assert scan['announcements'][0]['review_status'] == 'PENDING_HUMAN_REVIEW'
    assert handoff['model_context']['input_descriptor_sha256'] == descriptor['input_sha256']
    decision = handoff['unsigned_response']['event_materiality']['decisions'][0]
    assert decision['announcement_id'] == '123' and decision['human_decision'] is None
    assert decision['requires_recalculation'] is None
    assert handoff['unsigned_response']['reviewer_id'] is None
    assert all(result[key] is False for key in ('approval_changed', 'materiality_approved',
        'research_admitted', 'price_admitted', 'valuation_recomputed'))
    assert all(p.read_bytes() == body for p, body in before.items())
    receipt = service._binding(root, kwargs['output_dir'] / 'supplement.json')
    assert service.verify_event_scan_supplement(root=root, binding=receipt) == result
    with pytest.raises(FileExistsError):
        service.prepare_event_scan_supplement(**kwargs)


@pytest.mark.parametrize('mutation', ['gap', 'overlap', 'symbol', 'future', 'hash', 'traversal', 'partial'])
def test_invalid_window_bindings_fail_before_output(inputs, mutation):
    root, _, kwargs = inputs
    binding = kwargs['observation_bindings'][1]
    observation = read(root / binding['path'])
    if mutation == 'gap':
        kwargs['observation_bindings'] = kwargs['observation_bindings'][:1]
    elif mutation == 'overlap':
        kwargs['observation_bindings'][1] = kwargs['observation_bindings'][0]
    elif mutation == 'hash':
        binding['sha256'] = '0' * 64
    elif mutation == 'traversal':
        binding['path'] = '../outside.json'
    else:
        if mutation == 'symbol':
            observation['symbol'] = '000001'
        elif mutation == 'future':
            observation['acquired_at'] = '2099-01-01T00:00:00+00:00'
        else:
            observation['full_calendar_window_elapsed'] = False
        kwargs['observation_bindings'][1] = save(root, root / binding['path'], observation)
    with pytest.raises(ValueError):
        service.prepare_event_scan_supplement(**kwargs)
    assert not kwargs['output_dir'].exists()


@pytest.mark.parametrize('target', ['raw', 'package', 'scan', 'handoff', 'receipt'])
def test_rebound_tampering_fails_replay(inputs, target):
    root, _, kwargs = inputs
    result = service.prepare_event_scan_supplement(**kwargs)
    if target == 'raw':
        (root / 'runtime/window-0/raw-index/response-0002.bin').write_bytes(b'changed raw bytes')
    elif target == 'receipt':
        result['materiality_approved'] = True
    else:
        key = {'package': 'package_binding', 'scan': 'scan_binding', 'handoff': 'handoff_binding'}[target]
        path = root / result[key]['path']
        data = read(path)
        if target == 'package':
            data['facts']['verified'] = True
        elif target == 'scan':
            data['announcements'] = []
        else:
            data['unsigned_response']['event_materiality']['decisions'][0]['human_decision'] = 'NOT_MATERIAL'
        result[key] = save(root, path, data)
    receipt = save(root, kwargs['output_dir'] / 'supplement.json', result)
    with pytest.raises(ValueError):
        service.verify_event_scan_supplement(root=root, binding=receipt)


def test_predecessor_approvals_are_not_carried_to_new_context(inputs):
    root, original, kwargs = inputs
    for key in ('human_research_approval', 'event_materiality_review', 'research_reviews',
                'valuation_approval'):
        original[key] = {'TEST_ONLY': 'old context cannot authorize new context'}
    kwargs['package_binding'] = save(root, root / kwargs['package_binding']['path'], original)
    result = service.prepare_event_scan_supplement(**kwargs)
    package = read(root / result['package_binding']['path'])
    for key in ('human_research_approval', 'event_materiality_review', 'research_reviews'):
        assert key not in package
    for key in ('valuation_approval', 'entry_thesis', 'investment_consistency_review'):
        assert package[key] is None
    assert package['research_case']['research_status'] == 'DATA_CHECK'
    assert package['research_case']['valuation_status'] == 'NOT_ASSESSED'


@pytest.mark.parametrize('key', ['entry_thesis', 'investment_consistency_review'])
def test_invalid_typed_decisions_cannot_be_laundered_by_supplement(inputs, key):
    root, original, kwargs = inputs
    original[key] = {'TEST_ONLY': 'invalid typed economic object'}
    kwargs['package_binding'] = save(root, root / kwargs['package_binding']['path'], original)
    with pytest.raises(ValueError):
        service.prepare_event_scan_supplement(**kwargs)
    assert not kwargs['output_dir'].exists()


def test_current_day_is_not_a_completed_cutoff_even_if_declared_complete(inputs):
    root, _, kwargs = inputs
    binding = kwargs['observation_bindings'][1]
    observation = read(root / binding['path'])
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    observation['scan_to'] = today.isoformat()
    observation['full_calendar_window_elapsed'] = True
    kwargs['review_cutoff'] = today
    kwargs['observation_bindings'][1] = save(root, root / binding['path'], observation)
    with pytest.raises(ValueError, match='elapsed'):
        service.prepare_event_scan_supplement(**kwargs)
    assert not kwargs['output_dir'].exists()


def test_altered_predecessor_original_is_not_rescued_by_new_version(inputs):
    root, original, kwargs = inputs
    (root / original['sources'][0]['local_path']).write_bytes(b'changed underlying financial source')
    with pytest.raises(ValueError):
        service.prepare_event_scan_supplement(**kwargs)
    assert not kwargs['output_dir'].exists()


@pytest.fixture
def consumed(inputs):
    root, _, kwargs = inputs
    service.prepare_event_scan_supplement(**kwargs)
    save(root, root / 'config/research-evidence-stop-ledger-v1.json',
         dict(schema_version='research-evidence-stop-ledger-v1', stops=[]))
    supplement = service._binding(root, kwargs['output_dir'] / 'supplement.json')
    result = service.consume_event_scan_supplement(root=root, supplement_binding=supplement,
                                                  output_dir=root / 'runtime/consumed')
    return root, supplement, result


def test_existing_workbench_and_review_packet_consume_exact_event_context(consumed):
    root, supplement, result = consumed
    original = service.verify_event_scan_supplement(root=root, binding=supplement)
    workbench = read(root / result['workbench_binding']['path'])
    packet = read(root / result['review_packet_binding']['path'])
    assert result['model_context_scope'] == 'ACTUALLY_CONSUMED'
    assert workbench['input_descriptor_sha256'] == packet['input_descriptor_sha256'] == original['model_context']['input_descriptor_sha256']
    assert result['model_context'] == original['model_context']
    assert result['candidate_binding'] is None
    assert result['g3_candidate_status'] == 'UNAVAILABLE_UNASSESSED_VALUATION'
    assert workbench['valuation']['status'] == 'not_ready'
    assert all(workbench['valuation'][key] is None for key in ('bear_value', 'base_value', 'bull_value'))
    assert not (root / 'runtime/consumed/candidate.json').exists()
    assert not (root / 'runtime/research-review-responses').exists()
    assert result['consumer']['entrypoint'] == 'scripts/current/review_materiality.py'
    binding = service._binding(root, root / 'runtime/consumed/consumption.json')
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert service.verify_consumed_event_scan_supplement(root=root, binding=binding) == result
    assert all(p.read_bytes() == body for p, body in before.items())


@pytest.mark.parametrize('target', ['packet', 'receipt', 'scope'])
def test_rehashed_consumption_cannot_change_signing_scope(consumed, target):
    root, _, result = consumed
    if target == 'receipt':
        result['candidate_binding'] = result['workbench_binding']
    else:
        key = 'review_packet_binding' if target == 'packet' else 'schedule_binding'
        path = root / result[key]['path']
        payload = read(path)
        if target == 'packet':
            payload['input_descriptor_sha256'] = '0' * 64
        else:
            payload['reopen_condition_met'] = True
        result[key] = save(root, path, payload)
    binding = save(root, root / 'runtime/consumed/consumption.json', result)
    with pytest.raises(ValueError):
        service.verify_consumed_event_scan_supplement(root=root, binding=binding)


def test_active_stop_cannot_be_bypassed_or_claimed_by_event_supplement(inputs):
    root, package, kwargs = inputs
    service.prepare_event_scan_supplement(**kwargs)
    stop = dict(stop_id='TEST_ONLY_stop', symbol=package['symbol'], source_id='CNINFO',
        period='TEST_ONLY', research_question_id='TEST_ONLY', blocker_id='TEST_ONLY',
        reviewed_evidence_ids=[], reopen_condition='TEST_ONLY actual new evidence required')
    save(root, root / 'config/research-evidence-stop-ledger-v1.json',
         dict(schema_version='research-evidence-stop-ledger-v1', stops=[stop]))
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Active Evidence Stop'):
        service.consume_event_scan_supplement(root=root,
            supplement_binding=service._binding(root, kwargs['output_dir'] / 'supplement.json'),
            output_dir=root / 'runtime/denied')
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


def test_bound_draft_adapter_rejects_unvalued_consumed_case_without_fabrication(consumed):
    from value_investment_agent.application.product.research_draft import (
        BOUND_DRAFT_SCHEMA, DRAFT_STATUS, POINTER_SCHEMA, _validate_draft, load_current_research_draft,
    )
    from value_investment_agent.application.product.bound_draft_review import prepare_bound_draft_review_candidate

    root, supplement_binding, result = consumed
    supplement = service.verify_event_scan_supplement(root=root, binding=supplement_binding)
    workbench = read(root / result['workbench_binding']['path'])
    draft = dict(schema_version=BOUND_DRAFT_SCHEMA, symbol=result['symbol'], action='no_order',
        status=DRAFT_STATUS, available_at=datetime.now(timezone.utc).isoformat(),
        research_as_of=result['model_context']['research_as_of'], valuation=workbench['valuation'],
        model_input_binding=dict(package=supplement['package_binding'],
                                 input_sha256=result['model_context']['input_descriptor_sha256']))
    ref = save(root, root / 'artifacts/current/TEST_ONLY-event-draft.json', draft)
    save(root, root / 'config/current-research-drafts.json',
         dict(schema_version=POINTER_SCHEMA, action='no_order', drafts={result['symbol']: ref}))
    with pytest.raises(ValueError, match='valuation is not conditional'):
        _validate_draft(draft, result['symbol'], datetime.now(timezone.utc))
    assert load_current_research_draft(root, result['symbol']) is None
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='CURRENT_SOURCE_BOUND_DRAFT_UNAVAILABLE'):
        prepare_bound_draft_review_candidate(root=root, symbol=result['symbol'], output_dir=root / 'runtime/blocked-bound-review')
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('mutation', [None, 'wrong_context', 'source_bytes'])
def test_new_consumed_context_uses_existing_authenticated_materiality_contract(consumed, mutation):
    """TEST_ONLY key and classifications stay entirely inside the isolated root."""
    from copy import deepcopy
    from datetime import timedelta
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from value_investment_agent.application.product.research_materiality_reviews import (
        MATERIALITY_RESPONSE_PURPOSE, consume_materiality_review_response,
    )
    from value_investment_agent.application.product.research_reviews import attach_research_reviews
    from value_investment_agent.application.product.company_research import run_company_research_for_symbol
    from value_investment_agent.infrastructure.evidence.trust_root_registry import (
        _use_test_trust_registry, trust_root_fingerprint,
    )
    from value_investment_agent.research_run_contract import canonical_contract_payload

    root, supplement_binding, result = consumed
    supplement = service.verify_event_scan_supplement(root=root, binding=supplement_binding)
    handoff = read(root / result['handoff_binding']['path'])
    payload = deepcopy(handoff['unsigned_response'])
    now = datetime.now(timezone.utc)
    stamp, reviewer = now.isoformat(), 'TEST_ONLY_EVENT_REVIEWER'
    payload.update(reviewer_id=reviewer, reviewed_at=stamp)
    review = payload['event_materiality']
    review.update(review_id='TEST_ONLY_review', reviewed_at=stamp, review_as_of=now.date().isoformat(), reviewer_id=reviewer)
    for decision in review['decisions']:
        decision.update(event_decision_id='TEST_ONLY_' + decision['announcement_id'],
            reviewer_id=reviewer, reviewed_at=stamp, human_decision='NOT_MATERIAL',
            requires_recalculation=False, requires_model_stale=False, requires_followup=False,
            review_notes=['TEST_ONLY synthetic original; no real issuer approval'])
    if mutation == 'wrong_context':
        payload['model_context']['input_descriptor_sha256'] = '0' * 64
    key = Ed25519PrivateKey.generate()
    trust = dict(schema_version='research-review-transport-trust-root-v1', reviewer_id=reviewer,
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        scopes=['human_event_materiality'], symbols=[result['symbol']],
        valid_from=(now-timedelta(days=1)).isoformat(), valid_until=(now+timedelta(days=1)).isoformat())
    registry = save(root, root / 'runtime/TEST_ONLY-registry.json',
        dict(schema_version='authorization-trust-root-registry-v1', pinned_trust_root_sha256=[trust_root_fingerprint(trust)]))
    response = save(root, root / 'runtime/TEST_ONLY-response.json', dict(payload=payload,
        signature=key.sign(MATERIALITY_RESPONSE_PURPOSE + canonical_contract_payload(payload).encode('utf-8')).hex()))
    trust_ref = save(root, root / 'runtime/TEST_ONLY-trust.json', trust)
    if mutation == 'source_bytes':
        source = handoff['announcements'][0]['evidence_refs'][0]
        (root / source['path']).write_bytes(b'TEST_ONLY changed original')
    args = dict(root=root, handoff_path=root / result['handoff_binding']['path'],
        handoff_sha256=result['handoff_binding']['sha256'], response_path=root / response['path'],
        response_sha256=response['sha256'], trust_root_path=root / trust_ref['path'],
        trust_root_sha256=trust_ref['sha256'], output_dir=root / 'runtime/TEST_ONLY-import')
    with _use_test_trust_registry(root / registry['path']):
        if mutation:
            with pytest.raises(ValueError):
                consume_materiality_review_response(**args)
            assert not args['output_dir'].exists()
            return
        receipt = consume_materiality_review_response(**args)
        packet_ref = receipt['review_packet_binding']
        descriptor = service.build_materiality_review_descriptor(root=root,
            package_binding=supplement['package_binding'], scan_binding=supplement['scan_binding'])
        spec = attach_research_reviews(root=root, descriptor=descriptor,
            spec=service.build_research_run_spec(descriptor), path=root / packet_ref['path'],
            expected_sha256=packet_ref['sha256'], event_sha256=supplement['scan_binding']['sha256'],
            require_model_binding=True)
        assert spec.event_materiality_review is not None and spec.human_research_approval is None
        scope = read(root / result['schedule_binding']['path'])
        actual = run_company_research_for_symbol(root=root, symbol=result['symbol'],
            package_path=root / supplement['package_binding']['path'], schedule_request=scope,
            schedule_request_sha256=result['schedule_binding']['sha256'],
            reviews_path=root / packet_ref['path'], reviews_sha256=packet_ref['sha256'])['result']
        assert actual['event_materiality_review']['review_id'] == 'TEST_ONLY_review'
        # Attachment deliberately derives a new execution hash from the reviewed
        # descriptor, authenticated packet and exact original model context.
        assert actual['input_descriptor_sha256'] == spec.input_descriptor_sha256
        assert receipt['model_context'] == result['model_context']
        assert actual['input_descriptor_sha256'] != result['model_context']['input_descriptor_sha256']
        assert actual['valuation']['base_value'] is None and actual['human_research_approval'] is None
        assert receipt['whole_model_approved'] is receipt['research_admitted'] is receipt['price_admitted'] is False

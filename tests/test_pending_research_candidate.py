"""Shared candidate contracts use synthetic inputs, never issuer approval."""
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

pytestmark = pytest.mark.usefixtures('synthetic_pending_candidate_clock')

from test_neutral_valuation_proposal import proposal_inputs
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.pending_research_candidate import (
    prepare_pending_research_candidate, verify_pending_research_candidate,
)
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.research_artifact_codecs import artifact_payload


def candidate_inputs(root):
    package_path, policy_path = proposal_inputs(root)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    package['sources'][0]['issuer_identity'] = dict(venue='CNINFO',
        security_code=package['symbol'], issuer_name=package['name'], organization_id='gssh0600887')
    ref = package['facts']['evidence_refs'][0]
    package['research_case']['evidence_refs'] = [ref]
    for field in ('positives', 'counter_evidence', 'thesis_breakers', 'next_events'):
        for item in package['research_case'].get(field, []):
            item['evidence_refs'] = ['facts']
    package_path.write_text(json.dumps(package), encoding='utf-8')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['source_package_sha256'] = sha256_file(package_path)
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    (root / 'config').mkdir()
    (root / 'config/research-evidence-stop-ledger-v1.json').write_text(
        json.dumps({'schema_version': 'research-evidence-stop-ledger-v1', 'stops': []}), encoding='utf-8')
    request = dict(schema_version='research-schedule-request-v1', symbol=package['symbol'],
        source_id='CNINFO', period=package['point_in_time']['report_period'],
        research_question_id='pending-finite-research', blocker_id='no-active-evidence-stop',
        reopen_condition_met=False, new_evidence_ids=[])
    return package_path, policy_path, request


def run(root, package, policy, request, **kwargs):
    return prepare_pending_research_candidate(root=root, package_path=package,
        package_sha256=sha256_file(package), policy_path=policy, policy_sha256=sha256_file(policy),
        choice_id='continuity', output_dir=root / 'runtime/pending',
        schedule_request=request, schedule_request_sha256='a' * 64,
        **kwargs)


def test_selected_inputs_are_consumed_by_actual_application_without_admission(
        tmp_path, synthetic_pending_candidate_clock):
    package, policy, request = candidate_inputs(tmp_path)
    before = package.read_bytes()
    result = run(tmp_path, package, policy, request)
    assert package.read_bytes() == before
    assert result['status'] == 'PENDING_REVIEW'
    from zoneinfo import ZoneInfo
    assert result['candidate_research_as_of'] == synthetic_pending_candidate_clock.astimezone(
        ZoneInfo('Asia/Shanghai')).date().isoformat()
    assert result['prior_research_as_of'] == '2026-09-22'
    assert result['price_admitted'] is result['registered_current_case_changed'] is False
    assert result['position_guidance'] is None
    work = json.loads((tmp_path / 'runtime/pending/workbench.json').read_text(encoding='utf-8'))
    objects = verify_current_decision_workbench(work).dependency_objects
    facts = artifact_payload(objects['financial_facts'])[1]
    candidate = json.loads((tmp_path / 'runtime/pending/package.json').read_text(encoding='utf-8'))
    assert len(candidate['facts']['scenario_inputs']['base']['forecast_roes']) == 15
    assert len(candidate['assumption_bindings']) == 19 * 3
    assert facts['operating_inputs'] == candidate['facts']['operating_inputs']
    assert facts['scenario_inputs']['base']['forecast_roes'] == candidate['facts']['scenario_inputs']['base']['forecast_roes']
    assert work['suggested_state'] == 'NO_ACTION'
    assert work['valuation']['status'] == 'conditional_research_only', work['valuation']['blockers']
    assert candidate['quote'] is None
    assert candidate['model_validity_input']['blockers']
    assert candidate['source_contract']['strict_contemporaneous_pit'] == 'NOT_PROVEN'
    assert (tmp_path / 'runtime/pending/consumed-review.json').is_file()
    assert Decimal(result['candidate_valuation']['base_value']) > 0


@pytest.mark.parametrize('change', ['choice', 'future-source', 'wrong-schedule', 'original-drift'])
def test_invalid_candidates_do_not_publish_or_write_a_candidate(tmp_path, change):
    package, policy, request = candidate_inputs(tmp_path)
    if change == 'choice':
        data = json.loads(policy.read_text(encoding='utf-8'))
        data['choices'][0]['id'] = 'not-continuity'
        policy.write_text(json.dumps(data), encoding='utf-8')
    elif change == 'future-source':
        data = json.loads(package.read_text(encoding='utf-8'))
        data['sources'][0]['source_available_at'] = '2099-09-24T00:00:00+08:00'
        data['sources'][0]['availability_basis'] = 'synthetic'
        package.write_text(json.dumps(data), encoding='utf-8')
        data = json.loads(policy.read_text(encoding='utf-8'))
        data['source_package_sha256'] = sha256_file(package)
        policy.write_text(json.dumps(data), encoding='utf-8')
    elif change == 'wrong-schedule':
        request['symbol'] = '000001'
    else:
        (tmp_path / 'runtime/original.md').write_text('drift', encoding='utf-8')
    with pytest.raises(ValueError):
        run(tmp_path, package, policy, request)
    assert not (tmp_path / 'runtime/pending/candidate.json').exists()


def test_candidate_keeps_active_scheduler_stop(tmp_path):
    package, policy, request = candidate_inputs(tmp_path)
    request['blocker_id'] = 'synthetic-stop'
    stop = dict(stop_id='synthetic-stop', symbol=request['symbol'], source_id='CNINFO',
        period=request['period'], research_question_id=request['research_question_id'],
        blocker_id='synthetic-stop', reviewed_evidence_ids=['facts'], reopen_condition='new official fact')
    (tmp_path / 'config/research-evidence-stop-ledger-v1.json').write_text(json.dumps(
        {'schema_version':'research-evidence-stop-ledger-v1', 'stops':[stop]}), encoding='utf-8')
    result = run(tmp_path, package, policy, request)
    assert result['candidate_valuation'] is None
    assert result['recommendation_type'] == 'NOT_READY'
    assert result['model_context_scope'] == 'PREPARED_NOT_CONSUMED'
    assert result['research_blockers']
    assert result['decision_blockers']
    assert result['schedule_gate']
    assert not (tmp_path / 'runtime/pending/consumed-review.json').exists()


@pytest.mark.parametrize('year', [2026, 2099])
def test_actual_candidate_rejects_backdated_or_future_injected_clock(tmp_path, year):
    package, policy, request = candidate_inputs(tmp_path)
    with pytest.raises(ValueError, match='injected computation time'):
        run(tmp_path, package, policy, request,
            computed_at=datetime(year, 9, 23, 12, tzinfo=timezone.utc))
    assert not (tmp_path / 'runtime/pending').exists()


def test_grouped_economic_review_is_pinned_visible_and_not_approval(tmp_path):
    from value_investment_agent.presentation.daily_trade_assistant import _render_pending_candidate_review
    package, policy, request = candidate_inputs(tmp_path)
    data = json.loads(policy.read_text(encoding='utf-8'))
    data['human_review_groups'] = [dict(id='earnings', question='Can historical earnings persist?',
        support='Synthetic disclosed historical profit.', countercase='Synthetic impairment risk.',
        impact='Pending forecast changes, not an admitted buy price.',
        field_paths=['facts.scenario_inputs', 'research_case.financial_summary'])]
    policy.write_text(json.dumps(data), encoding='utf-8')
    result = run(tmp_path, package, policy, request)
    path = tmp_path / 'runtime/pending/candidate.json'
    text = _render_pending_candidate_review(result, sha256_file(path))
    assert 'Can historical earnings persist?' in text
    assert 'Synthetic impairment risk.' in text
    assert 'VERIFIED/REJECTED/INSUFFICIENT' in text
    assert result['approval_changed'] is False
    verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))
    result['review_groups'][0]['countercase'] = 'No risks.'
    path.write_text(json.dumps(result), encoding='utf-8')
    with pytest.raises(ValueError, match='review questions differ'):
        verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))


@pytest.mark.parametrize('change', [None, 'source', 'context', 'values', 'approval'])
def test_candidate_surface_requires_the_exact_consumed_inputs_and_boundary(tmp_path, change):
    from value_investment_agent.presentation.research_supplement_surface import project_research_supplements

    package, policy, request = candidate_inputs(tmp_path)
    run(tmp_path, package, policy, request)
    path = tmp_path / 'runtime/pending/candidate.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if change == 'source':
        (tmp_path / 'runtime/original.md').write_text('drift', encoding='utf-8')
    elif change == 'context':
        data['model_context']['facts_sha256'] = '0' * 64
    elif change == 'values':
        data['candidate_valuation']['base_value'] = '999999'
    elif change == 'approval':
        data['approval_changed'] = True
    if change not in {None, 'source'}:
        path.write_text(json.dumps(data), encoding='utf-8')
    binding = dict(role='pending_research_candidate', path='runtime/pending/candidate.json',
                   sha256=sha256_file(path))
    payload = dict(as_of='2026-09-22', companies=[dict(symbol=data['symbol'], evidence_refs=[],
        valuation=dict(status='NOT_READY'), decision_status='NO_ACTION')], audit=dict(evidence=[]))
    if change:
        with pytest.raises(ValueError):
            verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))
        with pytest.raises(ValueError):
            project_research_supplements(payload, root=tmp_path, symbol=data['symbol'], bindings=[binding])
    else:
        project_research_supplements(payload, root=tmp_path, symbol=data['symbol'], bindings=[binding])
        assert payload['as_of'] == '2026-09-22'
        assert payload['companies'][0]['decision_status'] == 'NO_ACTION'
        assert payload['companies'][0]['valuation'] == dict(status='NOT_READY')
        assert payload['companies'][0]['decision_review'][0]['label'] == '完整主估值候选待审'


def prior_session_inputs(root, monkeypatch, *, coverage_offset=0):
    """Retained TEST_ONLY B1 and official-response fixtures, without network."""
    import base64
    import hashlib
    from datetime import date, timedelta
    from zoneinfo import ZoneInfo
    from pypdf import PdfWriter
    from test_quote_sessions import evidence, sse_evidence, document
    from value_investment_agent import disclosures
    from value_investment_agent.application.product import daily_event_observation as collector
    from value_investment_agent.application.product import pending_research_candidate as service

    package, policy, request = candidate_inputs(root)
    raw = json.loads(package.read_bytes())
    coverage_start = date.fromisoformat(raw['point_in_time']['report_period']) + timedelta(days=1)
    pre_model_day = (coverage_start + timedelta(days=1)).isoformat()
    raw['facts']['valuation_timing'] = dict(basis_at='2026-06-30T23:59:59+08:00',
        valuation_at='2026-09-22T15:00:00+08:00', evidence_refs=raw['facts']['evidence_refs'])
    package.write_text(json.dumps(raw), encoding='utf-8')
    value = json.loads(policy.read_bytes())
    value['source_package_sha256'] = sha256_file(package)
    policy.write_text(json.dumps(value), encoding='utf-8')
    packet = evidence(symbol=raw['symbol'], day='2026-10-09')
    packet['calendar_exchange'] = 'SSE'
    packet['calendar_documents'] = sse_evidence(day='2026-10-09')['calendar_documents']
    for name in ('tencent', 'sina'):
        item = packet[name]
        packet[name] = document(base64.b64decode(item['raw_base64']), item['source_url'],
                                fetched='2026-10-09T09:00:00+00:00')
    documents, references = {}, {}
    for name in ('tencent', 'sina', 'calendar_documents'):
        identities = []
        for item in packet[name] if name == 'calendar_documents' else [packet[name]]:
            identity = hashlib.sha256((item['source_url'] + '\n' + item['fetched_at']
                                       + '\n' + item['sha256']).encode()).hexdigest()
            documents[identity] = dict(item, http_status=200)
            identities.append(identity)
        references[name] = identities if name == 'calendar_documents' else identities[0]
    bundle = root / 'runtime/basis-bundle.json'
    bundle.write_text(json.dumps(dict(version='quote-session-collection-v1', status='TEST_ONLY',
        finished_at='2026-10-09T09:00:00+00:00', documents=documents,
        references={raw['symbol']: dict(symbol=raw['symbol'], calendar_exchange='SSE',
                                       document_refs=references)})), encoding='utf-8')
    basis = dict(path=bundle.relative_to(root).as_posix(), sha256=sha256_file(bundle))
    monkeypatch.setattr(collector, 'datetime', service.datetime)

    def pdf(url, path):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with path.open('wb') as stream:
            writer.write(stream)
        return sha256_file(path)

    def query(parameters, *, raw_response_sink):
        if not parameters['seDate']:
            payload = dict(totalAnnouncement=1, announcements=[
                dict(secCode=raw['symbol'], orgId='TEST_ONLY_org')])
        else:
            first = parameters['seDate'].endswith('2026-10-08')
            published = pre_model_day if first else '2026-10-09'
            identity = '123' if first else '124'
            payload = dict(totalAnnouncement=1, hasMore=False, announcements=[dict(
                secCode=raw['symbol'], orgId='TEST_ONLY_org', announcementId=identity,
                announcementTitle='TEST_ONLY filing ' + identity,
                adjunctUrl='finalpage/' + published + '/' + identity + '.PDF',
                announcementTime=int(datetime.fromisoformat(published).replace(
                    tzinfo=ZoneInfo('Asia/Shanghai')).timestamp() * 1000))])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method='POST', request=parameters,
            page=int(parameters['pageNum']), acquired_at=service.datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body)))
        return payload

    monkeypatch.setattr(disclosures, '_request_json', query)
    monkeypatch.setattr(collector, 'download_disclosure_pdf', pdf)
    windows = []
    start_day = (coverage_start + timedelta(days=coverage_offset)).isoformat()
    for index, (start, end) in enumerate([(start_day, '2026-10-08'), ('2026-10-09', '2026-10-09')]):
        folder = root / f'runtime/coverage-{index}'
        collector.collect_daily_event_observation(root=root, symbol=raw['symbol'], issuer_name='TEST_ONLY',
            start=date.fromisoformat(start), end=date.fromisoformat(end), output_dir=folder,
            retain_raw_index=True)
        path = folder / 'observation.json'
        windows.append(dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path)))
    monkeypatch.setattr(disclosures, '_request_json', lambda *a, **k: pytest.fail('candidate must be offline'))
    return package, policy, request, dict(valuation_basis_quote_binding=basis,
                                         complete_coverage_windows=windows)


def test_prior_session_basis_recomputes_dated_model_and_exact_materiality_context(tmp_path, monkeypatch):
    from datetime import date
    from value_investment_agent.m1_valuation_package_builder import build_descriptor
    from value_investment_agent.research_input import build_research_run_spec
    from value_investment_agent.valuation_models.residual_income import ResidualIncomeEquityValuationModel
    from value_investment_agent.model_validity import evaluate_model_validity

    package, policy, request, kwargs = prior_session_inputs(tmp_path, monkeypatch)
    before = package.read_bytes()
    result = run(tmp_path, package, policy, request, **kwargs)
    folder = tmp_path / 'runtime/pending'
    candidate = json.loads((folder / 'package.json').read_bytes())
    handoff = json.loads((folder / 'materiality-handoff.json').read_bytes())
    scan = json.loads((folder / 'event-scan.json').read_bytes())
    assert package.read_bytes() == before
    assert result['valuation_basis_date'] == '2026-10-09'
    assert result['valuation_basis_scope'] == 'EX_POST_PRIOR_COMPLETED_SESSION'
    assert result['candidate_research_as_of'] == '2026-10-11'
    assert candidate['point_in_time']['valuation_date'] == candidate['facts']['as_of'] == '2026-10-09'
    assert candidate['facts']['valuation_timing']['valuation_at'] == '2026-10-09T15:00:00+08:00'
    assert candidate['point_in_time']['computed_at'] == result['generated_at']
    assert candidate['source_contract']['cutoff_at'] == result['generated_at']
    assert result['model_context_scope'] == 'ACTUALLY_CONSUMED'
    assert result['candidate_valuation']['model_version'] == 'residual-income-equity-shared-dated-v2'
    assert handoff['model_context'] == result['model_context']
    assert handoff['unsigned_response']['reviewer_id'] is None
    assert len(scan['announcements']) == len(handoff['announcements']) == 2
    assert [item['pre_model'] for item in scan['announcements']] == [True, False]
    spec = build_research_run_spec(build_descriptor(candidate, root=tmp_path))
    recalculated = ResidualIncomeEquityValuationModel().value(spec.facts, spec.research_case)
    assert str(recalculated.base_value) == result['candidate_valuation']['base_value']
    assert result['retained_date_valuation']['base_value'] != result['candidate_valuation']['base_value']
    assert candidate['quote'] is None and candidate['source_contract']['strict_contemporaneous_pit'] == 'NOT_PROVEN'
    assert result['materiality_approved'] is result['current_market_validity_approved'] is False
    validity = evaluate_model_validity(model_id=spec.model_validity_input.model_id, symbol=spec.symbol,
        model_as_of=date(2026, 10, 9), valid_from=date(2026, 10, 9), quote_date=date(2026, 10, 11),
        events=[], event_scan_evidence_refs=[], event_scan=spec.model_validity_input.event_scan)
    assert validity.status == 'INVALID'
    path = folder / 'candidate.json'
    assert verify_pending_research_candidate(root=tmp_path, path=path,
        expected_sha256=sha256_file(path)) == result


@pytest.mark.parametrize('mutation', ['basis-hash', 'issuer', 'future', 'stale', 'b1',
                                    'coverage-issuer', 'coverage-gap', 'partial', 'missing-basis'])
def test_prior_session_basis_rejects_invalid_acquisition_without_fallback(tmp_path, monkeypatch, mutation):
    package, policy, request, kwargs = prior_session_inputs(tmp_path, monkeypatch)
    binding = kwargs['valuation_basis_quote_binding']
    path = tmp_path / binding['path']
    if mutation == 'basis-hash':
        binding['sha256'] = '0' * 64
    elif mutation == 'missing-basis':
        kwargs.pop('valuation_basis_quote_binding')
    elif mutation.startswith('coverage') or mutation == 'partial':
        if mutation == 'coverage-gap':
            kwargs['complete_coverage_windows'] = kwargs['complete_coverage_windows'][:1]
        else:
            ref = kwargs['complete_coverage_windows'][1]
            target = tmp_path / ref['path']
            value = json.loads(target.read_bytes())
            if mutation == 'coverage-issuer':
                value['symbol'] = '600519'
            else:
                value['full_calendar_window_elapsed'] = False
            target.write_text(json.dumps(value), encoding='utf-8')
            ref['sha256'] = sha256_file(target)
    else:
        value = json.loads(path.read_bytes())
        if mutation == 'issuer':
            value['references'] = {'600519': value['references'][request['symbol']]}
            path.write_text(json.dumps(value), encoding='utf-8')
            binding['sha256'] = sha256_file(path)
        else:
            from value_investment_agent.application.product import pending_research_candidate as service
            fixed = datetime(2026, 10, 8 if mutation == 'future' else 12, 10, tzinfo=timezone.utc)
            if mutation == 'b1':
                fixed = datetime(2026, 10, 9, 10, tzinfo=timezone.utc)

            class Clock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

            monkeypatch.setattr(service, 'datetime', Clock)
    with pytest.raises(ValueError):
        run(tmp_path, package, policy, request, **kwargs)
    assert not (tmp_path / 'runtime/pending/candidate.json').exists()


@pytest.mark.parametrize('mutation', ['basis-date', 'scope', 'strip-basis', 'basis-source', 'context',
                                    'raw-source', 'approval', 'handoff', 'rebound-handoff',
                                    'coverage-window', 'future-generated', 'implementation'])
def test_prior_session_receipt_rechecks_basis_coverage_context_and_implementation(tmp_path, monkeypatch, mutation):
    package, policy, request, kwargs = prior_session_inputs(tmp_path, monkeypatch)
    result = run(tmp_path, package, policy, request, **kwargs)
    path = tmp_path / 'runtime/pending/candidate.json'
    if mutation == 'basis-date':
        result['valuation_basis_date'] = '2026-10-08'
    elif mutation == 'scope':
        result['valuation_basis_scope'] = 'CURRENT_APPROVED'
    elif mutation == 'strip-basis':
        for key in ('valuation_basis_date', 'valuation_basis_scope', 'basis_binding', 'coverage_binding'):
            result.pop(key)
    elif mutation == 'context':
        result['model_context']['facts_sha256'] = '0' * 64
    elif mutation == 'future-generated':
        result['generated_at'] = '2099-10-11T04:00:00+00:00'
    elif mutation == 'coverage-window':
        result['coverage_binding']['observation_bindings'] = result['coverage_binding']['observation_bindings'][1:]
    elif mutation == 'rebound-handoff':
        ref = result['coverage_binding']['handoff_binding']
        target = tmp_path / ref['path']
        handoff = json.loads(target.read_bytes())
        handoff['unsigned_response']['event_materiality']['decisions'][0]['human_decision'] = 'NOT_MATERIAL'
        target.write_text(json.dumps(handoff), encoding='utf-8')
        ref['sha256'] = sha256_file(target)
        for source in result['source_bindings']:
            if source['path'] == ref['path']:
                source['sha256'] = ref['sha256']
    elif mutation == 'approval':
        result['current_market_validity_approved'] = True
    elif mutation == 'implementation':
        target = tmp_path / 'runtime/implementation.py'
        target.write_text('TEST_ONLY original', encoding='utf-8')
        result['implementation_bindings'] = [dict(path='runtime/implementation.py', sha256=sha256_file(target))]
        target.write_text('TEST_ONLY drift', encoding='utf-8')
    else:
        target = (tmp_path / kwargs['valuation_basis_quote_binding']['path'] if mutation == 'basis-source'
                  else tmp_path / 'runtime/coverage-0/raw-index/response-0002.bin' if mutation == 'raw-source'
                  else tmp_path / result['coverage_binding']['handoff_binding']['path'])
        target.write_bytes(b'TEST_ONLY drift')
    path.write_text(json.dumps(result), encoding='utf-8')
    with pytest.raises(ValueError):
        verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))


def test_default_candidate_has_no_prior_session_scope(tmp_path):
    package, policy, request = candidate_inputs(tmp_path)
    result = run(tmp_path, package, policy, request)
    assert not {'valuation_basis_date', 'valuation_basis_scope', 'basis_binding', 'coverage_binding'} & result.keys()


def test_prior_session_candidate_remains_auditable_next_day_without_current_admission(tmp_path, monkeypatch):
    from value_investment_agent.application.product import pending_research_candidate as service

    package, policy, request, kwargs = prior_session_inputs(tmp_path, monkeypatch)
    result = run(tmp_path, package, policy, request, **kwargs)

    class NextSession(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 10, 12, 10, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(service, 'datetime', NextSession)
    path = tmp_path / 'runtime/pending/candidate.json'
    audited = verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))
    assert audited == result
    assert audited['valuation_basis_date'] == '2026-10-09'
    assert audited['current_market_validity_approved'] is audited['materiality_approved'] is False
    with pytest.raises(ValueError, match='current B1'):
        service._basis_quote(tmp_path, kwargs['valuation_basis_quote_binding'], request['symbol'],
                             NextSession.now(timezone.utc))


@pytest.mark.parametrize('mutation', ['drop-first-window', 'later-start-with-pre-model'])
def test_complete_coverage_start_is_anchored_to_report_period(tmp_path, monkeypatch, mutation):
    package, policy, request, kwargs = prior_session_inputs(tmp_path, monkeypatch,
        coverage_offset=1 if mutation == 'later-start-with-pre-model' else 0)
    if mutation == 'drop-first-window':
        kwargs['complete_coverage_windows'] = kwargs['complete_coverage_windows'][1:]
    with pytest.raises(ValueError, match='ordered, exact and contiguous'):
        run(tmp_path, package, policy, request, **kwargs)
    assert not (tmp_path / 'runtime/pending/candidate.json').exists()

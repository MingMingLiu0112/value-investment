"""TEST_ONLY scheduling transport: no official facts, approvals or network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from value_investment_agent.application.research import value_enrichment_batch as batch
from value_investment_agent.infrastructure.screening.value_enrichment_progress import digest


SYMBOLS = ['000151', '000498', '000544', '000568']


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    clock = {'now': datetime.now(timezone.utc)}
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock['now']
    monkeypatch.setattr(batch, 'datetime', Clock)
    def forbidden(*args, **kwargs):
        raise AssertionError('TEST_ONLY scheduling must never access network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    calls = []
    def unavailable(root, row, *args, **kwargs):
        calls.append(row['symbol'])
        raise ValueError('TEST_ONLY official evidence is absent; no facts admitted')
    monkeypatch.setattr(batch, '_annual_source_for_row', unavailable)
    replay = {}
    # Only queue transport is stubbed. The real batch, exact work key, progress
    # hashes, attempt receipts and financial-export read all run unchanged.
    monkeypatch.setattr(batch, 'build_value_research_priority_v2', lambda **kwargs: deepcopy(replay['queue']))
    points = [dict(symbol=s, field_name='TEST_ONLY_observation', period_label='2025-12-31',
        value='10', unit='percent', fetched_at='2026-01-01T00:00:00+00:00',
        available_at='2026-01-01T00:00:00+00:00', raw_file_hash='a' * 64,
        metadata=dict(source_binding=dict(path='runtime/TEST_ONLY-e1-a.json', sha256='a' * 64)))
        for s in SYMBOLS]
    rows = [dict(symbol=s, timing=dict(financial_period='2025-12-31'),
        evidence_completeness=dict(accepted_fields=[]), queue_status='SELECTED_FOR_RESEARCH') for s in SYMBOLS]
    def run(name, *, current_points=None, current_rows=None, token=None):
        export = runtime / (name + '-export.json')
        export.write_text(json.dumps(dict(points=current_points or points)), encoding='utf-8')
        binding = dict(path=export.relative_to(tmp_path).as_posix(), sha256=sha256(export.read_bytes()).hexdigest())
        queue = dict(schema_version='value-research-priority-v2', action='no_order',
            admission='RESEARCH_QUEUE_ONLY', budget=2, enrichment_budget=4,
            evaluation_at=clock['now'].isoformat(), evidence_enrichment_work_queue=deepcopy(current_rows or rows),
            inputs=dict(financial_export_path=binding['path'], financial_export_sha256=binding['sha256'],
                report_path='runtime/TEST_ONLY-report.json', report_sha256='b' * 64,
                receipt_path='runtime/TEST_ONLY-receipt.json', receipt_sha256='c' * 64))
        queue['content_sha256'] = batch._canonical_hash(queue)
        replay['queue'] = queue
        original_queue = deepcopy(queue)
        result = batch.execute_value_enrichment_batch(root=tmp_path, queue=queue,
            financial_export_path=export, financial_export_sha256=binding['sha256'],
            output_dir=runtime / name, budget=2, allow_network=False, retry_token=token)
        assert result['attempted_count'] <= 2
        assert result['formal_eligibility'] is False and result['new_fact_approvals'] == 0
        assert result['action'] == 'no_order'
        assert queue == original_queue  # No change to research ranks or display order.
        return result
    return dict(root=tmp_path, run=run, points=points, rows=rows, clock=clock, calls=calls)


def refreshed(points):
    result = deepcopy(points)
    for point in result:
        point.update(fetched_at='2026-02-01T00:00:00+00:00', available_at='2026-02-01T00:00:00+00:00')
        point['metadata']['source_binding'] = dict(path='runtime/TEST_ONLY-e1-b.json', sha256='b' * 64)
    return result


def test_reacquisition_moves_next_two_without_reusing_old_results(scheduler):
    s = scheduler
    first = s['run']('first')
    assert [i['symbol'] for i in first['items']] == SYMBOLS[:2]
    s['clock']['now'] += timedelta(seconds=1)
    second = s['run']('second', current_points=refreshed(s['points']))
    assert [i['symbol'] for i in second['items']] == SYMBOLS[2:]
    assert all(i['attempt'] == 1 for i in second['items'])
    assert s['calls'] == SYMBOLS
    assert not second['skipped_unchanged']


@pytest.mark.parametrize('change', ['facts', 'implementation', 'explicit_reopen'])
def test_changed_work_reopens_but_never_steals_unattempted_slots(scheduler, monkeypatch, change):
    s = scheduler
    s['run']('first')
    changed = deepcopy(s['points'])
    token = None
    if change == 'facts':
        changed[0]['value'] = '11'
        changed[0]['raw_file_hash'] = 'f' * 64
    elif change == 'implementation':
        implementation = s['root'] / 'TEST_ONLY-implementation.py'
        implementation.write_text('# TEST_ONLY updated producer\n', encoding='utf-8')
        monkeypatch.setattr(batch, '__file__', str(implementation))
    else:
        token = 'TEST_ONLY reviewed source change'
    s['clock']['now'] += timedelta(seconds=1)
    second = s['run']('second', current_points=changed, token=token)
    assert [i['symbol'] for i in second['items']] == SYMBOLS[2:]
    s['clock']['now'] += timedelta(seconds=1)
    third = s['run']('third', current_points=changed, token=token)
    assert third['items'][0]['symbol'] == SYMBOLS[0]
    assert third['items'][0]['attempt'] == 1


def test_oldest_precedes_count_and_count_only_breaks_completion_ties(scheduler):
    s = scheduler
    s['run']('first')
    s['clock']['now'] += timedelta(seconds=1)
    s['run']('second')
    s['clock']['now'] += timedelta(seconds=1)
    third = s['run']('third', current_points=refreshed(s['points']))
    assert [i['symbol'] for i in third['items']] == SYMBOLS[:2]
    # Attention count cannot supersede an older completion in another bucket.
    rows = deepcopy(s['rows'])
    rows[0]['evidence_completeness']['accepted_fields'] = ['TEST_ONLY accepted field']
    s['clock']['now'] += timedelta(seconds=1)
    fourth = s['run']('fourth', current_points=s['points'], current_rows=rows, token='TEST_ONLY new review')
    assert [i['symbol'] for i in fourth['items']] == SYMBOLS[2:]


def test_reacquisition_with_one_vs_zero_accepted_fields_cannot_starve_peers(scheduler):
    s = scheduler
    rows = deepcopy(s['rows'])
    first = s['run']('first')
    assert [i['symbol'] for i in first['items']] == SYMBOLS[:2]
    for row in rows[:2]:
        row['evidence_completeness']['accepted_fields'] = ['TEST_ONLY ratio']
    for index in range(1, 6):
        points = refreshed(s['points'])
        for point in points:
            point['fetched_at'] = f'2026-02-0{index}T00:00:00+00:00'
            point['metadata']['source_binding']['path'] = f'runtime/TEST_ONLY-{index}.json'
        s['clock']['now'] += timedelta(seconds=1)
        result = s['run']('fresh-' + str(index), current_points=points, current_rows=rows)
        assert [i['symbol'] for i in result['items']] == (SYMBOLS[2:] if index % 2 else SYMBOLS[:2])
        assert all(i['attempt'] == 1 for i in result['items'])
        assert not result['skipped_unchanged']
    assert s['rows'] == [dict(symbol=symbol, timing=dict(financial_period='2025-12-31'),
        evidence_completeness=dict(accepted_fields=[]), queue_status='SELECTED_FOR_RESEARCH') for symbol in SYMBOLS]


def test_attention_count_breaks_only_unattempted_ties(scheduler):
    rows = deepcopy(scheduler['rows'])
    rows[3]['evidence_completeness']['accepted_fields'] = ['TEST_ONLY ratio']
    result = scheduler['run']('ties', current_rows=rows)
    assert [i['symbol'] for i in result['items']] == [SYMBOLS[3], SYMBOLS[0]]


def checkpoint(s):
    return next((s['root'] / 'runtime/value-evidence-enrichment/progress-v1').glob('*.json'))


@pytest.mark.parametrize('mutation', ['envelope', 'attempt', 'result', 'scheduling', 'period', 'implementation'])
def test_bad_history_is_rejected_before_any_further_acquisition(scheduler, mutation):
    s = scheduler
    s['run']('first')
    path = checkpoint(s)
    envelope = json.loads(path.read_bytes())
    payload = envelope['payload']
    execution = s['root'] / payload['execution_binding']['path']
    outcome = json.loads(execution.read_bytes())
    if mutation == 'envelope':
        envelope['sha256'] = '0' * 64
    elif mutation == 'attempt':
        execution.write_bytes(execution.read_bytes() + b' ')
    elif mutation == 'result':
        result = s['root'] / 'runtime/TEST_ONLY-result.json'
        result.write_text('{}', encoding='utf-8')
        outcome['result_binding'] = dict(path=result.relative_to(s['root']).as_posix(), sha256='0' * 64)
    elif mutation == 'period':
        payload['scheduling']['financial_period'] = '2025-06-30'
        outcome['scheduling'] = deepcopy(payload['scheduling'])
    elif mutation == 'implementation':
        payload['scheduling']['implementation_sha256'] = 'NOT_A_HASH'
        outcome['scheduling'] = deepcopy(payload['scheduling'])
    else:
        payload['scheduling']['symbol'] = SYMBOLS[-1]
    if mutation in {'result', 'period', 'implementation'}:
        execution.write_text(json.dumps(outcome), encoding='utf-8')
        payload['execution_binding']['sha256'] = sha256(execution.read_bytes()).hexdigest()
    if mutation != 'envelope':
        envelope['sha256'] = digest(payload)
    path.write_text(json.dumps(envelope), encoding='utf-8')
    before = len(s['calls'])
    with pytest.raises(ValueError):
        s['run']('rejected')
    assert len(s['calls']) == before
    assert not (s['root'] / 'runtime/rejected').exists()


def test_legacy_history_is_not_guessed_or_used_as_fact_reuse(scheduler):
    s = scheduler
    s['run']('first')
    directory = s['root'] / 'runtime/value-evidence-enrichment/progress-v1'
    for path in directory.glob('*.json'):
        envelope = json.loads(path.read_bytes())
        payload = envelope['payload']
        execution = s['root'] / payload['execution_binding']['path']
        outcome = json.loads(execution.read_bytes())
        payload.pop('scheduling')
        outcome.pop('scheduling')
        execution.write_text(json.dumps(outcome), encoding='utf-8')
        payload['execution_binding']['sha256'] = sha256(execution.read_bytes()).hexdigest()
        envelope['sha256'] = digest(payload)
        path.write_text(json.dumps(envelope), encoding='utf-8')
    second = s['run']('second', current_points=refreshed(s['points']))
    assert [i['symbol'] for i in second['items']] == SYMBOLS[:2]
    assert not second['skipped_unchanged']


def test_retry_backoff_and_three_attempt_cap_remain_exact_keyed(scheduler, monkeypatch):
    s = scheduler
    def timeout(*args, **kwargs):
        raise TimeoutError('TEST_ONLY temporary transport failure')
    monkeypatch.setattr(batch, '_annual_source_for_row', timeout)
    s['run']('first')
    second = s['run']('second')
    assert [i['symbol'] for i in second['items']] == SYMBOLS[2:]
    assert s['run']('not-due')['attempted_count'] == 0
    for attempt in (2, 3):
        s['clock']['now'] += timedelta(minutes=10)
        a = s['run']('due-a-' + str(attempt))
        s['clock']['now'] += timedelta(seconds=1)
        b = s['run']('due-b-' + str(attempt))
        assert {i['symbol'] for result in (a, b) for i in result['items']} == set(SYMBOLS)
        assert all(i['attempt'] == attempt for result in (a, b) for i in result['items'])
    s['clock']['now'] += timedelta(minutes=10)
    assert s['run']('exhausted')['attempted_count'] == 0

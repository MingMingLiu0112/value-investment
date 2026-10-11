"""Append-only synthetic manual records never masquerade as account fills."""
from copy import deepcopy
import json

import pytest

from test_dual_sleeve_risk import GENERATED_AT, HOTSPOT
from value_investment_agent.application.product.dual_sleeve_risk import append_dual_sleeve_manual_record


def plan():
    return dict(record_id='synthetic-plan', kind='PLAN', namespace='SIMULATED', sleeve=HOTSPOT,
        symbol='600519', recorded_at=GENERATED_AT.isoformat(), trade_date='2026-09-22',
        research_version_sha256='a'*64, candidate_action='ENTRY_REVIEW_CANDIDATE',
        observed_price_cny='10', reason='Synthetic observation', risk_budget_cny='200',
        invalidation_condition='Synthetic structure failure', user_confirmation='PENDING',
        plan_record_sha256=None, fill=None, retrospective=None, evidence_ref='synthetic-research')


def append(root, body, head=None):
    return append_dual_sleeve_manual_record(root=root, directory=root/'.tmp/manual-journal', body=body,
        expected_head_sha256=head, synthetic=True, generated_at=GENERATED_AT)


def test_plan_fill_review_remain_distinct_and_immutable(tmp_path):
    first = append(tmp_path, plan())
    p = next((tmp_path/'.tmp/manual-journal').glob('*.json'))
    original = p.read_bytes()
    fill = dict(plan(), record_id='synthetic-fill', kind='FILL', user_confirmation='USER_CONFIRMED',
        plan_record_sha256=first['record_sha256'], fill=dict(transaction_id='manual-001', side='BUY',
            quantity='100', price_cny='10.2', fees_cny='5', next_sell_session='2026-09-23', source_ref='synthetic-user-fill'))
    second = append(tmp_path, fill, first['record_sha256'])
    retrospective = dict(plan(), record_id='synthetic-review', kind='REVIEW',
        plan_record_sha256=first['record_sha256'], retrospective='Synthetic review, not realized profit')
    third = append(tmp_path, retrospective, second['record_sha256'])
    assert p.read_bytes() == original
    records = [json.loads(x.read_text(encoding='utf-8')) for x in sorted(p.parent.glob('*.json'))]
    assert records[0]['body']['fill'] is None
    assert records[1]['body']['fill'] == fill['fill']
    assert all(not item['changes_holdings'] for item in records)
    assert not third['changes_holdings'] and third['action'] == 'no_order'


@pytest.mark.parametrize('change', ['stale_head', 'duplicate_id', 'plan_is_fill', 'unconfirmed_fill',
    'same_day_exit', 'unlinked_fill', 'wrong_sleeve', 'namespace', 'duplicate_transaction'])
def test_manual_record_conflicts_cannot_become_estimated_fills(tmp_path, change):
    first = append(tmp_path, plan())
    body = dict(plan(), kind='FILL', record_id='fill', plan_record_sha256=first['record_sha256'],
        user_confirmation='USER_CONFIRMED', fill=dict(transaction_id='manual-001', side='BUY',
            quantity='100', price_cny='10', fees_cny='5', next_sell_session='2026-09-23', source_ref='synthetic-user'))
    head = first['record_sha256']
    if change == 'stale_head': head = None
    if change == 'duplicate_id': body['record_id'] = 'synthetic-plan'
    if change == 'plan_is_fill': body['kind'] = 'PLAN'
    if change == 'unconfirmed_fill': body['user_confirmation'] = 'PENDING'
    if change == 'same_day_exit': body['fill']['next_sell_session'] = body['trade_date']
    if change == 'unlinked_fill': body['plan_record_sha256'] = 'b'*64
    if change == 'wrong_sleeve': body['sleeve'] = 'CORE_VALUE'
    if change == 'namespace': body['namespace'] = 'ACTUAL'
    if change == 'duplicate_transaction':
        head = append(tmp_path, body, head)['record_sha256']
        body = dict(body, record_id='different-record')
    before = {p: p.read_bytes() for p in (tmp_path/'.tmp/manual-journal').iterdir()}
    with pytest.raises(ValueError): append(tmp_path, body, head)
    assert {p: p.read_bytes() for p in (tmp_path/'.tmp/manual-journal').iterdir()} == before


def test_record_hash_drift_rejected_without_replacing_history(tmp_path):
    first = append(tmp_path, plan())
    record = next((tmp_path/'.tmp/manual-journal').glob('*.json'))
    payload = json.loads(record.read_text(encoding='utf-8'))
    payload['body']['reason'] = 'Tampered history'
    record.write_text(json.dumps(payload), encoding='utf-8')
    changed = record.read_bytes()
    with pytest.raises(ValueError, match='hash drift'):
        append(tmp_path, dict(plan(), record_id='new'), first['record_sha256'])
    assert record.read_bytes() == changed

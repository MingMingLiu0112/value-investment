import base64
from datetime import datetime, timezone
import hashlib

import pytest

from value_investment_agent.m6_operational_readiness import (
    M6PreflightConfig, RestoreTarget, PARTIAL, assess_session_ledger,
)
from value_investment_agent.m6_exchange_sessions import completed_exchange_sessions
from value_investment_agent.quote_sessions import (
    SSE_2026_CLOSURE_NOTICE_URL, SSE_2026_NOTICE_MARKERS,
)


def _calendar():
    raw = "\n".join(SSE_2026_NOTICE_MARKERS).encode('utf-8')
    return {
        'venue': 'SSE', 'observation_cutoff': '2026-09-24T08:30:00+00:00',
        'documents': [{
            'source_url': SSE_2026_CLOSURE_NOTICE_URL,
            'fetched_at': '2026-09-24T08:15:00+00:00',
            'raw_base64': base64.b64encode(raw).decode('ascii'),
            'sha256': hashlib.sha256(raw).hexdigest(),
        }],
    }


def _config():
    return M6PreflightConfig(
        target_rpo_hours=24, target_rto_hours=4,
        minimum_real_sessions=2, minimum_real_events=1,
        restore_target=RestoreTarget('127.0.0.1', 5433, 'value_agent_restore'),
        resource_limits={}, required_files=(), stage_status={}, authorization_required=(),
    )


def _record(day, calendar):
    document = calendar['documents'][0]
    return {
        'action': 'no_order', 'exchange': 'SSE', 'session_date': day,
        'observed_at': day + 'T15:10:00+08:00',
        'calendar_sha256': document['sha256'],
        'calendar_source_url': document['source_url'],
        'observed': 'actual', 'status': 'success',
        'resource_baseline_ok': True, 'real_event_materialized': False,
    }


def test_calendar_gap_breaks_streak_and_does_not_verify_real_shadow():
    calendar = _calendar()
    schedule = completed_exchange_sessions(
        'SSE', calendar['documents'], datetime.fromisoformat(calendar['observation_cutoff']))
    assert schedule['latest_completed_session'] == '2026-09-24'
    days = [item['session_date'] for item in schedule['sessions'][-3:]]
    result = assess_session_ledger(_config(), [_record(day, calendar) for day in days[-2:]],
                                   calendar_evidence=calendar)
    assert result['status'] == PARTIAL
    assert result['evidence']['latest_streak'] == 2
    assert result['evidence']['verified_actual_sessions'] == 0
    assert result['checks'][-1]['passed'] is True
    missing = assess_session_ledger(_config(), [_record(days[0], calendar),
                                                _record(days[2], calendar)], calendar_evidence=calendar)
    assert missing['evidence']['latest_streak'] == 1


@pytest.mark.parametrize('change', ['weekend', 'future', 'venue', 'hash', 'intraday', 'after_cutoff'])
def test_calendar_rejects_invalid_session_observation(change):
    calendar = _calendar()
    record = _record('2026-09-24', calendar)
    if change == 'weekend':
        record['session_date'] = '2026-09-20'
    elif change == 'future':
        record['session_date'] = '2026-09-28'
    elif change == 'venue':
        record['exchange'] = 'SZSE'
    elif change == 'hash':
        record['calendar_sha256'] = '0' * 64
    elif change == 'intraday':
        record['observed_at'] = '2026-09-24T10:00:00+08:00'
    else:
        record['observed_at'] = '2026-09-24T17:00:00+08:00'
    with pytest.raises(ValueError):
        assess_session_ledger(_config(), [record], calendar_evidence=calendar)

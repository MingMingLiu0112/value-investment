from datetime import datetime

import pytest

from value_investment_agent.quote_sessions import CHINA, b1_acquisition_verdict


MATCHED = {'status': 'matched_close', 'passed': True, 'expected_session': '2026-10-16'}


def documents(tencent, sina):
    return {'tencent': {'fetched_at': tencent}, 'sina': {'fetched_at': sina}}


@pytest.mark.parametrize(('tencent', 'sina', 'expected'), [
    ('2026-10-16T07:06:00Z', '2026-10-16T07:07:00Z', 'SAME_SESSION_POST_CLOSE'),
    ('2026-10-16T07:04:00Z', '2026-10-16T07:07:00Z', 'BEFORE_CLOSE_BUFFER'),
    ('2026-10-17T01:00:00Z', '2026-10-17T01:01:00Z', 'OUTSIDE_SESSION_DAY'),
    ('2026-10-16T07:06:00Z', '2026-10-17T01:00:00Z', 'OUTSIDE_SESSION_DAY'),
])
def test_b1_acquisition_requires_both_sources_after_same_session_close(tencent, sina, expected):
    verdict = b1_acquisition_verdict(MATCHED, documents(tencent, sina))
    assert verdict['status'] == expected
    assert verdict['eligible'] is (expected == 'SAME_SESSION_POST_CLOSE')
    expected_available = max(datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                             for stamp in (tencent, sina)).astimezone(CHINA).isoformat()
    assert verdict['available_at'] == expected_available


def test_b1_acquisition_does_not_upgrade_failed_close_or_missing_source():
    failed = b1_acquisition_verdict({**MATCHED, 'passed': False},
                                    documents('2026-10-16T07:06:00Z', '2026-10-16T07:07:00Z'))
    assert failed == {'status': 'CLOSE_NOT_VERIFIED', 'eligible': False, 'available_at': None}
    missing = b1_acquisition_verdict(MATCHED, {'tencent': {'fetched_at': '2026-10-16T07:06:00Z'}})
    assert missing['status'] == 'SOURCE_TIME_INVALID' and not missing['eligible']

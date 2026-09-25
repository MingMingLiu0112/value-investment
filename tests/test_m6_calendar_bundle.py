import base64
from datetime import datetime
import hashlib
import json

import pytest

from scripts.audit_m6_preflight import _calendar_from_bundle
from value_investment_agent.m6_exchange_sessions import completed_exchange_sessions
from value_investment_agent.quote_sessions import (
    SSE_2026_CLOSURE_NOTICE_URL, SSE_2026_NOTICE_MARKERS,
)


def _write_bundle(tmp_path):
    raw_notice = '\n'.join(SSE_2026_NOTICE_MARKERS).encode('utf-8')
    documents = {}
    ids = []
    for source_url, raw in (
        (SSE_2026_CLOSURE_NOTICE_URL, raw_notice),
        ('https://qt.gtimg.cn/q=sh600519', b'quote-a'),
        ('https://hq.sinajs.cn/list=sh600519', b'quote-b'),
    ):
        stamp = '2026-09-24T08:10:00+00:00'
        sha = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256((source_url + '\n' + stamp + '\n' + sha).encode()).hexdigest()
        documents[identity] = {
            'source_url': source_url, 'fetched_at': stamp, 'sha256': sha,
            'http_status': 200, 'raw_base64': base64.b64encode(raw).decode('ascii'),
        }
        ids.append(identity)
    bundle = {
        'version': 'quote-session-collection-v1',
        'status': 'collected_not_verified', 'request_failures': [],
        'finished_at': '2026-09-24T08:30:00+00:00',
        'documents': documents,
        'references': {'600519': {
            'symbol': '600519', 'calendar_exchange': 'SSE',
            'document_refs': {'calendar_documents': [ids[0]],
                              'tencent': ids[1], 'sina': ids[2]},
        }},
    }
    path = tmp_path / 'bundle.json'
    encoded = json.dumps(bundle).encode('utf-8')
    path.write_bytes(encoded)
    (tmp_path / 'report.json').write_text(json.dumps({
        'bundle_sha256': hashlib.sha256(encoded).hexdigest(),
        'bundle_bytes': len(encoded), 'status': bundle['status'],
    }), encoding='utf-8')
    return path


def test_calendar_bundle_binds_archive_and_official_schedule(tmp_path):
    path = _write_bundle(tmp_path)
    evidence = _calendar_from_bundle(path, '600519')
    schedule = completed_exchange_sessions(
        evidence['venue'], evidence['documents'],
        datetime.fromisoformat(evidence['observation_cutoff']))
    assert schedule['latest_completed_session'] == '2026-09-24'
    assert evidence['source_bundle_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('mutation', ['bundle', 'report', 'response', 'venue'])
def test_calendar_bundle_tampering_fails_closed(tmp_path, mutation):
    path = _write_bundle(tmp_path)
    if mutation == 'bundle':
        path.write_bytes(path.read_bytes() + b' ')
    elif mutation == 'report':
        report = tmp_path / 'report.json'
        report.write_text('{}', encoding='utf-8')
    else:
        bundle = json.loads(path.read_text(encoding='utf-8'))
        if mutation == 'response':
            item = next(iter(bundle['documents'].values()))
            item['http_status'] = 503
        else:
            bundle['references']['600519']['calendar_exchange'] = 'SZSE'
        encoded = json.dumps(bundle).encode('utf-8')
        path.write_bytes(encoded)
        (tmp_path / 'report.json').write_text(json.dumps({
            'bundle_sha256': hashlib.sha256(encoded).hexdigest(),
            'bundle_bytes': len(encoded), 'status': bundle['status'],
        }), encoding='utf-8')
    with pytest.raises((ValueError, KeyError)):
        _calendar_from_bundle(path, '600519')

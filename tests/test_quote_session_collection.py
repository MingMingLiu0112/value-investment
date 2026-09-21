import base64
from calendar import monthrange
from copy import deepcopy
from datetime import date
import json
from urllib.parse import urlencode

import pytest
import requests

from value_investment_agent.quote_session_collection import collect_session_bundle, resolve_session_reference
from value_investment_agent.quote_sessions import SSE_2026_CLOSURE_NOTICE_URL, evaluate_quote_session
from test_quote_sessions import NOW, evidence


class Session:
    def __init__(self, fail=False):
        self.urls = []
        self.fail = fail

    def get(self, url, *, params, headers, timeout):
        self.urls.append(url)
        assert timeout == (10, 20)
        if url == SSE_2026_CLOSURE_NOTICE_URL:
            raw = '''关于上海证券交易所2026年部分节假日休市安排的通知
            1月1日（星期四）至1月3日（星期六）休市
            2月15日（星期日）至2月23日（星期一）休市
            4月4日（星期六）至4月6日（星期一）休市
            5月1日（星期五）至5月5日（星期二）休市
            6月19日（星期五）至6月21日（星期日）休市
            9月25日（星期五）至9月27日（星期日）休市
            10月1日（星期四）至10月7日（星期三）休市'''.encode()
        elif params:
            year, month = map(int, params['month'].split('-'))
            rows = [{'jyrq': date(year, month, day).isoformat(),
                     'jybz': '1' if date(year, month, day).weekday() < 5 else '0'}
                    for day in range(1, monthrange(year, month)[1] + 1)]
            raw = json.dumps({'data': rows, 'nowdate': '2026-09-07'}).encode()
            url += '?' + urlencode(params)
        else:
            provider = 'sina' if 'sinajs' in url else 'tencent'
            if self.fail and provider == 'sina':
                raise requests.Timeout('bounded test timeout')
            identities = url.split('=')[1].split(',')
            raw = b''.join(base64.b64decode(evidence(symbol=item[2:])[provider]['raw_base64'])
                           for item in identities)

        class Response:
            content = raw
            status_code = 200

            def raise_for_status(self):
                pass
        response = Response()
        response.url = url
        return response


def test_one_batch_stores_quotes_and_calendars_once_and_reaches_decision_gate():
    transport = Session()
    bundle = collect_session_bundle(['000333', '000001'], session=transport, clock=lambda: NOW)
    assert len(bundle['documents']) == len(transport.urls) == 4
    left, right = (bundle['references'][symbol]['document_refs'] for symbol in ('000333', '000001'))
    assert left == right
    for symbol in bundle['references']:
        result = evaluate_quote_session(symbol, 60, bundle['references'][symbol], NOW,
                                        documents=bundle['documents'])
        assert result['passed'] and result['expected_session'] == '2026-09-07'


def test_shared_evidence_reaches_actual_reminder_without_cached_pass_flags():
    from test_reminders import payload
    from value_investment_agent.reminders import build_reminders
    bundle = collect_session_bundle(['000333'], session=Session(), clock=lambda: NOW)
    p = payload()
    p['points'][0]['metadata']['quote_session_evidence'] = bundle['references']['000333']
    p['quote_session_documents'] = bundle['documents']
    assert build_reminders(p, now=NOW)[0]['category'] == '买入研究候选'
    p['quote_session_documents'] = {}
    assert build_reminders(p, now=NOW)[0]['signal_blocked']


def test_missing_provider_is_a_partial_failure_not_silent_success():
    bundle = collect_session_bundle(['000333'], session=Session(fail=True), clock=lambda: NOW)
    assert bundle['status'] == 'partial_failure' and len(bundle['request_failures']) == 1
    assert not evaluate_quote_session('000333', 60, bundle['references']['000333'], NOW,
                                     documents=bundle['documents'])['passed']


def test_document_identity_prevents_relabeling_an_old_download_as_new():
    bundle = collect_session_bundle(['000333'], session=Session(), clock=lambda: NOW)
    ref = bundle['references']['000333']
    bundle['documents'][ref['document_refs']['tencent']]['fetched_at'] = '2026-09-08T08:00:00+00:00'
    with pytest.raises(ValueError, match='identity mismatch'):
        resolve_session_reference(ref, bundle['documents'])


def test_changed_raw_bytes_cannot_be_hidden_by_unchanged_reference():
    bundle = collect_session_bundle(['000333'], session=Session(), clock=lambda: NOW)
    ref = bundle['references']['000333']
    bundle['documents'][ref['document_refs']['tencent']]['raw_base64'] = base64.b64encode(b'changed').decode()
    assert not evaluate_quote_session('000333', 60, ref, NOW, documents=bundle['documents'])['passed']


@pytest.mark.parametrize('symbols,batch', [([], 50), (['000333'] * 2, 50),
    (['bad'], 50), ([{}], 50), (['000333'], True), (['000333'], '50'), (['000333'], 51)])
def test_invalid_requests_never_start_network_calls(symbols, batch):
    transport = Session()
    with pytest.raises(ValueError):
        collect_session_bundle(symbols, session=transport, clock=lambda: NOW, batch_size=batch)
    assert transport.urls == []


def test_each_batch_has_its_own_explicit_quote_references():
    bundle = collect_session_bundle(['000333', '000001'], session=Session(), clock=lambda: NOW, batch_size=1)
    assert len(bundle['documents']) == 6
    assert bundle['references']['000333']['document_refs']['tencent'] != bundle['references']['000001']['document_refs']['tencent']


def test_sse_bundle_uses_one_official_2026_notice_and_reaches_session_gate():
    bundle = collect_session_bundle(['600519'], session=Session(), clock=lambda: NOW)
    result = evaluate_quote_session('600519', 60, bundle['references']['600519'], NOW,
                                    documents=bundle['documents'])
    assert result['passed'] and result['expected_session'] == '2026-09-07'
    assert len(bundle['references']['600519']['document_refs']['calendar_documents']) == 1

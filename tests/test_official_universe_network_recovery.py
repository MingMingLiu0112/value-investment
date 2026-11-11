"""Configured transport recovery, not redirect or access-challenge bypass."""
from urllib.parse import parse_qs

import pytest
import requests

from test_official_universe import SATURDAY, v2_documents  # noqa: F401
from value_investment_agent.infrastructure.screening import official_universe_v2 as lists


@pytest.mark.parametrize('partial', [False, True])
def test_collectors_keep_configured_proxy_tls_and_no_redirects(
        partial, v2_documents, monkeypatch, tmp_path):
    # Exercise requests' actual environment merging, but intercept send before
    # any socket/network operation. No real proxy, token or CA is accessed.
    proxy = 'http://proxy.example.test:8443'
    for name in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy',
                 'ALL_PROXY', 'all_proxy'):
        monkeypatch.setenv(name, proxy)
    for name in ('NO_PROXY', 'no_proxy'):
        monkeypatch.setenv(name, '')
    for name in ('REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE'):
        monkeypatch.delenv(name, raising=False)
    documents = {doc['label']: doc['raw'] for doc in v2_documents}
    calls = []

    def send(session, request, **kwargs):
        assert session.trust_env is True
        assert kwargs['proxies']['https'] == proxy
        assert kwargs['verify'] is True
        assert kwargs['allow_redirects'] is False
        if request.url.startswith(lists.SZSE_URL):
            label = 'SZSE_A'
        elif request.url.startswith(lists.SSE_URL):
            label = 'SSE_' + parse_qs(request.url.split('?')[1])['STOCK_TYPE'][0]
        else:
            assert request.url == lists.BSE_URL
            assert request.method == 'POST'
            label = 'BSE_' + parse_qs(request.body.decode())['page'][0]
        calls.append(label)
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response._content = documents[label]
        response._content_consumed = True
        response.headers['Content-Type'] = 'application/json'
        return response

    monkeypatch.setattr(requests.Session, 'send', send)
    collector = (lists.collect_security_lists_with_coverage if partial
                 else lists.collect_security_lists_v2)
    payload = collector(tmp_path / 'raw', clock=lambda: SATURDAY)
    assert calls == ['SZSE_A', 'SSE_1', 'SSE_8', 'BSE_0', 'BSE_1']
    assert payload['complete'] is True
    assert payload['parser_version'] == lists.VERSION
    assert payload['exchange_counts']['BSE'] == 201
    assert payload['collection_timing']['strict_contemporaneous_pit'] is False

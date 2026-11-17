"""Scoped public transport checks for the owned refresh worker."""
from contextlib import contextmanager
import urllib.request
from urllib.parse import urlparse

import requests


@contextmanager
def public_refresh_transport(*, network_authorized, checkpoint):
    # Exact existing collector hosts; provider IO is intentionally unsupported here.
    hosts = {'query.sse.com.cn', 'www.sse.com.cn', 'static.sse.com.cn',
             'www.szse.cn', 'disc.static.szse.cn', 'www.bse.cn',
             'proxy.finance.qq.com', 'vip.stock.finance.sina.com.cn', 'quotes.sina.cn',
             'datacenter-web.eastmoney.com', 'www.cninfo.com.cn', 'static.cninfo.com.cn'}
    def guard(url):
        checkpoint()
        if network_authorized is not True:
            raise PermissionError('PUBLIC_REFRESH_NETWORK_AUTHORIZATION_REQUIRED')
        parsed = urlparse(url)
        if (parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username
                or parsed.password or parsed.port not in {None, 443}):
            raise PermissionError('PUBLIC_REFRESH_ENDPOINT_NOT_ALLOWED')

    send, opened = requests.Session.send, urllib.request.OpenerDirector.open
    def checked_send(session, request, **kwargs):
        guard(request.url)
        return send(session, request, **kwargs)
    def checked_open(opener, request, *args, **kwargs):
        guard(request.full_url if hasattr(request, 'full_url') else request)
        return opened(opener, request, *args, **kwargs)
    requests.Session.send, urllib.request.OpenerDirector.open = checked_send, checked_open
    try:
        yield checkpoint
    finally:
        requests.Session.send, urllib.request.OpenerDirector.open = send, opened

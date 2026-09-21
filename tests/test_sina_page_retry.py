import json
import sys
from collections import Counter
from types import ModuleType, SimpleNamespace

import pytest

from value_investment_agent.market import AllAMarketAdapter


def install_source(monkeypatch, page_rows):
    ak = ModuleType('akshare')
    stock = ModuleType('akshare.stock')
    source = ModuleType('akshare.stock.stock_zh_a_sina')
    source.zh_sina_a_stock_count_url = 'count'
    source.zh_sina_a_stock_url = 'pages'
    source.zh_sina_a_stock_payload = {'num': '80'}
    stock.stock_zh_a_sina = source
    ak.stock = stock
    utils = ModuleType('akshare.utils')
    utils.demjson = SimpleNamespace(decode=json.loads)
    for key, module in [('akshare',ak),('akshare.stock',stock),
                        ('akshare.stock.stock_zh_a_sina',source),('akshare.utils',utils)]:
        monkeypatch.setitem(sys.modules, key, module)
    calls = Counter()

    def get(url, params=None, **kwargs):
        if url == 'count':
            text = '"4001"'
        else:
            page = int(params['page'])
            calls[page] += 1
            values = [{'code':str(600000+i)} for i in range((page-1)*80,min(page*80,4001))]
            text = json.dumps(page_rows(page, calls[page], values))
        return SimpleNamespace(text=text, raise_for_status=lambda: None)

    monkeypatch.setattr('requests.get', get)
    monkeypatch.setattr('value_investment_agent.market.time.sleep', lambda seconds: None)
    return calls


def test_short_page_retried_without_duplicate_append(monkeypatch):
    calls = install_source(monkeypatch, lambda page, attempt, rows:
                           rows[:40] if page == 3 and attempt == 1 else rows)
    rows = AllAMarketAdapter._sina_rows()
    assert len(rows) == len({r['code'] for r in rows}) == 4001
    assert calls[3] == 2 and calls[51] == 1


def test_persistent_short_page_fails_after_bounded_retries(monkeypatch):
    calls = install_source(monkeypatch, lambda page, attempt, rows: [] if page == 2 else rows)
    with pytest.raises(RuntimeError, match='page 2 incomplete after 3 attempts'):
        AllAMarketAdapter._sina_rows()
    assert calls[2] == 3 and calls[3] == 0


def test_full_length_duplicate_pages_still_rejected(monkeypatch):
    install_source(monkeypatch, lambda page, attempt, rows:
                   [{'code':'600000'}] * len(rows) if page == 2 else rows)
    with pytest.raises(RuntimeError, match='duplicate or missing'):
        AllAMarketAdapter._sina_rows()

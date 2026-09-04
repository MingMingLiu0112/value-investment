import json
import sys
from decimal import Decimal
from types import SimpleNamespace

from value_investment_agent.market import AllAMarketAdapter, TENCENT_SOURCE, screen_rows


def test_market_screen_filters_and_classifies_initial_candidates() -> None:
    candidates = screen_rows([
        {'代码': '600001', '名称': '价值公司', '最新价': 10, '市盈率-动态': 10, '市净率': 1, '总市值': 20_000_000_000},
        {'代码': '600002', '名称': 'ST样例', '最新价': 10, '市盈率-动态': 10, '市净率': 1, '总市值': 20_000_000_000},
        {'代码': '600003', '名称': '高估公司', '最新价': 10, '市盈率-动态': 50, '市净率': 1, '总市值': 20_000_000_000},
    ], {'600001': '公用事业'})

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.symbol == '600001'
    assert candidate.sector == '公用事业'
    assert candidate.score == Decimal('54.33')
    assert candidate.status == 'initial_screen_pending_financial_review'


def test_tencent_fallback_keeps_missing_pb_out_of_complete_valuation_status() -> None:
    candidates = screen_rows([
        {'代码': '600001', '名称': '候选公司', '最新价': 10, '市盈率-动态': 10, '总市值': 20_000_000_000, '板块': '主板'},
    ], {}, require_pb=False)

    assert len(candidates) == 1
    assert candidates[0].pb is None
    assert candidates[0].sector == '主板'
    assert candidates[0].status == 'initial_screen_pending_pb_financial_review'


def test_tencent_rows_keep_units_and_board_classification() -> None:
    rows = AllAMarketAdapter._tencent_rows([
        {'code': 'sh600001', 'name': '样例', 'zxj': '12.34', 'pe_ttm': '10', 'zsz': '123.45', 'stock_type': 'GP-A-KCB'},
    ])

    assert rows == [{
        '代码': '600001', '名称': '样例', '最新价': '12.34', '市盈率-动态': '10',
        '总市值': Decimal('12345000000.00'), '板块': '科创板',
    }]


def test_market_adapter_records_primary_failure_when_using_tencent(monkeypatch) -> None:
    class Frame:
        def __init__(self, rows):
            self.rows = rows

        def to_dict(self, orient: str):
            assert orient == 'records'
            return self.rows

    fake_ak = SimpleNamespace(
        stock_zh_a_spot_em=lambda: (_ for _ in ()).throw(RuntimeError('eastmoney unavailable')),
        stock_zh_a_spot_tx=lambda: Frame([
            {'code': 'sh600001', 'name': '候选公司', 'zxj': '10', 'pe_ttm': '10', 'zsz': '100', 'stock_type': 'GP-A'},
        ]),
    )
    monkeypatch.setitem(sys.modules, 'akshare', fake_ak)

    _, _, candidates, raw, _, source = AllAMarketAdapter().fetch(include_industry=False)

    assert source == TENCENT_SOURCE
    assert candidates[0].status == 'initial_screen_pending_pb_financial_review'
    assert json.loads(raw)['fallback_reason'] == 'eastmoney unavailable'

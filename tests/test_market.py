import json
import sys
import pytest
from decimal import Decimal
from types import SimpleNamespace

from value_investment_agent.market import AllAMarketAdapter, TENCENT_SOURCE, board_for_symbol, screen_rows


@pytest.fixture(autouse=True)
def bounded_fixture_universe(monkeypatch):
    monkeypatch.setattr('value_investment_agent.market.MIN_UNIVERSE_SIZE',1)


def test_sina_cross_check_enriches_pb_only_for_agreeing_prices() -> None:
    merged, audit = AllAMarketAdapter._merge_tencent_with_sina(
        [
            {"symbol": f"{600000 + index}", "current_price": "10", "pe": "12", "market_cap": "10000000000"}
            for index in range(4000)
        ],
        [
            {"code": f"{600000 + index}", "trade": "10.01", "pb": "1.25", "per": "12", "mktcap": "1000000"}
            for index in range(4000)
        ],
    )

    assert audit["sina_status"] == "accepted"
    assert audit["pb_enriched"] == 4000
    assert merged[0]["pb"] == Decimal("1.25")
    assert merged[0]['price_cross_check']['status']=='matched'


def test_sina_cross_check_rejects_price_conflict() -> None:
    tencent_rows = [
        {"symbol": f"{600000 + index}", "current_price": "10", "pe": "12", "market_cap": "10000000000"}
        for index in range(4000)
    ]
    sina_rows = [
        {"code": f"{600000 + index}", "trade": "10", "pb": "1.25", "per": "12", "mktcap": "1000000"}
        for index in range(4000)
    ]
    sina_rows[0]["trade"] = "15"

    merged, audit = AllAMarketAdapter._merge_tencent_with_sina(tencent_rows, sina_rows)

    assert "pb" not in merged[0]
    assert audit["price_conflicts"] == 1
    assert audit["price_conflict_examples"][0]["symbol"] == "600000"
    assert merged[0]['price_cross_check']['status']=='conflict'


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
    assert candidate.board == '主板'
    assert candidate.score == Decimal('54.33')
    assert candidate.status == 'initial_screen_pending_financial_review'


def test_tencent_fallback_keeps_missing_pb_out_of_complete_valuation_status() -> None:
    candidates = screen_rows([
        {'代码': '600001', '名称': '候选公司', '最新价': 10, '市盈率-动态': 10, '总市值': 20_000_000_000, '板块': '主板'},
    ], {}, require_pb=False)

    assert len(candidates) == 1
    assert candidates[0].pb is None
    assert candidates[0].sector == '待行业映射'
    assert candidates[0].board == '主板'
    assert candidates[0].status == 'initial_screen_pending_pb_financial_review'


def test_board_is_code_based_and_never_used_as_industry() -> None:
    assert board_for_symbol('600001') == '主板'
    assert board_for_symbol('300001') == '创业板'
    assert board_for_symbol('302132') == '创业板'
    assert board_for_symbol('302999') == '待板块映射'
    assert board_for_symbol('688001') == '科创板'
    assert board_for_symbol('830001') == '北交所'


def test_tencent_rows_keep_units_and_board_classification() -> None:
    rows = AllAMarketAdapter._tencent_rows([
        {'code': 'sh600001', 'name': '样例', 'zxj': '12.34', 'pe_ttm': '10', 'zsz': '123.45', 'stock_type': 'GP-A-KCB'},
    ])

    assert rows == [{
        '代码': '600001', '名称': '样例', '最新价': '12.34', 'pe': '10',
        'pe_basis': 'ttm', 'pe_source_values': {'tencent_pe_ttm': '10'},
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
    fallback_reason = json.loads(raw)['fallback_reason']
    assert fallback_reason.startswith('RuntimeError: eastmoney unavailable')
    assert 'Sina valuation fallback unavailable' in fallback_reason


def test_industry_mapping_failure_keeps_primary_quote_source(monkeypatch) -> None:
    class Frame:
        def to_dict(self, orient: str):
            assert orient == 'records'
            return [{
                '代码': '600001', '名称': '候选公司', '最新价': '10',
                '市盈率-动态': '10', '市净率': '1', '总市值': '10000000000',
            }]

    fake_ak = SimpleNamespace(stock_zh_a_spot_em=lambda: Frame())
    monkeypatch.setitem(sys.modules, 'akshare', fake_ak)
    monkeypatch.setattr(AllAMarketAdapter, '_industry_map', staticmethod(lambda _ak: (_ for _ in ()).throw(RuntimeError('industry unavailable'))))
    monkeypatch.setattr(
        AllAMarketAdapter, '_sina_shenwan_industry_map',
        staticmethod(lambda: {f'{600000 + index}': '银行' for index in range(4000)}),
    )

    _, _, candidates, raw, _, source = AllAMarketAdapter().fetch(include_industry=True)

    assert source != TENCENT_SOURCE
    assert candidates[0].pb == Decimal('1')
    assert candidates[0].sector == '银行'
    snapshot = json.loads(raw)
    assert snapshot['industry_mapping_source'] == 'AkShare / Sina Shenwan level-1 industry mapping'
    assert snapshot['industry_mapping_count'] == 1


def test_tencent_quote_fallback_still_enriches_industry(monkeypatch) -> None:
    class Frame:
        def to_dict(self, orient: str):
            assert orient == 'records'
            return [{'code': 'sh600001', 'name': '样例公司', 'zxj': '10', 'pe_ttm': '10', 'zsz': '100', 'stock_type': 'GP-A'}]

    fake_ak = SimpleNamespace(
        stock_zh_a_spot_em=lambda: (_ for _ in ()).throw(RuntimeError('eastmoney unavailable')),
        stock_zh_a_spot_tx=lambda: Frame(),
    )
    monkeypatch.setitem(sys.modules, 'akshare', fake_ak)
    monkeypatch.setattr(AllAMarketAdapter, '_sina_rows', staticmethod(lambda: (_ for _ in ()).throw(RuntimeError('sina valuation unavailable'))))
    monkeypatch.setattr(AllAMarketAdapter, '_industry_map', staticmethod(lambda _ak: (_ for _ in ()).throw(RuntimeError('industry unavailable'))))
    monkeypatch.setattr(
        AllAMarketAdapter, '_sina_shenwan_industry_map',
        staticmethod(lambda: {f'{600000 + index}': '银行' for index in range(4000)}),
    )

    _, _, candidates, raw, _, source = AllAMarketAdapter().fetch(include_industry=True)

    assert source == TENCENT_SOURCE
    assert candidates[0].sector == '银行'
    assert json.loads(raw)['industry_mapping_count'] == 1


def test_coverage_decisions_reconcile_with_screened_candidates():
    from value_investment_agent.market import market_coverage_audit
    rows=[{'代码':s,'名称':name,'最新价':10,'pe':pe,'pb':1,'market_cap':1e10}
          for s,name,pe in [('600001','样例',10),('300001','ST样例',10),('688001','高PE',30),('920001','北交所样例',10)]]
    audit=market_coverage_audit(rows,True)
    assert audit['received_rows']==4
    assert sum(audit['outcome_counts'].values())==4
    assert audit['outcome_counts']['candidate']==len(screen_rows(rows,{}))==2
    assert audit['candidate_board_counts']['北交所']==1
    assert audit['official_universe_reconciled'] is False


def test_incomplete_or_duplicate_full_market_snapshot_rejected(monkeypatch):
    from value_investment_agent.market import validate_snapshot
    monkeypatch.setattr('value_investment_agent.market.MIN_UNIVERSE_SIZE',4000)
    with pytest.raises(ValueError,match='truncated'):
        validate_snapshot([{'symbol':'600001'}])
    with pytest.raises(ValueError,match='Duplicate'):
        validate_snapshot([{'symbol':'600001'}]*4000)


def test_conflicting_quote_cannot_slip_through_with_preexisting_pb():
    r={'symbol':'600001','name':'样例','current_price':10,'pe':10,'pb':1,'market_cap':1e10,
       'price_cross_check':{'status':'conflict'}}
    assert not screen_rows([r],{})

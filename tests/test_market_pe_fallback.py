from value_investment_agent.market import AllAMarketAdapter


def test_sina_does_not_add_second_pe_when_tencent_ttm_exists():
    raw = [{'code':str(600000+i),'name':'sample','zxj':'10','pe_ttm':'12',
            'zsz':'100','stock_type':'GP-A'} for i in range(4000)]
    primary = AllAMarketAdapter._tencent_rows(raw)
    secondary = [{'code':r['code'],'trade':'10','pb':'1','per':'20'} for r in raw]
    merged, _ = AllAMarketAdapter._merge_tencent_with_sina(primary, secondary)
    assert all(r['pe'] == '12' and '市盈率-动态' not in r for r in merged)
    assert all(r['pe_basis'] == 'ttm' for r in merged)
    assert all(r['pe_source_values'] == {'tencent_pe_ttm':'12','sina_per':'20'} for r in merged)


def test_sina_can_fill_absent_tencent_pe():
    primary = [{'代码':str(600000+i),'最新价':'10','市盈率-动态':None} for i in range(4000)]
    secondary = [{'code':r['代码'],'trade':'10','pb':'1','per':'20'} for r in primary]
    merged, _ = AllAMarketAdapter._merge_tencent_with_sina(primary, secondary)
    assert all(str(r['pe']) == '20' for r in merged)
    assert all(r['pe_basis'] == 'sina_per_unspecified' for r in merged)

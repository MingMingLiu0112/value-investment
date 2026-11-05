from value_investment_agent.domain.discovery.financial_gap_diagnostics_v1 import build_diagnostics


def point(field,value='10',unit='percent',**kw):
    return dict(field_name=field,value=value,unit=unit,period_label='2025-12-31',**kw)


def test_existing_unverified_is_not_missing():
    d,_=build_diagnostics([point('roe_weighted'),point('gross_margin'),point('total_revenue_yoy')],period='2025-12-31')
    assert d['available_count']==3 and d['verified_count']==0 and d['missing_count']==6
    assert d['fields'][0]['status']=='AVAILABLE_PENDING_VERIFICATION'


def test_parent_growth_preserves_explicit_parent_label():
    d,_=build_diagnostics([point('parent_net_income_yoy')],period='2025-12-31')
    assert next(r for r in d['fields'] if r['field']=='net_income_yoy')['label']=='归母净利润同比'
    assert next(r for r in d['fields'] if r['field']=='net_income_yoy')['status']=='AVAILABLE_PENDING_VERIFICATION'


def test_partial_debt_not_complete_and_zero_is_observed():
    d,_=build_diagnostics([point('interest_bearing_debt','100','CNY'),point('cash','0','CNY')],period='2025-12-31')
    assert next(r for r in d['fields'] if r['field']=='interest_bearing_debt')['status']=='PARTIAL_SCOPE'
    assert next(r for r in d['fields'] if r['field']=='cash')['value']=='0'


def test_institution_requires_different_metrics_not_bad_stock():
    d,a=build_diagnostics([],period='2025-12-31',institution_kind='bank')
    assert a['kind']=='bank' and '不良贷款率' in a['required_metrics'] and a['provisional']


def test_conflicting_unit_and_period_never_selected():
    d,_=build_diagnostics([point('roe'),point('roe_weighted','12'),point('cash','2','万元')],period='2025-12-31')
    assert d['conflict_count']==2 and d['available_count']==0


def test_statement_amounts_use_group_profit_not_parent_or_share_proxies():
    from value_investment_agent.domain.discovery.financial_gap_diagnostics_v1 import statement_observations
    ref=dict(path='runtime/test.json',sha256='a'*64,source_url='https://example.test',acquired_at='2026-11-02T00:00:00+00:00')
    def row(**raw):return dict(raw=raw,source_ref=ref)
    data=dict(balance={'600001':row(MONETARYFUNDS=50,TOTAL_ASSETS=100,TOTAL_LIABILITIES=20)},
              income={'600001':row(NETPROFIT=10,PARENT_NETPROFIT=8,TOTAL_OPERATE_INCOME=200,NETPROFIT_YOY=5)},
              cashflow={'600001':row(NETCASH_OPERATE=12)})
    points=statement_observations(data,period='2025-12-31');p={r['field_name']:r for r in points}
    assert p['net_margin']['value']=='5.00' and p['operating_cash_flow_to_net_income']['value']=='120.0'
    assert p['cash']['value']=='50' and p['debt_ratio']['value']=='20.0'
    assert 'interest_bearing_debt' not in p
    assert all(r['validation_status']=='unverified' for r in points)
    data['income']['600001']['raw']['NETPROFIT']=0
    d,_=build_diagnostics(statement_observations(data,period='2025-12-31'),period='2025-12-31')
    ratio=next(p for p in d['fields'] if p['field']=='operating_cash_flow_to_net_income')
    assert ratio['status']=='PARTIAL_SCOPE' and ratio['value'] is None
    assert '非正' in ratio['reason']


def test_group_profit_derived_from_reported_pretax_and_tax_not_parent():
    from value_investment_agent.domain.discovery.financial_gap_diagnostics_v1 import statement_observations
    ref=dict(path='runtime/test.json',sha256='a'*64,source_url='https://example.test',acquired_at='2026-11-02T00:00:00+00:00')
    data=dict(income={'600001':dict(raw=dict(TOTAL_PROFIT=16,INCOME_TAX=4,PARENT_NETPROFIT=8,TOTAL_OPERATE_INCOME=200),source_ref=ref)},
              cashflow={'600001':dict(raw=dict(NETCASH_OPERATE=18),source_ref=ref)},balance={})
    p={r['field_name']:r for r in statement_observations(data,period='2025-12-31')}
    assert p['net_margin']['value']=='6.00'
    assert p['operating_cash_flow_to_net_income']['value']=='150.0'
    del data['income']['600001']['raw']['INCOME_TAX']
    assert not any(r['field_name']=='net_margin' for r in statement_observations(data,period='2025-12-31'))

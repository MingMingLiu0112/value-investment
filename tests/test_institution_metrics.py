from value_investment_agent.institution_metrics import parse_tables
from value_investment_agent.financial_institutions import provisional_financial_type
from value_investment_agent.financial_quality import evaluate_financial_quality


def test_official_current_first_table_has_percentage_and_page():
    facts=parse_tables(['2026年6月30日 2025年12月31日\n不良贷款率 1.05% 1.06%\n拨备覆盖率 219.58% 220.88%'],
                       'bank','2026-06-30')
    assert len(facts)==2
    assert facts[0]['value']=='1.05'
    assert facts[0]['page_number']==1


def test_current_period_end_before_opening_is_explicit_and_parent_scoped():
    page = ('七、母公司净资本及有关风险控制指标\n'
            '项目名称 本报告期末 本报告期初 本报告期末比\n期初增减\n'
            '风险覆盖率 196.45% 224.46% -28.01%\n'
            '资本杠杆率 15.44% 16.33% -0.89%\n'
            '流动性覆盖率 211.83% 181.44% 30.39%\n'
            '净稳定资金率 162.27% 163.21% -0.94%')
    facts = parse_tables([page], 'broker', '2026-06-30')
    assert [f['value'] for f in facts] == ['196.45', '15.44', '211.83', '162.27']
    assert all(f['statement_scope'] == '母公司（原文明确）' for f in facts)
    assert not parse_tables([page.replace('本报告期末 本报告期初', '本报告期初 本报告期末')],
                            'broker', '2026-06-30')


def test_rejects_historical_first_regulatory_missing_units_and_conflicts():
    for page in ['2025年12月31日 2026年6月30日\n不良贷款率 1.05% 1.06%',
                 '不良贷款率 1.05% 1.06%',
                 '本报告期末 上年度末\n不良贷款率 1.05 1.06',
                 '本报告期末 上年度末\n监管标准\n风险覆盖率(%) 100.00 225.00']:
        assert not parse_tables([page],'bank' if '不良' in page else 'broker','2026-06-30')
    assert not parse_tables(['本报告期末 上年度末\n不良贷款率 1.05% 1.06%',
                             '本报告期末 上年度末\n不良贷款率 1.08% 1.09%'],'bank','2026-06-30')


def test_insurers_are_not_scored_as_industrial_enterprises():
    for name in ['中国人寿','中国太保','中国平安','中国人保','新华保险']:
        assert provisional_financial_type(name,'非银金融')=='insurer'


def test_broker_heading_with_collapsed_chinese_spaces():
    assert len(parse_tables(['监管标准说明\n项目 本报告期末 上年度末\n风险覆盖率(%) 225.31 210.46'],
                            'broker','2026-06-30'))==1


def test_explicit_parent_risk_table_preserves_scope_evidence():
    page = '(三)母公司的净资本及风险控制指标\n项目 本报告期末 上年度末\n资本杠杆率(%) 17.21 19.95'
    facts = parse_tables([page], 'broker', '2026-06-30')
    assert facts[0]['statement_scope'] == '母公司（原文明确）'
    assert facts[0]['scope_evidence'] == '(三)母公司的净资本及风险控制指标'
    assert facts[0]['value'] == '17.21'
    unspecified = parse_tables(['项目 本报告期末 上年度末\n资本杠杆率(%) 17.21 19.95'], 'broker', '2026-06-30')
    assert unspecified[0]['scope_evidence'] is None


def test_institution_coverage_is_dynamic_without_fabricated_quality_score():
    p={'field_name':'npl_ratio','period_label':'2026-06-30','value':'1.05',
       'validation_status':'verified','metadata':{'automatic_cross_source_verification':True}}
    result=evaluate_financial_quality('000001','平安银行','银行',[p])
    assert result.coverage_ratio==0.25
    assert result.total_score is None
    assert '1/4' in result.reasons[0]


def test_cmb_vertical_dates_units_and_footnotes():
    page='''财务比率(%)
2026年
1-6月
2025年
1-6月
盈利能力指标(年化)
净利息收益率(2) 1.83 1.88
资产质量指标(%)
2026年
6月30日
2025年
12月31日
不良贷款率 0.94 0.94
拨备覆盖率(1) 385.10 391.79'''
    facts={f['field_name']:f for f in parse_tables([page],'bank','2026-06-30')}
    assert facts['net_interest_margin']['value']=='1.83'
    assert facts['npl_ratio']['value']=='0.94'
    assert facts['provision_coverage']['value']=='385.10'


def test_explicit_regulatory_comparator_is_not_the_company_ratio():
    facts=parse_tables(['单位:%\n项目 标准值 2026年6月30日 2025年12月31日\n拨备覆盖率 ≥130(注 3) 219.58 220.88'],
                       'bank','2026-06-30')
    assert facts[0]['value']=='219.58'


def test_regulatory_thresholds_after_reported_columns_do_not_shift_values():
    page = ('七、母公司净资本及有关风险控制指标\n'
            '项目 本报告期末 上年度末\n本报告期末比上年度末增减\n预警标准 监管标准\n'
            '资本杠杆率 18.37% 18.90% 减少 0.53 个百分点 ≥9.6% ≥8%\n'
            '流动性覆盖率 292.22% 268.07% 增加 24.15个百分点 ≥120% ≥100%')
    facts = parse_tables([page], 'broker', '2026-06-30')
    assert [r['value'] for r in facts] == ['18.37', '292.22']


def test_rounding_is_not_a_conflict_but_method_difference_is():
    facts=parse_tables(['2026年6月30日 2025年12月31日\n核心偿付能力充足率 156.80% 128.77%',
                        '2026年6月30日 2025年12月31日\n核心偿付能力充足率 157% 129%'],'insurer','2026-06-30')
    assert facts[0]['value']=='156.80'
    assert facts[0]['supporting_pages']==[1,2]
    assert not parse_tables(['资本充足率指标(%) 高级法\n2026年6月30日 2025年12月31日\n核心一级资本充足率 14.07 14.16',
                             '资本充足率指标(%) 权重法\n2026年6月30日 2025年12月31日\n核心一级资本充足率 11.84 11.90'],
                             'bank','2026-06-30')

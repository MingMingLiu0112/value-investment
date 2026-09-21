from value_investment_agent.institution_metrics import parse_tables


HEADER = '监管指标\n监管\n标准\n2026年6月30日 2025年12月31日 2024年12月31日\n'
FIRST = HEADER + '资本状况\n核心一级资本充足率（%） ≥7.5 10.63 10.93 11.08\n'
SECOND = ('某银行2026年半年度报告全文\n8\n流动性 流动性比例（%） ≥25 91 90 89\n'
          '不良贷款率（%） ≤5 0.94 0.94 0.94\n'
          '拨备覆盖率（%） ≥150 325.07 328.87 376.03\n'
          '净息差（%） 不适用 1.35 1.39 1.62\n注：说明\n')


def test_regulatory_threshold_is_not_the_value():
    facts = parse_tables([FIRST, SECOND], 'bank', '2026-06-30')
    assert {f['field_name']: f['value'] for f in facts} == {
        'cet1_ratio': '10.63', 'npl_ratio': '0.94', 'provision_coverage': '325.07'}
    assert all(f['period_header_page'] == 1 for f in facts)


def test_no_header_leak_across_gap_or_new_table():
    facts = parse_tables([FIRST, '', SECOND], 'bank', '2026-06-30')
    assert not any(f['field_name'] == 'provision_coverage' for f in facts)
    facts = parse_tables([FIRST, SECOND.replace('不良贷款率', '项目\n不良贷款率')], 'bank', '2026-06-30')
    assert not any(f['field_name'] == 'provision_coverage' for f in facts)

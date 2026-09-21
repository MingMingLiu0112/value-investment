from value_investment_agent.institution_metrics import parse_tables


HEADER = ('七、母公司净资本及有关风险控制指标\n单位：元\n'
          '项目 本报告期末 上年度末 本报告期末比上年度末增减\n'
          '核心净资本 23,440 23,393 0.20%\n附属净资本 4,870 3,960 22.98%\n')
BODY = ('某证券2026年半年度报告\n8\n净资本 28,310 27,353 3.50%\n'
        '风险覆盖率 343.21% 356.45% 下降13.24个百分点\n'
        '资本杠杆率 25.21% 27.81% 下降2.60个百分点\n'
        '流动性覆盖率 304.74% 321.05% 下降16.31个百分点\n'
        '净稳定资金率 184.10% 194.73% 下降10.63个百分点\n')


def test_broker_continuation_preserves_parent_scope():
    facts = parse_tables([HEADER, BODY], 'broker', '2026-06-30')
    assert {f['value'] for f in facts} == {'343.21', '25.21', '304.74', '184.10'}
    assert all(f['period_header_page'] == 1 and f['page_number'] == 2
               and f['statement_scope'] == '母公司（原文明确）' for f in facts)


def test_no_scope_or_header_carry_across_gaps_or_new_tables():
    assert not parse_tables([HEADER, '', BODY], 'broker', '2026-06-30')
    assert not parse_tables([HEADER.replace('母公司', '子公司'), BODY], 'broker', '2026-06-30')
    assert not parse_tables([HEADER, BODY.replace('风险覆盖率', '项目\n风险覆盖率')], 'broker', '2026-06-30')

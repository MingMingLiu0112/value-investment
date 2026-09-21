from value_investment_agent.financing_table import TITLE, extract_financing_total, extract_financing_components


def table(wrapped=False):
    values = ['2,845,794,781.76','7,676,503,207.85','358,737,056.69',
              '6,675,219,938.53','193,159,483.42','4,012,655,624.35']
    parts = [v[:-2] if wrapped and i in (0,1,3,5) else v for i,v in enumerate(values)]
    row = '合计    ' + ''.join(v.ljust(24) for v in parts)
    tail = ' '*6 + ''.join((' '*(len(parts[i])-2)+values[i][-2:]).ljust(24)
                           if i in (0,1,3,5) else ' '*24 for i in range(6))
    return '\n'.join([TITLE,'单位：元','项目 期初余额 本期增加 本期减少 期末余额',
        '现金变动 非现金变动 现金变动 非现金变动',row,tail if wrapped else '', '(4) next'])


def test_total_and_wrapped_total():
    for wrapped in (False,True):
        result = extract_financing_total(table(wrapped))
        assert result['amounts']['closing']=='4012655624.35'
        assert result['status']=='total_reconciled_components_and_scope_unverified'


def test_bad_unit_amount_or_headers_block():
    for old,new in [('单位：元','单位：万元'),('4,012,655,624.35','4,012,655,624.36'),
                    ('本期增加','本期减少'),('非现金变动','现金变动')]:
        assert extract_financing_total(table().replace(old,new)) is None


def test_missing_wrapped_digits_do_not_get_invented():
    lines = table(True).splitlines()
    del lines[-2]
    assert extract_financing_total('\n'.join(lines)) is None


def test_parenthesized_component_label_stays_one_row():
    def line(label, values):
        return label.ljust(22)+''.join(v.ljust(24) for v in values)
    layout = '\n'.join([TITLE,'单位：元','项目 期初余额 本期增加 本期减少 期末余额',
        '现金变动 非现金变动 现金变动 非现金变动','长期借款（含',
        line('一年内到期的',['10.00','2.00','1.00','3.00','0.00','10.00']),
        '长期借款）',line('合计',['10.00','2.00','1.00','3.00','0.00','10.00'])])
    result = extract_financing_components(layout)
    assert len(result['rows'])==1
    assert result['rows'][0]['label']=='长期借款（含一年内到期的长期借款）'
    assert result['balances_reconcile']
    assert result['full_movements_reconcile']
    incomplete = layout.replace(line('一年内到期的',['10.00','2.00','1.00','3.00','0.00','10.00']),
        line('一年内到期的',['10.00','2.00','1.00','3.00','','10.00']))
    result = extract_financing_components(incomplete)
    assert result['balances_reconcile']
    assert not result['full_movements_reconcile']

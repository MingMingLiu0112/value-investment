from value_investment_agent.filing_extract import extract_candidates_from_pages


def page(title):
    return ('单位:人民币千元\n资产 附注 期末数 期初数\n'
            + '表格留白\n' * 30 + '资产总计 120,292,088.16 96,946,024.77\n'
            + title + '\n 法定代表人: 方某 主管会计工作负责人：袁某\n')


def test_footer_consolidated_heading_retains_unit_and_page():
    rows = extract_candidates_from_pages([page('合并资产负债表')])
    asset = next(r for r in rows if r['field_name'] == 'total_assets')
    assert asset['value'] == '120292088160.00'
    assert asset['page'] == 1 and asset['unit'] == 'CNY'


def test_footer_parent_heading_never_promotes_parent_amounts():
    rows = extract_candidates_from_pages([page('母公司资产负债表')])
    assert not rows

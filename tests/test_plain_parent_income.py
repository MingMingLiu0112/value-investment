from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_plain_parent_income_requires_consolidated_statement_scope():
    pages = ['主要子公司分析\n单位：百万元\n归属于母公司股东的净利润 999 888',
             '合并利润表\n单位：百万元\n营业成本 100 90',
             '合并利润表 (续)\n单位：百万元\n1. 归属于母公司股东的净利润 58,671 59,694',
             '母公司利润表\n单位：百万元\n归属于母公司股东的净利润 123 456']
    rows = [r for r in extract_candidates_from_pages(pages) if r['field_name']=='net_income']
    assert len(rows)==1 and rows[0]['value']=='58671000000'
    assert rows[0]['page']==3


def test_owner_income_with_standalone_unit_and_conflict_rejection():
    text = ('合并利润表\n人民币百万元\n项目 附注 2018 年度 2017 年度\n'
            '1、归属于母公司所有者的净利润 43,867 45,037\n')
    rows = extract_candidates_from_pages([text])
    assert len(rows)==1 and rows[0]['value']=='43867000000'
    assert not extract_candidates_from_pages([text+'单位：万元\n'])
    assert not extract_candidates_from_pages([text.replace('合并利润表','母公司利润表')])
    assert not extract_candidates_from_pages([text.replace('人民币百万元','某项目人民币百万元说明')])

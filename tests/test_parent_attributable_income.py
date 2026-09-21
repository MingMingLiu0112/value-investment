from value_investment_agent.filing_extract import extract_candidates_from_pages


LABEL = '1.归属于母公司股东的净利润\n（净亏损以“-”号填列）\n'


def test_consolidated_parent_attributable_income_continuation():
    pages = ['合并利润表\n单位：元\n2025年度 2024年度',
             LABEL+'285,734,507.57 307,319,470.37']
    rows = [r for r in extract_candidates_from_pages(pages) if r['field_name']=='net_income']
    assert len(rows)==1 and rows[0]['value']=='285734507.57' and rows[0]['page']==2


def test_parent_company_statement_is_not_consolidated_income():
    pages = ['母公司利润表\n单位：元\n'+LABEL+'47,671,114.19 94,649,589.26']
    assert not extract_candidates_from_pages(pages)


def test_total_net_profit_and_minority_interest_do_not_match():
    pages = ['合并利润表\n单位：元\n五、净利润 100.00 90.00\n少数股东损益 10.00 9.00']
    assert not extract_candidates_from_pages(pages)

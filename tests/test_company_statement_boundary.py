import pytest
from value_investment_agent.filing_extract import extract_candidates_from_pages


@pytest.mark.parametrize('title,label,field', [
    ('利润表', '营业成本', 'operating_cost'),
    ('现金流量表', '经营活动产生的现金流量净额', 'operating_cash_flow'),
    ('资产负债表', '货币资金', 'cash'),
])
@pytest.mark.parametrize('same_page', [False, True])
def test_company_heading_ends_consolidated_scope(title, label, field, same_page):
    pages = [f'合并{title}\n人民币百万元\n{label} 67,511 54,288',
             f'公司{title}\n人民币百万元\n{label} 10,626 1,754',
             f'附注\n{label} 10,626 1,754']
    if same_page:
        pages = ['\n'.join(pages)]
    facts = [r for r in extract_candidates_from_pages(pages) if r['field_name'] == field]
    assert len(facts) == 1
    assert facts[0]['value'] == '67511000000'

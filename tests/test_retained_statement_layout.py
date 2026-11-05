"""TEST_ONLY layouts plus opt-in retained official original replay; no admission."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as parser
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages


CONTEXT = '本集团编制本财务报表时所采用的货币为人民币。'


def balance():
    return ['1、合并资产负债表\n2025 年 12 月 31 日\n单位：元\n项目 期末余额 期初余额\n'
            '资产总计 120.00 100.00\n短期借款 12.00 10.00',
            '负债合计 50.00 40.00\n长期借款 15.00 14.00\n'
            '2、母公司资产负债表\n单位：元\n项目 期末余额 期初余额\n'
            '资产总计 999.00 888.00\n负债合计 777.00 666.00\n短期借款 444.00 333.00',
            CONTEXT]


def income():
    return ['3、合并利润表\n单位：元\n项目 2025 年度 2024 年度\n营业收入 120.00 100.00',
            '归属于母公司股东的净利润 24.00 20.00\n4、母公司利润表\n'
            '单位：元\n项目 2025 年度 2024 年度\n营业收入 999.00 888.00', CONTEXT]


def extract(kind, pages):
    if kind == 'income':
        return parser.extract_income_comparatives(pages, '2025-12-31')
    return parser.extract_debt_balance_candidates(pages, '2025-12-31', balance_totals=True)


@pytest.mark.parametrize('kind', ['balance', 'income'])
def test_numbered_separate_currency_and_in_page_boundary(kind):
    pages = balance() if kind == 'balance' else income()
    rows = extract(kind, pages)
    assert [r['value'] for r in rows] == (['120.00','50.00'] if kind == 'balance' else ['120.00','24.00'])
    for row in rows:
        assert row['currency'] == 'CNY' and row['currency_evidence_page'] == 3
        assert row['currency_evidence_excerpt'] == CONTEXT
        assert row['period_evidence_page'] == 1
        assert row['unit_evidence_excerpt'] == '单位：元'
        assert row['statement_scope'] == 'consolidated'
        assert 'unverified' in row['status'].lower() or 'NOT_INDEPENDENTLY_ADMITTED' in row['status']
    if kind == 'balance':
        assert rows[0]['prior_period_basis'] == 'ANNUAL_OPENING_INFERRED_NOT_EXPLICIT_SECOND_DATE'
        debts = parser.extract_debt_balance_candidates(pages,'2025-12-31')
        assert [r['value'] for r in debts] == ['12.00','15.00']


@pytest.mark.parametrize('kind', ['balance','income'])
@pytest.mark.parametrize('context', ['', '境外子公司以人民币为记账本位币。',
    '本公司以人民币为记账本位币。', '本集团编制本财务报表时所采用的货币为美元。',
    CONTEXT+'本集团编制本财务报表时所采用的货币为美元。'])
def test_insufficient_or_conflicting_group_currency_rejected(kind, context):
    pages = balance() if kind == 'balance' else income()
    pages[-1] = context
    assert extract(kind,pages) == []


@pytest.mark.parametrize('kind', ['balance','income'])
def test_issuer_report_presentation_currency_is_supported(kind):
    pages = balance() if kind == 'balance' else income()
    pages[-1] = '本公司编制本财务报表时所采用的货币为人民币。'
    rows = extract(kind,pages)
    assert len(rows) == 2
    assert all(r['currency_evidence_page'] == 3 and
               r['currency_evidence_excerpt'] == pages[-1] for r in rows)


@pytest.mark.parametrize('context', [
    '本公司之境外子公司以人民币为记账本位币。',
    '人民币为本公司及境内子公司经营所处的主要经济环境中的货币。',
    '本公司编制本财务报表时所采用的货币为人民币。'
    '本集团编制本财务报表时所采用的货币为美元。',
    '本公司编制本财务报表时所采用的货币为人民币。'
    '本公司编制本财务报表时所采用的货币为港元。'])
def test_functional_currency_or_conflicting_presentation_currency_is_not_admitted(context):
    for pages, kind in ((balance(),'balance'), (income(),'income')):
        pages[-1] = context
        assert extract(kind,pages) == []


@pytest.mark.parametrize('kind', ['balance','income'])
def test_local_currency_conflict_and_missing_unit_rejected(kind):
    pages = balance() if kind == 'balance' else income()
    pages[0] = pages[0].replace('单位：元','单位：元 币种：美元')
    assert extract(kind,pages) == []
    pages[0] = pages[0].replace('单位：元 币种：美元','')
    assert extract(kind,pages) == []


@pytest.mark.parametrize('fault', ['no_date','wrong_date','reversed','extra_date','restated','third_column','single'])
def test_relative_columns_require_report_date_order_and_two_values(fault):
    pages = balance()
    if fault == 'no_date': pages[0] = pages[0].replace('2025 年 12 月 31 日','')
    if fault == 'wrong_date': pages[0] = pages[0].replace('2025 年 12 月 31 日','2026年12月31日')
    if fault == 'reversed': pages[0] = pages[0].replace('期末余额 期初余额','期初余额 期末余额')
    if fault == 'extra_date': pages[0] = pages[0].replace('单位：元','2024年12月31日\n单位：元')
    if fault == 'restated': pages[0] = pages[0].replace('期初余额','期初余额 调整后')
    if fault == 'third_column': pages[0] = pages[0].replace('120.00 100.00','120.00 100.00 90.00')
    if fault == 'single': pages[0] = pages[0].replace('120.00 100.00','120.00')
    assert not any(r['field_name']=='total_assets' for r in extract('balance',pages))


def test_income_cannot_borrow_parent_years_or_unit():
    pages = income()
    pages[0] = pages[0].replace('2025 年度 2024 年度','2024 年度 2023 年度')
    assert extract('income',pages) == []
    pages = ['3、合并利润表\n项目 2025年度 2024年度\n营业收入 120.00 100.00\n'
             '4、母公司利润表\n单位：元 币种：人民币\n营业收入 999.00 888.00',CONTEXT]
    assert extract('income',pages) == []


@pytest.mark.parametrize('symbol',['000498','600519','600887'])
def test_retained_real_official_originals(symbol):
    raw = os.environ.get('RETAINED_LAYOUT_REAL_ROOT')
    if not raw:
        pytest.skip('Explicit retained public original root required; no downloads')
    root = Path(raw)
    if symbol == '000498':
        path = root/'runtime/daily-marketwide/20261025T0017454129658Z/research-priority-v2-enrichment/000498-official-original/original.pdf'
        expected_sha = 'ecbc66587299817b4c51f8f029ccc77baf4b61b004477c712c4973b8226ffa17'
        expected = [('revenue','68567696803.55','71353764354.48',156),
                    ('net_income','2227194256.24','2322991718.37',157)]
    else:
        spec = json.loads((root/'docs/current/two-company-earnings-bridge-20261024/sources.json').read_text(encoding='utf-8'))['companies'][symbol][0]
        path, expected_sha = root/spec['path'], spec['sha256']
        expected = {'600519':[('revenue','168838102514.79','170899152276.34',61),
                              ('net_income','82320067101.68','86228146421.62',62)],
                    '600887':[('revenue','115636231250.05','115393310976.69',86),
                              ('net_income','11565166497.81','8452859993.18',87)]}[symbol]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha
    pages = extract_pages(path)
    rows = extract('income',pages)
    assert [(r['field_name'],r['value'],r['prior_value'],r['page']) for r in rows] == expected
    for row in rows:
        assert row['currency_evidence_excerpt'] in pages[row['currency_evidence_page']-1]
        assert row['period_evidence_excerpt'] in pages[row['period_evidence_page']-1]
        assert row['unit_evidence_excerpt'] in pages[row['unit_evidence_page']-1]
    if symbol == '000498':
        totals = extract('balance',pages)
        assert [(r['field_name'],r['value'],r['page']) for r in totals] == [
            ('total_assets','182362833542.24',152),('total_liabilities','139525056417.84',153)]
        assert all(r['currency_evidence_page']==175 for r in rows+totals)
        assert all(r['period_evidence_page']==151 for r in totals)
        assert all(r['period_evidence_excerpt'] in pages[150] for r in totals)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha

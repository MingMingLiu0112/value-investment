"""Direct tests for the four-page consolidated balance replay."""
from datetime import datetime, timezone

import pytest

from value_investment_agent.infrastructure.filings import first_research_fact_replay_v2 as v2
from test_first_research_fact_replay_v1 import native as v1_native


@pytest.fixture
def native(tmp_path, monkeypatch):
    case = v1_native.__wrapped__(tmp_path, monkeypatch)
    spec, pages = case['spec'], case['pages']
    spec['schema_version'] = v2.SCHEMA
    spec['symbol'] = spec['sources'][0]['symbol'] = '600519'
    spec['issuer_name'] = spec['sources'][0]['issuer_name'] = '贵州茅台酒股份有限公司'
    spec['financial_basis'] = spec['sources'][0]['report_period'] = '2025-06-30'
    spec['sources'][0]['report_title'] = '2025年半年度报告'
    spec['facts'] = [spec['facts'][1]]
    row = spec['facts'][0]
    row.update(physical_page=4, header_pages=[1, 2, 3, 4],
               period_end='2025-06-30', column_periods=['2025-06-30', '2024-12-31'],
               column_header='项目 2025年6月30日 2024年12月31日')
    pages[:] = [
        '公司代码：600519\n贵州茅台酒股份有限公司\n2025年半年度报告\n合并资产负债表\n2025 年 6 月 30 日\n单位：元 币种：人民币\n' + row['column_header'],
        '资产总计 400.00 330.00', '负债合计 100.00 80.00',
        row['excerpt'] + '\n少数股东权益 20.00 15.00',
    ]
    monkeypatch.setattr(v2, 'extract_pages', lambda path: list(pages))
    return case


def replay(case):
    return v2.replay_first_research_facts(root=case['root'], binding=case['seal'](),
                                          now=datetime(2026, 10, 31, tzinfo=timezone.utc))


def test_four_page_primary_equity_preserves_provenance(native):
    result = replay(native)
    row, = result['facts']
    assert result['schema_version'] == v2.SCHEMA
    assert result['action'] == 'no_order' and not result['formal_eligibility']
    assert (row['value'], row['unit'], row['scope'], row['period_end']) == (
        '300.00', 'CNY', 'consolidated_parent_equity', '2025-06-30')
    assert row['source_sha256'] == native['spec']['sources'][0]['sha256']
    assert result['symbol'] == '600519'


@pytest.mark.parametrize('fault', ['shifted', 'duplicate', 'wrong_page', 'wrong_period', 'wrong_scope'])
def test_four_page_rejects_invalid_span(native, fault):
    pages, row = native['pages'], native['spec']['facts'][0]
    if fault == 'shifted':
        pages.insert(1, 'preface')
        row.update(physical_page=5, header_pages=[2, 3, 4, 5])
    elif fault == 'duplicate':
        pages[2] += '\n' + row['excerpt']
    elif fault == 'wrong_page':
        row['header_pages'] = [2, 3, 4]
    elif fault == 'wrong_period':
        pages[0] = pages[0].replace('2025 年 6 月 30 日', '2025 年 3 月 31 日')
    else:
        pages[2] += '\n母公司资产负债表'
    with pytest.raises(ValueError):
        replay(native)

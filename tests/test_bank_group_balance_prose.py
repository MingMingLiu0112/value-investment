import pytest

from value_investment_agent.institution_metrics import _bank_group_prose
from value_investment_agent.institution_metrics import parse_tables


ASSET = ('报告期末，本集团不良贷款余额586.39亿元，比上年末增加78.97亿元；'
         '不良贷款率1.44%，比上年末上升0.17个百分点；'
         '拨备覆盖率150.02%，比上年末下降24.12个百分点；贷款拨备率2.16%。')
CAPITAL = ('报告期末，本集团核心一级资本净额5,026.30亿元，比上年末增加78.10亿元；'
           '一级资本净额6,077.49亿元；核心一级资本充足率9.67%，'
           '一级资本充足率11.69%，资本充足率13.35%，均符合监管要求。')


def test_explicit_group_metrics_after_section_headings():
    text = '（三）资产质量不断夯实\n' + ASSET + '\n（四）资本充足率\n' + CAPITAL
    facts = _bank_group_prose(text, 18, 'pypdf')
    values = {f['field_name']: f['value'] for f in facts}
    assert values == {'npl_ratio': '1.44', 'provision_coverage': '150.02', 'cet1_ratio': '9.67'}
    assert all(f['scope_evidence'] and f['page_number'] == 18 for f in facts)


@pytest.mark.parametrize('prefix', ['预计', '目标为', '假设', '上年'])
def test_forecast_or_historical_prefix_is_not_current(prefix):
    assert _bank_group_prose(prefix + CAPITAL, 1, 'pypdf') == []


@pytest.mark.parametrize('entity', ['母公司', '子公司', '本行'])
def test_other_entity_not_group(entity):
    assert _bank_group_prose(CAPITAL.replace('本集团', entity), 1, 'pypdf') == []


def test_footnote_removed_only_with_same_page_matching_definition():
    table = ('项目 2026年6月30日 2025年12月31日\n资产质量指标（%）\n'
             '拨备覆盖率 6 150.02 174.14\n')
    defined = table + '6.拨备覆盖率=贷款减值准备/不良贷款余额。'
    facts = parse_tables([defined], 'bank', '2026-06-30')
    assert facts[0]['value'] == '150.02'
    # Without an explicit definition the integer must not silently disappear.
    assert not any(f['value'] == '150.02' for f in parse_tables([table], 'bank', '2026-06-30'))


def test_continued_margin_requires_adjacent_matching_duration_header():
    previous = ('项目 2026年1-6月 2025年1-6月 本期比上年同期增减 2024年1-6月\n'
                '盈利能力指标（%）\n净利差 1.36 1.31 +0.05个百分点 1.46\n')
    current = '9\n净利息收益率 1.42 1.40 +0.02个百分点 1.54\n'
    facts = parse_tables([previous, current], 'bank', '2026-06-30')
    assert facts[0]['value'] == '1.42'
    assert facts[0]['period_header_page'] == 1
    assert facts[0]['page_number'] == 2
    assert facts[0]['period_basis'] == 'YTD'
    assert not parse_tables([previous, '', current], 'bank', '2026-06-30')
    assert not parse_tables([previous, current], 'bank', '2026-09-30')
    assert not parse_tables([previous + '项目 2025年12月31日\n', current], 'bank', '2026-06-30')

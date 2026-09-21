from value_investment_agent.institution_metrics import parse_tables


def test_dated_table_retains_period_across_unit_section_and_blank_lines():
    text = ('项目 2026年1-6月 2025年1-6月\n\n盈利能力指标（%）\n\n净息差 1.59 1.54\n'
            '项目 2026年6月30日 2025年12月31日\n\n资产质量指标（%）\n\n'
            '不良贷款率 1.50 1.55\n拨备覆盖率 144.80 143.30')
    facts = {f['field_name']: f for f in parse_tables([text], 'bank', '2026-06-30')}
    assert {k: v['value'] for k, v in facts.items()} == {
        'net_interest_margin': '1.59', 'npl_ratio': '1.50', 'provision_coverage': '144.80'}
    assert facts['net_interest_margin']['period_basis'] == 'YTD'


def test_unit_caption_does_not_override_historical_first_columns():
    text = ('项目 2025年12月31日 2026年6月30日\n资产质量指标（%）\n不良贷款率 1.55 1.50')
    assert parse_tables([text], 'bank', '2026-06-30') == []


def long_table(extra='', current='2026', prior='2025'):
    return (f'{current}年\n1-6月\n{prior}年\n1-6月\n本报告期比\n上年同期\n'
            '2024年\n1-6月\n经营业绩（人民币百万元） 增减(%)\n'
            + '营业收入 10 9 8\n' * 32 + extra
            + '盈利能力指标(%) 变动百分点\n净息差（年化） 1.47 1.39 0.08 1.38')


def test_explicit_long_summary_header_preserves_ytd_period():
    facts = parse_tables([long_table()], 'bank', '2026-06-30')
    assert len(facts) == 1
    assert facts[0]['value'] == '1.47'
    assert facts[0]['period_basis'] == 'YTD'


def test_long_context_does_not_cross_new_dates_sections_or_scopes():
    for extra in ('二、其他指标\n', '母公司\n', '2025年12月31日\n'):
        assert parse_tables([long_table(extra)], 'bank', '2026-06-30') == []
    assert parse_tables([long_table(current='2025', prior='2026')], 'bank', '2026-06-30') == []

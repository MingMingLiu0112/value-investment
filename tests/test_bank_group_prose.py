import pytest
import unicodedata

from value_investment_agent.institution_metrics import parse_tables


def test_explicit_group_current_prose():
    facts = parse_tables(['业务稳步提升。报告期，集团净息差为1.43%，较上年提升。'
                          '经营平稳。报告期末，集团核心一级资本充足率9.05%，持续改善。'],
                         'bank', '2026-06-30')
    assert {f['field_name']: f['value'] for f in facts} == {
        'net_interest_margin': '1.43', 'cet1_ratio': '9.05'}
    assert all(f['statement_scope'] == '集团（原文明确）' for f in facts)


@pytest.mark.parametrize('text', [
    '预计下个报告期，集团净息差为1.43%。',
    '上年报告期，集团净息差为1.43%。',
    '报告期，子公司净息差为1.43%。',
    '报告期，集团净息差预计为1.43%。',
    '报告期末，集团核心一级资本充足率为999%。',
])
def test_no_forecast_historical_or_subsidiary_prose(text):
    assert parse_tables([text], 'bank', '2026-06-30') == []


def test_current_group_asset_quality_sentence():
    text = ('报告期末，本集团不良贷款余额732.02亿元，较上年末增加12.12亿元；'
            '不良贷款率1.25%，较上年末下降0.01个百分点；'
            '拨备覆盖率197.81%，较上年末下降2.91个百分点。')
    facts = parse_tables([text], 'bank', '2026-06-30')
    assert {f['field_name']: f['value'] for f in facts} == {
        'npl_ratio': '1.25', 'provision_coverage': '197.81'}
    assert all(f['scope_evidence'] == unicodedata.normalize('NFKC', text) for f in facts)


@pytest.mark.parametrize('tail', [
    '。不良贷款率1.25%。',
    '；子公司不良贷款率1.25%。',
    '；预计不良贷款率1.25%。',
    '；上年不良贷款率1.25%。',
])
def test_group_scope_cannot_leak_into_other_sentence_or_entity(tail):
    assert parse_tables(['报告期末，本集团不良贷款余额732亿元' + tail],
                        'bank', '2026-06-30') == []

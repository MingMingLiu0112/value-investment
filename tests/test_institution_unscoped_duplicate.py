from value_investment_agent.institution_metrics import parse_tables


def page(value, scoped=False):
    title = '\u6bcd\u516c\u53f8\u7684\u51c0\u8d44\u672c\u53ca\u98ce\u9669\u63a7\u5236\u6307\u6807\n' if scoped else ''
    return title + '\u9879\u76ee \u672c\u62a5\u544a\u671f\u672b \u4e0a\u5e74\u5ea6\u672b\n' + '\u98ce\u9669\u8986\u76d6\u7387(%) ' + value + ' 298.67\n'


def test_matching_unscoped_duplicate_does_not_erase_explicit_scope():
    facts = parse_tables([page('262.55', True), page('262.55')], 'broker', '2026-06-30')
    assert len(facts) == 1
    assert facts[0]['value'] == '262.55'
    assert facts[0]['scope_evidence']
    assert facts[0]['supporting_pages'] == [1]


def test_conflicting_unscoped_value_still_blocks():
    assert parse_tables([page('262.55', True), page('265.55')], 'broker', '2026-06-30') == []


def test_unscoped_alone_does_not_gain_parent_scope():
    facts = parse_tables([page('262.55')], 'broker', '2026-06-30')
    assert facts[0]['scope_evidence'] is None

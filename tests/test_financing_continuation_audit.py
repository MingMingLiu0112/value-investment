"""Do not attach arbitrary adjacent financial tables to a financing heading."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('financing_local_audit',
    Path(__file__).resolve().parents[1] / 'scripts' / 'audit_local_financing_tables.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

TITLE_PAGE = '3)' + module.TITLE + '\n\n177'
NEXT_PAGE = '\n'.join(['Company annual report', '本期增加 本期减少',
    '项目 期初余额 期末余额', '现金变动 非现金变动 现金变动 非现金变动',
    '银行借款及其他 10.00', '合计 10.00', '71、 现金流量表补充资料', 'unrelated'])


def test_heading_only_next_page_is_bounded_and_unit_not_invented():
    result = module.continuation_evidence(TITLE_PAGE, NEXT_PAGE)
    assert result is not None
    assert 'unrelated' not in result['layout']
    assert not result['explicit_cny_unit']


def test_intervening_content_and_duplicate_titles_reject():
    assert module.continuation_evidence(TITLE_PAGE + '\nother section', NEXT_PAGE) is None
    assert module.continuation_evidence(TITLE_PAGE + '\n' + module.TITLE, NEXT_PAGE) is None


def test_next_section_header_cannot_be_skipped():
    assert module.continuation_evidence(TITLE_PAGE, '71、 Other note\n' + NEXT_PAGE) is None
    assert module.continuation_evidence(TITLE_PAGE, '(4) Other note\n' + NEXT_PAGE) is None


def test_incomplete_header_is_not_continuation():
    assert module.continuation_evidence(TITLE_PAGE, NEXT_PAGE.replace('期初余额', '')) is None


def continuation_fixture():
    cells = [['项目', '期初余额', '本期增加', None, '本期减少', None, '期末余额'],
             [None, None, '现金变动', '非现金变动', '现金变动', '非现金变动', None],
             ['租赁负债(含一年内到期)', '100.00', '', '20.00', '30.00', '-10.00', '100.00'],
             ['合计', '100.00', '0.00', '20.00', '30.00', '-10.00', '100.00']]
    prefix = '某公司2025年年度报告全文\n\uf052适用□不适用\n单位：元'
    return NEXT_PAGE.replace('Company annual report', prefix), prefix, cells


def test_continuation_preserves_negative_blank_and_both_page_evidence():
    layout, prefix, cells = continuation_fixture()
    result = module.continuation_cells(TITLE_PAGE, layout, prefix, cells)
    assert result['rows'][0]['amounts']['noncash_decrease'] == '-10.00'
    assert result['rows'][0]['amounts']['cash_increase'] is None
    assert result['balances_reconcile']
    assert not result['full_movements_reconcile']
    assert not result['complete_debt_verified']
    assert result['previous_page_layout'] == TITLE_PAGE
    assert result['next_page_prefix'] == prefix
    assert 'unrelated' not in result['bounded_next_page_layout']


def test_continuation_requires_explicit_unit_applicability_and_no_intervening_prose():
    layout, prefix, cells = continuation_fixture()
    for invalid in (prefix.replace('单位：元', ''), prefix.replace('单位：元', '单位：万元'),
                    prefix.replace('\uf052适用□不适用', '□适用\uf052不适用'),
                    prefix + '\n其他表格', prefix.replace('单位：元', '58、其他资料\n单位：元')):
        assert module.continuation_cells(TITLE_PAGE, layout, invalid, cells) is None
    assert module.continuation_cells(TITLE_PAGE + '\n其他资料', layout, prefix, cells) is None
    assert module.continuation_cells(TITLE_PAGE, layout.replace('单位：元', ''), prefix, cells) is None
    assert module.continuation_cells(TITLE_PAGE, '58、其他资料\n' + layout, prefix, cells) is None


def test_unrelated_first_table_is_not_skipped():
    layout, prefix, _ = continuation_fixture()
    assert module.continuation_cells(TITLE_PAGE, layout, prefix,
                                    [['补充资料', '本期金额', '上期金额']]) is None

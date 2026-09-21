from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from value_investment_agent.current_maturities import (
    TITLE, extract_current_maturities, extract_current_maturity_continuation,
    extract_borderless_current_maturities)


CONTEXT = '31、' + TITLE + '\n单位：元'


def cells():
    return [['项目', '期末余额', '期初余额'],
            ['一年内到期的租赁负债', '170.00', '150.00'],
            ['一年内到期的远期外汇合约', '9.00', ''],
            ['合计', '179.00', '150.00']]


def test_derivatives_remain_separate_and_blank_prior_period_is_not_zero():
    result = extract_current_maturities(cells(), CONTEXT)
    assert result['rows'][1]['category'] == 'derivatives_separate_scope'
    assert result['rows'][1]['amounts']['opening'] is None
    assert result['reconciliation'] == {'closing': True, 'opening': False}
    assert not result['complete_debt_verified']


@pytest.mark.parametrize('marker', ['√', '\uf052', '☑'])
def test_explicit_thousand_units_and_applicable_marker_normalize(marker):
    context = CONTEXT.replace('单位：元', marker + '适用□不适用\n单位：千元 币种：人民币')
    result = extract_current_maturities(cells(), context)
    assert result['total']['amounts']['closing'] == '179000.00'
    assert result['rows'][1]['amounts']['opening'] is None
    assert result['normalization_multiplier'] == '1000'
    assert result['total']['unit'] == 'CNY'


def test_not_applicable_and_conflicting_units_reject():
    for suffix in ('□适用√不适用\n单位：千元 币种：人民币', '单位：元\n单位：千元', '单位：元 币种：美元'):
        assert extract_current_maturities(cells(), CONTEXT.replace('单位：元', suffix)) is None


def geometry_fixture():
    boxes = [(0, 0, 200, 20), (200, 0, 300, 20), (300, 0, 400, 20)]
    words = []
    for row, (label, closing, opening) in enumerate([
        ('一年内到期的长期借款', '', '100.00'),
        ('一年内到期的租赁负债', '10.00', '20.00'), ('合计', '10.00', '120.00')]):
        for column, text in enumerate((label, closing, opening)):
            if text:
                x = (10, 210, 310)[column]
                words.append({'text': text, 'x0': x, 'x1': x + 50, 'top': 30 + row * 20})
    return boxes, words


def test_borderless_body_preserves_empty_closing_column():
    boxes, words = geometry_fixture()
    result = extract_borderless_current_maturities(cells()[0], boxes, words, CONTEXT)
    assert result['rows'][0]['amounts'] == {'closing': None, 'opening': '100.00'}
    assert result['reconciliation'] == {'closing': False, 'opening': True}
    assert result['body_words'] == words
    assert not result['complete_debt_verified']


def test_borderless_requires_total_header_unit_and_unambiguous_columns():
    boxes, words = geometry_fixture()
    assert extract_borderless_current_maturities(cells()[0], boxes, words[:-3], CONTEXT) is None
    assert extract_borderless_current_maturities(cells()[0], boxes, words, TITLE) is None
    assert extract_borderless_current_maturities(['项目', '期初余额', '期末余额'], boxes, words, CONTEXT) is None
    crossing = deepcopy(words)
    crossing[1].update(x0=290, x1=320)
    assert extract_borderless_current_maturities(cells()[0], boxes, crossing, CONTEXT) is None
    wrong_label = deepcopy(words)
    wrong_label[0]['text'] = '其他流动负债'
    assert extract_borderless_current_maturities(cells()[0], boxes, wrong_label, CONTEXT) is None


@pytest.mark.parametrize('context', [TITLE + '\n单位：元', CONTEXT.replace('元', '万元'),
    CONTEXT.replace('单位：元', ''), CONTEXT.replace('单位：元', '32、其他资料\n单位：元'),
    CONTEXT + '\n其他说明', CONTEXT + '\n' + CONTEXT])
def test_explicit_note_and_unit_boundary_required(context):
    assert extract_current_maturities(cells(), context) is None


def test_conflict_is_retained_but_does_not_reconcile():
    table = cells()
    table[-1][1] = '180.00'
    result = extract_current_maturities(table, CONTEXT)
    assert not result['reconciliation']['closing']
    assert result['total']['amounts']['closing'] == '180.00'


def test_reversed_headers_and_duplicate_rows_are_rejected():
    table = cells()
    table[0][1:] = ['期初余额', '期末余额']
    assert extract_current_maturities(table, CONTEXT) is None
    table = cells()
    table.insert(2, deepcopy(table[1]))
    assert extract_current_maturities(table, CONTEXT) is None


@pytest.mark.parametrize('value', ['-1.00', 'NaN', '1.00 2.00', '说明'])
def test_malformed_component_cannot_create_reconciliation(value):
    table = cells()
    table[1][1] = value
    assert extract_current_maturities(table, CONTEXT) is None


def test_unknown_component_is_preserved_not_classified_as_borrowing():
    table = cells()
    table[2][0] = '一年内到期的职工福利'
    result = extract_current_maturities(table, CONTEXT)
    assert result['rows'][1]['category'] == 'requires_note_classification'
    assert result['reconciliation']['closing']


def test_nine_grid_merged_placeholders_preserve_actual_missing_cells():
    table = [['', '项目', '', '', '期末余额', '', '', '期初余额', '']]
    table += [['', row[0], '', row[1], None, None, row[2], None, None] for row in cells()[1:]]
    result = extract_current_maturities(table, CONTEXT)
    assert result['reconciliation'] == {'closing': True, 'opening': False}
    assert result['rows'][1]['amounts']['opening'] is None
    assert result['rows'][0]['raw_cells'] == table[1]
    table[1][4] = '1.00'
    assert extract_current_maturities(table, CONTEXT) is None


def test_long_label_can_span_all_label_subcells_without_losing_explicit_zero():
    table = [['', '项目', '', '', '期末余额', '', '', '期初余额', ''],
             ['一年内到期的长期应付职工薪酬', None, None, '0.00', None, None, '9.00', None, None],
             ['', '合计', '', '0.00', None, None, '9.00', None, None]]
    result = extract_current_maturities(table, CONTEXT)
    assert result['rows'][0]['amounts']['closing'] == '0.00'
    assert result['rows'][0]['category'] == 'requires_note_classification'
    assert result['reconciliation'] == {'closing': True, 'opening': True}


def test_eight_grid_integer_cny_is_not_assumed_to_be_thousands():
    table = [['', '项目', '', '', '期末余额', '', '期初余额', ''],
             ['', '一年内到期的长期应付款', '', '490,024,031', None, None, '568,753,565', None],
             ['', '合计', '', '490,024,031', None, None, '568,753,565', None]]
    result = extract_current_maturities(table, CONTEXT)
    assert result['rows'][0]['amounts']['closing'] == '490024031'
    assert result['rows'][0]['category'] == 'current_payables_require_terms'
    assert result['reconciliation']['closing']


@pytest.mark.parametrize('repeated_header', [False, True])
@pytest.mark.parametrize('first_has_row', [False, True])
def test_adjacent_continuation_preserves_headers_missing_values_and_scope(repeated_header, first_has_row):
    table = cells()
    first = table[:2] if first_has_row else table[:1]
    following = table[2:] if first_has_row else table[1:]
    if repeated_header:
        following = table[:1] + following
    result = extract_current_maturity_continuation(first, following, CONTEXT, '169', '示例股份有限公司2025年年度报告全文')
    assert result['reconciliation'] == {'closing': True, 'opening': False}
    assert not result['complete_debt_verified']
    assert result['previous_table_cells'] == first
    assert result['continuation_table_cells'] == following


def test_continuation_rejects_intervening_sections_units_and_completed_table():
    table = cells()
    prefix = '示例股份有限公司2025年年度报告全文'
    for tail, next_prefix, context in [('169\n其他说明', prefix, CONTEXT),
            ('169', '其他说明\n' + prefix, CONTEXT),
            ('169', prefix + '\n33、其他流动负债', CONTEXT),
            ('169', prefix, CONTEXT.replace('单位：元', '')), ('', prefix, CONTEXT)]:
        assert extract_current_maturity_continuation(table[:1], table[1:], context, tail, next_prefix) is None
    assert extract_current_maturity_continuation(table, table[1:], CONTEXT, '169', prefix) is None
    assert extract_current_maturity_continuation(table[:1], [['其他项目', '179.00', '150.00']], CONTEXT, '169', prefix) is None


@pytest.mark.parametrize('kind', ['lease', 'borrowing'])
def test_inclusive_bridge_uses_only_matching_component_not_all_maturities(kind):
    spec = importlib.util.spec_from_file_location('current_maturity_audit',
        Path(__file__).resolve().parents[1] / 'scripts' / 'audit_current_maturity_notes.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = {'symbol': '301376', 'report_period': '2025-12-31', 'sha256': 'a' * 64,
              'source_url': 'https://example.test/report.pdf'}
    base = {'symbol': source['symbol'], 'period_label': source['report_period'],
            'sha256': source['sha256'], 'source_url': source['source_url'], 'unit': 'CNY',
            'source_id': 'official', 'validation_status': 'verified',
            'metadata': {'automatic_cross_source_verification': True, 'secondary_source_id': 'secondary',
                         'secondary_data_point_id': 'second-fact', 'secondary_source_url': 'https://example.test/secondary',
                         'official_file_sha256': source['sha256']}}
    field = 'lease_liabilities_noncurrent' if kind == 'lease' else 'long_term_borrowings'
    label = '租赁负债' if kind == 'lease' else '长期借款'
    group = 'inclusive_lease_bridges' if kind == 'lease' else 'inclusive_borrowing_bridges'
    points = [{**base, 'data_point_id': 'total', 'field_name': 'current_portion_long_term_debt', 'value': '179'},
              {**base, 'data_point_id': 'component', 'field_name': field, 'value': '200'}]
    financing = {'rows': [{'label': label + '(含一年内到期)', 'amounts': {'closing': '370'}}]}
    table = cells()
    table[1][0] = '一年内到期的' + label
    note = extract_current_maturities(table, CONTEXT)
    result = module.reconcile(source, note, financing, points)
    bridge = result[group][0]
    assert bridge['derived_noncurrent_cny'] == '200.00'
    assert bridge['balance_bridge']['matched_rows'] == 1
    assert not bridge['complete_debt_verified']
    note['reconciliation']['closing'] = False
    assert module.reconcile(source, note, financing, points)[group] == []
    note['reconciliation']['closing'] = True
    points[0]['validation_status'] = 'pending'
    assert module.reconcile(source, note, financing, points)[group] == []
    points[0]['validation_status'] = 'verified'
    note['rows'][0]['amounts']['closing'] = None
    assert module.reconcile(source, note, financing, points)[group] == []

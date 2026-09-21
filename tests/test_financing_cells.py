from copy import deepcopy

from value_investment_agent.financing_cells import extract_financing_cells
from value_investment_agent.financing_table import TITLE

CONTEXT = TITLE + '\n单位：元'


def cells():
    return [['项目', '期初余额', '本期增加', None, '本期减少', None, '期末余额'],
            [None, None, '现金变动', '非现金变动', '现金变动', '非现金变动', None],
            ['短期借款', '1,2\n00.00', '200.00', '10.00', '300.00', '10.00', '1,100.00'],
            ['合计', '1,2\n00.00', '200.00', '10.00', '300.00', '10.00', '1,100.00']]


def test_fragmented_cells_preserve_raw_evidence_and_reconcile():
    result = extract_financing_cells(cells(), CONTEXT)
    assert result['rows'][0]['amounts']['opening'] == '1200.00'
    assert result['rows'][0]['raw_cells'][1] == '1,2\n00.00'
    assert result['balances_reconcile']
    assert result['full_movements_reconcile']


def test_explicit_thousand_integer_unit_normalizes_without_inventing_blanks():
    table = cells()
    table[2] = ['短期借款', '1,200', '200', '10', '300', '', '1,100']
    table[3] = ['合计', '1,200', '200', '10', '300', '10', '1,100']
    result = extract_financing_cells(table, TITLE + '\n单位：千元 币种：人民币')
    assert result['source_unit'] == 'CNY_thousand'
    assert result['rows'][0]['amounts']['closing'] == '1100000'
    assert result['rows'][0]['amounts']['noncash_decrease'] is None
    assert result['rows'][0]['raw_cells'][1] == '1,200'
    assert not result['complete_debt_verified']


def test_integer_amounts_cannot_silently_gain_thousand_unit():
    table = cells()
    table[2][1] = '1200'
    assert extract_financing_cells(table, CONTEXT) is None


def test_blank_is_not_zero_or_complete_debt():
    table = cells()
    table[2][5] = ''
    result = extract_financing_cells(table, CONTEXT)
    assert result['rows'][0]['amounts']['noncash_decrease'] is None
    assert not result['full_movements_reconcile']
    assert result['status'] == 'extracted_scope_unverified'


def test_detail_dash_is_retained_as_unknown_not_zero():
    table = cells()
    table[2][-1] = '-'
    result = extract_financing_cells(table, CONTEXT)
    assert result['rows'][0]['amounts']['closing'] is None
    assert result['rows'][0]['raw_cells'][-1] == '-'
    assert not result['balances_reconcile']
    assert not result['full_movements_reconcile']
    assert not result['complete_debt_verified']


def test_total_mismatch_and_multiple_amounts_in_one_cell_reject():
    for replacement in ('1,100.01', '1,100.00\n20.00', '-', 'NaN'):
        table = cells()
        table[-1][-1] = replacement
        assert extract_financing_cells(table, CONTEXT) is None


def test_missing_wrong_units_headers_and_columns_reject():
    for context in (TITLE, TITLE + '\n单位：万元', 'Other\n单位：元'):
        assert extract_financing_cells(cells(), context) is None
    for index in (0, 1, 2):
        table = deepcopy(cells())
        table[index].append('unexpected')
        assert extract_financing_cells(table, CONTEXT) is None


def test_dividends_are_not_borrowings():
    table = cells()
    table[2][0] = '应付股利'
    assert extract_financing_cells(table, CONTEXT)['rows'][0]['label_category'] == 'dividends_excluded'


def test_duplicate_rows_and_early_total_reject():
    table = cells()
    table.insert(3, table[2])
    assert extract_financing_cells(table, CONTEXT) is None
    table = cells()
    table.insert(2, table[-1])
    assert extract_financing_cells(table, CONTEXT) is None


def test_negative_sign_wrapped_within_cell_is_preserved():
    for negative in ('-\n10.00', '-\n10.\n00'):
        table = cells()
        for row in table[2:]:
            row[5] = negative
            row[6] = '1,120.00'
        result = extract_financing_cells(table, CONTEXT)
        assert result['rows'][0]['amounts']['noncash_decrease'] == '-10.00'
        assert result['rows'][0]['raw_cells'][5] == negative
        assert result['full_movements_reconcile']


def test_wrapped_sign_cannot_accept_multiple_numbers_or_double_sign():
    for invalid in ('-\n-10.00', '-\n10.00\n20.00', '-\ntext', '-\n+10.00'):
        table = cells()
        table[2][5] = invalid
        assert extract_financing_cells(table, CONTEXT) is None

from copy import deepcopy
from itertools import permutations

from value_investment_agent.db import resolve_latest_ties


def point(identifier, field='revenue', value='100', **metadata):
    return {'data_point_id': identifier, 'symbol': '000612', 'field_name': field,
            'value': value, 'unit': 'CNY', 'validation_status': 'verified',
            'metadata': {'automatic_cross_source_verification': True, **metadata}}


def test_conflict_and_cached_derivatives_block_independent_of_row_order():
    rows = [point('a'), point('b', value='101'),
            point('c', 'gross_margin', input_facts={'revenue': {}}),
            point('d', 'score', input_facts={'gross_margin': {}})]
    original = deepcopy(rows)
    for ordered in permutations(rows):
        result = resolve_latest_ties(list(ordered))
        assert all(p['validation_status'] == 'conflict' for p in result)
        revenue = next(p for p in result if p['field_name'] == 'revenue')
        assert revenue['metadata']['latest_tied_point_ids'] == ['a', 'b']
    assert rows == original


def test_equal_numeric_values_keep_all_ids_without_false_conflict():
    result = resolve_latest_ties([point('b', value='100.00'), point('a')])
    assert result[0]['validation_status'] == 'verified'
    assert result[0]['metadata']['latest_tied_point_ids'] == ['a', 'b']


def test_equal_value_unaccepted_alternative_cannot_be_hidden():
    result = resolve_latest_ties([point('a'), point('b', evidence_quarantine='unresolved')])
    assert result[0]['validation_status'] == 'conflict'


def test_other_issuer_is_not_blocked():
    other = point('c', 'gross_margin', input_facts={'revenue': {}})
    other['symbol'] = '600519'
    result = resolve_latest_ties([point('a'), point('b', value='101'), other])
    assert next(p for p in result if p['symbol'] == '600519')['validation_status'] == 'verified'


def test_equivalent_currency_units_do_not_create_false_conflicts():
    a = point('a', value='5932972054.81')
    b = point('b', value='59.3297205481')
    b['unit'] = 'CNY 100M'
    a['validation_status'] = b['validation_status'] = 'pending'
    result = resolve_latest_ties([a, b])
    assert result[0]['validation_status'] == 'pending'
    assert 'evidence_quarantine' not in result[0]['metadata']


def test_unknown_currency_units_cannot_be_assumed_equivalent():
    a, b = point('a'), point('b')
    b['unit'] = 'USD'
    assert resolve_latest_ties([a, b])[0]['validation_status'] == 'conflict'

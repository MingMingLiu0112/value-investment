from decimal import Decimal

import pytest

from value_investment_agent.candidate_review import comparable_value_agrees, latest_consistent_secondary


@pytest.mark.parametrize('unit,amount', [('CNY', '3069495469.62'),
    ('CNY 10K', '306949.546962'), ('CNY 100M', '30.6949546962')])
def test_explicit_scale_keeps_original_record(unit, amount):
    row = {'source_name': 'source', 'value': amount, 'unit': unit, 'data_point_id': 'original'}
    original = row.copy()
    assert latest_consistent_secondary([row], Decimal('3069495469.62'), 'CNY') is row
    assert row == original


@pytest.mark.parametrize('unit,value', [('USD', '3069495469.62'), ('CNY/share', '3069495469.62'),
    ('yuan', '3069495469.62'), ('CNY', 'NaN'), ('CNY 100M', 'Infinity'), ('CNY', None)])
def test_unknown_incompatible_or_nonfinite_refused(unit, value):
    assert not comparable_value_agrees(Decimal('3069495469.62'), 'CNY', {'value': value, 'unit': unit})


def test_newer_conflicting_scale_never_falls_back_to_old_agreement():
    rows = [{'source_name': 'same', 'value': '40', 'unit': 'CNY 100M'},
            {'source_name': 'same', 'value': '3069495469.62', 'unit': 'CNY'}]
    assert latest_consistent_secondary(rows, Decimal('3069495469.62'), 'CNY') is None


def test_one_conflicting_independent_source_blocks():
    rows = [{'source_name': 'a', 'value': '30.6949546962', 'unit': 'CNY 100M'},
            {'source_name': 'b', 'value': '40', 'unit': 'CNY 100M'}]
    assert latest_consistent_secondary(rows, Decimal('3069495469.62'), 'CNY') is None


def test_currency_tolerance_is_in_yuan_not_billions():
    assert not comparable_value_agrees(Decimal('0.00000001'), 'CNY 100M',
                                       {'value': '0.5', 'unit': 'CNY 100M'})

import importlib.util
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'moutai_annual_inputs', Path(__file__).resolve().parents[1] / 'scripts/build_moutai_annual_inputs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_original_2022_equity_not_later_restatement_and_independent_fraction_check():
    row = next(row for row in module.REVIEWED if row[0] == 2022)
    profit, equity, eps = row[5:8]
    assert equity == '197506672396.00'
    result = module.reference_arithmetic(profit, equity, '1256197800', eps)
    expected = (Fraction(eps) * 18 + Fraction(equity) * 4 / 1256197800) / 2
    actual = Fraction(result['annual_reference_on_report_end_share_basis'])
    assert abs(actual - expected) < Fraction(1, 10**34)
    rewritten = (Fraction(eps) * 18 + Fraction('197480041239.46') * 4 / 1256197800) / 2
    assert abs(actual - rewritten) > Fraction(4, 100)


def test_2014_rejects_post_bonus_share_basis():
    row = module.REVIEWED[0]
    result = module.reference_arithmetic(row[5], row[6], '1141998000', row[7])
    assert Decimal(result['parent_equity_per_ending_issued_share']) > 46
    with pytest.raises(ValueError, match='EPS does not reconcile'):
        module.reference_arithmetic(row[5], row[6], '1256197800', row[7])


def point(year, published, value):
    return dict(symbol='600519', field_name='annual_reference_original', period_label=f'{year}-12-31',
                source_id=f'original-{year}', raw_file_hash='hash', unit='CNY/share',
                value=value, validation_status='verified', timestamp_precision='date',
                publication_date_verified=True, availability_bound_verified=True,
                availability_method='china_publication_date_upper_bound', published_date=published,
                available_at=module.publication_date_upper_bound(published).isoformat())


def test_new_vintage_enters_at_publication_bound_without_rewriting_previous():
    old = point(2022, '2023-03-31', '763.82155')
    new = point(2023, '2024-04-03', '878.777217')
    rows = [new, old]
    assert not module.select_original_vintage(rows, '2023-03-31T23:59:59+08:00')
    assert module.select_original_vintage(rows, '2024-04-03T23:59:59+08:00') == [old]
    assert module.select_original_vintage(rows, '2024-04-03T16:00:00Z') == [new]
    assert old['value'] == '763.82155'


def test_unresolved_same_date_versions_do_not_select_arbitrarily():
    original = point(2022, '2023-03-31', '763.82155')
    conflicting = dict(original, source_id='other-original', value='763.779')
    with pytest.raises(ValueError, match='Conflicting evidence'):
        module.select_original_vintage([original, conflicting], '2023-04-01T00:00:00+08:00')

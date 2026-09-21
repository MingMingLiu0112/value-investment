import importlib.util
from fractions import Fraction
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('price_signal_sensitivity',
    Path(__file__).resolve().parents[1] / 'scripts' / 'audit_price_signal_sensitivity.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_exact_bounds_and_open_upper_endpoint():
    result = module.flip_intervals('220.20', '220.49')
    interval = result['buy_fair_value_interval']
    assert Fraction(interval['lower_exact']) == Fraction('220.20') / Fraction('.7')
    assert Fraction(interval['upper_exact']) == Fraction('220.49') / Fraction('.7')
    assert interval['lower_inclusive'] and not interval['upper_inclusive']
    assert result['actual_historical_signal_changed'] is None


def test_equal_prices_have_no_flip_interval_and_order_does_not_matter():
    assert module.flip_intervals('1', '1')['buy_fair_value_interval']['empty']
    assert module.flip_intervals('1', '2') == module.flip_intervals('2', '1')


@pytest.mark.parametrize('prices,margin', [(('0','1'), '.3'), (('1','2'), '1'), (('1','2'), '-.1')])
def test_invalid_inputs_rejected(prices, margin):
    with pytest.raises(ValueError):
        module.flip_intervals(*prices, margin)

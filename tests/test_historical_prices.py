import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('historical_prices',
    Path(__file__).parents[1] / 'scripts' / 'collect_historical_prices.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def raw(rows, field='day'):
    return json.dumps({'code': 0, 'data': {'sh600519': {field: rows}}})


def test_unadjusted_bars_filter_prior_year():
    bars = module.parse_bars(raw([
        ['2014-12-31', '10', '11', '12', '9', '100'],
        ['2015-01-05', '10', '11', '12', '9', '100'],
    ]), 'sh600519', 2015)
    assert len(bars) == 1
    assert bars[0]['open'] == '10'


@pytest.mark.parametrize('rows', [
    [],
    [['2015-01-05', '10', '11', '9', '8', '100']],
    [['2015-01-05', 'NaN', '11', '12', '9', '100']],
    [['2015-01-05', '10', '11', '12', '9', '-1']],
    [['2015-01-05', '10', '11', '12', '9', '100']] * 2,
])
def test_invalid_bars_rejected(rows):
    with pytest.raises(ValueError):
        module.parse_bars(raw(rows), 'sh600519', 2015)


def test_adjusted_prices_are_not_silently_accepted():
    with pytest.raises(KeyError):
        module.parse_bars(raw([['2015-01-05', '10', '11', '12', '9', '100']], 'qfqday'),
                          'sh600519', 2015)

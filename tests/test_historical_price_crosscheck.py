import importlib.util
from pathlib import Path
import sys

import pytest

scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
try:
    spec = importlib.util.spec_from_file_location('historical_price_crosscheck', scripts / 'crosscheck_historical_prices.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
finally:
    sys.path.pop(0)


def bar(day='2015-01-05T00:00:00.000Z', **changes):
    return dict(dict(date=day, open=10, high=11, low=9, close=10.5), **changes)


def test_raw_dates_are_neither_filled_nor_deduplicated_by_equal_prices():
    rows = module.normalize_sina([bar(), bar('2015-01-07T00:00:00Z')])
    assert sorted(rows) == ['2015-01-05', '2015-01-07']
    with pytest.raises(ValueError, match='Duplicate'):
        module.normalize_sina([bar(), bar()])


@pytest.mark.parametrize('row', [bar(high=8), bar(close=float('nan')), bar(open=0),
                                 bar('2015-01-05T16:00:00Z')])
def test_bad_prices_or_date_convention_rejected(row):
    with pytest.raises(ValueError):
        module.normalize_sina([row])


def test_price_and_missing_date_differences_remain_visible():
    left = module.normalize_sina([bar(), bar('2015-01-06T00:00:00Z')])
    right = module.normalize_sina([bar(close=10.51), bar('2015-01-07T00:00:00Z')])
    result = module.compare(left, right)
    assert result['only_tencent'] == ['2015-01-06']
    assert result['only_sina'] == ['2015-01-07']
    assert result['ohlc_mismatch_days'] == 1
    assert result['differences'][0]['differences']['close'] == {'tencent': '10.5', 'sina': '10.51'}
    assert not result['backtest_ready']


def test_symbol_wrapper_allows_observed_comment_but_not_executable_trailer():
    raw = b'var KLC_K2_sh600519="encoded";\n/* comment */'
    assert module.sina_payload(raw, 'sh600519') == 'encoded'
    with pytest.raises(ValueError):
        module.sina_payload(raw, 'sh601088')
    with pytest.raises(ValueError):
        module.sina_payload(raw + b';otherFunction()', 'sh600519')

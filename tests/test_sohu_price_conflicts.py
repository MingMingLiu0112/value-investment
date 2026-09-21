import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('sohu_conflicts',
    Path(__file__).resolve().parents[1] / 'scripts' / 'verify_price_conflicts_sohu.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def packet(**changes):
    return json.dumps([dict(dict(status=0, code='cn_600519', hq=[
        ['2015-12-03', '219.00', '220.20', '-1.38', '-0.62%', '216.70', '221.40', '22387', '48992.86', '0.18%']]), **changes)])


def test_read_only_the_explicit_requested_date_and_columns():
    result = module.parse_sohu(packet(), '600519', '2015-12-03')
    assert result == dict(date='2015-12-03', open='219.00', close='220.20', low='216.70', high='221.40')


def test_provider_gbk_summary_does_not_break_numeric_daily_record():
    value = json.loads(packet())
    value[0]['stat'] = ['累计:']
    raw = json.dumps(value, ensure_ascii=False).encode('gb18030')
    assert module.parse_sohu(raw, '600519', '2015-12-03')['close'] == '220.20'


@pytest.mark.parametrize('changes', [{'status': 1}, {'code': 'cn_601088'}, {'hq': []}])
def test_wrong_status_symbol_or_missing_day_rejected(changes):
    with pytest.raises(ValueError):
        module.parse_sohu(packet(**changes), '600519', '2015-12-03')


def test_wrong_date_and_duplicate_rows_rejected():
    with pytest.raises(ValueError):
        module.parse_sohu(packet(), '600519', '2015-12-04')
    rows = json.loads(packet())[0]['hq']
    with pytest.raises(ValueError):
        module.parse_sohu(packet(hq=rows * 2), '600519', '2015-12-03')

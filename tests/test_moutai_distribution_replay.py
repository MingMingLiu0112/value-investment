import importlib.util
from pathlib import Path
import sys

import pytest


spec = importlib.util.spec_from_file_location('moutai_distribution_replay',
    Path(__file__).resolve().parents[1] / 'scripts/replay_moutai_distributions.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def cash_case():
    event = dict(record_date='2025-06-25', ex_date='2025-06-26',
                 cash_payment_date='2025-06-26', cash_amount='27.673', per_shares='1',
                 ex_reference_cash_per_share='27.600')
    bars = [dict(date=day, close='1400') for day in ['2025-06-25', '2025-06-26']]
    rows = [dict(date=b['date'], shares=110, sellable_shares=110, cash_gross=cash,
                 receivable_gross=0, marked_equity_gross=cash+154000)
            for b, cash in zip(bars, [10000, 13044.03])]
    # 110 * 27.673 = 3044.03; the reference adjustment would be 3036.00.
    payments = [dict(record_date='2025-06-25', record_shares=110, gross_cash='3044.03')]
    return rows, payments, bars, [event]


def test_cash_uses_actual_entitlement_not_ex_reference_adjustment():
    rows, payments, bars, events = cash_case()
    result = module.verify_accounting(rows, payments, bars, events, 110, '10000')
    assert result['gross_distributions_cny'] == '3044.030'
    rows[-1].update(cash_gross=13036, marked_equity_gross=167036)
    payments[0]['gross_cash'] = '3036'
    with pytest.raises(ValueError, match='cash_gross mismatch'):
        module.verify_accounting(rows, payments, bars, events, 110, '10000')


def test_opening_inventory_must_be_in_first_mark():
    rows, payments, bars, events = cash_case()
    rows[0]['marked_equity_gross'] = 10000
    with pytest.raises(ValueError, match='2025-06-25: independent marked_equity_gross'):
        module.verify_accounting(rows, payments, bars, events, 110, '10000')


def test_bonus_is_not_sellable_before_listing():
    event = dict(record_date='2015-07-16', ex_date='2015-07-17', cash_payment_date='2015-07-17',
                 cash_amount='4.374', per_shares='1', bonus_shares_per_share='0.1',
                 bonus_listing_date='2015-07-20')
    bars = [dict(date=day, close=price) for day, price in
            [('2015-07-16', '200'), ('2015-07-17', '180'), ('2015-07-20', '182')]]
    rows = [dict(date=b['date'], shares=shares, sellable_shares=sellable, cash_gross=cash,
                 receivable_gross=0, marked_equity_gross=cash+shares*float(b['close']))
            for b, shares, sellable, cash in zip(bars, [100,110,110], [100,100,110], [10000,10437.4,10437.4])]
    payments = [dict(record_date='2015-07-16', record_shares=100, gross_cash='437.4')]
    assert module.verify_accounting(rows, payments, bars, [event], 100, '10000')['ending_shares'] == 110
    rows[1]['sellable_shares'] = 110
    with pytest.raises(ValueError, match='listing lock mismatch'):
        module.verify_accounting(rows, payments, bars, [event], 100, '10000')

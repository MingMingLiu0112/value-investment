from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from value_investment_agent.corporate_actions import validate_cash_distribution


def events():
    return json.loads((Path(__file__).parents[1] / 'docs' /
                       'reviewed-cash-distributions.json').read_text(encoding='utf-8'))['events']


def test_reviewed_actual_entitlement_not_proposal():
    rows = events()
    actual = {(e['symbol'], e['record_date']): validate_cash_distribution(e) for e in rows}
    assert len(actual) == len(rows)
    expected = {
        ('600519', '2021-06-24'): '19.293',
        ('600519', '2022-06-29'): '21.675',
        ('600519', '2023-06-29'): '25.911',
        ('600519', '2022-12-26'): '21.91',
        ('600519', '2024-06-18'): '30.876',
        ('600519', '2023-12-19'): '19.106',
        ('600519', '2024-12-19'): '23.882',
        ('600519', '2025-06-25'): '27.673',
        ('600519', '2025-12-18'): '23.957',
        ('600519', '2016-06-30'): '6.171',
        ('600519', '2017-07-06'): '6.787',
        ('600519', '2018-06-14'): '10.999',
        ('600519', '2019-06-27'): '14.539',
        ('600519', '2020-06-23'): '17.025',
        ('000333', '2022-06-01'): '1.7008943',
        ('000333', '2023-05-31'): '2.5',
        ('000333', '2024-05-14'): '3',
        ('000333', '2025-06-11'): '3.5',
        ('000333', '2025-11-17'): '0.5',
        ('000333', '2017-05-09'): '1.00',
        ('000333', '2018-05-03'): '1.20',
        ('000333', '2019-05-29'): '1.303962',
        ('000333', '2020-06-01'): '1.6',
        ('000333', '2015-04-29'): '1.00',
        ('000333', '2016-05-05'): '1.20',
        ('600519', '2015-07-16'): '4.37400',
        ('000333', '2021-06-01'): '1.6005847',
        ('601088', '2015-06-12'): '0.740',
        ('601088', '2016-07-01'): '0.320',
        ('601088', '2017-07-07'): '2.970',
        ('601088', '2018-07-06'): '0.91',
        ('601088', '2019-07-05'): '0.880',
        ('601088', '2020-06-12'): '1.260',
        ('601088', '2021-07-09'): '1.810',
        ('601088', '2022-07-08'): '2.54',
        ('601088', '2023-07-04'): '2.55',
        ('601088', '2024-07-05'): '2.26',
        ('601088', '2025-07-04'): '2.26',
        ('601088', '2025-11-07'): '0.98',
    }
    assert actual == {key: Decimal(value) for key, value in expected.items()}


def test_same_year_distributions_remain_separate_entitlements():
    rows = [e for e in events() if e['symbol'] == '601088'
            and e['record_date'].startswith('2025-')]
    assert len(rows) == 2
    assert {e['cash_payment_date'] for e in rows} == {'2025-07-07', '2025-11-10'}
    # Total applies only to an unchanged eligible share held across both record dates.
    assert sum(validate_cash_distribution(e) for e in rows) == Decimal('3.24')


@pytest.mark.parametrize('key,value', [
    ('cash_payment_date', '2020-06-02'),
    ('cash_per_share', '1.6'),
    ('cash_amount', 'NaN'),
    ('per_shares', '0'),
    ('amount_basis', 'proposal'),
    ('evidence', []),
])
def test_bad_event_cannot_enter_cash_accounting(key, value):
    event = deepcopy(next(e for e in events() if e['symbol'] == '000333'
                          and e['record_date'] == '2021-06-01'))
    event[key] = value
    with pytest.raises(ValueError):
        validate_cash_distribution(event)

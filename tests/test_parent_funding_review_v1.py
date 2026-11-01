from decimal import Decimal
import pytest
from value_investment_agent.domain.research.parent_distribution_capacity_v1 import assess_capacity


def run(**changes):
    args = dict(opening_cash='23517778984.18', dividend_payable='6501567650.57',
                retained_profit='23214184665.64', obligations=[])
    args.update(changes)
    return assess_capacity(**args)


def test_historical_and_conditional_budget():
    assert run()['static_after_declared_dividend'] == '17016211333.61'
    result = run(cash_floor='6000000000', additional_distribution='8500000000',
                 obligations_complete=True)
    assert Decimal(result['conditional_shortfall']) == 0
    assert result['current_capacity_proven'] is False
    assert run()['status'] == 'INCOMPLETE_OBLIGATIONS'


def test_paid_dividend_not_deducted_again():
    assert run(opening_cash='17016211333.61', dividend_already_deducted=True)['static_after_declared_dividend'] == '17016211333.61'


@pytest.mark.parametrize('value', [-1, 'NaN', 'Infinity', True])
def test_invalid_cash(value):
    with pytest.raises(ValueError):
        run(opening_cash=value)


def test_scope_and_duplicate():
    for obligations in ([dict(id='x', amount=1, scope='consolidated')],
                        [dict(id='declared_dividend', amount=1, scope='parent')],
                        [dict(id='x', amount=1, scope='parent')]*2):
        with pytest.raises(ValueError):
            run(obligations=obligations)

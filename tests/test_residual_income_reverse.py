from decimal import Decimal
import pytest
from value_investment_agent.domain.valuation.residual_income_reverse import implied_terminal_roe
from value_investment_agent.valuation_models.residual_income import scenario_value


def configuration():
    return dict(cost_of_equity='0.09', forecast_roe=['0.18', '0.17', '0.16'],
                terminal_roe='0.10', terminal_growth='0.02', retention='0.25')


def test_inverse_reconciles_without_changing_original_scenarios():
    config = configuration()
    original = dict(config)
    price = Decimal(scenario_value(Decimal('100'), Decimal('10'), Decimal('0.09'), config)[
        'conditional_value_per_2025_issued_share_cny'])
    result = implied_terminal_roe(start_book=Decimal('100'), shares=Decimal('10'), price=price, configuration=config)
    assert abs(Decimal(result['implied_terminal_roe']) - Decimal('0.10')) < Decimal('1e-20')
    assert config == original
    assert not result['forecast']
    assert not result['investment_admitted']


@pytest.mark.parametrize('price', ['0', '-1', 'NaN', 'Infinity'])
def test_invalid_price_fails_closed(price):
    with pytest.raises(ValueError):
        implied_terminal_roe(start_book=Decimal('100'), shares=Decimal('10'),
                             price=Decimal(price), configuration=configuration())

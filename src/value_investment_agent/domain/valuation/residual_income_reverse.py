"""Conditional inversion of the existing residual-income terminal ROE."""
from decimal import Decimal, localcontext
from ...valuation_models.residual_income import scenario_value


def implied_terminal_roe(*, start_book: Decimal, shares: Decimal, price: Decimal,
                         configuration: dict) -> dict:
    if not price.is_finite() or price <= 0:
        raise ValueError('reverse valuation requires a positive finite price')
    cost = Decimal(str(configuration['cost_of_equity']))
    original = scenario_value(start_book, shares, cost, configuration)
    growth = Decimal(str(configuration['terminal_growth']))
    book = Decimal(original['terminal_opening_book_equity_cny'])
    explicit = Decimal(original['present_value_explicit_residual_income_cny'])
    years = len(configuration['forecast_roe'])
    with localcontext() as context:
        context.prec = 48
        required_roe = cost + (price * shares - start_book - explicit) * (cost - growth) * (1 + cost) ** years / book
        if required_roe <= 0 or required_roe < growth:
            return dict(status='NOT_ASSESSABLE', reason='Required terminal ROE is outside the self-funded model domain.')
        implied = dict(configuration, terminal_roe=str(required_roe))
        checked = scenario_value(start_book, shares, cost, implied)
        rebuilt_price = Decimal(checked['conditional_value_per_2025_issued_share_cny'])
        if abs(rebuilt_price - price) > Decimal('0.00000001'):
            raise ValueError('reverse valuation forward reconciliation failed')
    return dict(status='CONDITIONAL_ARITHMETIC_ONLY', implied_terminal_roe=str(required_roe),
        original_terminal_roe=str(configuration['terminal_roe']), market_price=str(price),
        forward_reconciled_price=str(rebuilt_price), fixed_assumptions=dict(configuration),
        interpretation='Only terminal ROE varies; equity cost, growth, retention and forecast ROEs stay fixed.',
        forecast=False, investment_admitted=False, action='no_order')

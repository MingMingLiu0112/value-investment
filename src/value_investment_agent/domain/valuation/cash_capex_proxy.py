"""A descriptive cash residual, deliberately not FCFF or distributable cash."""
from decimal import Decimal


def cash_capex_proxy(*, cfo: Decimal, cash_capex: Decimal) -> dict:
    if not cfo.is_finite() or not cash_capex.is_finite() or cash_capex < 0:
        raise ValueError('cash proxy requires finite CFO and nonnegative cash capex')
    return dict(proxy_cny=str(cfo - cash_capex), formula='CFO - cash purchases of fixed/intangible/other long-term assets',
        fcff=False, fcfe=False, distributable_cash_proven=False, maintenance_capex_identified=False,
        limitation='No separation of maintenance/growth capex, acquisition cash, debt flows, interest, minority interests or financial subsidiaries.',
        action='no_order')

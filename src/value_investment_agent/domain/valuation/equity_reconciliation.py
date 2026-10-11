"""Historical equity movement arithmetic, separate from future model assumptions."""
from decimal import Decimal, localcontext


def reconcile_equity_movements(*, amounts: dict, expected_equity: Decimal,
        profit: Decimal, oci: Decimal) -> dict:
    required = {'opening', 'closing', 'change', 'comprehensive', 'contribution',
                'distribution', 'reserve', 'other'}
    if set(amounts) != required or any(set(row) != {'parent', 'minority', 'total'} for row in amounts.values()):
        raise ValueError('equity bridge requires all ownership-scoped movement inputs')
    values = [expected_equity, profit, oci, *(value for row in amounts.values() for value in row.values())]
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in values):
        raise ValueError('equity bridge amounts must be finite Decimals')
    with localcontext() as ctx:
        ctx.prec = 48
        for row in amounts.values():
            if row['parent'] + row['minority'] != row['total']:
                raise ValueError('equity bridge parent/minority/total columns do not reconcile')
        movements = ('comprehensive', 'contribution', 'distribution', 'reserve', 'other')
        for scope in ('parent', 'minority', 'total'):
            movement = sum((amounts[key][scope] for key in movements), Decimal(0))
            if (movement != amounts['change'][scope]
                    or amounts['opening'][scope] + movement != amounts['closing'][scope]):
                raise ValueError('equity bridge opening/movements/closing do not reconcile')
        if amounts['closing']['parent'] != expected_equity:
            raise ValueError('equity bridge closing differs from consumed balance-sheet equity')
        if profit + oci != amounts['comprehensive']['parent']:
            raise ValueError('equity bridge profit/OCI components do not reconcile')
        naive = amounts['opening']['parent'] + profit + amounts['distribution']['parent']
        adjustment = oci + amounts['other']['parent'] + amounts['reserve']['parent'] + amounts['contribution']['parent']
        if naive + adjustment != expected_equity:
            raise ValueError('equity bridge outside-profit adjustments do not reconcile')
        return dict(parent_profit_cny=str(profit), parent_oci_cny=str(oci),
            naive_profit_distribution_equity_cny=str(naive), outside_profit_adjustment_cny=str(adjustment),
            reconciled_closing_parent_equity_cny=str(expected_equity), unexplained_difference_cny='0')

"""Explicit signed-NCI parent-profit arithmetic; no source or valuation approval."""
from decimal import Decimal as D, InvalidOperation, localcontext


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, D)):
        raise ValueError('Signed parent-profit inputs require explicit decimal values')
    try:
        result = D(value)
    except InvalidOperation as error:
        raise ValueError('Signed parent-profit inputs require valid decimals') from error
    if not result.is_finite():
        raise ValueError('Signed parent-profit inputs must be finite')
    return result


def _plain(value):
    if isinstance(value, D):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def build_signed_parent_profit_path(*, years, group_pbt_cny, tax_assumptions, signed_nci_cny, currency):
    """Explicit PBT - tax - signed NCI, without a parent-share ratio.

    Years are consecutive positive integer projection steps or calendar years.
    Each tax row is exactly {basis: amount_cny|effective_rate, value: decimal}.
    Amounts may include explicitly assumed tax credits; a rate applies literally
    to signed PBT, so any resulting tax benefit is an assumption, not recognition.
    NCI is an explicit signed amount each year, never inferred from history.
    The caller owns source/period/assumption provenance. This is arithmetic only.
    """
    if currency != 'CNY':
        raise ValueError('Signed parent-profit arithmetic requires explicit CNY currency')
    if (not isinstance(years, list) or not years
            or any(type(year) is not int or year <= 0 for year in years)
            or any(right != left+1 for left, right in zip(years, years[1:]))):
        raise ValueError('Years must be explicit consecutive positive integers')
    if any(not isinstance(values, list) or len(values) != len(years)
           for values in (group_pbt_cny, tax_assumptions, signed_nci_cny)):
        raise ValueError('PBT, explicit tax and signed NCI require one input per year')
    rows = []
    with localcontext() as ctx:
        ctx.prec = 48
        for year, pbt_input, tax_input, nci_input in zip(
                years, group_pbt_cny, tax_assumptions, signed_nci_cny):
            if (not isinstance(tax_input, dict) or set(tax_input) != {'basis', 'value'}
                    or tax_input['basis'] not in ('amount_cny', 'effective_rate')):
                raise ValueError('Each year requires an explicit tax amount or effective-rate assumption')
            pbt, tax_value, nci = map(_number, (pbt_input, tax_input['value'], nci_input))
            if tax_input['basis'] == 'effective_rate' and not 0 <= tax_value <= 1:
                raise ValueError('Effective tax rate must be within [0,1]')
            tax = tax_value if tax_input['basis'] == 'amount_cny' else pbt*tax_value
            group_profit = pbt-tax
            parent = group_profit-nci
            rows.append(dict(year=year, currency='CNY', group_pbt_cny=pbt,
                tax_assumption=dict(basis=tax_input['basis'], value=tax_value),
                income_tax_cny=tax, group_after_tax_profit_cny=group_profit,
                signed_nci_cny=nci, parent_profit_cny=parent,
                bridge_residual_cny=parent-(pbt-tax-nci)))
    return _plain(dict(status='ARITHMETIC_COMPLETE', rows=rows, currency='CNY', action='no_order',
        scope='SIGNED_NCI_PARENT_PROFIT_ARITHMETIC_NOT_FORECAST_OR_APPROVAL',
        formula='parent_profit = group_pbt - income_tax - signed_nci',
        normalized_parent_profit_cny=None, economic_approval=False,
        limitations=['All future PBT, tax and signed NCI inputs must be explicitly researched by the caller.',
            'Negative NCI increases parent-attributable profit arithmetically; its persistence is not assumed.',
            'No impairment addback, normalized earnings, cash distribution, valuation or admission is produced.']))

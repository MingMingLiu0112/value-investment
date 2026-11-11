"""Parent cash reconciliation and dated ordinary-cash policy arithmetic only."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import re


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('Explicit finite decimals required; no missing, bool or float substitutes')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('Invalid decimal') from error
    if not result.is_finite():
        raise ValueError('Finite decimals required')
    return result


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('Explicit ISO date required')
    return date.fromisoformat(value)


def _period(row):
    start, end = _date(row['period_start']), _date(row['period_end'])
    if start > end:
        raise ValueError('Invalid reporting period')
    return start, end


def _symbol(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{6}', value):
        raise ValueError('Explicit six-digit security identity required')


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _boundaries():
    return dict(action='no_order', formal_eligibility=False, research_admitted=False,
        economic_approval=False, price_admitted=False, strategy_admitted=False,
        action_admitted=False, sustainable_distribution_proven=False)


def reconcile_parent_cash_statement(*, statement):
    """Exact signed CFO/CFI/CFF/FX and balances for one standalone-parent period.

    All amounts are CNY cash-and-cash-equivalents on the same statement basis.
    A blank FX line is not zero. No component of CFF is classified as dividend.
    Caller authenticates originals, issuer, scope, period and acquisition dates.
    """
    amounts = ('opening_cash_cny', 'cfo_cny', 'cfi_cny', 'cff_cny', 'fx_cny',
               'reported_net_change_cny', 'closing_cash_cny')
    required = {'symbol', 'period_start', 'period_end', 'scope', 'unit', 'currency', *amounts}
    if not isinstance(statement, dict) or set(statement) != required:
        raise ValueError('Complete explicit parent cash statement fields required')
    _symbol(statement['symbol'])
    _period(statement)
    if statement['scope'] != 'issuer_parent_standalone' or statement['unit'] != 'CNY' or statement['currency'] != 'CNY':
        raise ValueError('Standalone-parent cash statement and CNY unit/currency required')
    with localcontext() as ctx:
        ctx.prec = 48
        values = {key: _number(statement[key]) for key in amounts}
        if min(values['opening_cash_cny'], values['closing_cash_cny']) < 0:
            raise ValueError('Cash-and-cash-equivalents balances must be nonnegative')
        change = sum(values[key] for key in ('cfo_cny', 'cfi_cny', 'cff_cny', 'fx_cny'))
        net_residual = change-values['reported_net_change_cny']
        balance_residual = values['opening_cash_cny']+change-values['closing_cash_cny']
        if net_residual != 0 or balance_residual != 0:
            raise ValueError('Parent cash flows, reported net change and closing balance do not reconcile exactly')
        return _plain(dict(_boundaries(), status='HISTORICAL_CASH_RECONCILED_NOT_DISTRIBUTABLE',
            statement={**statement, **values}, computed_net_change_cny=change,
            net_change_residual_cny=net_residual, closing_cash_residual_cny=balance_residual,
            annualized_cfo_cny=None, distributable_cash_cny=None, ordinary_cash_dividend_paid_cny=None,
            interpretation='Cash balance is not distributable cash; CFF and combined dividend/profit/interest payments are not ordinary-share dividends.'))


def evaluate_cash_dividend_policy(*, policy, fiscal_year, profit, shares):
    """Calculate explicit annual ordinary-cash policy thresholds, not capacity.

    Policy profit_basis must be either consolidated_parent_attributable or
    issuer_parent_standalone_profit. They are never converted into one another.
    Ratios/DPS minima and the inclusive fiscal-year window are caller inputs.
    Shares must identify the dividend-eligible ordinary-share denominator for
    that fiscal year, not weighted EPS shares, personal holdings or treasury stock.
    """
    if (not isinstance(policy, dict) or set(policy) != {'symbol', 'scope', 'currency', 'unit',
            'fiscal_year_start', 'fiscal_year_end', 'profit_basis', 'minimum_payout_ratio', 'minimum_dps_cny'}):
        raise ValueError('Complete explicit ordinary-cash policy terms required')
    if (not isinstance(profit, dict) or set(profit) != {'symbol', 'period_start', 'period_end',
            'scope', 'unit', 'currency', 'value'}):
        raise ValueError('Explicit annual profit identity, period, scope and CNY required')
    if (not isinstance(shares, dict) or set(shares) != {'symbol', 'fiscal_year', 'as_of', 'scope', 'unit', 'value'}):
        raise ValueError('Explicit ordinary dividend-eligible share basis required')
    for row in (policy, profit, shares):
        _symbol(row['symbol'])
    if not policy['symbol'] == profit['symbol'] == shares['symbol']:
        raise ValueError('Policy, profit and shares belong to different issuers')
    if (policy['scope'] != 'ordinary_cash_dividend_policy'
            or policy['unit'] != 'ratio_and_CNY_per_share' or policy['currency'] != 'CNY'
            or profit['unit'] != 'CNY' or profit['currency'] != 'CNY'
            or policy['profit_basis'] not in ('consolidated_parent_attributable', 'issuer_parent_standalone_profit')
            or profit['scope'] != policy['profit_basis']):
        raise ValueError('Ordinary-cash policy and exact profit ownership/unit basis required')
    if shares['scope'] != 'ordinary_dividend_eligible_shares' or shares['unit'] != 'shares':
        raise ValueError('Dividend-eligible ordinary shares required, not EPS or account shares')
    start, end = policy['fiscal_year_start'], policy['fiscal_year_end']
    if (any(type(year) is not int or not 1 <= year <= 9999
            for year in (fiscal_year, start, end, shares['fiscal_year'])) or start > end):
        raise ValueError('Explicit valid fiscal years and finite policy window required')
    pstart, pend = _period(profit)
    _date(shares['as_of'])
    if (pstart != date(fiscal_year, 1, 1) or pend != date(fiscal_year, 12, 31)
            or shares['fiscal_year'] != fiscal_year):
        raise ValueError('Policy requires the exact fiscal-year profit and share basis; no interim annualization')
    with localcontext() as ctx:
        ctx.prec = 48
        amount, count, ratio, dps = map(_number, (profit['value'], shares['value'],
            policy['minimum_payout_ratio'], policy['minimum_dps_cny']))
        if count <= 0 or count != count.to_integral_value() or not 0 <= ratio <= 1 or dps < 0:
            raise ValueError('Positive whole shares, bounded payout ratio and nonnegative DPS required')
        base = dict(_boundaries(), symbol=policy['symbol'], fiscal_year=fiscal_year,
            policy={**policy, 'minimum_payout_ratio': ratio, 'minimum_dps_cny': dps},
            profit={**profit, 'value': amount}, shares={**shares, 'value': count},
            policy_threshold_cny=None, ratio_threshold_cny=None, dps_threshold_cny=None,
            distributable_cash_cny=None, parent_legal_profit_inferred=False,
            policy_is_dividend_guarantee=False, ordinary_cash_dividend_paid_cny=None)
        if fiscal_year < start or fiscal_year > end:
            return _plain(dict(base, status='POLICY_NOT_EFFECTIVE' if fiscal_year < start else 'POLICY_EXPIRED',
                reason='No policy threshold extrapolated outside its explicit fiscal-year window.'))
        if amount <= 0:
            return _plain(dict(base, status='NOT_ASSESSABLE_NON_POSITIVE_POLICY_PROFIT',
                reason='Non-positive profit does not establish whether policy payout conditions are met.'))
        ratio_amount, dps_amount = amount*ratio, count*dps
        return _plain(dict(base, status='POLICY_THRESHOLD_RESEARCH_ONLY', ratio_threshold_cny=ratio_amount,
            dps_threshold_cny=dps_amount, policy_threshold_cny=max(ratio_amount, dps_amount),
            interpretation='Threshold assumes both explicit minima apply. It proves neither legal reserves, parent cash access, declaration nor payment.'))

"""Conditional parent-only cash bridge, not a dividend approval."""
from decimal import Decimal


def money(value, *, signed=False):
    if type(value) not in (str, int, Decimal):
        raise ValueError("explicit decimal amount required")
    result = Decimal(str(value))
    if not result.is_finite() or (result < 0 and not signed):
        raise ValueError("finite nonnegative amount required")
    return result


def assess_capacity(*, opening_cash, dividend_payable, retained_profit,
                    obligations, obligations_complete=False, cash_floor=0,
                    additional_distribution=0, dividend_already_deducted=False):
    """Obligations have unique IDs; reserve only incremental cash uses.

    Retained profit is an accounting ceiling proxy, not cash or a legal opinion.
    Completeness is an explicit scenario assertion, never inferred from blanks.
    """
    if type(obligations_complete) is not bool or type(dividend_already_deducted) is not bool:
        raise ValueError('explicit boolean required')
    retained = money(retained_profit, signed=True)
    cash, dividend = money(opening_cash), money(dividend_payable)
    static = cash - (Decimal(0) if dividend_already_deducted else dividend)
    seen, uses, overlap = set(), Decimal(0), Decimal(0)
    floor = money(cash_floor)
    for item in obligations:
        economic_id = item.get('economic_id', item['id'])
        if economic_id in seen or economic_id == 'declared_dividend' or item.get('kind') == 'declared_dividend':
            raise ValueError("duplicate obligation")
        seen.add(economic_id)
        if item.get('scope') != 'parent':
            raise ValueError("parent scope required")
        included = item.get('included_in_cash_floor', False)
        if type(included) is not bool:
            raise ValueError('explicit boolean required')
        amount = money(item['amount'])
        if included:
            overlap += amount
            if overlap > floor:
                raise ValueError('overlap exceeds cash floor')
            continue
        uses += amount
    remaining = static - uses - floor
    ceiling = min(max(remaining, Decimal(0)), max(retained, Decimal(0)))
    assessable = obligations_complete and retained >= 0
    target = money(additional_distribution)
    return dict(static_after_declared_dividend=str(static),
                conditional_cash_remaining=str(remaining),
                conditional_distribution_ceiling=str(ceiling) if assessable else None,
                conditional_shortfall=str(max(target - ceiling, Decimal(0))) if assessable else None,
                status=('NOT_ASSESSABLE' if retained < 0 else
                        'CONDITIONAL_SCENARIO' if obligations_complete else 'INCOMPLETE_OBLIGATIONS'),
                current_capacity_proven=False, approved=False, action='no_order')

"""Conditional parent-only cash bridge, not a dividend approval."""
from decimal import Decimal


def money(value):
    if isinstance(value, bool):
        raise ValueError("boolean amount")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("finite nonnegative amount required")
    return result


def assess_capacity(*, opening_cash, dividend_payable, retained_profit,
                    obligations, obligations_complete=False, cash_floor=0,
                    additional_distribution=0, dividend_already_deducted=False):
    """Obligations have unique IDs; reserve only incremental cash uses.

    Retained profit is an accounting ceiling proxy, not cash or a legal opinion.
    Completeness is an explicit scenario assertion, never inferred from blanks.
    """
    cash, dividend = money(opening_cash), money(dividend_payable)
    static = cash - (Decimal(0) if dividend_already_deducted else dividend)
    seen, uses = set(), Decimal(0)
    for item in obligations:
        if item['id'] in seen or item['id'] == 'declared_dividend':
            raise ValueError("duplicate obligation")
        seen.add(item['id'])
        if item.get('scope') != 'parent':
            raise ValueError("parent scope required")
        if item.get('included_in_cash_floor'):
            continue
        uses += money(item['amount'])
    remaining = static - uses - money(cash_floor)
    ceiling = min(max(remaining, Decimal(0)), money(retained_profit))
    target = money(additional_distribution)
    return dict(static_after_declared_dividend=str(static),
                conditional_cash_remaining=str(remaining),
                conditional_distribution_ceiling=str(ceiling),
                conditional_shortfall=str(max(target - ceiling, Decimal(0))),
                status='CONDITIONAL_SCENARIO' if obligations_complete else 'INCOMPLETE_OBLIGATIONS',
                current_capacity_proven=False, approved=False, action='no_order')

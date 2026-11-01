"""Declared-book-liability payment hypotheses; no new profit or cash engine."""
from decimal import Decimal, InvalidOperation, localcontext

VERSION = "nonproductive-liability-settlement-v1"

def compile_liability_settlements(*, obligations, years=10):
    """Schedule full settlement once, without treating it as CapEx or new dividend.

    The caller authenticates source_refs and proves these balances remain in
    opening cash. An explicit payment year is a research assumption, not a
    disclosed maturity or a current payment receipt. None retains the liability.
    The resulting cash uses must not also remain in a model's cash floor.
    """
    if type(years) is not int or not 1 <= years <= 100:
        raise ValueError("EXPLICIT_SETTLEMENT_HORIZON_REQUIRED")
    if not isinstance(obligations, list) or not obligations:
        raise ValueError("SOURCE_BOUND_EXISTING_LIABILITIES_REQUIRED")
    seen, parsed = set(), []
    for item in obligations:
        if not isinstance(item, dict) or set(item) != {
            "obligation_id", "opening_balance_cny", "payment_year", "source_refs"
        }:
            raise ValueError("EXACT_EXISTING_LIABILITY_FIELDS_REQUIRED")
        ident = item["obligation_id"]
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError("UNIQUE_LIABILITY_ID_REQUIRED")
        seen.add(ident)
        raw = item["opening_balance_cny"]
        if not isinstance(raw, str) or len(raw) > 40:
            raise ValueError("EXPLICIT_BOOK_AMOUNT_REQUIRED")
        try:
            amount = Decimal(raw)
        except InvalidOperation as error:
            raise ValueError("FINITE_NONNEGATIVE_BOOK_AMOUNT_REQUIRED") from error
        if not amount.is_finite() or amount < 0:
            raise ValueError("FINITE_NONNEGATIVE_BOOK_AMOUNT_REQUIRED")
        year = item["payment_year"]
        if year is not None and (type(year) is not int or not 1 <= year <= years):
            raise ValueError("EXPLICIT_PAYMENT_YEAR_OR_UNPAID_REQUIRED")
        refs = item["source_refs"]
        if not isinstance(refs, list) or not refs or any(
            not isinstance(ref, dict) or not ref for ref in refs
        ):
            raise ValueError("EXISTING_LIABILITY_SOURCE_REFS_REQUIRED")
        parsed.append((ident, amount, year))
    with localcontext() as context:
        context.prec = 48
        balances = {ident: amount for ident, amount, _ in parsed}
        initial = sum(balances.values(), Decimal(0))
        rows = []
        for year in range(1, years + 1):
            start = sum(balances.values(), Decimal(0))
            details = []
            for ident, _, payment_year in parsed:
                opening = balances[ident]
                payment = opening if payment_year == year else Decimal(0)
                balances[ident] -= payment
                details.append(dict(obligation_id=ident,
                    opening_balance_cny=str(opening), payment_cny=str(payment),
                    closing_balance_cny=str(balances[ident])))
            payment = sum((Decimal(item["payment_cny"]) for item in details), Decimal(0))
            closing = sum(balances.values(), Decimal(0))
            assert start - payment == closing
            rows.append(dict(year=year, opening_outstanding_cny=str(start),
                payment_cny=str(payment), closing_outstanding_cny=str(closing),
                items=details))
        return dict(schema_version=VERSION,
            classification="NONPRODUCTIVE_LIABILITY_SETTLEMENT",
            initial_outstanding_cny=str(initial), rows=rows,
            terminal_outstanding_cny=str(sum(balances.values(), Decimal(0))),
            new_shareholder_distribution=False, productive_capital_addition=False,
            maturity_dates_proven=False, action="no_order",
            limitation="Caller must exclude scheduled balances from duplicate reserves, WC and cash uses; no payment source, refinancing, legal capacity or future interest inferred.")

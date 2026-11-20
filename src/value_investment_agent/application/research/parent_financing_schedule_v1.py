"""Project verified parent gross financing and later contractual principal."""
from datetime import date
from decimal import Decimal, localcontext


def project_parent_financing_schedule(*, period_end, reported_ytd, issuance_events):
    """Use parsed official terms. Keep contracted maturities separate from cash."""
    cutoff = date.fromisoformat(period_end)
    reported = {}
    for field in ("borrowings_received_cny", "debt_repayments_paid_cny"):
        amount = Decimal(reported_ytd[field]["current"])
        if not amount.is_finite() or amount < 0:
            raise ValueError("PARENT_FINANCING_INVALID_HISTORICAL_FLOW")
        reported[field] = amount

    with localcontext() as context:
        context.prec = 48
        by_code = {}
        by_maturity = {}
        total_at_issue_price = Decimal(0)
        for event in issuance_events:
            terms, source = event["issue"], event["source_binding"]
            code = terms["code"]
            start = date.fromisoformat(terms["interest_start"])
            maturity = date.fromisoformat(terms["maturity"])
            principal = Decimal(terms["face_value_cny"])
            price = Decimal(terms["issue_price_per_100_face_cny"])
            if (not cutoff < start < maturity or not principal.is_finite() or principal <= 0
                    or not price.is_finite() or price <= 0):
                raise ValueError("PARENT_FINANCING_INVALID_LATER_ISSUE")
            if code in by_code:
                if by_code[code]["terms"] != terms:
                    raise ValueError("PARENT_FINANCING_CONFLICTING_ISSUE_TERMS")
                if source not in by_code[code]["sources"]:
                    by_code[code]["sources"].append(source)
                continue
            by_code[code] = dict(terms=terms, sources=[source])
            by_maturity[maturity] = by_maturity.get(maturity, Decimal(0)) + principal
            total_at_issue_price += principal * price / 100
        return dict(
            schema_version="parent-financing-schedule-v1",
            period_end=period_end,
            reported_ytd_cny={key: str(value) for key, value in reported.items()},
            later_issues=by_code,
            later_issuance_proceeds_at_issue_price_cny=str(total_at_issue_price),
            scheduled_face_principal_by_maturity_cny={
                day.isoformat(): str(value) for day, value in sorted(by_maturity.items())
            },
            actual_later_cash_verified=False,
            remaining_debt_verified=False,
            formal_eligibility=False,
            action="no_order",
        )

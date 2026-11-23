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


def disclosed_financing_limits(schedule):
    """Derive the policy bounds for disclosed issues and observed financing."""
    observed_year = date.fromisoformat(schedule["period_end"]).year
    reported = schedule["reported_ytd_cny"]
    with localcontext() as context:
        context.prec = 48
        borrowing_limit = (
            Decimal(reported["borrowings_received_cny"])
            + Decimal(schedule["later_issuance_proceeds_at_issue_price_cny"])
        )
        repayment_floors = {
            observed_year: Decimal(reported["debt_repayments_paid_cny"]),
        }
        for maturity, value in schedule["scheduled_face_principal_by_maturity_cny"].items():
            year = date.fromisoformat(maturity).year
            repayment_floors[year] = repayment_floors.get(year, Decimal(0)) + Decimal(value)

    return observed_year, borrowing_limit, repayment_floors


def validate_disclosed_financing_policy(schedule, policy):
    observed_year, borrowing_limit, repayment_floors = disclosed_financing_limits(schedule)
    years = policy["years"]
    series = policy["series"]
    if not repayment_floors.keys() <= set(years):
        raise ValueError("PARENT_FINANCING_SCHEDULE_YEAR_MISSING")
    for year, borrowed, repaid in zip(
        years, series["new_borrowing"]["values"], series["debt_repayment"]["values"],
        strict=True,
    ):
        borrowing = Decimal(borrowed)
        repayment = Decimal(repaid)
        if any(not value.is_finite() or value < 0 for value in (borrowing, repayment)):
            raise ValueError("PARENT_FINANCING_SCHEDULE_INVALID_POLICY_AMOUNT")
        if year == observed_year and borrowing > borrowing_limit:
            raise ValueError(f"PARENT_FINANCING_ABOVE_DISCLOSED_PROCEEDS:{year}")
        if year in repayment_floors and repayment < repayment_floors[year]:
            raise ValueError(f"PARENT_FINANCING_BELOW_CONTRACTUAL_PRINCIPAL:{year}")

def disclosed_schedule_from_context(context):
    issues = (context.get("constraints") or {}).get("issued_financing", [])
    observations = [
        row["financing_cash_flows"]
        for row in context.get("historical_financing_observations", [])
        if row["financing_cash_flows"]["period_end"].endswith("-09-30")
    ]
    if len(observations) != 1 or not issues:
        return None
    cash = observations[0]
    cutoff = date.fromisoformat(cash["period_end"])
    selected = [
        row for row in issues
        if cutoff < date.fromisoformat(row["issue_date"]) <= date(cutoff.year, 12, 31)
    ]
    if not selected or any(row.get("gross_issue_price_amount_cny") is None for row in selected):
        return None
    fields = ("borrowings_received_cny", "debt_repayments_paid_cny")
    flows = cash["components"]
    if cash["period_start"] != f"{cutoff.year}-01-01" or any(
        flows[field]["classification"] != "FACT" for field in fields
    ):
        return None
    events = []
    for row in selected:
        principal = Decimal(row["principal_cny"])
        gross = Decimal(row["gross_issue_price_amount_cny"])
        if not principal.is_finite() or principal <= 0 or not gross.is_finite() or gross <= 0:
            raise ValueError("PARENT_FINANCING_INVALID_LATER_ISSUE")
        events.append({
            "issue": {"code": row["code"], "interest_start": row["issue_date"],
                      "maturity": row["maturity"], "face_value_cny": str(principal),
                      "issue_price_per_100_face_cny": str(gross * 100 / principal)},
            "source_binding": row.get("source_refs", []),
        })
    return project_parent_financing_schedule(
        period_end=cash["period_end"],
        reported_ytd={field: {"current": flows[field]["value_cny"]} for field in fields},
        issuance_events=events,
    )

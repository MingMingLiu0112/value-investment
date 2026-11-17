"""Same-original historical parent cash proxy for conditional research.

This is a diagnostic of past cash flows, never a distributable-cash fact,
future accessible-profit ratio, or valuation input by itself.
"""

from decimal import Decimal, InvalidOperation
from datetime import datetime
import re


VERSION = "parent-cash-reach-anchor-v1"
_REQUIRED = {
    "parent_profit": "consolidated_parent",
    "cfo_cny": "ISSUER_PARENT_STANDALONE",
    "investment_income_cash_cny": "ISSUER_PARENT_STANDALONE",
    "gross_capex_cny": "ISSUER_PARENT_STANDALONE",
}


def historical_parent_cash_reach(context: dict) -> dict | None:
    """Join only unique FY lines from the same original and observation time."""
    if not isinstance(context, dict) or not isinstance(context.get("evidence"), list):
        raise ValueError("PARENT_CASH_REACH_CONTEXT_INVALID")
    cutoff = context.get("source_as_of")
    if cutoff is not None:
        try:
            cutoff = datetime.fromisoformat(cutoff)
            if cutoff.utcoffset() is None:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise ValueError("PARENT_CASH_REACH_CUTOFF_INVALID") from error
    grouped: dict[tuple[str, str, str], dict[str, list[dict]]] = {}
    for row in context["evidence"]:
        if not isinstance(row, dict) or row.get("field") not in _REQUIRED:
            continue
        field = row["field"]
        if (row.get("scope") != _REQUIRED[field] or row.get("unit") != "CNY"
                or row.get("period_basis") != "FY"):
            continue
        period, original, available = (row.get(key) for key in
                                       ("period", "pdf_sha256", "available_at"))
        if (not isinstance(period, str) or not period.endswith("-12-31")
                or not isinstance(original, str) or re.fullmatch(r"[0-9a-f]{64}", original) is None
                or not isinstance(available, str) or not available
                or not isinstance(row.get("id"), str) or not row["id"]):
            continue
        try:
            observed_at = datetime.fromisoformat(available)
            if observed_at.utcoffset() is None or (cutoff is not None and observed_at > cutoff):
                continue
        except ValueError:
            continue
        grouped.setdefault((period, original, available), {}).setdefault(field, []).append(row)
    observations = []
    for (period, original, available), fields in sorted(grouped.items()):
        if any(len(fields.get(field, [])) != 1 for field in _REQUIRED):
            continue
        rows = {field: fields[field][0] for field in _REQUIRED}
        cash_sources = {rows[field].get("source_id") for field in
                        ("cfo_cny", "investment_income_cash_cny", "gross_capex_cny")}
        if len(cash_sources) != 1 or None in cash_sources:
            continue
        try:
            amounts = {field: Decimal(str(row["value"])) for field, row in rows.items()}
        except (KeyError, InvalidOperation, TypeError):
            continue
        if (not all(value.is_finite() for value in amounts.values())
                or amounts["parent_profit"] <= 0 or amounts["gross_capex_cny"] < 0):
            continue
        operating_plus_investment = amounts["cfo_cny"] + amounts["investment_income_cash_cny"]
        after_gross_capex = operating_plus_investment - amounts["gross_capex_cny"]
        observations.append({
            "period": period, "pdf_sha256": original, "available_at": available,
            "consolidated_parent_profit_cny": str(amounts["parent_profit"]),
            "parent_cfo_cny": str(amounts["cfo_cny"]),
            "parent_investment_income_cash_cny": str(amounts["investment_income_cash_cny"]),
            "parent_gross_capex_cny": str(amounts["gross_capex_cny"]),
            "historical_parent_cash_after_gross_capex_cny": str(after_gross_capex),
            "historical_cash_proxy_to_profit_ratio": str(
                (after_gross_capex / amounts["parent_profit"]).quantize(Decimal("0.0001"))),
            "evidence_ids": [rows[field]["id"] for field in _REQUIRED],
        })
    counts = {row["period"]: sum(item["period"] == row["period"] for item in observations)
              for row in observations}
    observations = [row for row in observations if counts[row["period"]] == 1]
    if not observations:
        return None
    return {
        "schema_version": VERSION, "action": "no_order",
        "scope": "HISTORICAL_PARENT_CASH_PROXY_NOT_DISTRIBUTABLE_CASH",
        "observations": observations,
        "limitation": (
            "Parent CFO plus investment-income cash less all gross capex is historical "
            "cash-flow arithmetic. Gross capex is not maintenance capex; the ratio is "
            "not a future accessible-profit ratio, available distribution, or proof "
            "of recurring subsidiary remittance. Other financing and cash restrictions "
            "are not resolved by this diagnostic."
        ),
    }

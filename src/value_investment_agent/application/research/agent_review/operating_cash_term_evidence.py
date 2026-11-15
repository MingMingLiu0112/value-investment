"""Build compact, scope-specific cash evidence from an already verified context."""
from decimal import Decimal

from .operating_cash_policy_draft_v16_generic import candidates


# Rules describe the evidence needed for research, not fallback model inputs.
TERM_INPUTS = {
    "target_payout_ratio": (
        (), ("DISCLOSED_CONDITIONAL_RETURN_PLAN",),
        "Test a scenario under the disclosed policy while its conditions hold. A floor is not a target or a payment.",
    ),
    "accessible_profit_ratio": (
        ("parent_net_profit", "parent_profit", "parent_cash_balance", "investment_income_cash_cny"),
        (),
        "Compare standalone and consolidated attributable profit for the same period, then test upstreaming and cash constraints. The profit ratio itself is not an accessible-cash ratio.",
    ),
    "reserve_ratio": (
        ("parent_surplus_reserve", "parent_ordinary_share_capital"),
        ("ISSUER_ARTICLES_RULE_TEXT",),
        "Apply the disclosed threshold under unchanged charter and share capital only. Explicitly test changes to either condition.",
    ),
    "net_maintenance_cash_cny": (
        ("parent_capex", "gross_capex_cny"),
        (),
        "Use actual historical gross payments to test sensitivity; separate growth and any noncash offsets. A historical gross payment cannot identify future net maintenance.",
    ),
    "operating_wc_cash_cny": (
        ("parent_customer_cash", "parent_supplier_cash", "parent_cfo"),
        ("ISSUER_PARENT_STANDALONE_BALANCE_PROXY",),
        "Compare same-length historical parent receipts and payments. Balance movements are a cross-check, never the cash-component forecast.",
    ),
    "commitment_cash_cny": (
        (), ("ISSUER_PARENT_UNDATED_COMMITMENT_BOUND",),
        "Separate remaining exposure from payment timing. A conditional draw scenario needs a stated timing trigger; no scheduled amount or zero may be assumed without support.",
    ),
}
TYPED_SCOPES = {"parent", "ISSUER_PARENT_STANDALONE", "consolidated_parent"}


def build_cash_term_evidence(context, source_binding):
    """Keep typed parent fields ahead of broad text matches from other scopes."""
    eligible = candidates(context, source_binding)
    evidence = context["evidence"]
    output = {}
    for term, (fields, scopes, mechanism) in TERM_INPUTS.items():
        rows = [row for row in evidence if
                (row.get("field") in fields and row.get("scope") in TYPED_SCOPES
                 and row.get("unit") == "CNY")
                or row.get("scope") in scopes]
        rows.sort(key=lambda row: row["period"], reverse=True)
        output[term] = {
            "mechanism_to_test": mechanism,
            "validator_candidate_ids": [row["id"] for row in rows[:12] if row["id"] in eligible[term]],
            "evidence": [{k: row[k] for k in ("id", "field", "period", "scope", "unit", "value")
                          if k in row} for row in rows[:12]],
        }
    comparisons = []
    for period in sorted({row["period"] for row in evidence}, reverse=True):
        pair = []
        for field, scope in (("parent_net_profit", "parent"), ("parent_profit", "consolidated_parent")):
            matches = [r for r in evidence if r.get("field") == field and r["scope"] == scope
                       and r["period"] == period and r["unit"] == "CNY"]
            if len(matches) != 1:
                break
            pair.append(matches[0])
        if (len(pair) == 2 and pair[0].get("pdf_sha256")
                and pair[0]["pdf_sha256"] == pair[1]["pdf_sha256"]
                and pair[0].get("period_basis") in {"FY", "H1"}
                and pair[0]["period_basis"] == pair[1].get("period_basis")
                and Decimal(pair[1]["value"]) > 0):
            comparisons.append({
                "period": period, "basis": pair[0]["period_basis"],
                "standalone_to_attributable_profit_ratio": str(
                    (Decimal(pair[0]["value"]) / Decimal(pair[1]["value"])).quantize(Decimal("0.000001"))),
                "evidence_ids": [row["id"] for row in pair],
                "scope": "HISTORICAL_PROFIT_COMPARISON_NOT_CASH_CONVERSION",
            })
    output["accessible_profit_ratio"]["historical_comparisons"] = comparisons
    return output


def build_term_guided_cash_request(original, context, source_binding):
    """Use the verified annual summary with a new, traceable cash evidence appendix."""
    from dataclasses import replace

    from .operating_cash_request_compact import MAX_REQUEST_CHARS
    from .operating_draft_v1 import _canonical

    prefix, marker, suffix = original.user.partition("\nTERM_HISTORICAL_CANDIDATE_IDS=")
    _, boundary, annual = suffix.partition("\nVALIDATED_ANNUAL_CALCULATIONS=")
    if not marker or not boundary or not annual:
        raise ValueError("CASH_TERM_GUIDE_REQUIRES_COMPACT_REQUEST")
    guide = build_cash_term_evidence(context, source_binding)
    for section in guide.values():
        # The full evidence already appears in the base prompt. Avoid sending
        # a second copy and retain the exact evidence IDs for local validation.
        valid = set(section["validator_candidate_ids"])
        section["supplemental_evidence_ids"] = [
            row["id"] for row in section.pop("evidence") if row["id"] not in valid
        ]
    guide = _canonical(guide)
    user = prefix + "\nTERM_EVIDENCE_GUIDE=" + guide + boundary + annual
    if len(user) > MAX_REQUEST_CHARS:
        raise ValueError("CASH_TERM_GUIDE_REQUEST_OVER_BUDGET")
    return replace(original, user=user, system=original.system +
        " Use the term evidence guide and the source context to test prospective scenarios. "
        "An economic scenario may state its conditions and a calculable bound without claiming "
        "that future events have happened. Use UNKNOWN for genuinely unsupported values. "
        "For numerical terms include a validator_candidate_id for that term and state how the assumption could fail.")

"""Inspect the scope of evidence supplied to shareholder cash research."""

PARENT_SCOPES = {"parent", "ISSUER_PARENT_STANDALONE"}
HISTORICAL_ANCHORS = {
    "accessible_profit_ratio": {"parent_cfo", "parent_net_profit", "parent_investment_cash",
                                "investment_income_cash_cny"},
    "reserve_ratio": {"parent_cash_balance", "parent_surplus_reserve", "parent_retained_earnings"},
    "net_maintenance_cash_cny": {"parent_capex", "gross_capex_cny"},
}


def describe_cash_evidence(context):
    """Report historical anchors without turning them into forecast assumptions."""
    from ..operating_horizon_cash_policy_e2_v17 import cash_constraint_anchor_ids

    anchors = cash_constraint_anchor_ids(context)
    rows = context["evidence"]
    historical = {
        term: [
            row["id"] for row in rows
            if row.get("scope") in PARENT_SCOPES and row.get("field") in fields
        ]
        for term, fields in HISTORICAL_ANCHORS.items()
    }
    return {
        "source_binding": context["source_binding"],
        "conditional_return_plan_ids": [
            row["id"] for row in rows
            if row.get("scope") == "DISCLOSED_CONDITIONAL_RETURN_PLAN"
        ],
        "standalone_parent_historical_anchor_ids": historical,
        "e2_applicable_anchor_ids": anchors,
        "e2_terms_without_applicable_anchor": [term for term, ids in anchors.items() if not ids],
        "terms_not_classified": ["operating_wc_cash_cny", "commitment_cash_cny"],
        "action": "no_order",
    }

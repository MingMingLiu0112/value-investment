"""Source-bound fiscal dividend review, without rewriting frozen cash research."""
from datetime import datetime
from decimal import Decimal, localcontext
import hashlib
import json
from .current_capital_observation_v1 import read_current_capital_observation
from .operating_cash_consumption_v1 import read_operating_cash_consumption
from .agent_review.operating_sources_v1 import build_operating_source_context
from ...domain.research.fiscal_distribution_review_v1 import evaluate_fiscal_distribution_policy
from ...domain.valuation.signed_parent_profit import build_signed_parent_profit_path

def read_operating_distribution_review(*, root, task, now):
    """Cold-recompute both public consumers; never trust an in-memory valuation."""
    observations = read_current_capital_observation(root, task["symbol"], now)
    result = dict(schema_version="operating-distribution-review-v1", action="no_order",
        symbol=task["symbol"], status="UNASSESSABLE", formal_eligibility=False,
        main_range_adopted=False, condition_price=None, personal_quantity=None,
        scenarios={}, current_observations=observations)
    if observations["status"] != "VERIFIED":
        return dict(result, reason="ALL_REGISTERED_CAPITAL_ORIGINALS_MUST_VERIFY")
    policies = []
    for row in observations["source_bound_observations"]:
        native = row["observation"].get("dividend_policy", {})
        if native.get("status") == "VERIFIED":
            for policy in native["policies"]:
                policies.append((policy, row["source"]))
    cutoff = datetime.fromisoformat(task["research_as_of"])
    context = build_operating_source_context(root=root, symbol=task["symbol"], now=cutoff,
                                            binding=task["source_binding"])
    period = context["financial_basis"]
    year = int(period[:4])
    if period != f"{year}-06-30":
        return dict(result, reason="REPORTED_H1_BASIS_REQUIRED")
    selected = [(p, s) for p, s in policies if p["fiscal_year"] == year]
    if not selected:
        return dict(result, reason="FISCAL_YEAR_DISTRIBUTION_POLICY_NOT_VERIFIED")
    enc = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    economic_fields = ("fiscal_year", "minimum_payout_ratio", "minimum_distribution_cny", "currency", "scope")
    def economics(policy):
        return {key: policy[key] for key in economic_fields}
    if len({enc(economics(p)) for p, _ in selected}) != 1:
        return dict(result, reason="CONFLICTING_DISCLOSED_FISCAL_POLICIES")
    anchors = [r for r in context["evidence"] if r.get("field") == "parent_profit"
               and r.get("period") == period and r.get("scope") == "consolidated_parent"
               and r.get("unit") == "CNY" and r.get("kind") == "VERIFIED_REPORTED_FACT"]
    if len(anchors) != 1:
        return dict(result, reason="EXACT_REPORTED_PARENT_PROFIT_ANCHOR_REQUIRED")
    cash = read_operating_cash_consumption(root=root, task=task, now=now)
    annual = cash.get("annual_followup", {})
    if annual.get("status") != "CONDITIONAL_STRESS_CONSUMED":
        return dict(result, reason="COLD_RECOMPUTED_ANNUAL_CASH_PATH_REQUIRED")
    with localcontext() as ctx:
        ctx.prec = 48
        for name, path in annual["transport"]["scenarios"].items():
            first = path["annual_income_rows"][0]
            witness = path["d2_witness"]
            if (first["period_start"] != f"{year}-07-01"
                    or first["period_end"] != f"{year+1}-06-30"):
                raise ValueError("ROLLING_TRANSPORT_PERIOD_CHANGED")
            # Remove the exact future-H1 witness from the rolling first-year row.
            # No H1*2, no second tax-rate assumption, no prior-year cash payments.
            profit = build_signed_parent_profit_path(years=[year], currency="CNY",
                group_pbt_cny=[str(Decimal(first["group_pbt_cny"])-Decimal(witness["group_pbt_cny"]))],
                tax_assumptions=[dict(basis="amount_cny", value=str(
                    Decimal(first["tax_assumption"]["value"])-Decimal(witness["income_tax_cny"])))],
                signed_nci_cny=[str(Decimal(first["signed_nci_cny"])-Decimal(witness["signed_nci_cny"]))])
            half = dict(scope="consolidated_parent", currency="CNY")
            result["scenarios"][name] = evaluate_fiscal_distribution_policy(
                policy=economics(selected[0][0]),
                reported_half=dict(half, period_start=f"{year}-01-01", period_end=period,
                                   parent_profit_cny=anchors[0]["value"], kind="REPORTED_FACT"),
                forecast_half=dict(half, period_start=f"{year}-07-01", period_end=f"{year}-12-31",
                    parent_profit_cny=profit["rows"][0]["parent_profit_cny"], kind="FORECAST_ASSUMPTION"))
    result.update(status="SOURCE_BOUND_FISCAL_POLICY_REVIEW", source_binding=[s for _, s in selected],
        policy_evidence=[dict(policy=p,source=s) for p,s in selected],
        reported_profit_anchor=anchors[0], cash_consumption_fingerprint=cash["consumption_fingerprint"],
        input_descriptor_sha256=annual["input_descriptor_sha256"], financial_basis=period,
        fiscal_payment_alignment="NOT_ASSESSED",
        limitations=["This is policy-versus-earnings research, not a cash-capacity test or dividend-compliance finding.",
            "The original July-June model ledger is unchanged; disclosed FY targets are not imposed on rolling years.",
            "Subsequent reports and events do not retroactively change frozen inputs; current use requires revalidation."])
    latest = observations["current_financial_coverage"].get("latest_report_period")
    result["financial_update_review"] = dict(
        status="NEWER_REPORT_REQUIRES_MODEL_REVALIDATION" if latest and latest > period else "REGISTERED_COVERAGE_ONLY",
        model_financial_basis=period, latest_registered_report_period=latest, current_model_validity="NOT_GRANTED")
    from ...domain.research.fiscal_distribution_review_v1 import compare_fiscal_projection_with_nine_months
    updates = [row for row in observations["source_bound_observations"]
        if row["observation"].get("financial_update", {}).get("status") == "VERIFIED"
        and row["observation"]["financial_update"].get("period_end") == f"{year}-09-30"]
    if len(updates) == 1:
        result["financial_update_review"]["comparisons"] = {
            name: compare_fiscal_projection_with_nine_months(
                fiscal_review=review,ytd_update=updates[0]["observation"]["financial_update"])
            for name,review in result["scenarios"].items()}
        result["financial_update_review"]["comparison_source"] = updates[0]["source"]
    else:
        result["financial_update_review"]["comparison_status"] = "NO_UNIQUE_VERIFIED_SAME_YEAR_Q3_UPDATE"
    from pathlib import Path
    from ...domain.research import fiscal_distribution_review_v1 as fiscal_kernel
    result["implementation_sha256"] = {
        "consumer": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fiscal_kernel": hashlib.sha256(Path(fiscal_kernel.__file__).read_bytes()).hexdigest()}
    result["review_fingerprint"] = hashlib.sha256(enc(result).encode()).hexdigest()
    return result

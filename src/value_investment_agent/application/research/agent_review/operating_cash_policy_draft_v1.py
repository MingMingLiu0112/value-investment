"""A bounded, source-bound D2 follow-up for shareholder-cash policy only.

It intentionally does not re-ask the model for annual operating scenarios.
That keeps the provider output small enough to audit while preserving the
existing annual-research and E2 boundaries.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import re

from . import operating_horizon_draft_v3 as policy
from .parent_cash_conversion_anchor_v1 import historical_parent_cash_conversion
from . import operating_driver_draft_v2 as driver_contract
from . import operating_draft_v1 as common
from .operating_driver_draft_v2 import _exact, _payload


VERSION = "operating-cash-policy-draft-v1"
PROMPT_VERSION = "operating-cash-policy-prompts-v2-evidence-anchored-assumptions"


def build_request(context, years, max_completion_tokens=2048, prior_hypothesis=None):
    """Build a compact policy-only request from an already sealed source context."""
    base = policy.build_request(context, years, max_completion_tokens=max_completion_tokens)
    dividend_anchor = policy.dividend_policy_anchor_v1.disclosed_per_share_growth_anchor(context)
    earnings_payout_anchor = policy.dividend_policy_anchor_v1.disclosed_attributable_profit_payout_anchor(context)
    parent_cash_anchor = historical_parent_cash_conversion(context)
    if prior_hypothesis is not None:
        if (not isinstance(prior_hypothesis, dict)
                or prior_hypothesis.get("forecast_year") not in years
                or prior_hypothesis.get("scope")
                != "OLDER_UNAPPROVED_CONDITIONAL_STRESS_FOR_CRITICAL_REVIEW_ONLY"):
            raise ValueError("D2_PRIOR_HYPOTHESIS_SCOPE_OR_YEAR_INVALID")
    prior_text = ("\nSOURCE_BOUND_OLDER_CONDITIONAL_STRESS_FOR_CRITIQUE=" +
        json.dumps(prior_hypothesis, sort_keys=True, ensure_ascii=False)
        if prior_hypothesis is not None else "")
    no_material_balance_date_commitment = any(
        row.get("unit") == "TEXT"
        and "资产负债表日存在的重要承诺" in row.get("text", "")
        and "\n无。" in row.get("text", "").replace("\r", "")
        for row in context.get("evidence", [])
    )
    ids = common._context(driver_contract.legacy_context(context))
    year_schema = dict(type="object", additionalProperties=False,
        required=["shareholder_cash_paths"],
        properties={"shareholder_cash_paths": dict(type="object", additionalProperties=False,
            required=list(policy.SCENARIOS),
            properties={name: policy._cash_path_schema(evidence_ids=ids)
                        for name in policy.SCENARIOS})})
    schema = dict(type="object", additionalProperties=False, required=["years"],
        properties={"years": dict(type="object", additionalProperties=False,
            required=[str(year) for year in years],
            properties={str(year): deepcopy(year_schema) for year in years})})
    return replace(base, output_schema=schema,
        user=base.user + ("\nSOURCE_BOUND_PARENT_CASH_CONVERSION_HISTORY=" +
            json.dumps(parent_cash_anchor, sort_keys=True, ensure_ascii=False)
            if parent_cash_anchor else "") + ("\nSOURCE_BOUND_ATTRIBUTABLE_PROFIT_PAYOUT_TARGET=" +
            json.dumps(earnings_payout_anchor, sort_keys=True, ensure_ascii=False)
            if earnings_payout_anchor else "") + prior_text,
        transport_output_contract=("Return only {years:{<requested year>:{shareholder_cash_paths:{bear,base,bull}}}}. "
            "Each of bear,base,bull has exactly these literal keys: target_payout_ratio, "
            "accessible_profit_ratio, reserve_ratio, net_maintenance_cash_cny, operating_wc_cash_cny, "
            "commitment_cash_cny, counter_evidence, reopen_condition. Do not use aliases including "
            "dividend_payout_ratio, parent_distributable_cash, dividend_per_share or "
            "net_cash_returned_to_shareholders. A quantified ratio term MUST have the literal unit ratio; "
            "describe its profit denominator in rationale, never as a custom unit. "
            "Every term has exactly classification,value,unit,rationale,"
            "evidence_ids; use FORECAST_ASSUMPTION with a decimal-string value and the native unit only when the "
            "rationale explains how sealed historical evidence anchors the scenario, otherwise use UNKNOWN with "
            "null value/not_quantified unit and a non-empty rationale. evidence_ids is always a non-empty array chosen only from supplied sealed "
            "evidence IDs, including for UNKNOWN. counter_evidence and reopen_condition are plain non-empty JSON "
            "strings, never objects. Each term rationale is 1-240 characters; counter_evidence and reopen_condition are each 1-600 characters. "
            "Keep citations in evidence_ids, not repeated prose. Never use status."),
        system=("CASH_POLICY_FOLLOWUP_ONLY_V1. " + PROMPT_VERSION + ": Return exactly the JSON structure in "
            "the user transport contract and no other fields. This is a schema-completion task, not an opportunity "
            "to invent a preferred dividend-report template. The six legal terms are target_payout_ratio, "
            "accessible_profit_ratio, reserve_ratio, net_maintenance_cash_cny, operating_wc_cash_cny and "
            "commitment_cash_cny. Each of bear, base and bull must include all six. Use FORECAST_ASSUMPTION only "
            "when its rationale identifies a sealed historical anchor, scenario rationale and counter-evidence; "
            "otherwise return UNKNOWN/null/not_quantified for that exact legal term. Do not repeat operating forecasts, "
            "valuation, prices, recommendations or approvals. Assess only shareholder-cash policy from sealed "
            "sources. Do not infer parent distributable cash from consolidated cash. Missing evidence remains "
            "UNKNOWN, never zero or one. For EVERY term, evidence_ids must contain at least one supplied sealed "
            "ID; UNKNOWN does not allow an empty list. counter_evidence and reopen_condition must be ordinary "
            "non-empty strings, with no classification, value, unit, rationale or evidence_ids object. Keep every term rationale at most 240 characters; "
            "put source IDs only in evidence_ids rather than repeating them in rationale text.") +
            (" The user input includes a source-bound conditional per-share dividend plan. "
             "Use it as a challengeable target-payout anchor only if parent earnings and share basis "
             "can be reconciled; never use it to infer accessible cash, maintenance, WC or commitments, "
             "and never copy per-share growth into a payout ratio."
             if dividend_anchor else "") +
            (" The source-bound dividend target is a ratio of consolidated profit attributable to ordinary shareholders, "
             "not standalone-parent net profit or distributable cash. Keep those denominators distinct. "
             "It is a conditional management target, not a cash-access ratio, reserve ratio, or guaranteed payment."
             if earnings_payout_anchor else "") +
            (" A filing reports no material commitments at its balance-sheet date. This does not prove "
             "zero future growth capex, working-capital needs, debt maturities, or contractual payments. "
             "Use it only as dated counter-evidence; future commitment_cash_cny still requires an "
             "independently reasoned scenario or UNKNOWN."
             if no_material_balance_date_commitment else "") +
            (" Same-original standalone-parent profit, operating cash flow and gross capex history is "
             "provided as arithmetic anchors. CFO less profit includes non-cash and timing effects; "
             "do not label that difference working capital. H1 is not an annual run rate. "
             "You may propose bounded, explicitly challengeable cash-conversion assumptions "
             "with separate counter-evidence, but do not copy historical CFO into future "
             "accessible profit or equate gross capex to maintenance."
             if parent_cash_anchor else "") +
            (" An older source-bound conditional STRESS proposal is supplied only for independent critique. "
             "Its figures are not official facts, a current main range, or defaults. For each policy term, "
             "explain whether current sealed facts and economic mechanism support a challengeable forecast; "
             "retain, revise, or reject the old amount. If the mechanism cannot support a numeric conditional "
             "assumption, return UNKNOWN. Do not cite the old proposal as an official evidence ID."
             if prior_hypothesis is not None else ""))


def validate_response(response, context, years, generated_at):
    """Validate policy-only output using the same six-term economics contract."""
    text = response.text if hasattr(response, "text") else response
    payload = _payload(text)
    _exact(payload, ("years",))
    _exact(payload["years"], [str(year) for year in years])
    ids = common._context(driver_contract.legacy_context(context))
    earnings_payout_anchor = policy.dividend_policy_anchor_v1.disclosed_attributable_profit_payout_anchor(context)
    result_years = {}
    for year, row in payload["years"].items():
        _exact(row, ("shareholder_cash_paths",))
        result_years[year] = {"shareholder_cash_paths": policy._cash_paths(
            row["shareholder_cash_paths"], ids=ids)}
        if earnings_payout_anchor and int(year) in earnings_payout_anchor["fiscal_years"]:
            for path in result_years[year]["shareholder_cash_paths"].values():
                term = path["terms"]["target_payout_ratio"]
                if (term["classification"] == "FORECAST_ASSUMPTION"
                        and re.search(r"\bparent\s+(?:net\s+)?(?:profit|earnings)\b|母公司(?:净)?利润",
                                      term["rationale"], flags=re.IGNORECASE)):
                    raise ValueError("SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT")
    complete = all(path["complete"] for row in result_years.values()
                   for path in row["shareholder_cash_paths"].values())
    return dict(schema_version=VERSION, prompt_version=PROMPT_VERSION,
        response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), years=result_years,
        cash_policy_appendix_status=("COMPLETE_UNAPPROVED" if complete else "INCOMPLETE_UNKNOWN_TERMS"),
        status=("CASH_POLICY_REQUIRES_INDEPENDENT_REVIEW" if complete
                else "CASH_POLICY_INCOMPLETE_UNKNOWN_TERMS"), valuation_produced=False,
        main_range_adopted=False, action="no_order", formal_eligibility=False)

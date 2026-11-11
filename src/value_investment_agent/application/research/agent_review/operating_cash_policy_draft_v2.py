"""D2 cash-stage draft contract with an explicit issuer-plan v2 anchor.

Root supplies the bound source context. This module makes no source or model calls.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from . import operating_cash_policy_draft_v1 as v1
from . import operating_driver_draft_v2 as driver_contract
from . import operating_draft_v1 as common
from . import operating_horizon_draft_v3 as policy
from .issuer_dividend_plan_v2 import URL
from .operating_driver_draft_v2 import _exact, _payload


VERSION = "operating-cash-policy-draft-v2-issuer-plan"
PROMPT_VERSION = "operating-cash-policy-prompts-v2-issuer-plan"


def _binding(value, *, source=False):
    keys = {"path", "sha256", "source_url"} if source else {"path", "sha256"}
    if (not isinstance(value, dict) or set(value) != keys
            or not isinstance(value["path"], str) or not value["path"]
            or Path(value["path"]).is_absolute() or ".." in Path(value["path"]).parts
            or not isinstance(value["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
            or (source and value["source_url"] != URL)):
        raise ValueError("D2_V2_POLICY_BINDING_REQUIRED")
    return deepcopy(value)


def policy_context_v2(context, years):
    """Validate the top-level plan envelope without altering the source rows."""
    if years != [2026]:
        raise ValueError("D2_V2_PLAN_ONLY_SUPPORTS_2026_NO_EXTRAPOLATION")
    if not isinstance(context, dict) or not isinstance(context.get("issuer_dividend_plan"), dict):
        raise ValueError("D2_V2_ISSUER_PLAN_REQUIRED")
    anchor = context["issuer_dividend_plan"]
    if (anchor.get("schema_version") != "d2-issuer-dividend-plan-anchor-v2"
            or anchor.get("symbol") != context.get("symbol") or anchor.get("symbol") != "600519"
            or anchor.get("status") != "DISCLOSED_CONDITIONAL_ANNUAL_PAYOUT_PLAN"
            or anchor.get("fiscal_years") != [2024, 2025, 2026]
            or anchor.get("minimum_ratios") != ["0.75"] * 3
            or anchor.get("profit_basis") != "consolidated_parent_attributable"
            or anchor.get("distribution_basis") != "annual_total_cash_dividends"
            or anchor.get("physical_pages") != [1, 2]
            or anchor.get("action") != "no_order" or anchor.get("formal_eligibility") is not False):
        raise ValueError("D2_V2_ISSUER_PLAN_IDENTITY_INVALID")
    source = _binding(anchor.get("source_binding"), source=True)
    receipt = _binding(anchor.get("receipt_binding"))
    try:
        available = datetime.fromisoformat(anchor["available_at"])
        as_of = datetime.fromisoformat(context["source_as_of"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("D2_V2_PLAN_PIT_INVALID") from error
    if as_of.utcoffset() is None or available.utcoffset() is None or available > as_of:
        raise ValueError("D2_V2_PLAN_NOT_AVAILABLE_AS_OF_RESEARCH")
    evidence_id = "issuer-plan-v2:" + source["sha256"][:24]
    original_ids = common._context(driver_contract.legacy_context({
        key: value for key, value in context.items()
        if key not in {"issuer_dividend_plan", "source_as_of"}}))
    if evidence_id in original_ids:
        raise ValueError("D2_V2_PLAN_EVIDENCE_ID_COLLISION")
    return dict(schema_version="d2-cash-policy-context-v2", symbol=anchor["symbol"],
        research_as_of=context["as_of"], source_as_of=as_of.isoformat(),
        evidence_id=evidence_id,
        source_binding=source, receipt_binding=receipt, available_at=available.isoformat(),
        disclosed_policy_target_2026=dict(minimum_ratio="0.75",
            profit_basis="consolidated_parent_attributable",
            scope="CONDITIONAL_ISSUER_PLAN_NOT_FORECAST_PAYOUT_OR_PARENT_CASH"))


def build_request(context, years, max_completion_tokens=2048, prior_hypothesis=None):
    plan = policy_context_v2(context, years)
    ordinary = {key: value for key, value in context.items()
        if key not in {"issuer_dividend_plan", "source_as_of"}}
    base = v1.build_request(ordinary, years, max_completion_tokens, prior_hypothesis)
    schema = deepcopy(base.output_schema)
    for scenario in policy.SCENARIOS:
        target_ids = schema["properties"]["years"]["properties"]["2026"]["properties"][
            "shareholder_cash_paths"]["properties"][scenario]["properties"]["target_payout_ratio"][
            "properties"]["evidence_ids"]["items"]["enum"]
        target_ids.append(plan["evidence_id"])
    instruction = (" The supplied 2024-2026 issuer plan is a conditional annual cash-dividend "
        "minimum of 75% of consolidated profit attributable to listed-company shareholders. "
        "Its 2026 target is not a forecast payout ratio, parent profit, parent distributable cash, "
        "cash access, or a guaranteed payment. For the 2026 target_payout_ratio cite its evidence ID; "
        "a numeric FORECAST_ASSUMPTION also requires independent ordinary evidence and a rationale "
        "that explicitly separates the conditional plan from the scenario forecast assumption. "
        "Never cite the plan for accessible_profit_ratio, reserves, maintenance cash, working "
        "capital or commitments. Do not extrapolate the plan to 2027 or later. "
        "UNKNOWN remains allowed when no independent forecast mechanism is established.")
    return replace(base, output_schema=schema,
        system=base.system + " " + PROMPT_VERSION + "." + instruction,
        user=base.user + "\nSOURCE_BOUND_ISSUER_DIVIDEND_PLAN_V2=" +
            json.dumps(plan, ensure_ascii=False, sort_keys=True))


def validate_response(response, context, years, generated_at):
    plan = policy_context_v2(context, years)
    ordinary = {key: value for key, value in context.items()
        if key not in {"issuer_dividend_plan", "source_as_of"}}
    ids = common._context(driver_contract.legacy_context(ordinary))
    if (not isinstance(generated_at, datetime) or generated_at.utcoffset() is None
            or generated_at < datetime.fromisoformat(plan["source_as_of"])):
        raise ValueError("D2_V2_GENERATED_BEFORE_RESEARCH")
    text = response.text if hasattr(response, "text") else response
    payload = _payload(text)
    _exact(payload, ("years",))
    _exact(payload["years"], ("2026",))
    _exact(payload["years"]["2026"], ("shareholder_cash_paths",))
    paths = policy._cash_paths(payload["years"]["2026"]["shareholder_cash_paths"],
        ids=ids | {plan["evidence_id"]})
    for path in paths.values():
        terms = path["terms"]
        target = terms["target_payout_ratio"]
        if plan["evidence_id"] not in target["evidence_ids"]:
            raise ValueError("D2_V2_TARGET_MUST_CITE_POLICY")
        for name, term in terms.items():
            if name != "target_payout_ratio" and plan["evidence_id"] in term["evidence_ids"]:
                raise ValueError("D2_V2_POLICY_CANNOT_ESTABLISH_PARENT_CASH")
        rationale = target["rationale"]
        if re.search(r"\bparent\s+(?:net\s+)?(?:profit|earnings|cash)\b|母公司(?:净)?利润|母公司现金",
                     rationale, re.IGNORECASE):
            raise ValueError("D2_V2_PAYOUT_DENOMINATOR_OR_CASH_INFERENCE")
        if target["classification"] == "FORECAST_ASSUMPTION" and (
                not set(target["evidence_ids"]) & ids
                or not re.search(r"conditional|条件", rationale, re.IGNORECASE)
                or not re.search(r"forecast|假设", rationale, re.IGNORECASE)):
            raise ValueError("D2_V2_CONDITIONAL_TARGET_IS_NOT_FORECAST")
    complete = all(path["complete"] for path in paths.values())
    return dict(schema_version=VERSION, prompt_version=PROMPT_VERSION,
        policy_context=plan, response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        years={"2026": {"shareholder_cash_paths": paths}},
        cash_policy_appendix_status="COMPLETE_UNAPPROVED" if complete else "INCOMPLETE_UNKNOWN_TERMS",
        status="CASH_POLICY_REQUIRES_INDEPENDENT_REVIEW" if complete else "CASH_POLICY_INCOMPLETE_UNKNOWN_TERMS",
        valuation_produced=False, main_range_adopted=False,
        action="no_order", formal_eligibility=False)

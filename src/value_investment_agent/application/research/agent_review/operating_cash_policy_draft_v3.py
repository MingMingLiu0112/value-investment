"""2027 cash draft: expired issuer plan is historical counterevidence only."""
from dataclasses import replace
from datetime import datetime
from copy import deepcopy
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from . import operating_cash_policy_draft_v1 as prior
from . import operating_cash_policy_draft_v2 as policy_v2
from . import operating_draft_v1 as common
from . import operating_driver_draft_v2 as drivers


VERSION = "operating-cash-policy-draft-v3-2027-historical-plan"
CHINA = ZoneInfo("Asia/Shanghai")


def _ordinary(context):
    return {key: value for key, value in context.items()
        if key not in {"issuer_dividend_plan", "source_as_of"}}


def historical_plan_context(context, years):
    if years != [2027]:
        raise ValueError("D2_V3_EXACT_2027_YEAR_REQUIRED")
    if not isinstance(context, dict) or not isinstance(context.get("issuer_dividend_plan"), dict):
        raise ValueError("D2_V3_HISTORICAL_PLAN_REQUIRED")
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
        raise ValueError("D2_V3_HISTORICAL_PLAN_IDENTITY_INVALID")
    source = policy_v2._binding(anchor.get("source_binding"), source=True)
    receipt = policy_v2._binding(anchor.get("receipt_binding"))
    try:
        available = datetime.fromisoformat(anchor["available_at"])
        source_as_of = datetime.fromisoformat(context["source_as_of"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("D2_V3_SOURCE_TIME_INVALID") from error
    if (available.utcoffset() is None or source_as_of.utcoffset() is None
            or available > source_as_of
            or source_as_of.astimezone(CHINA).date().isoformat() != context.get("as_of")):
        raise ValueError("D2_V3_PLAN_NOT_AVAILABLE_AT_EXACT_SOURCE_TIME")
    common._context(drivers.legacy_context(_ordinary(context)))
    return dict(schema_version="d2-cash-historical-plan-context-v3",
        symbol=context["symbol"], research_as_of=context["as_of"],
        source_as_of=source_as_of.isoformat(), available_at=available.isoformat(),
        source_binding=source, receipt_binding=receipt,
        policy_years=[2024, 2025, 2026], policy_minimum_ratio="0.75",
        scope="EXPIRED_HISTORICAL_COUNTEREVIDENCE_NOT_2027_TARGET_OR_CASH_CAPACITY")


def build_request(context, years, max_completion_tokens=2048, prior_hypothesis=None):
    historical = historical_plan_context(context, years)
    base = prior.build_request(_ordinary(context), years, max_completion_tokens, prior_hypothesis)
    annotation = common._canonical(historical)
    if len(base.user) + len(annotation) > 64000:
        raise ValueError("D2_V3_CASH_INPUT_OVER_BUDGET")
    return replace(base,
        user=base.user + "\nEXPIRED_ISSUER_PLAN_HISTORICAL_COUNTEREVIDENCE_V3=" + annotation,
        system=base.system + " " + VERSION + ": The issuer's 2024-2026 75% plan has expired "
            "for the requested 2027 year. It is historical counterevidence only, not a 2027 "
            "target minimum, forecast ratio, parent profit or cash capacity. Do not cite its "
            "binding as support for any numeric 2027 cash assumption. Every numeric cash term "
            "requires an ordinary historical source citation and an explicit economic mechanism "
            "in its rationale beginning 'Mechanism:'. UNKNOWN with null remains allowed; "
            "do not turn it into a positive E2 cash case.")


def validate_response(response, context, years, generated_at):
    historical = historical_plan_context(context, years)
    if (not isinstance(generated_at, datetime) or generated_at.utcoffset() is None
            or generated_at < datetime.fromisoformat(historical["source_as_of"])):
        raise ValueError("D2_V3_GENERATED_BEFORE_SOURCE")
    result = prior.validate_response(response, _ordinary(context), years, generated_at)
    ordinary_ids = {row["id"] for row in context["evidence"]
        if row.get("period", "") < "2027-01-01"}
    for path in result["years"]["2027"]["shareholder_cash_paths"].values():
        for name, term in path["terms"].items():
            if term["classification"] == "UNKNOWN":
                continue
            if (not set(term["evidence_ids"]) & ordinary_ids
                    or not re.match(r"Mechanism:\s*\S.{12,}", term["rationale"], re.IGNORECASE)):
                raise ValueError("D2_V3_NUMERIC_CASH_HISTORY_AND_MECHANISM_REQUIRED")
            if (name == "target_payout_ratio" and Decimal(term["value"]) == Decimal("0.75")
                    or re.search(r"2024\s*[-－—]\s*2026|75\s*%|issuer.?plan", term["rationale"], re.IGNORECASE)):
                raise ValueError("D2_V3_EXPIRED_PLAN_CANNOT_SET_2027_CASH")
    result = deepcopy(result)
    result.update(schema_version=VERSION, prompt_version=VERSION,
        historical_plan_context=historical, action="no_order", formal_eligibility=False)
    return result

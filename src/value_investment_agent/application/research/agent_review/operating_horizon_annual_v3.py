"""V3 annual D2 evidence contract over the sealed V7 source context.

Historical cost/revenue is counterevidence, never a unit-cost observation or
an adopted forecast. This module does not run a provider or publish facts.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, InvalidOperation
import hashlib

from . import operating_horizon_draft_v2 as prior
from . import operating_draft_v1 as common
from .operating_driver_draft_v2 import _payload, _exact
from ....infrastructure.agent_runtime.provider import LLMResponse

VERSION = "operating-horizon-annual-v3-cost-counterevidence"
PERIODS = (("2024-12-31", "FY"), ("2025-12-31", "FY"),
           ("2025-06-30", "H1"), ("2026-06-30", "H1"))


def cost_counterevidence(context):
    """Require one same-scope, same-period original pair for every period."""
    rows = context["evidence"]
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("V3_EVIDENCE_SCOPE_INVALID")
    result = []
    for period, basis in PERIODS:
        pair = {}
        for field in ("revenue", "cost"):
            matches = [row for row in rows if row.get("period") == period
                       and row.get("field") == field]
            if len(matches) != 1:
                raise ValueError("V3_COST_PAIR_MISSING_OR_DUPLICATE")
            row = matches[0]
            if (row.get("scope") != "consolidated" or row.get("period_basis") != basis
                    or row.get("unit") != "CNY" or not row.get("id")
                    or not row.get("source_id") or not row.get("pdf_sha256")):
                raise ValueError("V3_COST_PAIR_SCOPE_OR_PERIOD_MISMATCH")
            pair[field] = row
        if (pair["revenue"]["source_id"] != pair["cost"]["source_id"]
                or pair["revenue"]["pdf_sha256"] != pair["cost"]["pdf_sha256"]):
            raise ValueError("V3_COST_PAIR_SOURCE_MISMATCH")
        try:
            revenue, cost = (Decimal(pair[key]["value"]) for key in ("revenue", "cost"))
        except (InvalidOperation, KeyError, TypeError) as error:
            raise ValueError("V3_COST_PAIR_VALUE_INVALID") from error
        if not revenue.is_finite() or not cost.is_finite() or revenue <= 0 or cost < 0:
            raise ValueError("V3_COST_PAIR_VALUE_INVALID")
        result.append(dict(period=period, period_basis=basis, scope="consolidated",
                           revenue_cny=str(revenue), cost_cny=str(cost),
                           cost_to_revenue_ratio=str(cost / revenue),
                           revenue_evidence_id=pair["revenue"]["id"],
                           cost_evidence_id=pair["cost"]["id"],
                           interpretation="HISTORICAL_AGGREGATE_RATIO_NOT_UNIT_COST_OR_FORECAST"))
    return result


def build_request(context, years, max_completion_tokens=4096):
    observations = cost_counterevidence(context)
    old = prior.build_request(context, years, max_completion_tokens)
    schema = deepcopy(old.output_schema)
    ids = [row["id"] for row in context["evidence"]]
    declaration = dict(type="object", additionalProperties=False,
        required=["mechanism", "source_anchor_ids", "contrary_evidence_ids", "reopen_condition"],
        properties=dict(
            mechanism={"type": "string", "minLength": 12, "maxLength": 600},
            source_anchor_ids={"type": "array", "minItems": 1, "maxItems": 8,
                               "uniqueItems": True, "items": {"type": "string", "enum": ids}},
            contrary_evidence_ids={"type": "array", "minItems": 1, "maxItems": 8,
                                   "uniqueItems": True, "items": {"type": "string", "enum": ids}},
            reopen_condition={"type": "string", "minLength": 12, "maxLength": 600}))
    for year in schema["properties"]["years"]["properties"].values():
        for path in year["properties"]["operating_paths"]["properties"].values():
            path["required"].append("unit_cost_case")
            path["properties"]["unit_cost_case"] = deepcopy(declaration)
    user = common._canonical(dict(prior_request=old.user,
        historical_cost_counterevidence=observations))
    if len(user) > 76000:
        raise ValueError("V3_ANNUAL_CONTEXT_OVER_BUDGET")
    return replace(old, output_schema=schema, user=user,
        transport_output_contract=old.transport_output_contract +
            " Each path also requires unit_cost_case with exact keys mechanism,source_anchor_ids,contrary_evidence_ids,reopen_condition.",
        system=old.system + " " + VERSION + ": Each scenario's unit_cost_change must declare "
            "a defensible conditional mechanism, original source anchor IDs, contrary evidence IDs, "
            "and an observable re-open condition. Historical FY and H1 cost/revenue ratios are "
            "aggregate counterevidence, not unit costs or a mechanical forecast. Explain why the "
            "conditional range survives contrary FY/H1 observations; do not treat scenario values "
            "as reported facts, prices, approval, or orders.")


def validate_response(response, context, years, generated_at):
    observations = cost_counterevidence(context)
    text = response.text if isinstance(response, LLMResponse) else response
    payload = deepcopy(_payload(text))
    _exact(payload, ("years",))
    _exact(payload["years"], [str(year) for year in years])
    ids = {row["id"] for row in context["evidence"]}
    historical_ids = {item[key] for item in observations
                      for key in ("revenue_evidence_id", "cost_evidence_id")}
    cases = {}
    for year, row in payload["years"].items():
        _exact(row["operating_paths"], ("bear", "base", "bull"))
        cases[year] = {}
        for scenario, path in row["operating_paths"].items():
            case = path.pop("unit_cost_case", None)
            if not isinstance(case, dict):
                raise ValueError("V3_UNIT_COST_CASE_REQUIRED")
            _exact(case, ("mechanism", "source_anchor_ids", "contrary_evidence_ids", "reopen_condition"))
            for key in ("mechanism", "reopen_condition"):
                if not isinstance(case[key], str) or not 12 <= len(case[key].strip()) <= 600:
                    raise ValueError("V3_UNIT_COST_CASE_INCOMPLETE")
            for key in ("source_anchor_ids", "contrary_evidence_ids"):
                refs = case[key]
                if (not isinstance(refs, list) or not 1 <= len(refs) <= 8
                        or any(not isinstance(ref, str) for ref in refs)
                        or len(refs) != len(set(refs)) or not set(refs) <= ids):
                    raise ValueError("V3_UNIT_COST_CASE_CITATION_INVALID")
            if not set(case["contrary_evidence_ids"]) & historical_ids:
                raise ValueError("V3_HISTORICAL_COST_COUNTEREVIDENCE_REQUIRED")
            cases[year][scenario] = case
    forwarded = common._canonical(payload)
    if isinstance(response, LLMResponse):
        forwarded = replace(response, text=forwarded)
    result = prior.validate_response(forwarded, context, years, generated_at)
    result.update(schema_version=VERSION, prompt_version=VERSION,
                  response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  historical_cost_counterevidence=observations,
                  formal_eligibility=False, action="no_order", condition_price=None)
    for year, row in result["years"].items():
        row["unit_cost_cases"] = cases[year]
    return result

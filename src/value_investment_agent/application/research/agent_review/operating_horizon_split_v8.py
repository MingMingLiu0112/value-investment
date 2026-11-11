"""Offline 2027 annual-v3/cash-v3 split contract; no runner or provider calls."""
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib

from . import operating_horizon_annual_v3 as annual
from . import operating_cash_policy_draft_v3 as cash
from . import operating_horizon_draft_v3 as full
from . import operating_draft_v1 as common
from . import operating_task_v2 as task_projection
from .operating_driver_draft_v2 import _exact, _payload
from ....infrastructure.agent_runtime.provider import LLMResponse


VERSION = "operating-horizon-split-v8-2027-expired-plan"


class FullValidatorBlocked(ValueError):
    """A validated split that cannot be promoted through the unchanged full gate."""

    def __init__(self, binding, response_hashes, cash_policy_status, reason):
        super().__init__("V8_FULL_VALIDATOR_REJECTED_REQUIRED_ANNUAL_ANNOTATIONS_FAIL_CLOSED")
        self.binding = deepcopy(binding)
        self.response_hashes = deepcopy(response_hashes)
        self.cash_policy_status = cash_policy_status
        self.full_validator_reason = reason


def _hash(value):
    return hashlib.sha256(common._canonical(value).encode("utf-8")).hexdigest()


def _text(response):
    return response.text if isinstance(response, LLMResponse) else response


def _project(context, source_binding):
    if not isinstance(context, dict) or not isinstance(source_binding, dict) or not source_binding:
        raise ValueError("V8_SOURCE_CONTEXT_OR_BINDING_REQUIRED")
    if "source_binding" in context:
        if context["source_binding"] != source_binding:
            raise ValueError("V8_SOURCE_BINDING_MISMATCH")
        try:
            exact = datetime.fromisoformat(context["as_of"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("V8_EXACT_SOURCE_AS_OF_REQUIRED") from error
        if exact.utcoffset() is None:
            raise ValueError("V8_EXACT_SOURCE_AS_OF_REQUIRED")
        projected = task_projection.research_context(context, drivers=True)
        projected["source_as_of"] = exact.isoformat()
        projected["issuer_dividend_plan"] = deepcopy(context.get("issuer_dividend_plan"))
    else:
        projected = deepcopy(context)
        try:
            exact = datetime.fromisoformat(projected["source_as_of"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("V8_EXACT_SOURCE_AS_OF_REQUIRED") from error
        if exact.utcoffset() is None:
            raise ValueError("V8_EXACT_SOURCE_AS_OF_REQUIRED")
    cash.historical_plan_context(projected, [2027])
    return projected


def _annual_context(projected):
    return {key: deepcopy(value) for key, value in projected.items()
        if key not in {"issuer_dividend_plan", "source_as_of"}}


@dataclass(frozen=True)
class SplitRequests:
    annual: object
    cash: object
    binding: dict


def build_annual_request(context, years, *, source_binding, max_completion_tokens=4096):
    if years != [2027]:
        raise ValueError("V8_EXACT_2027_YEAR_REQUIRED")
    projected = _project(context, source_binding)
    return annual.build_request(_annual_context(projected), years, max_completion_tokens)


def build_requests(context, years, *, source_binding, annual_response,
                   annual_generated_at, max_completion_tokens=4096):
    if years != [2027]:
        raise ValueError("V8_EXACT_2027_YEAR_REQUIRED")
    projected = _project(context, source_binding)
    ordinary = _annual_context(projected)
    annual_request = annual.build_request(ordinary, years, max_completion_tokens)
    annual_result = annual.validate_response(annual_response, ordinary, years, annual_generated_at)
    annual_text = _text(annual_response)
    row = annual_result["years"]["2027"]
    scenarios = {}
    for name in ("bear", "base", "bull"):
        path = row["operating_paths"][name]
        scenarios[name] = dict(drivers=path["drivers"],
            capital_assumptions=path["capital_assumptions"],
            unit_cost_mechanism=row["unit_cost_mechanisms"][name],
            unit_cost_case=row["unit_cost_cases"][name],
            calculated_path=row["calculated_paths"][name])
    summary = dict(year="2027", estimate_kind=row["estimate_kind"],
        baseline_period=row["operating_paths"]["base"]["baseline_period"],
        scenarios=scenarios)
    if len(common._canonical(summary)) > 24000:
        raise ValueError("V8_ANNUAL_SUMMARY_OVER_BUDGET")
    annual_sha = hashlib.sha256(annual_text.encode("utf-8")).hexdigest()
    cash_request = cash.build_request(projected, years, max_completion_tokens)
    attached = common._canonical(dict(validated_same_year_annual_summary=summary,
        annual_response_sha256=annual_sha))
    if len(cash_request.user) + len(attached) > 76000:
        raise ValueError("V8_CASH_INPUT_OVER_BUDGET")
    cash_request = replace(cash_request,
        user=cash_request.user + "\nVALIDATED_2027_ANNUAL_V3=" + attached,
        system=cash_request.system + " Cash values must reconcile to the attached validated "
            "same-year annual scenarios; the annual response hash identifies those exact bytes.")
    binding = dict(version=VERSION, year="2027", action="no_order",
        source_context_sha256=_hash(context), projected_context_sha256=_hash(projected),
        source_binding_sha256=_hash(source_binding),
        issuer_plan_context_sha256=_hash(cash.historical_plan_context(projected, years)),
        annual_request_sha256=_hash(annual_request.__dict__),
        annual_response_sha256=annual_sha, annual_result_sha256=_hash(annual_result),
        validated_annual_summary_sha256=_hash(summary),
        cash_request_sha256=_hash(cash_request.__dict__))
    return SplitRequests(annual_request, cash_request, binding)


def validate_responses(annual_response, cash_response, *, context, years,
                       source_binding, binding, annual_generated_at: datetime,
                       cash_generated_at: datetime):
    requests = build_requests(context, years, source_binding=source_binding,
        annual_response=annual_response, annual_generated_at=annual_generated_at)
    if binding != requests.binding or binding.get("action") != "no_order":
        raise ValueError("V8_SPLIT_SOURCE_REQUEST_OR_ANNUAL_CHANGED")
    if (not isinstance(cash_generated_at, datetime) or cash_generated_at.utcoffset() is None
            or cash_generated_at < annual_generated_at):
        raise ValueError("V8_CASH_GENERATION_ORDER_INVALID")
    if (isinstance(annual_response, LLMResponse) != isinstance(cash_response, LLMResponse)
            or (isinstance(annual_response, LLMResponse)
                and annual_response.model_id != cash_response.model_id)):
        raise ValueError("V8_RESPONSE_MODEL_OR_TYPE_MISMATCH")
    projected = _project(context, source_binding)
    cash_result = cash.validate_response(cash_response, projected, years, cash_generated_at)
    response_hashes = dict(
        annual=hashlib.sha256(_text(annual_response).encode("utf-8")).hexdigest(),
        cash=hashlib.sha256(_text(cash_response).encode("utf-8")).hexdigest())
    annual_payload, cash_payload = _payload(_text(annual_response)), _payload(_text(cash_response))
    _exact(annual_payload, ("years",))
    _exact(annual_payload["years"], ("2027",))
    _exact(cash_payload, ("years",))
    _exact(cash_payload["years"], ("2027",))
    combined = deepcopy(annual_payload)
    combined["years"]["2027"]["shareholder_cash_paths"] = deepcopy(
        cash_payload["years"]["2027"]["shareholder_cash_paths"])
    combined_text = common._canonical(combined)
    try:
        result = full.validate_response(combined_text, _annual_context(projected), years, cash_generated_at)
    except ValueError as error:
        raise FullValidatorBlocked(binding, response_hashes,
            cash_result["cash_policy_appendix_status"], str(error)) from error
    result["split_contract"] = deepcopy(binding)
    result["split_response_sha256"] = response_hashes
    result["cash_policy_v3"] = cash_result
    result["action"] = "no_order"
    result["formal_eligibility"] = False
    return result

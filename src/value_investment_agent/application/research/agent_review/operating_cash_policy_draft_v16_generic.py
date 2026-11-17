"""Plan-optional 2027 cash research from a sealed generic issuer source.

This is a new request/validation contract. Historical V3/V14/V15 tasks keep
requiring their exact 600519 dividend-plan source and remain unchanged.
"""
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from . import operating_cash_policy_draft_v1 as base
from . import operating_horizon_draft_v3 as full
from . import operating_horizon_annual_v3 as annual
from . import operating_draft_v1 as common
from .operating_driver_draft_v2 import _payload, _exact
from . import operating_task_v2 as task

VERSION = "operating-cash-policy-draft-v16-generic-2027"
TERMS = {
    "target_payout_ratio": r"dividend|distribution|分红|派息|利润分配",
    "accessible_profit_ratio": r"parent|母公司|profit|净利润|cash.flow|现金流|CFO",
    "reserve_ratio": r"parent|母公司|profit|净利润|cash|现金|capex|购建",
    "net_maintenance_cash_cny": r"capex|购建|资本|固定资产|cash.flow|现金流",
    "operating_wc_cash_cny": r"working.capital|营运|经营.*现金|应收|存货|应付|CFO",
    "commitment_cash_cny": r"commitment|承诺|合同|在建|投资|购建|capex",
}


def _source(context, source_binding, *, generated_at=None):
    if (not isinstance(source_binding, dict)
            or set(source_binding) != {"path", "sha256"}
            or not isinstance(source_binding["path"], str)
            or not source_binding["path"]
            or "\\" in source_binding["path"]
            or Path(source_binding["path"]).is_absolute()
            or ".." in Path(source_binding["path"]).parts
            or not isinstance(source_binding["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", source_binding["sha256"]) is None):
        raise ValueError("V16_GENERIC_BOUND_SOURCE_REQUIRED")
    if (not isinstance(context, dict)
            or context.get("schema_version") != "operating-horizon-sources-v1"
            or context.get("source_binding") != source_binding
            or context.get("action") != "no_order"
            or context.get("formal_eligibility") is not False
            or not isinstance(context.get("evidence"), list)):
        raise ValueError("V16_GENERIC_BOUND_SOURCE_REQUIRED")
    try:
        cutoff = datetime.fromisoformat(context["as_of"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("V16_GENERIC_SOURCE_TIME_INVALID") from error
    if cutoff.utcoffset() is None or (generated_at is not None and
            (generated_at.utcoffset() is None or generated_at < cutoff)):
        raise ValueError("V16_GENERIC_SOURCE_TIME_INVALID")
    ids = set()
    for row in context["evidence"]:
        try:
            available = datetime.fromisoformat(row["available_at"])
            period = row["period"]
            identifier = row["id"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("V16_GENERIC_EVIDENCE_INVALID") from error
        if (available.utcoffset() is None or available > cutoff
                or period >= "2027-01-01" or identifier in ids):
            raise ValueError("V16_GENERIC_EVIDENCE_UNAVAILABLE_OR_DUPLICATE")
        ids.add(identifier)
    if not ids:
        raise ValueError("V16_GENERIC_EVIDENCE_REQUIRED")
    return task.research_context(context, drivers=True)


def candidates(context, source_binding):
    _source(context, source_binding)
    rows = context["evidence"]
    return {name: [row["id"] for row in rows if re.search(pattern, " ".join(
        str(row.get(key, "")) for key in ("field", "text", "scope")), re.I)]
        for name, pattern in TERMS.items()}


def build_request(context, source_binding, *, max_completion_tokens=4096):
    projected = _source(context, source_binding)
    request = base.build_request(projected, [2027], max_completion_tokens)
    anchors = {name: ids[:8] for name, ids in candidates(context, source_binding).items()}
    appendix = json.dumps(anchors, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(request.user) + len(appendix) > 64000:
        raise ValueError("V16_GENERIC_REQUEST_OVER_BUDGET")
    return replace(request, user=request.user + "\nTERM_HISTORICAL_CANDIDATE_IDS=" + appendix,
        system=request.system + " " + VERSION + ": No issuer dividend plan is assumed. "
        "For every numeric 2027 cash term cite a relevant listed historical candidate ID "
        "and start rationale with 'Mechanism:'. Explain historical period, parent versus "
        "consolidated scope, conditional change and overturn condition. These are forecasts, "
        "never source facts or approved policy. If no defensible bound exists use UNKNOWN/null. "
        "A dividend proposal is not implemented cash; do not infer current approval or a "
        "future payout target. Preserve action=no_order.")


def validate_response(response, context, source_binding, generated_at):
    projected = _source(context, source_binding, generated_at=generated_at)
    result = base.validate_response(response, projected, [2027], generated_at)
    allowed = {name: set(ids) for name, ids in candidates(context, source_binding).items()}
    for path in result["years"]["2027"]["shareholder_cash_paths"].values():
        for name in full.TERMS:
            term = path["terms"][name]
            if term["classification"] == "UNKNOWN":
                continue
            if (term["classification"] != "FORECAST_ASSUMPTION"
                    or not allowed[name].intersection(term["evidence_ids"])
                    or not re.match(r"Mechanism:\s*\S.{12,}", term["rationale"], re.I)):
                raise ValueError("V16_GENERIC_NUMERIC_TERM_LACKS_BOUND_MECHANISM:" + name)
    return {**result, "schema_version": VERSION, "prompt_version": VERSION,
            "source_binding": source_binding, "action": "no_order", "formal_eligibility": False}


def build_staged_cash_request(context, source_binding, annual_response, annual_generated_at):
    """Bind cash research to a validated same-year annual result, without an issuer plan."""
    projected = _source(context, source_binding, generated_at=annual_generated_at)
    annual_result = annual.validate_response(
        annual_response, projected, [2027], annual_generated_at)
    annual_text = annual_response.text if hasattr(annual_response, "text") else annual_response
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
    attached = common._canonical(dict(validated_same_year_annual_summary=summary,
        annual_response_sha256=hashlib.sha256(annual_text.encode("utf-8")).hexdigest()))
    request = build_request(context, source_binding)
    if len(request.user) + len(attached) > 76000:
        raise ValueError("V16_GENERIC_STAGED_REQUEST_OVER_BUDGET")
    request = replace(request,
        user=request.user + "\nVALIDATED_2027_ANNUAL_V3=" + attached,
        system=request.system + " Cash assumptions must reconcile to the attached "
            "validated annual scenarios; the annual hash binds the exact response bytes.")
    digest = lambda value: hashlib.sha256(common._canonical(value).encode("utf-8")).hexdigest()
    binding = dict(version=VERSION, source_context_sha256=digest(context),
        source_binding_sha256=digest(source_binding),
        annual_response_sha256=hashlib.sha256(annual_text.encode("utf-8")).hexdigest(),
        annual_result_sha256=digest(annual_result),
        annual_summary_sha256=digest(summary),
        cash_request_sha256=digest(request.__dict__), action="no_order")
    return request, binding


def validate_staged_responses(annual_response, cash_response, *, context,
                              source_binding, binding, annual_generated_at,
                              cash_generated_at):
    """Replay both source-bound stages; never promote an incomplete cash path."""
    request, expected = build_staged_cash_request(
        context, source_binding, annual_response, annual_generated_at)
    if binding != expected or binding.get("action") != "no_order":
        raise ValueError("V16_GENERIC_STAGE_BINDING_CHANGED")
    if (not isinstance(cash_generated_at, datetime)
            or cash_generated_at.utcoffset() is None
            or cash_generated_at < annual_generated_at):
        raise ValueError("V16_GENERIC_CASH_TIME_INVALID")
    annual_is_packet = hasattr(annual_response, "text")
    if annual_is_packet != hasattr(cash_response, "text") or (annual_is_packet
            and annual_response.model_id != cash_response.model_id):
        raise ValueError("V16_GENERIC_RESPONSE_MODEL_MISMATCH")
    cash = validate_response(cash_response, context, source_binding, cash_generated_at)
    annual_text = annual_response.text if annual_is_packet else annual_response
    cash_text = cash_response.text if annual_is_packet else cash_response
    annual_payload, cash_payload = _payload(annual_text), _payload(cash_text)
    _exact(annual_payload, ("years",))
    _exact(cash_payload, ("years",))
    _exact(annual_payload["years"], ("2027",))
    _exact(cash_payload["years"], ("2027",))
    combined = json.loads(common._canonical(annual_payload))
    for path in combined["years"]["2027"]["operating_paths"].values():
        path.pop("unit_cost_case")
    combined["years"]["2027"]["shareholder_cash_paths"] = (
        cash_payload["years"]["2027"]["shareholder_cash_paths"])
    if cash["cash_policy_appendix_status"] != "COMPLETE_UNAPPROVED":
        return dict(status="WAITING_EVIDENCE", reason="CASH_POLICY_INCOMPLETE",
            cash_policy_status=cash["cash_policy_appendix_status"],
            stage_binding=binding, annual_result_sha256=binding["annual_result_sha256"],
            cash_result=cash, action="no_order", formal_eligibility=False)
    try:
        result = full.validate_response(common._canonical(combined),
            _source(context, source_binding, generated_at=cash_generated_at),
            [2027], cash_generated_at)
    except ValueError as error:
        return dict(status="WAITING_EVIDENCE", reason="FULL_VALIDATOR_REJECTED",
            full_validator_reason=str(error), stage_binding=binding,
            cash_result=cash, action="no_order", formal_eligibility=False)
    result.update(stage_binding=binding, cash_policy_result=cash,
        split_contract=binding,
        split_response_sha256={"annual": hashlib.sha256(annual_text.encode("utf-8")).hexdigest(),
            "cash": hashlib.sha256(cash_text.encode("utf-8")).hexdigest()},
        cash_request_sha256=binding["cash_request_sha256"],
        action="no_order", formal_eligibility=False)
    return result

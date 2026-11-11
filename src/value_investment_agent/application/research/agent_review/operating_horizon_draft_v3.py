"""D2 annual operating scenarios with an explicit, source-bound cash-policy appendix.

This is deliberately a new contract.  V1/V2 annual research remains readable,
but it cannot silently become shareholder cash or an E2 valuation input because
it did not ask for distribution, maintenance, working-capital and commitment
terms.  The appendix is still an unapproved forecast assumption, never a fact,
approval or order.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

from . import operating_horizon_draft_v2 as prior
from . import operating_draft_v1 as common
from . import operating_driver_draft_v2 as driver_contract
from . import dividend_policy_anchor_v1
from . import parent_cash_conversion_anchor_v1
from .operating_driver_draft_v2 import _payload, _exact
from ....domain.research import operating_driver_bridge_v1 as bridge
from ....infrastructure.agent_runtime.provider import LLMResponse


VERSION = "operating-horizon-draft-v3-cash-policy"
PROMPT_VERSION = "operating-horizon-prompts-v3-cash-policy"
SCENARIOS = ("bear", "base", "bull")
RATIO_TERMS = ("target_payout_ratio", "accessible_profit_ratio", "reserve_ratio")
CASH_TERMS = ("net_maintenance_cash_cny", "operating_wc_cash_cny", "commitment_cash_cny")
TERMS = RATIO_TERMS + CASH_TERMS


def _term_schema(*, unit, evidence_ids):
    return dict(type="object", additionalProperties=False,
        required=["classification", "value", "unit", "rationale", "evidence_ids"],
        properties=dict(
            classification={"type": "string", "enum": ["FORECAST_ASSUMPTION", "UNKNOWN"]},
            value={"type": ["string", "null"]},
            unit={"type": "string", "enum": [unit, "not_quantified"]},
            rationale={"type": "string", "minLength": 1, "maxLength": 240},
            evidence_ids={"type": "array", "minItems": 1, "maxItems": 8,
                          "items": {"type": "string", "enum": sorted(evidence_ids)}}))


def _cash_path_schema(*, evidence_ids):
    properties = {name: _term_schema(unit="ratio", evidence_ids=evidence_ids) for name in RATIO_TERMS}
    properties.update({name: _term_schema(unit="CNY", evidence_ids=evidence_ids) for name in CASH_TERMS})
    return dict(type="object", additionalProperties=False, required=list(TERMS) + ["counter_evidence", "reopen_condition"],
        properties={**properties,
            "counter_evidence": {"type": "string", "minLength": 1, "maxLength": 600},
            "reopen_condition": {"type": "string", "minLength": 1, "maxLength": 600}})


def build_request(context, years, max_completion_tokens=4096):
    request = prior.build_request(context, years, max_completion_tokens)
    dividend_anchor = dividend_policy_anchor_v1.disclosed_per_share_growth_anchor(context)
    parent_cash_anchor = parent_cash_conversion_anchor_v1.historical_parent_cash_conversion(context)
    ids = common._context(driver_contract.legacy_context(context))
    schema = deepcopy(request.output_schema)
    for row in schema["properties"]["years"]["properties"].values():
        row["required"].append("shareholder_cash_paths")
        row["properties"]["shareholder_cash_paths"] = dict(type="object", additionalProperties=False,
            required=list(SCENARIOS), properties={name: _cash_path_schema(evidence_ids=ids) for name in SCENARIOS})
    transport = request.transport_output_contract + "; shareholder_cash_paths exact keys bear,base,bull. " + \
        "Each cash path contains target_payout_ratio,accessible_profit_ratio,reserve_ratio," + \
        "net_maintenance_cash_cny,operating_wc_cash_cny,commitment_cash_cny,counter_evidence,reopen_condition. " + \
        "Every term is FORECAST_ASSUMPTION with decimal-string value and its schema unit: use literal ratio for target_payout_ratio,accessible_profit_ratio,reserve_ratio; use literal CNY for net_maintenance_cash_cny,operating_wc_cash_cny,commitment_cash_cny; or UNKNOWN with value:null/unit:not_quantified."
    system = request.system + " " + PROMPT_VERSION + ": Add a distinct shareholder-cash policy appendix to every scenario. " + \
        "Do not default any missing term to zero, one, or historical payout. Each term must cite supplied evidence " + \
        "as an anchor but remains a forecast assumption. UNKNOWN is preferred to invented precision. Do not convert " + \
        "group cash to parent distributable cash; do not turn this appendix into a valuation, BUY or approval. " + \
        "JSON placement is mandatory: shareholder_cash_paths belongs inside each years.<year> object, never beside it. " + \
        "Every cash term must contain exactly classification,value,unit,rationale,evidence_ids. Use classification=" + \
        "FORECAST_ASSUMPTION or UNKNOWN; never use status. Do not invent alternative unit labels such as ratio_of_parent_net_income. UNKNOWN must still include a non-empty rationale and supplied evidence_ids."
    if dividend_anchor is not None:
        system += (" A disclosed per-share dividend plan is supplied as a conditional anchor. "
                   "Use it to reason about target payout only if share count and forecast parent earnings "
                   "can be reconciled; it does not prove parent cash access, maintenance cash, WC or commitments. "
                   "Do not copy its growth ratio into target_payout_ratio.")
    if parent_cash_anchor is not None:
        system += (" A same-original historical parent-profit/CFO/capex bridge is supplied. "
                   "Use it only to explain historical cash conversion and frame uncertain future "
                   "maintenance, working-capital and funding-access sensitivities. It is not "
                   "distributable parent cash or a proven forecast conversion ratio. Disclosed "
                   "unpaid commitments have unknown payment years: do not assign annual cash "
                   "amounts or double-count them against a cash floor without a reasoned schedule.")
    user = request.user + ("\nSOURCE_BOUND_DIVIDEND_POLICY_ANCHOR=" +
        json.dumps(dividend_anchor, sort_keys=True, ensure_ascii=False) if dividend_anchor else "") + (
        "\nSOURCE_BOUND_HISTORICAL_PARENT_CASH_BRIDGE=" +
        json.dumps(parent_cash_anchor, sort_keys=True, ensure_ascii=False) if parent_cash_anchor else "")
    return replace(request, output_schema=schema, transport_output_contract=transport,
        system=system, user=user)


def _term(value, *, unit, ids):
    _exact(value, ("classification", "value", "unit", "rationale", "evidence_ids"))
    common._text(value["rationale"], 240)
    prior.prior._citations(value["evidence_ids"], ids)
    if value["classification"] == "UNKNOWN":
        if value["value"] is not None or value["unit"] != "not_quantified":
            raise ValueError("UNKNOWN_CASH_POLICY_TERM_MUST_REMAIN_NULL")
        return deepcopy(value)
    if value["classification"] != "FORECAST_ASSUMPTION" or value["unit"] != unit:
        raise ValueError("CASH_POLICY_TERM_CLASSIFICATION_OR_UNIT_INVALID")
    numeric = bridge._num(value["value"])
    if (unit == "ratio" and not (0 <= numeric <= 1)) or (unit == "CNY" and numeric < 0):
        raise ValueError("CASH_POLICY_TERM_VALUE_OUT_OF_RANGE")
    return deepcopy(value)


def _cash_paths(paths, *, ids):
    _exact(paths, SCENARIOS)
    result = {}
    for scenario, path in paths.items():
        _exact(path, list(TERMS) + ["counter_evidence", "reopen_condition"])
        common._text(path["counter_evidence"])
        common._text(path["reopen_condition"])
        terms = {}
        unknown = False
        for name in RATIO_TERMS:
            terms[name] = _term(path[name], unit="ratio", ids=ids)
            unknown = unknown or terms[name]["classification"] == "UNKNOWN"
        for name in CASH_TERMS:
            terms[name] = _term(path[name], unit="CNY", ids=ids)
            unknown = unknown or terms[name]["classification"] == "UNKNOWN"
        result[scenario] = dict(terms=terms, complete=not unknown,
            counter_evidence=path["counter_evidence"], reopen_condition=path["reopen_condition"])
    return result


def _normalize_single_year_cash_transport(payload, years):
    """Repair one unambiguous provider transport placement before validation.

    Some OpenAI-compatible gateways have returned ``shareholder_cash_paths``
    beside the single year key inside ``years`` despite the generated JSON
    schema placing it inside that year.  This is not a semantic repair: it is
    accepted only for exactly one requested year, exactly one misplaced field,
    and a year object which otherwise omits that required field.  All evidence,
    units, ranges and cash-policy checks still run through the normal strict
    validator below.  Multi-year or otherwise ambiguous responses fail closed.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("years"), dict):
        return payload
    expected = [str(year) for year in years]
    observed = payload["years"]
    if (len(expected) != 1 or not isinstance(observed.get(expected[0]), dict)
            or "shareholder_cash_paths" in observed[expected[0]]):
        return payload
    if set(payload) == {"years", "shareholder_cash_paths"} and set(observed) == {expected[0]}:
        normalized = deepcopy(payload)
        normalized["years"][expected[0]]["shareholder_cash_paths"] = normalized.pop(
            "shareholder_cash_paths")
        return normalized
    if set(payload) != {"years"} or set(observed) != {expected[0], "shareholder_cash_paths"}:
        return payload
    normalized = deepcopy(payload)
    normalized["years"][expected[0]]["shareholder_cash_paths"] = normalized["years"].pop(
        "shareholder_cash_paths")
    return normalized


def validate_response(response, context, years, generated_at):
    text = response.text if isinstance(response, LLMResponse) else response
    payload = _normalize_single_year_cash_transport(_payload(text), years)
    _exact(payload, ("years",))
    _exact(payload["years"], [str(year) for year in years])
    ids = common._context(driver_contract.legacy_context(context))
    cash = {}
    sanitized = deepcopy(payload)
    for year, row in payload["years"].items():
        _exact(row, ("estimate_kind", "operating_paths", "shareholder_cash_paths", "counter_evidence", "reopen_condition"))
        cash[year] = _cash_paths(row["shareholder_cash_paths"], ids=ids)
        del sanitized["years"][year]["shareholder_cash_paths"]
    forwarded = replace(response, text=common._canonical(sanitized)) if isinstance(response, LLMResponse) else common._canonical(sanitized)
    result = prior.validate_response(forwarded, context, years, generated_at)
    for year, row in result["years"].items():
        row["shareholder_cash_paths"] = cash[year]
    complete = all(path["complete"] for row in cash.values() for path in row.values())
    result.update(schema_version=VERSION, prompt_version=PROMPT_VERSION,
        response_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        cash_policy_appendix_status=("COMPLETE_UNAPPROVED" if complete else "INCOMPLETE_UNKNOWN_TERMS"),
        status=("ANNUAL_OPERATING_AND_CASH_POLICY_SUPPLEMENT_REQUIRES_INDEPENDENT_REVIEW" if complete
                else "ANNUAL_OPERATING_SUPPLEMENT_CASH_POLICY_INCOMPLETE"),
        valuation_produced=False, main_range_adopted=False, action="no_order", formal_eligibility=False)
    return result

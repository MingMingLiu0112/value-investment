"""Pure staged D2 request and merge contract; no provider or publication path."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from .direct_owner_cash_agent_draft_v1 import (DRIVERS, HORIZON, POLICY,
    SCENARIOS, TERMINAL_POLICY, VERSION as DRAFT_VERSION, _explanation)
from .direct_owner_cash_agent_facts_v1 import read_parent_cash_agent_facts
from .direct_owner_cash_agent_request_v1 import _term_schema, _unique
from ...infrastructure.agent_runtime.provider import LLMRequest, LLMResponse

VERSION = "direct-owner-cash-staged-v2"
STAGES = ("operating", "policy", "terminal")
FIELDS = {"operating": frozenset(DRIVERS), "policy": POLICY}


def _text(value):
    if not isinstance(value, str) or len(value.strip()) < 12:
        raise ValueError("PARENT_V2_EXPLANATION_REQUIRED")


def _prose(value):
    """Canonicalize only explicit, nonempty prose lists; never infer content."""
    if isinstance(value, list):
        if not 1 <= len(value) <= 8:
            raise ValueError("PARENT_V2_EXPLANATION_REQUIRED")
        for item in value:
            _text(item)
        value = "\n".join(value)
    _text(value)
    return value


def _term(value, anchors, count, *, years=None):
    if isinstance(value, dict) and isinstance(value.get("values"), dict) and years is not None:
        expected = [str(year) for year in years]
        raw_values = value["values"]
        if set(raw_values) != set(expected) or len(raw_values) != count:
            raise ValueError("PARENT_V2_VALUES_REQUIRED")
        value["values"] = [raw_values[year] for year in expected]
    _explanation(value, anchors)
    if not isinstance(value["values"], list) or len(value["values"]) != count:
        raise ValueError("PARENT_V2_VALUES_REQUIRED")
    for raw in value["values"]:
        if not isinstance(raw, str):
            raise ValueError("PARENT_V2_DECIMAL_STRING_REQUIRED")
        try:
            if not Decimal(raw).is_finite():
                raise ValueError("PARENT_V2_FINITE_REQUIRED")
        except InvalidOperation as error:
            raise ValueError("PARENT_V2_DECIMAL_INVALID") from error


def staged_parent_cash_request(*, root: Path, spec_binding: dict, scenario: str,
                               stage: str, generated_at: datetime,
                               prior_drafts: dict | None = None,
                               verified_context: dict | None = None,
                               max_completion_tokens: int = 4096) -> LLMRequest:
    if scenario not in SCENARIOS or stage not in STAGES or not 1024 <= max_completion_tokens <= 8192:
        raise ValueError("PARENT_V2_REQUEST_INVALID")
    # The task service may pass a context reopened and verified once for this
    # read/drive operation. Public standalone callers still reopen originals.
    context = (verified_context if verified_context is not None else
               read_parent_cash_agent_facts(root=root, spec_binding=spec_binding, now=generated_at))
    years = list(range(int(context["valuation_date"][:4]) + 1,
                       int(context["valuation_date"][:4]) + HORIZON + 1))
    ids = sorted(context["facts"])
    prior = prior_drafts or {}
    required_prior = (set() if stage == "operating" else {"operating"}
                      if stage == "policy" else {"operating", "policy"})
    if set(prior) != required_prior:
        raise ValueError("PARENT_V2_PRIOR_STAGE_REQUIRED")
    for name in required_prior:
        expected = FIELDS[name]
        row = prior[name]
        if (not isinstance(row, dict) or row.get("years") != years
                or not isinstance(row.get("series"), dict)
                or set(row["series"]) != expected):
            raise ValueError("PARENT_V2_PRIOR_STAGE_INVALID")
        for term in row["series"].values():
            _term(term, set(ids), HORIZON)
    # Pass only numeric assumptions from earlier stages. Model prose is not
    # promoted into a later instruction or factual source.
    prior_values = {name: {field: row["values"] for field, row in prior[name]["series"].items()}
                    for name in required_prior}
    string = dict(type="string", minLength=12)
    if stage != "terminal":
        fields = sorted(FIELDS[stage])
        properties = {"years": dict(type="array", minItems=HORIZON, maxItems=HORIZON,
                                     items=dict(type="integer")),
                      "series": dict(type="object", additionalProperties=False,
                                     required=fields,
                                     properties={key: _term_schema(ids, HORIZON) for key in fields})}
        if stage == "operating":
            properties["annual_notes"] = dict(type="array", minItems=HORIZON,
                                               maxItems=HORIZON, items=string)
    else:
        fields = sorted(TERMINAL_POLICY)
        properties = {"terminal": dict(type="object", additionalProperties=False,
            required=["policy", "remaining_scheduled_events", "max_transition_years",
                      "financing", "rationale", "counter_evidence", "reopen_condition"],
            properties={"policy": dict(type="object", additionalProperties=False,
                required=fields, properties={key: _term_schema(ids, 1) for key in fields}),
                "remaining_scheduled_events": dict(type="array", items=dict(type="object")),
                "max_transition_years": dict(type="integer", minimum=1, maximum=100),
                "financing": dict(type=["object", "null"]),
                "rationale": string, "counter_evidence": string, "reopen_condition": string}),
            "cost_of_equity": _term_schema(ids, 1)}
    if stage == "operating":
        properties.update({key: string for key in ("rationale", "counter_evidence", "reopen_condition")})
    schema = dict(type="object", additionalProperties=False,
                  required=sorted(properties), properties=properties)
    source_context = {key: value for key, value in context.items()
                      if key not in {"action", "formal_eligibility"}}
    user = json.dumps(dict(source_context=source_context, scenario=scenario, stage=stage,
        required_years=years, required_fields=fields,
        prior_forecast_assumptions_not_facts=prior_values), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"))
    if len(user.encode("utf-8")) > 64000:
        raise ValueError("PARENT_V2_CONTEXT_OVER_BUDGET")
    return LLMRequest(role="FUNDAMENTAL", system=(
        "Return only the requested JSON fields. Use exact field names and explicit decimal "
        "strings for every value. evidence_anchors must be an array of exact source_context.facts "
        "KEYS such as ['revenue','cost']; never put a fact description, URL, PDF page, "
        "hash or source sentence in evidence_anchors. Put explanations in mechanism. "
        "counter_evidence, rationale and reopen_condition must each be one JSON STRING, "
        "not a list. Each evidence_anchors list must contain 1 to 8 distinct allowed IDs. Forecasts are "
        "conditional assumptions, never an order or approval. Prior stage values are "
        "unapproved forecast assumptions, not verified facts. Keep operating_cash "
        "distinct from the required other_operating_cash component. Consume scheduled events "
        "explicitly in the terminal policy and explain any remaining events."),
        user=user, output_schema=schema, max_completion_tokens=max_completion_tokens,
        transport_output_contract=("Return one JSON object with exactly these keys: "
            + ", ".join(sorted(properties)) + ". series/policy keys exactly: "
            + ", ".join(fields) + ". Each term has values, evidence_anchors, "
            "mechanism, counter_evidence, reopen_condition. Years must equal required_years; "
            "no aliases, missing keys, defaults, or identity metadata in response. "
            "Allowed evidence_anchors IDs only: " + ", ".join(ids) + ". "
            "Each values field is a JSON ARRAY, not a year-keyed object. "
            "For operating stage annual_notes is a JSON ARRAY of exactly ten strings "
            "in required_years order, never an object keyed by year."))


def parse_staged_parent_cash_response(response: LLMResponse, *, request: LLMRequest,
                                      source_fingerprint: str) -> dict:
    """Validate against a sealed request; caller retains response.text unchanged."""
    if response.tool_calls:
        raise ValueError("PARENT_V2_TOOL_CALL_FORBIDDEN")
    packet = json.loads(request.user)
    if packet["source_context"]["input_fingerprint"] != source_fingerprint:
        raise ValueError("PARENT_V2_SOURCE_BINDING_INVALID")
    try:
        value = json.loads(response.text, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("PARENT_V2_NONFINITE_JSON")))
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("PARENT_V2_INVALID_JSON") from error
    if not isinstance(value, dict) or set(value) != set(request.output_schema["required"]):
        raise ValueError("PARENT_V2_FIELDS_INVALID")
    anchors = set(packet["source_context"]["facts"])
    stage = packet["stage"]
    # JSON-object transport can represent multiple prose points as a list.
    # Preserve each written point in order; do not synthesize a missing reason.
    if stage != "terminal":
        if not isinstance(value["series"], dict):
            raise ValueError("PARENT_V2_FIELDS_INVALID")
        prose_rows = [value, *value["series"].values()]
    else:
        terminal_row = value["terminal"]
        if (not isinstance(terminal_row, dict) or
                not isinstance(terminal_row.get("policy"), dict)):
            raise ValueError("PARENT_V2_TERMINAL_INVALID")
        prose_rows = [terminal_row, *terminal_row["policy"].values(),
                      value["cost_of_equity"]]
    for row in prose_rows:
        if not isinstance(row, dict):
            raise ValueError("PARENT_V2_FIELDS_INVALID")
        for key in ("mechanism", "counter_evidence", "reopen_condition", "rationale"):
            if key in row:
                row[key] = _prose(row[key])
    if stage != "terminal":
        if value["years"] != packet["required_years"] or set(value["series"]) != set(packet["required_fields"]):
            raise ValueError("PARENT_V2_YEARS_OR_SERIES_INVALID")
        for term in value["series"].values():
            _term(term, anchors, HORIZON, years=packet["required_years"])
        if stage == "operating":
            notes = value["annual_notes"]
            # Some JSON-object providers preserve the ten notes under exact
            # year keys. This is a lossless structural representation only
            # when every requested year occurs once and no other key exists.
            # The sealed raw response remains unchanged in the task store.
            if isinstance(notes, dict):
                expected = [str(year) for year in packet["required_years"]]
                if set(notes) != set(expected) or len(notes) != HORIZON:
                    raise ValueError("PARENT_V2_NOTES_INVALID")
                notes = [notes[year] for year in expected]
                value["annual_notes"] = notes
            if not isinstance(notes, list) or len(notes) != HORIZON:
                raise ValueError("PARENT_V2_NOTES_INVALID")
            for note in notes:
                _text(note)
            for key in ("rationale", "counter_evidence", "reopen_condition"):
                _text(value[key])
    else:
        terminal = value["terminal"]
        if not isinstance(terminal, dict) or set(terminal) != set(request.output_schema["properties"]["terminal"]["required"]):
            raise ValueError("PARENT_V2_TERMINAL_INVALID")
        if not isinstance(terminal["policy"], dict) or set(terminal["policy"]) != set(packet["required_fields"]):
            raise ValueError("PARENT_V2_TERMINAL_POLICY_INVALID")
        for term in terminal["policy"].values():
            _term(term, anchors, 1)
        _term(value["cost_of_equity"], anchors, 1)
        if (not isinstance(terminal["remaining_scheduled_events"], list)
                or type(terminal["max_transition_years"]) is not int
                or not 1 <= terminal["max_transition_years"] <= 100
                or terminal["financing"] is not None and not isinstance(terminal["financing"], dict)):
            raise ValueError("PARENT_V2_TERMINAL_SHAPE_INVALID")
        for key in ("rationale", "counter_evidence", "reopen_condition"):
            _text(terminal[key])
    return value


def merge_staged_parent_cash(*, scenario: str, source_fingerprint: str,
                             requests: dict, responses: dict) -> dict:
    if scenario not in SCENARIOS or set(requests) != set(STAGES) or set(responses) != set(STAGES):
        raise ValueError("PARENT_V2_STAGES_INCOMPLETE")
    parsed = {}
    for stage in STAGES:
        packet = json.loads(requests[stage].user)
        if packet["scenario"] != scenario or packet["stage"] != stage:
            raise ValueError("PARENT_V2_REQUEST_BINDING_INVALID")
        parsed[stage] = parse_staged_parent_cash_response(responses[stage],
            request=requests[stage], source_fingerprint=source_fingerprint)
    if parsed["operating"]["years"] != parsed["policy"]["years"]:
        raise ValueError("PARENT_V2_YEAR_MISMATCH")
    series = {**parsed["operating"]["series"], **parsed["policy"]["series"]}
    if len(series) != len(FIELDS["operating"]) + len(FIELDS["policy"]):
        raise ValueError("PARENT_V2_SERIES_OVERLAP")
    return dict(schema_version=DRAFT_VERSION, scenario=scenario,
        source_fingerprint=source_fingerprint, years=parsed["operating"]["years"],
        annual_notes=parsed["operating"]["annual_notes"], series=series,
        terminal=parsed["terminal"]["terminal"],
        cost_of_equity=parsed["terminal"]["cost_of_equity"],
        rationale=parsed["operating"]["rationale"],
        counter_evidence=parsed["operating"]["counter_evidence"],
        reopen_condition=parsed["operating"]["reopen_condition"])

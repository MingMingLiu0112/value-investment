"""Source-only parent cash request; provider output remains an unapproved draft."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from .direct_owner_cash_agent_draft_v1 import (
    HORIZON, POLICY, SCENARIOS, SERIES, TERMINAL_POLICY, VERSION,
)
from .direct_owner_cash_agent_facts_v1 import read_parent_cash_agent_facts
from ...infrastructure.agent_runtime.provider import LLMRequest, LLMResponse


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("PARENT_DRAFT_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _term_schema(ids, count):
    return dict(type="object", additionalProperties=False,
                required=["values", "evidence_anchors", "mechanism",
                          "counter_evidence", "reopen_condition"],
                properties=dict(
                    values=dict(type="array", minItems=count, maxItems=count,
                                items=dict(type="string")),
                    evidence_anchors=dict(type="array", minItems=1, maxItems=8,
                                          uniqueItems=True,
                                          items=dict(type="string", enum=ids)),
                    mechanism=dict(type="string", minLength=12),
                    counter_evidence=dict(type="string", minLength=12),
                    reopen_condition=dict(type="string", minLength=12)))


def parent_cash_request(*, root: Path, spec_binding: dict, scenario: str,
                        generated_at: datetime, max_completion_tokens: int = 8192) -> LLMRequest:
    """Use only independently reopened facts; old manual scenarios never enter the prompt."""
    if scenario not in SCENARIOS or not 1024 <= max_completion_tokens <= 16384:
        raise ValueError("PARENT_DRAFT_REQUEST_BOUNDS_INVALID")
    context = read_parent_cash_agent_facts(root=root, spec_binding=spec_binding,
                                           now=generated_at)
    ids = sorted(context["facts"])
    annual_term, terminal_term = _term_schema(ids, HORIZON), _term_schema(ids, 1)
    string = dict(type="string", minLength=12)
    terminal = dict(type="object", additionalProperties=False,
                    required=["policy", "remaining_scheduled_events",
                              "max_transition_years", "financing", "rationale",
                              "counter_evidence", "reopen_condition"],
                    properties=dict(
                        policy=dict(type="object", additionalProperties=False,
                                    required=sorted(TERMINAL_POLICY),
                                    properties={key: terminal_term for key in TERMINAL_POLICY}),
                        remaining_scheduled_events=dict(type="array", items=dict(type="object")),
                        max_transition_years=dict(type="integer", minimum=1, maximum=100),
                        financing=dict(type=["object", "null"]),
                        rationale=string, counter_evidence=string, reopen_condition=string))
    schema = dict(type="object", additionalProperties=False,
                  required=["schema_version", "scenario", "source_fingerprint",
                            "years", "annual_notes", "series", "terminal",
                            "cost_of_equity", "rationale", "counter_evidence",
                            "reopen_condition"],
                  properties=dict(
                      schema_version=dict(type="string", const=VERSION),
                      scenario=dict(type="string", const=scenario),
                      source_fingerprint=dict(type="string", const=context["input_fingerprint"]),
                      years=dict(type="array", minItems=HORIZON, maxItems=HORIZON,
                                 items=dict(type="integer")),
                      annual_notes=dict(type="array", minItems=HORIZON, maxItems=HORIZON,
                                        items=string),
                      series=dict(type="object", additionalProperties=False,
                                  required=sorted(SERIES),
                                  properties={key: annual_term for key in SERIES}),
                      terminal=terminal, cost_of_equity=terminal_term,
                      rationale=string, counter_evidence=string, reopen_condition=string))
    context = {key: value for key, value in context.items()
               if key not in {"action", "formal_eligibility"}}
    user = json.dumps(dict(scenario=scenario,
                           schema_version=VERSION,
                           source_fingerprint=context["input_fingerprint"],
                           source_context=context,
                           required_years=list(range(int(context["valuation_date"][:4]) + 1,
                                                     int(context["valuation_date"][:4]) + HORIZON + 1)),
                           annual_fields=sorted(SERIES), terminal_fields=sorted(TERMINAL_POLICY)),
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(user.encode("utf-8")) > 64000:
        raise ValueError("PARENT_DRAFT_CONTEXT_OVER_BUDGET")
    transport = (f"Return one JSON object; schema_version must be exactly '{VERSION}'. "
        "scenario and source_fingerprint must equal the values supplied in the user message. "
        "Do not invent or rename contract identifiers. Fields: "
        "years, annual_notes, series, terminal, cost_of_equity, rationale, "
        "counter_evidence, reopen_condition. years has exactly ten consecutive years; "
        "annual_notes has ten explanations. series has exactly the annual_fields listed "
        "in the user message. Each series term has values (ten decimal strings), "
        "evidence_anchors (existing fact IDs), mechanism, counter_evidence, "
        "reopen_condition. terminal has policy with exactly terminal_fields, each "
        "using the same term shape but one decimal string, plus "
        "remaining_scheduled_events (array), max_transition_years (integer), "
        "financing (object or null), rationale, counter_evidence, reopen_condition. "
        "cost_of_equity is one-value term. Every rationale, counter_evidence, "
        "reopen_condition and mechanism must be a substantive string of at least "
        "12 characters; none may be null, empty or a numeric value. "
        "No extra keys, unknown source IDs or approvals.")
    return LLMRequest(role="FUNDAMENTAL", system=(
        "Research one conditional parent-company shareholder cash scenario. "
        "Use only the provided verified facts and cite existing fact IDs. "
        f"Forecast values are assumptions, not facts. Schema version is exactly {VERSION}. "
        "Return all named fields with substantive explanations. "
        "Do not copy a prior valuation, infer missing refinancing as assured, "
        "treat consolidated cash as parent cash, or issue an order or approval. "
        "For unsupported inputs, report uncertainty in rationale; never fabricate evidence."),
        user=user, output_schema=schema,
        max_completion_tokens=max_completion_tokens,
        transport_output_contract=transport)


def parse_parent_cash_response(response: LLMResponse, *, scenario: str,
                               source_fingerprint: str) -> dict:
    if response.tool_calls or scenario not in SCENARIOS:
        raise ValueError("PARENT_DRAFT_UNAUTHORIZED_TOOL_OR_SCENARIO")
    try:
        draft = json.loads(response.text, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               ValueError("PARENT_DRAFT_NONFINITE_JSON")))
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("PARENT_DRAFT_INVALID_JSON") from error
    if (not isinstance(draft, dict) or draft.get("scenario") != scenario
            or draft.get("schema_version") != VERSION
            or draft.get("source_fingerprint") != source_fingerprint):
        raise ValueError("PARENT_DRAFT_RESPONSE_BINDING_INVALID")
    return draft

"""Replay V25 annual responses with a narrowly bounded citation transcription fix."""
from dataclasses import replace
from datetime import datetime
import re

from . import operating_horizon_task_v25_canonical as v25
from .operating_cash_policy_draft_v16_generic import _source
from .operating_horizon_native_transport_v2 import _json, _payload
from .task_execution_v1 import _bytes, _hash


PREFIX = "operating-statement:"
VERSION = "v25-annual-citation-transcription-v1"


def replay_annual_citation_transcription(service, task_id):
    """Return a separately bound research draft; leave the original task immutable."""
    _, receipt = prepare_transcribed_annual(service, task_id)
    return receipt


def prepare_transcribed_annual(service, task_id):
    spec, state, pin = service._load(task_id)
    if (
        spec["task_contract"] != v25.CONTRACT
        or state["status"] != "FAILED"
        or state["error_code"] != "V25_BULL_RESPONSE_REJECTED"
        or state["stage_validated"] != ["bear", "base"]
        or set(state["stage_responses"]) != set(v25.SCENARIOS)
        or set(state["stage_intents"]) != set(v25.SCENARIOS)
    ):
        raise ValueError("V25_TRANSCRIPTION_ORIGINAL_STAGE_UNSUPPORTED")
    context = service._context(spec)
    projected = _source(context, spec["source_binding"])
    responses = {}
    bindings = {}
    for scenario in v25.SCENARIOS:
        packet = service._packet(spec, state, scenario)
        request, _ = service._request_for_stage(spec, state, context, scenario)
        if packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V25_TRANSCRIPTION_REQUEST_CHANGED")
        response = v25.LLMResponse(**packet["response"])
        service._usage(response, request, spec["config"]["model_id"])
        service._verify_stage_settlement(spec, state, scenario, packet)
        responses[scenario] = response
        bindings[scenario] = state["stage_responses"][scenario]
    generated = service._annual_generated_at(spec, state)
    try:
        v25.assemble_annual(responses, projected, generated)
    except ValueError as error:
        if str(error) != "UNKNOWN_MISSING_DUPLICATE_HORIZON_CITATION":
            raise
    else:
        raise ValueError("V25_TRANSCRIPTION_ORIGINAL_DID_NOT_FAIL")

    source_by_id = {row["id"]: row for row in projected["evidence"]}
    bull = _payload(responses["bull"].text)
    matches = [row for row in bull["drivers"] if row["driver_id"] == "unit_cost_change"]
    if len(matches) != 1:
        raise ValueError("V25_TRANSCRIPTION_UNIT_COST_ROW_AMBIGUOUS")
    anchors = matches[0]["baseline_anchor_ids"]
    invalid = [(i, ref) for i, ref in enumerate(anchors) if ref not in source_by_id]
    if len(invalid) != 1 or len(anchors) < 2:
        raise ValueError("V25_TRANSCRIPTION_CITATION_SCOPE_UNSUPPORTED")
    index, original = invalid[0]
    if not re.fullmatch(PREFIX + r"[a-f0-9]{65}", original):
        raise ValueError("V25_TRANSCRIPTION_REQUIRES_ONE_EXTRA_HEX_CHARACTER")
    digest = original[len(PREFIX):]
    candidates = {PREFIX + digest[:i] + digest[i + 1:] for i in range(len(digest))}
    matched = candidates & source_by_id.keys()
    if len(matched) != 1:
        raise ValueError("V25_TRANSCRIPTION_CITATION_NOT_UNIQUE")
    replacement = next(iter(matched))
    source = source_by_id[replacement]
    if (source.get("field") != "cost" or source.get("scope") != "consolidated"
            or source.get("unit") != "CNY" or replacement in anchors
            or datetime.fromisoformat(source["available_at"]) > generated):
        raise ValueError("V25_TRANSCRIPTION_CITATION_NOT_APPLICABLE")
    anchors[index] = replacement
    bull_text = _json(bull)
    responses["bull"] = replace(responses["bull"], text=bull_text)
    annual_response, verified = v25.assemble_annual(responses, projected, generated)
    from .operating_cash_request_compact import build_compact_cash_request
    cash_request, cash_binding = build_compact_cash_request(
        context, spec["source_binding"], annual_response, generated)
    return cash_request, {
        "next_cash_request_sha256": _hash(_bytes(cash_request.__dict__)),
        "next_cash_binding": cash_binding,
        "version": VERSION, "task_id": task_id, "source_binding": spec["source_binding"],
        "original_state_binding": pin, "original_response_bindings": bindings,
        "edited_field": f"bull.unit_cost_change.baseline_anchor_ids[{index}]",
        "original_citation": original, "replayed_citation": replacement,
        "replayed_bull_sha256": _hash(bull_text.encode("utf-8")),
        "annual_response_sha256": _hash(annual_response.text.encode("utf-8")),
        "annual_draft": verified, "formal_eligibility": False, "action": "no_order",
    }

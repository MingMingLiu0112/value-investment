"""Recover a single extra closing brace without discarding JSON data."""
from json import JSONDecoder, JSONDecodeError


def remove_single_extra_object_close(text: str) -> str:
    """Only accept an intact first object followed by exactly one extra brace."""
    candidate = text.lstrip()
    decoder = JSONDecoder()
    try:
        value, end = decoder.raw_decode(candidate)
    except JSONDecodeError as error:
        raise ValueError("CASH_JSON_NO_COMPLETE_INITIAL_OBJECT") from error
    if not isinstance(value, dict) or candidate[end:].strip() != "}":
        raise ValueError("CASH_JSON_TRAILING_DATA_NOT_SINGLE_OBJECT_CLOSE")
    # Return the untouched object text. The consumer's strict schema parser
    # still checks duplicate keys, invalid constants and all economic terms.
    return candidate[:end]


def replay_guided_cash_diagnostic(service, task_id):
    """Reverify a sealed cash response and preserve partial results as diagnostics."""
    from datetime import datetime

    from .operating_cash_policy_draft_v16_generic import validate_response
    from .operating_cash_term_evidence import build_term_guided_cash_request
    from .operating_horizon_v25_citation_transcription import prepare_transcribed_annual
    from .operating_task_v2 import LiveOperatingTaskService
    from .task_execution_v1 import _bytes, _hash
    from ...product.common import require_inside
    from ....infrastructure.agent_runtime.provider import LLMResponse

    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        original, receipt = prepare_transcribed_annual(service, task_id)
        context = service._context(spec)
    request = build_term_guided_cash_request(original, context, spec["source_binding"])
    directory = service._directory(task_id) / "cash-term-guided-v1"
    pins = {name: service._binding(directory / (name + ".json"))
            for name in ("intent", "response", "result")}
    intent, packet, result = (service._bound(pins[name]) for name in pins)
    lineage = intent["lineage"]
    if (head != receipt["original_state_binding"]
            or lineage["source_task_id"] != task_id
            or lineage["source_task_state"] != head
            or lineage["source_binding"] != spec["source_binding"]
            or lineage["annual_stage_responses"] != receipt["original_response_bindings"]
            or lineage["transcription_receipt_sha256"] != _hash(_bytes(receipt))
            or lineage["guided_request_sha256"] != _hash(_bytes(request.__dict__))
            or packet["intent_binding"] != pins["intent"] or result["response_binding"] != pins["response"]
            or any(item.get("action") != "no_order" for item in (intent, packet, result))
            or result.get("formal_eligibility") is not False
            or result["status"] != "FAILED_CASH_RESPONSE_REJECTED"):
        raise ValueError("CASH_DIAGNOSTIC_LINEAGE_MISMATCH")
    prior_dir = service._directory(task_id) / "cash-continuation-v1"
    if lineage["prior_attempt"] != {name: service._binding(prior_dir / (name + ".json"))
                                  for name in ("intent", "response", "result")}:
        raise ValueError("CASH_DIAGNOSTIC_PRIOR_ATTEMPT_CHANGED")
    response = LLMResponse(**packet["response"])
    config = spec["config"]
    service._usage(response, request, config["model_id"])
    cost = str(service._cost(response.prompt_tokens, response.completion_tokens, config))
    if result["settled_cost"] != cost:
        raise ValueError("CASH_DIAGNOSTIC_SETTLEMENT_MISMATCH")
    ledger = LiveOperatingTaskService(service.root if service.test_provider else service.shared_budget_root)
    day = require_inside(ledger.base, ledger.base / "budget" / intent["budget_day"], "cash diagnostic budget")
    import json
    with ledger._lock(day):
        budget_pin = json.loads((day / "current.json").read_bytes())
        paid = ledger._bound(budget_pin)["records"].get(intent["reservation"])
        if paid != {"status": "SETTLED", "cost": cost}:
            raise ValueError("CASH_DIAGNOSTIC_SETTLEMENT_MISMATCH")
    corrected = remove_single_extra_object_close(response.text)
    generated = datetime.fromisoformat(packet["generated_at"])
    diagnostic = validate_response(corrected, context, spec["source_binding"], generated)
    scenarios = diagnostic["years"]["2027"]["shareholder_cash_paths"]
    from ..operating_horizon_cash_policy_e2_v17 import missing_cash_constraint_citations
    quantified = {name: {"terms": {key: term for key, term in path["terms"].items()
                                   if term["classification"] == "FORECAST_ASSUMPTION"}}
                  for name, path in scenarios.items()}
    missing_anchors = missing_cash_constraint_citations({"2027": quantified}, context)
    return {
        "version": "guided-cash-diagnostic-v1", "task_id": task_id,
        "original_task_status": state["status"], "original_cash_status": result["status"],
        "source_binding": spec["source_binding"], "run_pins": pins,
        "economic_status": diagnostic["cash_policy_appendix_status"],
        "unknown_terms": {name: [key for key, value in path["terms"].items()
                                 if value["classification"] == "UNKNOWN"]
                          for name, path in scenarios.items()},
        "missing_e2_anchors": missing_anchors,
        "observed_cost_cny": cost, "normalized_response_sha256": _hash(corrected.encode("utf-8")),
        "e2_eligible": False, "formal_eligibility": False, "action": "no_order",
    }

"""Execute one bounded cash follow-up from a verified V25 checkpoint."""

import json
from decimal import Decimal
from zoneinfo import ZoneInfo

from .operating_cash_policy_draft_v16_generic import validate_response
from .operating_task_v2 import LiveOperatingTaskService
from ....infrastructure.agent_runtime.provider import LLMResponse
from .operating_cash_request_compact import prepare_cash_only_continuation
from .task_execution_v1 import _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes


def run_cash_only_continuation(service, task_id):
    """Persist an intent before sending and never automatically resend it."""
    request, lineage = prepare_cash_only_continuation(service, task_id)
    return _run_prepared_cash(service, task_id, request, lineage)


def run_transcribed_cash_continuation(service, task_id):
    """Spend one cash call after replaying and verifying the repaired annual draft."""
    from .operating_horizon_v25_citation_transcription import prepare_transcribed_annual

    with service._lock(service._directory(task_id)):
        request, receipt = prepare_transcribed_annual(service, task_id)
    lineage = {
        **receipt["next_cash_binding"],
        "source_task_id": task_id,
        "source_task_state": receipt["original_state_binding"],
        "source_binding": receipt["source_binding"],
        "annual_stage_responses": receipt["original_response_bindings"],
        "transcription_receipt_sha256": _hash(_bytes(receipt)),
    }
    return _run_prepared_cash(service, task_id, request, lineage)


def run_term_guided_cash_continuation(service, task_id):
    """One new request after a completed cash failure, with both attempts retained."""
    from .operating_cash_term_evidence import build_term_guided_cash_request
    from .operating_horizon_v25_citation_transcription import prepare_transcribed_annual

    with service._lock(service._directory(task_id)):
        original, receipt = prepare_transcribed_annual(service, task_id)
        spec, _, record = service._load(task_id)
    if record != receipt["original_state_binding"]:
        raise ValueError("CASH_CONTINUATION_TASK_CHANGED")
    prior = service._directory(task_id) / "cash-continuation-v1"
    intent_pin = service._binding(prior / "intent.json")
    response_pin = service._binding(prior / "response.json")
    result_pin = service._binding(prior / "result.json")
    intent, packet, result = (service._bound(pin) for pin in (intent_pin, response_pin, result_pin))
    lineage = intent["lineage"]
    if (lineage["source_task_id"] != task_id or lineage["source_task_state"] != record
            or lineage["cash_request_sha256"] != receipt["next_cash_binding"]["cash_request_sha256"]
            or lineage["transcription_receipt_sha256"] != _hash(_bytes(receipt))
            or packet["intent_binding"] != intent_pin or result["response_binding"] != response_pin
            or any(item["action"] != "no_order" for item in (intent, packet, result))
            or result["formal_eligibility"] is not False
            or result["status"] not in {"FAILED_CASH_RESPONSE_REJECTED", "CASH_POLICY_INCOMPLETE_UNKNOWN_TERMS"}):
        raise ValueError("CASH_GUIDE_PRIOR_ATTEMPT_UNSUPPORTED")
    old_response = LLMResponse(**packet["response"])
    cfg = spec["config"]
    service._usage(old_response, original, cfg["model_id"])
    old_cost = service._cost(old_response.prompt_tokens, old_response.completion_tokens, cfg)
    if str(old_cost) != result["settled_cost"]:
        raise ValueError("CASH_GUIDE_PRIOR_COST_MISMATCH")
    ledger = LiveOperatingTaskService(service.root if service.test_provider else service.shared_budget_root)
    day = require_inside(ledger.base, ledger.base / "budget" / intent["budget_day"], "cash budget")
    with ledger._lock(day):
        head = json.loads((day / "current.json").read_bytes())
        paid = ledger._bound(head)["records"].get(intent["reservation"])
        if paid != {"status": "SETTLED", "cost": str(old_cost)}:
            raise ValueError("CASH_GUIDE_PRIOR_SETTLEMENT_NOT_VERIFIED")
    context = service._context(spec)
    request = build_term_guided_cash_request(original, context, spec["source_binding"])
    request_hash = _hash(_bytes(request.__dict__))
    if request_hash == receipt["next_cash_request_sha256"]:
        raise ValueError("CASH_GUIDE_REQUEST_UNCHANGED")
    return _run_prepared_cash(service, task_id, request, {
        **lineage,
        "prior_attempt": {"intent": intent_pin, "response": response_pin, "result": result_pin},
        "guided_request_sha256": request_hash,
    }, attempt="cash-term-guided-v1", prior_cost=old_cost)


def _run_prepared_cash(service, task_id, request, lineage, *,
                       attempt="cash-continuation-v1", prior_cost=Decimal(0)):
    spec, state, record = service._load(task_id)
    if (record != lineage["source_task_state"]
            or "cash" in state["stage_intents"] or "cash" in state["stage_responses"]
            or state.get("cash_binding") is not None):
        raise ValueError("CASH_CONTINUATION_TASK_CHANGED")
    cfg = spec["config"]
    if service.test_provider is None and cfg["model_id"] != "deepseek-flash":
        raise PermissionError("V25_EXACT_MODEL_REQUIRED")
    provider = service._provider(spec)
    context = service._context(spec)
    directory = require_inside(service.base, service._directory(task_id) / attempt,
                               "cash continuation")
    reserve = service._cost(len(_bytes(request.__dict__)) + 4096,
                            request.max_completion_tokens, cfg)
    if Decimal(state["settled_cost"]) + prior_cost + reserve > Decimal(str(cfg["max_run_cost"])):
        raise ValueError("V25_RUN_BUDGET_EXHAUSTED")

    with service._lock(directory, "execution"):
        intent_path = directory / "intent.json"
        if intent_path.exists():
            raise ValueError("CASH_CONTINUATION_ALREADY_ATTEMPTED")
        now = _now()
        day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        reservation = _hash(_bytes([attempt, task_id, record]))
        service._daily_budget(day, reservation, reserve, cfg)
        intent = {"lineage": lineage, "budget_day": day, "reservation": reservation,
                  "reserved_cost": str(reserve), "created_at": now.isoformat(), "action": "no_order"}
        write_new_bytes(intent_path, _bytes(intent))
        response = provider.complete(request)
        generated = _now()
        response_path = directory / "response.json"
        write_new_bytes(response_path, _bytes({
            "intent_binding": service._binding(intent_path), "generated_at": generated.isoformat(),
            "response": response.__dict__, "action": "no_order",
        }))
        service._usage(response, request, cfg["model_id"])
        cost = service._cost(response.prompt_tokens, response.completion_tokens, cfg)
        service._daily_budget(day, reservation, cost, cfg, settle=True)
        result = {"response_binding": service._binding(response_path), "settled_cost": str(cost),
                  "economic_review": None, "formal_eligibility": False, "action": "no_order"}
        try:
            result["economic_review"] = validate_response(
                response, context, spec["source_binding"], generated)
            result["status"] = result["economic_review"]["status"]
        except ValueError as error:
            result.update(status="FAILED_CASH_RESPONSE_REJECTED", reason=str(error))
        write_new_bytes(directory / "result.json", _bytes(result))
        return result

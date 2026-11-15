"""Execute one bounded cash follow-up from a verified V25 checkpoint."""

from decimal import Decimal
from zoneinfo import ZoneInfo

from .operating_cash_policy_draft_v16_generic import validate_response
from .operating_cash_request_compact import prepare_cash_only_continuation
from .task_execution_v1 import _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes


def run_cash_only_continuation(service, task_id):
    """Persist an intent before sending and never automatically resend it."""
    request, lineage = prepare_cash_only_continuation(service, task_id)
    spec, state, record = service._load(task_id)
    if record != lineage["source_task_state"]:
        raise ValueError("CASH_CONTINUATION_TASK_CHANGED")
    cfg = spec["config"]
    if service.test_provider is None and cfg["model_id"] != "deepseek-flash":
        raise PermissionError("V25_EXACT_MODEL_REQUIRED")
    provider = service._provider(spec)
    context = service._context(spec)
    # One continuation per terminal task, even across dates or prompt revisions.
    directory = require_inside(service.base, service._directory(task_id) / "cash-continuation-v1",
                               "cash continuation")
    reserve = service._cost(len(_bytes(request.__dict__)) + 4096,
                            request.max_completion_tokens, cfg)
    if Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"])):
        raise ValueError("V25_RUN_BUDGET_EXHAUSTED")

    with service._lock(directory, "execution"):
        intent_path = directory / "intent.json"
        if intent_path.exists():
            raise ValueError("CASH_CONTINUATION_ALREADY_ATTEMPTED")
        now = _now()
        day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        reservation = _hash(_bytes(["cash-continuation-v1", task_id, record]))
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

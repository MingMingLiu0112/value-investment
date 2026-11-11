"""Read-only V12 annual checkpoint admission for V13 cash preparation.

This adapter creates no V13 task or annual response. A caller must persist a
separate V13 lineage and settle its own cash budget before any provider call.
"""
from datetime import datetime
from pathlib import Path

from . import operating_horizon_task_v12_live as v12
from . import operating_horizon_request_v13 as request_v13
from .task_execution_v1 import _bytes, _hash
from ....infrastructure.agent_runtime.provider import LLMResponse

VERSION = "operating-horizon-carryover-v13-from-v12"


def prepare_cash(root, task_id, *, expected_source_binding, expected_context_sha256,
                 expected_annual_response_sha256, expected_budget_day):
    """Verify a sealed V12 annual stage and return a V13 cash input and lineage.

    All expected values must come from the caller's independent admission pin.
    No disk writes, budget reservations, or model calls occur here.
    """
    service = v12.OperatingHorizonTaskService(root)
    spec, state, head = service._load(task_id)
    if (spec["mode"] != "LIVE_OPERATING" or spec["years"] != [2027]
            or spec["source_binding"] != expected_source_binding
            or spec["context_sha256"] != expected_context_sha256
            or state.get("action") != "no_order"
            or "annual" not in state["stage_validated"]
            or state.get("new_llm_calls", 0) < 1):
        raise ValueError("V13_CARRYOVER_SOURCE_MISMATCH")
    context = service._context(spec)
    result = service._verify_annual_checkpoint(spec, state, context)
    packet = service._packet(spec, state, "annual")
    response_pin = state["stage_responses"]["annual"]
    response_bytes = (service.root / response_pin["path"]).read_bytes()
    if _hash(response_bytes) != response_pin["sha256"]:
        raise ValueError("V13_CARRYOVER_RESPONSE_BYTES_CHANGED")
    response = LLMResponse(**packet["response"])
    response_hash = _hash(response.text.encode("utf-8"))
    intent = state["stage_intents"]["annual"]
    settlement = state["reservations"][intent["reservation"]]
    if (response_hash != expected_annual_response_sha256
            or settlement["budget_day"] != expected_budget_day
            or settlement["status"] != "SETTLED"
            or packet["request_sha256"] != spec["annual_request_sha256"]):
        raise ValueError("V13_CARRYOVER_ANNUAL_OR_BUDGET_MISMATCH")
    cash_request, cash_binding = request_v13.build_cash_request(
        context, [2027], source_binding=spec["source_binding"],
        annual_response=response,
        annual_generated_at=datetime.fromisoformat(packet["generated_at"]))
    lineage = dict(version=VERSION, action="no_order", source_task_id=task_id,
        source_contract=v12.CONTRACT, source_record_binding=head,
        source_input_sha256=_hash((service._directory(task_id) / "input.json").read_bytes()),
        source_binding=spec["source_binding"], source_context_sha256=spec["context_sha256"],
        source_annual_request_sha256=packet["request_sha256"],
        source_annual_response_binding=response_pin,
        source_annual_response_sha256=response_hash,
        source_annual_generated_at=packet["generated_at"],
        source_annual_result_sha256=_hash(_bytes(result)),
        source_budget_day=settlement["budget_day"],
        source_budget_reservation=intent["reservation"],
        source_budget_actual_cost=settlement["actual_cost"],
        v13_cash_binding=cash_binding,
        v13_cash_request_sha256=_hash(_bytes(cash_request.__dict__)))
    return cash_request, lineage

"""Read-only, fail-closed V16 failed-annual admission for a V17 cash task."""

from datetime import datetime

from . import operating_horizon_task_v16_live as v16
from . import operating_horizon_split_v13 as split
from . import operating_horizon_annual_response_repair_v1 as repair
from .task_execution_v1 import _bytes, _hash
from ....infrastructure.agent_runtime.provider import LLMResponse

def replay(source_service, source_task_id):
    """Return verified source context, packet and normalized annual text."""
    if (not isinstance(source_task_id, str) or not source_task_id.startswith("rt-")
            or not isinstance(source_service, v16.OperatingHorizonTaskService)):
        raise ValueError("V17_EXACT_V16_SOURCE_REQUIRED")
    spec, state, pin = source_service._load(source_task_id)
    if (spec.get("task_contract") != v16.CONTRACT or spec.get("years") != [2027]
            or state.get("status") != "FAILED"
            or state.get("error_code") != "V16_ANNUAL_RESPONSE_REJECTED"
            or set(state.get("stage_intents", {})) != {"annual"}
            or set(state.get("stage_responses", {})) != {"annual"}
            or state.get("stage_validated") != []
            or state.get("provider_requests") != 1):
        raise ValueError("V17_SOURCE_STATE_INVALID")
    if spec.get("source_loader_binding") != source_service._loader_binding():
        raise ValueError("V17_SOURCE_LOADER_CHANGED")
    context = source_service._context(spec)
    packet = source_service._packet(spec, state, "annual")
    if packet is None:
        raise ValueError("V17_SOURCE_PACKET_MISSING")
    request, _ = source_service._request_for_stage(spec, state, context, "annual")
    if (packet["request_sha256"] != spec["annual_request_sha256"]
            or packet["request_sha256"] != _hash(_bytes(request.__dict__))):
        raise ValueError("V17_SOURCE_REQUEST_CHANGED")
    source_service._usage(LLMResponse(**packet["response"]), request, spec["config"]["model_id"])
    source_service._verify_stage_settlement(spec, state, "annual", packet)
    generated_at = datetime.fromisoformat(packet["generated_at"])
    normalized = repair.normalize_response(packet["response"]["text"],
        split._annual_context(split._project(context, spec["source_binding"])),
        [2027], generated_at)
    # The validated annual hash must refer to the derived text, never the raw packet.
    if normalized["validated_result"]["response_sha256"] != normalized["derived_sha256"]:
        raise ValueError("V17_NORMALIZATION_BINDING_INVALID")
    lineage = dict(version="V17_FAILED_V16_ANNUAL_REPAIR", action="no_order",
        source_task_id=source_task_id, source_contract=v16.CONTRACT,
        source_record_binding=pin, source_binding=spec["source_binding"],
        source_loader_binding=spec["source_loader_binding"],
        source_context_sha256=spec["context_sha256"],
        source_request_sha256=spec["annual_request_sha256"],
        source_implementation_sha256=spec["implementation_sha256"],
        source_packet_binding=state["stage_responses"]["annual"],
        source_budget_day=state["reservations"][state["stage_intents"]["annual"]["reservation"]]["budget_day"],
        normalization={key: normalized[key] for key in ("version", "raw_sha256", "derived_sha256", "relocations")})
    return context, packet, normalized, lineage

"""Cold-read a V12 annual checkpoint and locally settled V14 cash for E2."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .operating_horizon_cash_policy_e2_v2 import _read_bound_cash_policy_e2_input
from .agent_review.operating_horizon_task_v14_live import CONTRACT, OperatingHorizonTaskService

VERSION = "operating-horizon-cash-policy-e2-input-v6"


def read_v14_cash_policy_e2_input(root: Path, task_id: str,
                                  now: datetime, service=None) -> dict:
    service = service or OperatingHorizonTaskService(root)
    task = service.read(task_id)
    if (task.get("workflow") != CONTRACT or task.get("status") != "SUCCEEDED"
            or task.get("annual_status") != "IMPORTED_V12"
            or task.get("cash_status") != "SETTLED_VALIDATED"
            or task.get("action") != "no_order" or task.get("formal_eligibility") is not False
            or set(task.get("stage_responses", {})) != {"cash"}):
        raise ValueError("V14_E2_IMPORTED_TASK_REQUIRED")
    spec, state, _ = service._load(task_id)
    request, lineage, context, annual_packet = service._imported(spec)
    cash_packet = service._packet(spec, state, "cash")
    research = task.get("research_result")
    if (not isinstance(research, dict)
            or research.get("cash_policy_v14", {}).get("cash_policy_appendix_status")
                != "COMPLETE_UNAPPROVED"
            or research.get("cash_policy_v14", {}).get("action") != "no_order"
            or lineage != spec.get("imported_annual")
            or state.get("stage_responses") != task["stage_responses"]
            or state.get("stage_validated") != ["annual", "cash"]
            or request.max_completion_tokens != spec["config"]["max_completion_tokens_cap"]
            or lineage.get("source_annual_response_binding") is None
            or lineage.get("source_context_sha256") != spec.get("context_sha256")
            or context.get("symbol") != task.get("symbol")):
        raise ValueError("V14_E2_IMPORTED_PINS_INVALID")
    hashes = research.get("split_response_sha256", {})
    if (not isinstance(hashes, dict) or set(hashes) != {"annual", "cash"}
            or any(hashes[stage] != hashlib.sha256(packet["response"]["text"].encode("utf-8")).hexdigest()
                   for stage, packet in (("annual", annual_packet), ("cash", cash_packet)))):
        raise ValueError("V14_E2_RESPONSE_HASH_CHANGED")

    # Normalize only the verified external annual checkpoint for the existing
    # E2 economics gate. No task or source record is written or relabeled.
    annual_pin = deepcopy(lineage["source_annual_response_binding"])
    task_view = deepcopy(task)
    task_view["annual_status"] = "SETTLED_VALIDATED"
    task_view["stage_responses"] = {"annual": annual_pin, "cash": deepcopy(task["stage_responses"]["cash"])}
    spec_view = {**spec, "context_fingerprint": context["snapshot_fingerprint"]}
    state_view = {**state, "stage_responses": deepcopy(task_view["stage_responses"])}

    class Replay:
        def read(self, candidate):
            if candidate != task_id:
                raise ValueError("V14_E2_TASK_CHANGED")
            return deepcopy(task_view)

        def _load(self, candidate):
            if candidate != task_id:
                raise ValueError("V14_E2_TASK_CHANGED")
            return spec_view, state_view, None

        def _context(self, _):
            return service._context(spec)

        def _packet(self, _, __, stage):
            return annual_packet if stage == "annual" else service._packet(spec, state, stage)

    result = _read_bound_cash_policy_e2_input(root=root, task_id=task_id, now=now,
        contract=CONTRACT, task_service=OperatingHorizonTaskService,
        version=VERSION, label="V14", service=Replay())
    manifest = result["input_manifest"]
    manifest["imported_annual"] = deepcopy(lineage)
    result["annual_operating_status"] = "VERIFIED_V12_ANNUAL_COMPILED"
    result["input_fingerprint"] = hashlib.sha256(json.dumps(manifest, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return result

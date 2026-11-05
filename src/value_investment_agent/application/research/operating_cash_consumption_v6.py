"""Read terminal failed repair status without revalidating it as research."""
from datetime import datetime
import hashlib
import json
from . import operating_cash_consumption_v2 as base
from . import operating_cash_consumption_v5 as full
from .agent_review import operating_horizon_task_v3 as repair


def read_operating_cash_consumption(*, root, task, now):
    service = repair.OperatingHorizonTaskService(root)
    directory = service._directory(repair.SINGLE_TASK_ID)
    if not (directory / "input.json").exists():
        return full.read_operating_cash_consumption(root=root, task=task, now=now)
    with service._lock(directory):
        spec, state, pin = service._load(repair.SINGLE_TASK_ID)
    if spec["symbol"] != task["symbol"] or state["status"] not in {"FAILED", "CANCELLED"}:
        return full.read_operating_cash_consumption(root=root, task=task, now=now)
    if now.utcoffset() is None:
        raise ValueError("AWARE_SUPPLEMENT_CUTOFF_REQUIRED")
    for value in (spec["created_at"], spec["repair_requested_at"], state["updated_at"]):
        date = datetime.fromisoformat(value)
        if date.utcoffset() is None or date > now:
            raise ValueError("HORIZON_TASK_AFTER_CONSUMPTION_CUTOFF")
    result = base.read_operating_cash_consumption(root=root, task=task, now=now)
    supplement = dict(status=state["status"], task_id=spec["task_id"],
        reason=state.get("error_code"), research_as_of=spec["created_at"],
        repair_requested_at=spec["repair_requested_at"], repair_of=spec["repair_of"],
        record_binding=pin, source_binding=spec["source_binding"],
        source_status="NOT_REPLAYED_FOR_FAILED_TASK_NO_RESEARCH_ACCEPTED",
        execution_mode=spec["mode"], years={}, action="no_order", formal_eligibility=False,
        cash_model_ready=False, condition_price=None)
    result["annual_research_supplement"] = supplement
    result["preceding_consumption_fingerprint"] = result.get("consumption_fingerprint")
    result["consumption_fingerprint"] = hashlib.sha256(json.dumps(
        {"prior":result["preceding_consumption_fingerprint"],"supplement":supplement},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return result

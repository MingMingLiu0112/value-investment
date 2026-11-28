"""Seal and cold-replay a successful native note-grid V3 terminal continuation."""
from hashlib import sha256
from pathlib import Path

from . import parent_note_grid_task_receipt_v2 as v2
from . import parent_note_grid_task_receipt_v1 as v1
from .parent_cash_task_receipt_v3 import _completion
from .direct_owner_cash_research_v1 import _bytes, _read, _write
from ..product.common import require_inside

SCHEMA = "parent-note-grid-task-receipt-v3"


def _implementations():
    from . import parent_note_grid_terminal_service_v3 as terminal
    return {**v2._implementations(), **terminal.implementation(),
            __name__: sha256(Path(__file__).read_bytes()).hexdigest()}


def execute(*, root, task_id, task_head, case_package_binding, distribution_binding, now):
    root = Path(root).resolve()
    from . import parent_note_grid_terminal_service_v3 as terminal
    service = terminal.ParentCashService(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = _completion(spec, state, head, task_head, now)
        if (spec.get(v1.MARKER) != v1.VERSION or spec.get("terminal_response_wire") != terminal.WIRE
                or case_package_binding != spec.get("case_package_binding") or not distribution_binding
                or distribution_binding != spec.get("implemented_distribution_receipt_binding")):
            raise ValueError("NOTE_GRID_V3_TERMINAL_RECEIPT_INPUT_MISMATCH")
        if v2.terminal._base_financing_unverified(spec):
            raise ValueError(v2.terminal.BASE_BLOCKER)
        v2._settled_responses(service, spec, state)
        candidate = v2._reopen_candidate(service, spec, state, completed)
    provenance = dict(task_id=task_id, task_record_binding=head, task_input_sha256=state["input_sha256"],
        completed_at=completed.isoformat(), spec_binding=spec["spec_binding"], source_adapter_version=v1.VERSION,
        source_fingerprint=candidate["source_fingerprint"], task_implementation_sha256=spec["implementation_sha256"],
        case_package_binding=case_package_binding, distribution_receipt_binding=distribution_binding,
        response_bindings=state["responses"], scenario_draft_sha256=candidate["scenario_draft_sha256"],
        task_receipt_schema=SCHEMA, terminal_response_wire=terminal.WIRE, seed=spec["seed"])
    return v2._value_candidate(root, candidate, case_package_binding, task_id, head, completed, provenance)


def build(*, root, output_dir, now, **inputs):
    root = Path(root).resolve()
    output = require_inside(root / "runtime", Path(output_dir).resolve(), "note-grid V3 receipt")
    if output.exists():
        raise FileExistsError("PARENT_TASK_NEW_OUTPUT_REQUIRED")
    result = execute(root=root, now=now, **inputs)
    result_binding = _write(root, output / "result.json", result)
    return _write(root, output / "receipt.json", dict(schema_version=SCHEMA, inputs=inputs,
        result_binding=result_binding, implementation_sha256=_implementations(), action="no_order", formal_eligibility=False))


def replay(*, root, receipt_binding, now):
    root = Path(root).resolve()
    receipt = _read(root, receipt_binding)
    if receipt.get("schema_version") != SCHEMA:
        return v2.replay(root=root, receipt_binding=receipt_binding, now=now)
    if (receipt.get("implementation_sha256") != _implementations() or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False):
        raise ValueError("NOTE_GRID_V3_RECEIPT_IMPLEMENTATION_CHANGED")
    stored = _read(root, receipt["result_binding"])
    current = execute(root=root, now=now, **receipt["inputs"])
    if _bytes(current) != _bytes(stored):
        raise ValueError("NOTE_GRID_V3_RECEIPT_COLD_REPLAY_CHANGED")
    return current

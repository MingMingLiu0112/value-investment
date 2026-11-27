"""Seal and reopen an exact live note-grid task using the existing valuation adapter."""
from pathlib import Path

from . import parent_cash_corrected_receipt_v1 as previous
from . import parent_cash_task_receipt_v3 as legacy
from .parent_note_grid_case_v1 import package_candidate, run_registered_research
from .parent_note_grid_task_service_v1 import ParentCashService, MARKER, VERSION, implementation

SCHEMA = "parent-note-grid-task-receipt-v1"


def _implementations():
    return {**previous._implementations(), **implementation(),
            __name__: legacy.sha256(Path(__file__).read_bytes()).hexdigest()}


def execute(*, root, task_id, task_head, case_package_binding, distribution_binding, now):
    root = Path(root).resolve()
    service = ParentCashService(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = legacy._completion(spec, state, head, task_head, now)
        if (spec.get(MARKER) != VERSION or spec.get("case_package_binding") != case_package_binding or not distribution_binding
                or spec.get("implemented_distribution_receipt_binding") != distribution_binding):
            raise ValueError("NOTE_GRID_RECEIPT_TASK_OR_DISTRIBUTION_MISMATCH")
        drafts = service._drafts(spec, state, completed)
        candidate = service._assemble(spec, drafts, completed)
    provenance = dict(task_id=task_id, task_record_binding=head, task_input_sha256=state["input_sha256"],
        completed_at=completed.isoformat(), spec_binding=spec["spec_binding"], source_adapter_version=VERSION,
        source_fingerprint=candidate["source_fingerprint"], task_implementation_sha256=spec["implementation_sha256"],
        case_package_binding=case_package_binding, distribution_receipt_binding=distribution_binding,
        response_bindings=state["responses"], scenario_draft_sha256=candidate["scenario_draft_sha256"])
    compiled = candidate["compiled"]
    package = package_candidate(root, candidate, case_package_binding, task_id, head, completed, provenance, SCHEMA)
    package["source_contract"]["distribution_receipt_binding"] = distribution_binding
    outcome, descriptor = run_registered_research(root, package, completed)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("NOTE_GRID_CONDITIONAL_VALUATION_REQUIRED")
    valuation = legacy.json.loads(outcome.valuation.to_json())
    if valuation["assumptions"]["scenario_calculations"] != {
            name: row["calculation"] for name, row in compiled["scenarios"].items()}:
        raise ValueError("NOTE_GRID_SCENARIO_CONSUMPTION_MISMATCH")
    return dict(symbol=package["symbol"], action="no_order", formal_eligibility=False, main_range_adopted=False,
                adoptable_valuation=False, provenance=provenance, source_bindings=compiled["source_bindings"],
                annual_payout_reservations=compiled["annual_payout_reservations"],
                input_descriptor_sha256=descriptor.input_sha256, descriptor=descriptor.as_policy(), valuation=valuation)


def build(*, root, output_dir, now, **inputs):
    root = Path(root).resolve()
    output = legacy.require_inside(root / "runtime", Path(output_dir).resolve(), "note-grid valuation receipt")
    if output.exists():
        raise FileExistsError("PARENT_TASK_NEW_OUTPUT_REQUIRED")
    result = execute(root=root, now=now, **inputs)
    binding = legacy._write(root, output / "result.json", result)
    return legacy._write(root, output / "receipt.json", dict(schema_version=SCHEMA, inputs=inputs,
        result_binding=binding, implementation_sha256=_implementations(), action="no_order", formal_eligibility=False))


def replay(*, root, receipt_binding, now):
    root = Path(root).resolve()
    receipt = legacy._read(root, receipt_binding)
    if receipt.get("schema_version") != SCHEMA:
        return previous.replay(root=root, receipt_binding=receipt_binding, now=now)
    if (receipt.get("implementation_sha256") != _implementations() or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False):
        raise ValueError("NOTE_GRID_RECEIPT_IMPLEMENTATION_CHANGED")
    stored = legacy._read(root, receipt["result_binding"])
    result = execute(root=root, now=now, **receipt["inputs"])
    if legacy._bytes(result) != legacy._bytes(stored):
        raise ValueError("NOTE_GRID_RECEIPT_COLD_REPLAY_CHANGED")
    return result

"""Cold replay and conditional publication of a corrected Bear continuation."""
from pathlib import Path

from . import parent_cash_task_distribution_receipt_v1 as distribution
from . import parent_cash_task_receipt_v3 as legacy
from .parent_cash_corrected_continuation_v1 import ContinuationService, MARKER

RECEIPT_SCHEMA = "parent-cash-task-backed-receipt-v3-corrected-policy-v1"


def _implementations():
    names = ("parent_cash_corrected_continuation_v1.py", "parent_cash_corrected_receipt_v1.py",
             "parent_cash_policy_correction_v1.py")
    return {**distribution.implementations(), **{
        f"application/research/{name}": legacy.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in names}}


def execute(*, root, task_id, task_head, case_package_binding, distribution_binding, now):
    root = Path(root).resolve()
    service = ContinuationService(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = legacy._completion(spec, state, head, task_head, now)
        if MARKER not in spec or spec.get("implemented_distribution_receipt_binding") != distribution_binding:
            raise ValueError("PARENT_CORRECTED_DISTRIBUTION_BINDING_CHANGED")
        drafts = service._drafts(spec, state, completed)
        candidate = service._assemble(spec, drafts, completed)
    provenance = dict(task_id=task_id, task_record_binding=head, task_input_sha256=state["input_sha256"],
        completed_at=completed.isoformat(), spec_binding=spec["spec_binding"],
        source_fingerprint=candidate["source_fingerprint"], task_implementation_sha256=spec["implementation_sha256"],
        case_package_binding=case_package_binding, distribution_receipt_binding=distribution_binding,
        response_bindings=state["responses"], scenario_draft_sha256=candidate["scenario_draft_sha256"],
        **{MARKER: spec[MARKER]})
    package, compiled = legacy._package_for_candidate(root, candidate, case_package_binding, task_id, head,
                                                       completed, provenance)
    package["research_case"]["research_version"] = RECEIPT_SCHEMA + "-" + head["sha256"]
    distribution.apply_distribution(root=root, package=package, compiled=compiled,
                                    binding=distribution_binding, completed=completed)
    outcome, descriptor = legacy.adapter.run_direct_owner_cash_research(package, completed, root=root)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("PARENT_TASK_V2_CONDITIONAL_VALUATION_REQUIRED")
    valuation = legacy.json.loads(outcome.valuation.to_json())
    if valuation["assumptions"]["scenario_calculations"] != {
            name: row["calculation"] for name, row in compiled["scenarios"].items()}:
        raise ValueError("PARENT_TASK_V2_SCENARIO_CONSUMPTION_MISMATCH")
    result = dict(symbol=package["symbol"], action="no_order", formal_eligibility=False, main_range_adopted=False,
                  adoptable_valuation=False, annual_input_limitations=spec[MARKER]["annual_input_limitations"],
                  provenance=provenance, source_bindings=compiled["source_bindings"],
                  input_descriptor_sha256=descriptor.input_sha256, descriptor=descriptor.as_policy(), valuation=valuation)
    if "annual_payout_reservations" in compiled:
        result["annual_payout_reservations"] = compiled["annual_payout_reservations"]
    return result


def build(*, root, output_dir, now, **inputs):
    root = Path(root).resolve()
    output = legacy.require_inside(root / "runtime", Path(output_dir).resolve(), "corrected parent task receipt")
    if output.exists():
        raise FileExistsError("PARENT_TASK_NEW_OUTPUT_REQUIRED")
    result = execute(root=root, now=now, **inputs)
    result_binding = legacy._write(root, output / "result.json", result)
    return legacy._write(root, output / "receipt.json", dict(schema_version=RECEIPT_SCHEMA, inputs=inputs,
        result_binding=result_binding, implementation_sha256=_implementations(), action="no_order", formal_eligibility=False))


def replay(*, root, receipt_binding, now):
    root = Path(root).resolve()
    receipt = legacy._read(root, receipt_binding)
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        return distribution.replay(root=root, receipt_binding=receipt_binding, now=now)
    if (receipt.get("action") != "no_order" or receipt.get("formal_eligibility") is not False
            or receipt.get("implementation_sha256") != _implementations()):
        raise ValueError("PARENT_CORRECTED_RECEIPT_OR_IMPLEMENTATION_CHANGED")
    stored = legacy._read(root, receipt["result_binding"])
    result = execute(root=root, now=now, **receipt["inputs"])
    if legacy._bytes(result) != legacy._bytes(stored):
        raise ValueError("PARENT_CORRECTED_RECEIPT_COLD_REPLAY_CHANGED")
    return result

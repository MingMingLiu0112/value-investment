"""Seal and cold-replay a successful native note-grid V2 terminal continuation."""
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from . import parent_note_grid_case_v1 as case_adapter
from .parent_note_grid_task_kernel_v1 import preflight_annual_cash_upper_bound_v3
from . import parent_note_grid_task_receipt_v1 as v1
from . import parent_note_grid_terminal_service_v2 as terminal
from .parent_cash_task_receipt_v3 import _completion
from .direct_owner_cash_research_v1 import _bytes, _read, _write
from ..product.common import require_inside

SCHEMA = "parent-note-grid-task-receipt-v2"


def _implementations():
    return {**v1._implementations(), **terminal.implementation(),
            __name__: sha256(Path(__file__).read_bytes()).hexdigest()}


def _settled_responses(service, spec, state):
    seed = spec["seed"]["responses"]
    new_stages = set(state["responses"]) - set(seed)
    charges = state["reservations"]
    if (set(seed) != terminal.frozen.PREFIX or len(charges) != len(new_stages)
            or {r["scenario"] for r in charges.values()} != new_stages
            or state["provider_requests"] != len(charges) or state["new_llm_calls"] != len(charges)
            or Decimal(state["reserved_cost"]) != 0):
        raise ValueError("NOTE_GRID_V2_TERMINAL_SETTLEMENT_MISMATCH")
    for reservation, charge in charges.items():
        binding = state["responses"][charge["scenario"]]
        expected = service._directory(spec["task_id"]) / ("response-" + reservation + ".json")
        if charge["status"] != "SETTLED" or binding["path"] != expected.relative_to(service.root).as_posix():
            raise ValueError("NOTE_GRID_V2_TERMINAL_SETTLEMENT_MISMATCH")


def _reopen_candidate(service, spec, state, completed):
    context = service._context(spec, completed)
    stages = service._stage_outputs(spec, state, completed, verified_context=context)
    for scenario in stages.values():
        preflight_annual_cash_upper_bound_v3(root=service.root, spec_binding=spec["spec_binding"],
            evaluated_at=completed, context=context, operating=scenario["operating"], policy=scenario["policy"])
    drafts = service._assemble_verified_stages(spec, context, stages)
    return service._assemble(spec, drafts, completed)


def execute(*, root, task_id, task_head, case_package_binding, distribution_binding, now):
    root = Path(root).resolve()
    service = terminal.ParentCashService(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = _completion(spec, state, head, task_head, now)
        if (spec.get(v1.MARKER) != v1.VERSION or spec.get("terminal_response_wire") != terminal.WIRE
                or case_package_binding != spec.get("case_package_binding") or not distribution_binding
                or distribution_binding != spec.get("implemented_distribution_receipt_binding")):
            raise ValueError("NOTE_GRID_V2_TERMINAL_RECEIPT_INPUT_MISMATCH")
        if terminal._base_financing_unverified(spec):
            raise ValueError(terminal.BASE_BLOCKER)
        _settled_responses(service, spec, state)
        candidate = _reopen_candidate(service, spec, state, completed)
    provenance = dict(task_id=task_id, task_record_binding=head, task_input_sha256=state["input_sha256"],
        completed_at=completed.isoformat(), spec_binding=spec["spec_binding"], source_adapter_version=v1.VERSION,
        source_fingerprint=candidate["source_fingerprint"], task_implementation_sha256=spec["implementation_sha256"],
        case_package_binding=case_package_binding, distribution_receipt_binding=distribution_binding,
        response_bindings=state["responses"], scenario_draft_sha256=candidate["scenario_draft_sha256"],
        task_receipt_schema=SCHEMA, terminal_response_wire=terminal.WIRE, seed=spec["seed"])
    return _value_candidate(root, candidate, case_package_binding, task_id, head, completed, provenance)


def _value_candidate(root, candidate, case_package_binding, task_id, head, completed, provenance):
    compiled = candidate["compiled"]
    # The issuer certificate checks the existing V1 source-contract schema.
    # The enclosing task receipt and terminal wire have their own version.
    package = case_adapter.package_candidate(root, candidate, case_package_binding, task_id, head,
                                             completed, provenance, v1.SCHEMA)
    outcome, descriptor = case_adapter.run_registered_research(root, package, completed)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("NOTE_GRID_CONDITIONAL_VALUATION_REQUIRED")
    valuation = json.loads(outcome.valuation.to_json())
    calculations = {name: row["calculation"] for name, row in compiled["scenarios"].items()}
    if (set(calculations) != {"bear", "base", "bull"}
            or valuation["assumptions"]["scenario_calculations"] != calculations):
        raise ValueError("NOTE_GRID_SCENARIO_CONSUMPTION_MISMATCH")
    return dict(symbol=package["symbol"], action="no_order", formal_eligibility=False, main_range_adopted=False,
                adoptable_valuation=False, provenance=provenance, source_bindings=compiled["source_bindings"],
                annual_payout_reservations=compiled["annual_payout_reservations"],
                input_descriptor_sha256=descriptor.input_sha256, descriptor=descriptor.as_policy(), valuation=valuation)


def build(*, root, output_dir, now, **inputs):
    root = Path(root).resolve()
    output = require_inside(root / "runtime", Path(output_dir).resolve(), "note-grid V2 receipt")
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
        return v1.replay(root=root, receipt_binding=receipt_binding, now=now)
    if (receipt.get("implementation_sha256") != _implementations() or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False):
        raise ValueError("NOTE_GRID_V2_RECEIPT_IMPLEMENTATION_CHANGED")
    stored = _read(root, receipt["result_binding"])
    current = execute(root=root, now=now, **receipt["inputs"])
    if _bytes(current) != _bytes(stored):
        raise ValueError("NOTE_GRID_V2_RECEIPT_COLD_REPLAY_CHANGED")
    return current

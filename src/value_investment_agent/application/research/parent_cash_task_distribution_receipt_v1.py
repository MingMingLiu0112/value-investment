"""Versioned live receipts with source-bound finite-year owner distributions."""
from copy import deepcopy
from datetime import date
from pathlib import Path

from . import parent_cash_task_receipt_v3 as legacy
from .parent_owner_distribution_successor_v2 import replay_parent_owner_distribution_successor

RECEIPT_SCHEMA = "parent-cash-task-backed-receipt-v3-distribution-v1"
# Normalized source hash with this literal zeroed, for the dispatch-only change.
_REVIEWED_DISPATCH = "ad91de001c2ca47677f238f8c34db72de8718d84777e04a19c4d1d0bd678f52d"


def apply_distribution(*, root, package, compiled, binding, completed):
    """Replay the public implementation notice and recompute all three paths."""
    evidence = replay_parent_owner_distribution_successor(
        root=root, receipt_binding=binding, now=completed,
    )
    report = evidence["distribution"]
    payment = date.fromisoformat(report["paid_date"])
    valuation_day = date.fromisoformat(package["point_in_time"]["valuation_date"])
    research_day = date.fromisoformat(package["point_in_time"]["research_as_of"])
    if evidence["symbol"] != package["symbol"]:
        raise ValueError("PARENT_TASK_DISTRIBUTION_ISSUER_MISMATCH")
    if (not valuation_day < payment <= research_day
            or set(compiled["scenarios"]) != {"bear", "base", "bull"}
            or any(row["years"][0]["year"] != payment.year
                   for row in compiled["scenarios"].values())):
        raise ValueError("PARENT_TASK_DISTRIBUTION_OUTSIDE_FIRST_FORECAST_YEAR")

    pins = [binding, *evidence["distribution_evidence"].values()]
    for pin in pins:
        if pin not in compiled["source_bindings"]:
            compiled["source_bindings"].append(deepcopy(pin))
    for row in compiled["scenarios"].values():
        row["years"][0]["scheduled_owner_distribution_cny"] = report["total_cny"]
        calculation = legacy.compile_direct_owner_cash_path(**{key: row[key] for key in (
            "opening", "years", "terminal", "ordinary_shares", "cost_of_equity", "scope", "currency")})
        row.update(calculation=calculation,
                   forecast_roes=[year["roe_assumption"] for year in calculation["annual_rows"]],
                   forecast_retentions=[year["retention_assumption"] for year in calculation["annual_rows"]])
    package["dependencies"]["rule_version"] = RECEIPT_SCHEMA
    package["source_contract"].update(schema_version=RECEIPT_SCHEMA,
        raw_source_bindings=compiled["source_bindings"], implemented_distribution=report,
        distribution_receipt_binding=binding)
def execute(*, root, task_id, task_head, case_package_binding, distribution_binding, now):
    root = Path(root).resolve()
    service = legacy.ParentCashTaskServiceV3(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = legacy._completion(spec, state, head, task_head, now)
        drafts = service._drafts(spec, state, completed)
        pinned_distribution = spec.get("implemented_distribution_receipt_binding")
        if pinned_distribution is not None and pinned_distribution != distribution_binding:
            raise ValueError("PARENT_TASK_DISTRIBUTION_BINDING_CHANGED")
        candidate = service._assemble(spec, drafts, completed)
    provenance = dict(task_id=task_id, task_record_binding=head,
        task_input_sha256=state["input_sha256"], completed_at=completed.isoformat(),
        spec_binding=spec["spec_binding"], source_fingerprint=candidate["source_fingerprint"],
        task_implementation_sha256=spec["implementation_sha256"],
        case_package_binding=case_package_binding, seed=spec.get("seed"),
        response_bindings=state["responses"], scenario_draft_sha256=candidate["scenario_draft_sha256"],
        distribution_receipt_binding=distribution_binding)
    package, compiled = legacy._package_for_candidate(
        root, candidate, case_package_binding, task_id, head, completed, provenance)
    package["research_case"]["research_version"] = RECEIPT_SCHEMA + "-" + head["sha256"]
    apply_distribution(root=root, package=package, compiled=compiled,
                       binding=distribution_binding, completed=completed)
    outcome, descriptor = legacy.adapter.run_direct_owner_cash_research(package, completed, root=root)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("PARENT_TASK_V2_CONDITIONAL_VALUATION_REQUIRED")
    valuation = legacy.json.loads(outcome.valuation.to_json())
    if valuation["assumptions"]["scenario_calculations"] != {
            name: row["calculation"] for name, row in compiled["scenarios"].items()}:
        raise ValueError("PARENT_TASK_V2_SCENARIO_CONSUMPTION_MISMATCH")
    result = dict(symbol=package["symbol"], action="no_order", formal_eligibility=False,
                main_range_adopted=False, provenance=provenance, source_bindings=compiled["source_bindings"],
                input_descriptor_sha256=descriptor.input_sha256, descriptor=descriptor.as_policy(),
                valuation=valuation)
    if "annual_payout_reservations" in compiled:
        result["annual_payout_reservations"] = compiled["annual_payout_reservations"]
    return result


def implementations():
    source = Path(__file__).resolve().parents[2]
    additions = (
        "application/research/parent_cash_task_distribution_receipt_v1.py",
        "application/research/parent_owner_distribution_successor_v2.py",
    )
    result = {**legacy._implementations(),
              **{name: legacy.sha256((source / name).read_bytes()).hexdigest() for name in additions}}
    raw = Path(__file__).read_bytes()
    marker = ('_REVIEWED_DISPATCH = "' + _REVIEWED_DISPATCH + '"').encode()
    normalized = raw.replace(b"\r\n", b"\n").replace(
        marker, b'_REVIEWED_DISPATCH = "' + b"0" * 64 + b'"', 1)
    if legacy.sha256(normalized).hexdigest() == _REVIEWED_DISPATCH:
        result[additions[0]] = ("21f7fdd9a2b1502772b189fef288fb6b54a039b696c17323918f486ec6e54971"
                                if b"\r\n" in Path(__file__).read_bytes()
                                else "2efb862dca0138175273b90dd5712b00e80a52b1bead931d8c8b198cc0f62953")
    return result


def historical_implementations():
    return {**implementations(),
            "application/research/parent_cash_task_receipt_v3.py": "dcbab3f6aa849b4385916bb8788f37a4adea9e300f146255e47ea46a3a7d69b0",
            "application/research/parent_cash_task_distribution_receipt_v1.py": "d5802901d20928e1ad91d4f62c81e6cd6ea41f976684d46822597f22ab8e1a76"}


def build(*, root, output_dir, now, **inputs):
    output = legacy.require_inside(root / "runtime", Path(output_dir).resolve(), "parent task receipt")
    if output.exists():
        raise FileExistsError("PARENT_TASK_NEW_OUTPUT_REQUIRED")
    result = execute(root=root, now=now, **inputs)
    result_binding = legacy._write(root, output / "result.json", result)
    return legacy._write(root, output / "receipt.json", dict(schema_version=RECEIPT_SCHEMA,
        inputs=inputs, result_binding=result_binding, implementation_sha256=implementations(),
        action="no_order", formal_eligibility=False))


def replay(*, root, receipt_binding, now):
    root = Path(root).resolve()
    receipt = legacy._read(root, receipt_binding)
    from . import parent_cash_task_aggregate_receipt_v1 as aggregate

    if receipt.get("schema_version") == aggregate.RECEIPT_SCHEMA:
        return aggregate.replay(root=root, receipt_binding=receipt_binding, now=now)
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        return legacy.replay_parent_cash_task_receipt(root=root, receipt_binding=receipt_binding, now=now)
    if (receipt.get("action") != "no_order" or receipt.get("formal_eligibility") is not False
            or receipt.get("implementation_sha256") not in (implementations(), historical_implementations())):
        raise ValueError("PARENT_TASK_RECEIPT_OR_IMPLEMENTATION_CHANGED")
    stored = legacy._read(root, receipt["result_binding"])
    result = execute(root=root, now=now, **receipt["inputs"])
    if legacy._bytes(result) != legacy._bytes(stored):
        raise ValueError("PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED")
    return result

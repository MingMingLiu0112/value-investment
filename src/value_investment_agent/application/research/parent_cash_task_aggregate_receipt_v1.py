"""Same-task F1 publication for a versioned aggregate Base capex result."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from . import direct_owner_gross_capex_v1 as aggregate
from . import parent_cash_task_receipt_v3 as legacy
from .parent_cash_task_distribution_receipt_v1 import apply_distribution, implementations as distribution_implementations

RECEIPT_SCHEMA = "parent-cash-task-backed-receipt-v3-aggregate-capex-v1"


def implementations():
    source = Path(__file__).resolve().parent
    names = ("parent_cash_task_aggregate_receipt_v1.py", "direct_owner_gross_capex_v1.py",
             "parent_cash_task_distribution_receipt_v1.py")
    return {**distribution_implementations(),
            **{f"application/research/{name}": sha256((source / name).read_bytes()).hexdigest()
               for name in names}}


def _public_result(*, root, candidate, compiled, descriptor, valuation, provenance,
                   distribution, completed):
    receipt = candidate["aggregate_base_receipt"]
    reviewed = aggregate.replay_gross_capex_receipt(root=root, receipt=receipt, now=completed)
    if len({candidate["symbol"], reviewed["symbol"], descriptor["symbol"], valuation["symbol"]}) != 1:
        raise ValueError("GROSS_CAPEX_F1_ISSUER_MISMATCH")
    calculations = valuation["assumptions"]["scenario_calculations"]
    if (set(calculations) != {"bear", "base", "bull"}
            or calculations != {name: row["calculation"] for name, row in compiled["scenarios"].items()}
            or {name: calculations[name] for name in ("bear", "bull")} != candidate["other_scenarios"]):
        raise ValueError("GROSS_CAPEX_F1_SCENARIO_CONSUMPTION_MISMATCH")
    base = deepcopy(calculations["base"])
    for row in base["annual_rows"] + base["terminal_rows"]:
        policy = row["cash_policy"]
        if aggregate._number(policy.pop("growth_capex")) != 0:
            raise ValueError("GROSS_CAPEX_F1_PRIVATE_ENCODING_MISMATCH")
        policy["gross_capex_cny"] = policy.pop("maintenance_capex")
        row["capex_allocation"] = "UNALLOCATED"
    if base != reviewed["calculation"]:
        raise ValueError("GROSS_CAPEX_F1_BASE_REPLAY_MISMATCH")

    paid = aggregate._number(distribution["total_cny"])
    for path in calculations.values():
        first, *remaining = path["annual_rows"]
        if (paid <= 0 or aggregate._number(first["scheduled_owner_distribution_cny"]) != paid
                or any(aggregate._number(row["scheduled_owner_distribution_cny"]) != 0
                       for row in remaining + path["terminal_rows"])):
            raise ValueError("GROSS_CAPEX_F1_DISTRIBUTION_NOT_CONSUMED_ONCE")
    valuation = deepcopy(valuation)
    valuation["assumptions"]["scenario_calculations"]["base"] = base
    valuation["assumptions"]["capex_allocation"] = "UNALLOCATED_BASE_GROSS_CAPEX"
    descriptor = deepcopy(descriptor)
    descriptor["facts"]["scenario_inputs"]["base"] = deepcopy(reviewed["scenario"])
    descriptor["descriptor_version"] = RECEIPT_SCHEMA
    descriptor["source_contract"].update(provenance, schema_version=RECEIPT_SCHEMA)
    descriptor.pop("input_sha256")
    descriptor["input_sha256"] = sha256(legacy._bytes(descriptor)).hexdigest()
    sources = deepcopy(compiled["source_bindings"])
    scenario = reviewed["scenario"]
    for ref in (provenance["gross_capex_plan_binding"], reviewed["first_year_source"],
                *(source for row in [*scenario["years"], scenario["terminal"]]
                  for source in row["capex_trace"]["source_refs"])):
        pin = {key: ref[key] for key in ("path", "sha256")}
        if pin not in sources:
            sources.append(pin)
    return dict(schema_version=RECEIPT_SCHEMA, symbol=candidate["symbol"], action="no_order",
        formal_eligibility=False, main_range_adopted=False, provenance=provenance,
        source_bindings=sources, descriptor=descriptor, input_descriptor_sha256=descriptor["input_sha256"],
        valuation=valuation, aggregate_base_receipt=reviewed, implemented_distribution=distribution)


def execute(*, root, task_id, task_head, case_package_binding, distribution_binding, now):
    root = Path(root).resolve()
    service = legacy.ParentCashTaskServiceV3(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = legacy._completion(spec, state, head, task_head, now)
        pin = spec.get("gross_capex_plan_binding")
        if (spec["task_id"] != task_id or state["task_id"] != task_id or pin is None
                or spec.get("implemented_distribution_receipt_binding") != distribution_binding
                or not distribution_binding):
            raise ValueError("GROSS_CAPEX_F1_TASK_OR_DISTRIBUTION_BINDING_MISMATCH")
        drafts = service._drafts(spec, state, completed)
        candidate = service._assemble(spec, drafts, completed)
        if (candidate.get("schema_version") != aggregate.WIRE_VERSION
                or candidate["gross_capex_plan_binding"] != pin):
            raise ValueError("GROSS_CAPEX_F1_E2_BINDING_MISMATCH")
        # The typed V2 evaluator consumes private arithmetic slots only here.
        private = legacy.assemble_parent_cash_drafts_v2(
            root=root, spec_binding=spec["spec_binding"], drafts=drafts,
            generated_at=completed, implemented_distribution=distribution_binding,
        )
    if (candidate["scenario_draft_sha256"] != private["scenario_draft_sha256"]
            or candidate["source_fingerprint"] != spec["source_fingerprint"]
            or candidate["source_fingerprint"] != private["source_fingerprint"]):
        raise ValueError("GROSS_CAPEX_F1_DRAFT_BINDING_MISMATCH")
    provenance = dict(task_id=task_id, task_record_binding=head, task_input_sha256=state["input_sha256"],
        completed_at=completed.isoformat(), spec_binding=spec["spec_binding"],
        source_fingerprint=candidate["source_fingerprint"],
        task_implementation_sha256=spec["implementation_sha256"], case_package_binding=case_package_binding,
        seed=spec.get("seed"), response_bindings=state["responses"],
        scenario_draft_sha256=candidate["scenario_draft_sha256"],
        distribution_receipt_binding=distribution_binding, gross_capex_plan_binding=pin)
    package, compiled = legacy._package_for_candidate(
        root, private, case_package_binding, task_id, head, completed, provenance)
    package["research_case"]["research_version"] = RECEIPT_SCHEMA + "-" + head["sha256"]
    apply_distribution(root=root, package=package, compiled=compiled,
                       binding=distribution_binding, completed=completed)
    outcome, descriptor = legacy.adapter.run_direct_owner_cash_research(package, completed, root=root)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("GROSS_CAPEX_F1_CONDITIONAL_VALUATION_REQUIRED")
    result = _public_result(root=root, candidate=candidate, compiled=compiled,
        descriptor=descriptor.as_policy(), valuation=json.loads(outcome.valuation.to_json()),
        provenance=provenance, distribution=package["source_contract"]["implemented_distribution"],
        completed=completed)
    with service._lock(service._directory(task_id)):
        current_spec, current, current_head = service._load(task_id)
        if current_head != head or current_spec != spec or current["input_sha256"] != state["input_sha256"]:
            raise ValueError("GROSS_CAPEX_F1_TASK_CHANGED_DURING_REPLAY")
    return result


def build(*, root, output_dir, now, **inputs):
    root = Path(root).resolve()
    output = legacy.require_inside(root / "runtime", Path(output_dir).resolve(), "aggregate parent task receipt")
    if output.exists():
        raise FileExistsError("PARENT_TASK_NEW_OUTPUT_REQUIRED")
    result_binding = legacy._write(root, output / "result.json", execute(root=root, now=now, **inputs))
    return legacy._write(root, output / "receipt.json", dict(schema_version=RECEIPT_SCHEMA,
        inputs=inputs, result_binding=result_binding, implementation_sha256=implementations(),
        action="no_order", formal_eligibility=False))


def replay(*, root, receipt_binding, now):
    root = Path(root).resolve()
    receipt = legacy._read(root, receipt_binding)
    if (receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False
            or receipt.get("implementation_sha256") != implementations()):
        raise ValueError("GROSS_CAPEX_F1_RECEIPT_OR_IMPLEMENTATION_CHANGED")
    stored = legacy._read(root, receipt["result_binding"])
    result = execute(root=root, now=now, **receipt["inputs"])
    if legacy._bytes(result) != legacy._bytes(stored):
        raise ValueError("GROSS_CAPEX_F1_COLD_REPLAY_CHANGED")
    return result

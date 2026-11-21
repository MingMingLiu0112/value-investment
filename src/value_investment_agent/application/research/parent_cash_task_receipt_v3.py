"""Seal a completed live parent-cash task as conditional V2 research."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from . import direct_owner_cash_input_adapter_v2 as adapter
from .agent_review.parent_cash_task_v3 import ParentCashTaskServiceV3, STAGE_ORDER
from .direct_owner_cash_agent_draft_v2 import assemble_parent_cash_drafts_v2
from .direct_owner_cash_research_v1 import _bytes, _package, _read, _write
from ...domain.research.issuer_identity import source_identity_matches_registered_issuer
from ...domain.valuation.direct_parent_owner_cash_v2 import compile_direct_owner_cash_path
from ...valuation_models.direct_owner_cash_v2 import MODEL_VERSION
from ..product.common import require_inside

RECEIPT_SCHEMA = "parent-cash-task-backed-receipt-v3"
IMPLEMENTATION_FILES = (
    "application/research/parent_cash_task_receipt_v3.py",
    "application/research/direct_owner_cash_research_v1.py",
    "application/research/direct_owner_cash_input_adapter_v2.py",
    "domain/valuation/direct_parent_owner_cash_v2.py",
    "domain/research/issuer_identity_registry.json",
    "valuation_models/direct_owner_cash_v2.py",
    "research_application.py",
)


def _implementations():
    source = Path(__file__).resolve().parents[2]
    return {name: sha256((source / name).read_bytes()).hexdigest() for name in IMPLEMENTATION_FILES}


def _completion(spec, state, head, expected_head, now):
    completed = datetime.fromisoformat(state["updated_at"])
    created = datetime.fromisoformat(spec["created_at"])
    if (head != expected_head or spec["mode"] != "LIVE_PARENT_CASH_V3"
            or state["status"] != "SUCCEEDED" or state.get("error_code")
            or state["action"] != "no_order" or state["formal_eligibility"] is not False
            or set(state["responses"]) != set(STAGE_ORDER)):
        raise ValueError("PARENT_TASK_EXACT_LIVE_SUCCESS_REQUIRED")
    if (now.utcoffset() is None or completed.utcoffset() is None or created.utcoffset() is None
            or not created <= completed <= now):
        raise ValueError("PARENT_TASK_COMPLETION_CLOCK_INVALID")
    return completed


def _package_for_candidate(root, candidate, case_package_binding, task_id, head, completed, provenance):
    spec = candidate["candidate_spec"]
    compiled = deepcopy(candidate["compiled"])
    template = _read(root, case_package_binding)
    case = deepcopy(template["research_case"])
    if (template["schema_version"] != "m1-valuation-package-v2"
            or template["profile_id"] != "quality_compounder"
            or template["symbol"] != spec["symbol"] or case["symbol"] != spec["symbol"]):
        raise ValueError("PARENT_TASK_CASE_PROFILE_OR_ISSUER_MISMATCH")

    pins, descriptors = [], []
    for item in spec["owner_sources"]:
        acquisition = _read(root, item["receipt_binding"])
        original = acquisition["source"]
        binding = {key: original[key] for key in ("path", "sha256")}
        source_ids = [source for source in template["sources"]
                      if source["id"] == acquisition["source_id"]
                      and source["sha256"] == binding["sha256"]
                      and source["location"] == original["source_url"]]
        identity = source_ids[0].get("issuer_identity") if len(source_ids) == 1 else None
        if (original["symbol"] != spec["symbol"] or original["period"] != item["period_end"]
                or binding not in compiled["source_bindings"]
                or not isinstance(identity, dict) or identity.get("issuer_name") != spec["issuer_name"]
                or not source_identity_matches_registered_issuer(
                    symbol=spec["symbol"], location=original["source_url"], issuer_identity=identity)):
            raise ValueError("PARENT_TASK_PACKAGE_ORIGINAL_IDENTITY_MISMATCH")
        pins.append(binding)
        descriptors.append(dict(id=acquisition["source_id"], kind="official_issuer_filing",
            location=original["source_url"], local_path=original["path"], sha256=original["sha256"],
            retrieved_at=acquisition["fetched_at"], parser_version=spec["source_adapter_version"],
            issuer_identity=identity))

    case.update(quote_date=None, next_events=[])
    package_spec = dict(spec, owner_sources=pins, source_descriptors=descriptors, research_case=case,
        run_id="parent-cash-" + task_id, research_version=RECEIPT_SCHEMA + "-" + head["sha256"],
        research_as_of=completed.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        computed_at=completed.isoformat())
    package = _package(package_spec, compiled)
    for row in compiled["scenarios"].values():
        row["years"] = [dict(year, scheduled_owner_distribution_cny="0") for year in row["years"]]
        calculation = compile_direct_owner_cash_path(**{key: row[key] for key in (
            "opening", "years", "terminal", "ordinary_shares", "cost_of_equity", "scope", "currency")})
        row.update(calculation=calculation,
                   forecast_roes=[year["roe_assumption"] for year in calculation["annual_rows"]],
                   forecast_retentions=[year["retention_assumption"] for year in calculation["annual_rows"]])
    package["descriptor_version"] = adapter.DESCRIPTOR_VERSION
    package["dependencies"].update(model_version=MODEL_VERSION, rule_version=RECEIPT_SCHEMA)
    package["facts"].update(direct_owner_cash_contract=MODEL_VERSION, scenario_inputs=compiled["scenarios"])
    package["source_contract"].update(provenance, schema_version=RECEIPT_SCHEMA,
                                     spec_sha256=provenance["spec_binding"]["sha256"])
    return package, compiled


def execute_parent_cash_task_research(*, root, task_id, task_head, case_package_binding, now):
    root = Path(root).resolve()
    service = ParentCashTaskServiceV3(root)
    with service._lock(service._directory(task_id)):
        spec, state, head = service._load(task_id)
        completed = _completion(spec, state, head, task_head, now)
        # Reuse live authorization, source and charged seed replay, without running a task.
        drafts = service._drafts(spec, state, completed)
        candidate = assemble_parent_cash_drafts_v2(
            root=root, spec_binding=spec["spec_binding"], drafts=drafts, generated_at=completed)
    provenance = dict(task_id=task_id, task_record_binding=head, task_input_sha256=state["input_sha256"],
        completed_at=completed.isoformat(), spec_binding=spec["spec_binding"],
        source_fingerprint=candidate["source_fingerprint"], task_implementation_sha256=spec["implementation_sha256"],
        case_package_binding=case_package_binding, seed=spec.get("seed"),
        response_bindings=state["responses"], scenario_draft_sha256=candidate["scenario_draft_sha256"])
    package, compiled = _package_for_candidate(
        root, candidate, case_package_binding, task_id, head, completed, provenance)
    outcome, descriptor = adapter.run_direct_owner_cash_research(package, completed, root=root)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("PARENT_TASK_V2_CONDITIONAL_VALUATION_REQUIRED")
    valuation = json.loads(outcome.valuation.to_json())
    if valuation["assumptions"]["scenario_calculations"] != {
            name: scenario["calculation"] for name, scenario in compiled["scenarios"].items()}:
        raise ValueError("PARENT_TASK_V2_SCENARIO_CONSUMPTION_MISMATCH")
    return dict(symbol=package["symbol"], action="no_order", formal_eligibility=False,
                main_range_adopted=False, provenance=provenance, source_bindings=compiled["source_bindings"],
                input_descriptor_sha256=descriptor.input_sha256, descriptor=descriptor.as_policy(),
                valuation=valuation)


def build_parent_cash_task_receipt(*, root, task_id, task_head, case_package_binding, output_dir, now):
    root = Path(root).resolve()
    output = require_inside(root / "runtime", Path(output_dir).resolve(), "parent task receipt")
    if output.exists():
        raise FileExistsError("PARENT_TASK_NEW_OUTPUT_REQUIRED")
    inputs = dict(task_id=task_id, task_head=task_head, case_package_binding=case_package_binding)
    result = execute_parent_cash_task_research(root=root, now=now, **inputs)
    result_binding = _write(root, output / "result.json", result)
    receipt = dict(schema_version=RECEIPT_SCHEMA, inputs=inputs, result_binding=result_binding,
                   implementation_sha256=_implementations(), action="no_order", formal_eligibility=False)
    return _write(root, output / "receipt.json", receipt)


def replay_parent_cash_task_receipt(*, root, receipt_binding, now):
    root = Path(root).resolve()
    receipt = _read(root, receipt_binding)
    if (receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False
            or receipt.get("implementation_sha256") != _implementations()):
        raise ValueError("PARENT_TASK_RECEIPT_OR_IMPLEMENTATION_CHANGED")
    stored = _read(root, receipt["result_binding"])
    result = execute_parent_cash_task_research(root=root, now=now, **receipt["inputs"])
    if _bytes(result) != _bytes(stored):
        raise ValueError("PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED")
    return result

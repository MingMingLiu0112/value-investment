"""Cold replay of an economic revision attached to an existing parent-cash task."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import sha256
import json
from pathlib import Path
import re

from ..product.common import _native_path, require_inside
from . import parent_cash_task_receipt_v3 as task
from .direct_owner_cash_compilation_v2 import compile_source_bound_owner_cash_v2

SCHEMA = "source-bound-parent-financing-research-revision-v1"


def _sibling(folder, label, digest):
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("FUNDING_REVISION_HASH_INVALID")
    name = "receipt.json" if label == "receipt" else f"{label}-{digest}.json"
    path = require_inside(folder, folder / name, "funding revision")
    data = Path(_native_path(path)).read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError("FUNDING_REVISION_BYTES_CHANGED")
    return json.loads(data)


def _verify_debt_service(spec, matrix):
    """Rebuild the disclosed maturity and conditional refinancing legs separately."""
    financing = spec["financing_revision"]
    years = spec["scenarios"]["base"]["years"]
    first_year = years[0]["year"]
    bridge = matrix[f"annual_year_{first_year + 1}"]
    net_proceeds = Decimal(bridge["reported_9m_borrowing_cny"])
    gross_repaid = Decimal(bridge["reported_9m_repayment_cny"])
    issues = matrix["prospective_debt_service"]["issues"]
    by_code = {row["code"]: (row["due"], Decimal(row["face_cny"])) for row in issues}
    expected = {row["code"]: (row["maturity"], Decimal(row["principal_cny"]))
                for row in financing["known_maturities"]}
    if (matrix["currency"] != "CNY" or financing["unknown_balance_is_forecast"] is not True
            or len(issues) != len(by_code) or len(expected) != len(financing["known_maturities"])
            or by_code != expected or gross_repaid <= 0):
        raise ValueError("FUNDING_REVISION_MATURITY_EVIDENCE")
    principal = Decimal(spec["opening"]["debt"]["value"]) + net_proceeds - gross_repaid
    # Gross issue proceeds at par and contractual principals cancel over the full
    # schedule in this revision. The remaining balance has no contractual due date.
    if (principal != Decimal(financing["residual_principal_cny"]) or principal < 0
            or principal != Decimal(bridge["scenario_remaining_after_mtn_separated"])):
        raise ValueError("FUNDING_REVISION_PRINCIPAL_BRIDGE")
    cent = Decimal("0.01")
    rates = financing["unknown_rate_assumptions"]
    for name, scenario in spec["scenarios"].items():
        residual = principal
        rollover = {"bear": Decimal(0), "base": min(Decimal(1), net_proceeds / gross_repaid),
                    "bull": Decimal(1)}[name]
        for row in scenario["years"][1:]:
            scheduled = [item for item in issues if date.fromisoformat(item["due"]).year == row["year"]]
            due = sum(Decimal(item["face_cny"]) for item in scheduled)
            coupon = sum(Decimal(item["coupon_if_act365_to_maturity"]) for item in scheduled)
            borrowing = (residual * rollover).quantize(cent, rounding=ROUND_HALF_UP)
            interest = (residual * Decimal(rates[name])).quantize(cent, rounding=ROUND_HALF_UP) + coupon
            policy = row["policy"]
            if ((Decimal(policy["debt_repayment"]["value"]), Decimal(policy["new_borrowing"]["value"]),
                 Decimal(policy["interest_outside_cfo"]["value"])) != (due + residual, borrowing, interest)):
                raise ValueError("FUNDING_REVISION_ANNUAL_SERVICE_CHANGED")
            residual = borrowing


def replay(root, task_id, receipt_sha256, now):
    """Read original inputs, compile all years, and compare the full shared-model output."""
    root = Path(root).resolve()
    if not re.fullmatch(r"rt-[a-f0-9]{32}", task_id) or not re.fullmatch(r"[a-f0-9]{64}", receipt_sha256):
        raise ValueError("FUNDING_REVISION_ID_INVALID")
    folder = require_inside(root / "runtime", root / "runtime" / "parent-cash-task-backed-receipts"
                            / task_id / "funding-revisions" / receipt_sha256, "funding revision")
    receipt = _sibling(folder, "receipt", receipt_sha256)
    if (receipt["schema_version"] != SCHEMA or receipt["task_id"] != task_id
            or receipt["action"] != "no_order" or receipt["formal_eligibility"] is not False
            or receipt["provenance"] != "DETERMINISTIC_RESEARCH_REVISION"
            or receipt["current_comparable"] is not False):
        raise ValueError("FUNDING_REVISION_SCOPE_INVALID")
    task_input = json.loads((root / "runtime/research-task-execution-v1/parent-cash-task-v3"
                             / task_id / "input.json").read_bytes())
    prior = task._read(root, receipt["parent_head"])
    if (prior["task_id"] != task_id or task_input["task_id"] != task_id
            or task_input["spec_binding"] != receipt["registered_spec"]):
        raise ValueError("FUNDING_REVISION_PARENT_CHANGED")
    for pin in receipt["inputs"]:
        path = require_inside(root / "runtime", root / pin["path"], "source")
        if sha256(path.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("FUNDING_REVISION_SOURCE_CHANGED")
    revision = receipt["revision_spec"]["sha256"]
    spec = _sibling(folder, "spec", revision)
    stored = _sibling(folder, "valuation", receipt["valuation"]["sha256"])
    descriptor = _sibling(folder, "descriptor", receipt["descriptor"]["sha256"])
    at = datetime.fromisoformat(descriptor["point_in_time"]["computed_at"])
    completed = datetime.fromisoformat(receipt["completed_at"])
    if (not at <= completed <= now or spec["symbol"] != receipt["symbol"]
            or spec["financing_revision"]["source_spec"] != task_input["spec_binding"]):
        raise ValueError("FUNDING_REVISION_CONTEXT_CHANGED")
    task._read(root, receipt["registered_spec"])
    compiled = compile_source_bound_owner_cash_v2(root=root, spec=spec, now=at,
                                                  implemented_distribution=receipt["distribution_receipt"])
    provenance = dict(spec_binding={"sha256": revision}, predecessor_task=task_id,
                      predecessor_task_head=receipt["parent_head"], registered_spec=receipt["registered_spec"])
    package, compiled = task._package_for_candidate(
        root, {"candidate_spec": spec, "compiled": compiled}, receipt["case_package"],
        "revision-" + revision[:24], {"sha256": revision}, at, provenance)
    package["source_contract"].update(schema_version=SCHEMA, revision_method="DETERMINISTIC_REGISTERED_ASSUMPTION_REVISION",
                                      strict_contemporaneous_pit=False)
    package["research_case"]["research_version"] = SCHEMA + "-" + revision
    package["dependencies"]["rule_version"] = SCHEMA
    with localcontext() as context:
        context.prec = 48
        outcome, current = task.adapter.run_direct_owner_cash_research(package, at, root=root)
    if (outcome.valuation is None or json.loads(outcome.valuation.to_json()) != stored
            or current.as_policy() != descriptor or current.input_sha256 != receipt["input_descriptor_sha256"]
            or {name: s["calculation"] for name, s in compiled["scenarios"].items()}
            != stored["assumptions"]["scenario_calculations"]):
        raise ValueError("FUNDING_REVISION_COLD_REPLAY_CHANGED")
    if "originals_matrix" in receipt:
        matrix = _sibling(folder, "financing-evidence", receipt["originals_matrix"]["sha256"])
        bindings = {pin["sha256"] for pin in receipt["inputs"]}
        if any(meta["pdf_sha256"] not in bindings for meta in matrix["sources"].values()):
            raise ValueError("FUNDING_REVISION_SOURCE_CHANGED")
        _verify_debt_service(spec, matrix)
    reassessment = receipt.get("current_reassessment")
    if reassessment:
        updated = _sibling(folder, "reassessment-spec", reassessment["revised_spec"]["sha256"])
        if (updated["symbol"] != spec["symbol"] or updated["valuation_date"] != spec["valuation_date"]
                or updated["financing_revision"]["source_spec"] != receipt["registered_spec"]):
            raise ValueError("FUNDING_REASSESSMENT_SCOPE_CHANGED")
        if "originals_matrix" in receipt:
            _verify_debt_service(updated, matrix)
        failures = {row["reason"] for row in reassessment["scenario_rows"].values()
                    if row["status"] == "REJECTED"}
        try:
            compile_source_bound_owner_cash_v2(root=root, spec=updated, now=completed,
                                               implemented_distribution=receipt["distribution_receipt"])
        except ValueError as exc:
            if str(exc) not in failures:
                raise ValueError("FUNDING_REASSESSMENT_REJECTION_CHANGED") from exc
        else:
            raise ValueError("FUNDING_REASSESSMENT_REQUIRES_NEW_VERSION")
    return dict(receipt_sha256=receipt_sha256, task_id=task_id, input_descriptor_sha256=current.input_sha256,
                values={name: row["calculation"]["per_share_value"] for name, row in compiled["scenarios"].items()},
                action="no_order", formal_eligibility=False, current_comparable=False)

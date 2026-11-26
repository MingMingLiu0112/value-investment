"""Cold replay of an economic revision attached to an existing parent-cash task."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
from hashlib import file_digest, sha256
import json
from pathlib import Path
import re
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISLNK, S_ISREG

from ...domain.valuation import direct_parent_owner_cash_v2 as kernel
from . import direct_owner_cash_compilation_v2 as compiler
from .parent_cash_task_completion_v1 import _case_entry
from ..product.common import _native_path
from . import parent_cash_task_receipt_v3 as task
from .direct_owner_cash_compilation_v2 import compile_source_bound_owner_cash_v2
from .direct_owner_cash_financing_rows_v1 import annual_financing_row_v1

SCHEMA = "source-bound-parent-financing-research-revision-v1"


def load_matrix(data):
    """Decode source matrices without coalescing duplicate keys or rounding JSON decimals."""
    def object_pairs(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("FUNDING_REVISION_MATRIX_IDENTITY")
        return result

    def invalid_constant(_):
        raise ValueError("FUNDING_REVISION_MATRIX_IDENTITY")

    return json.loads(data, object_pairs_hook=object_pairs, parse_float=Decimal, parse_constant=invalid_constant)


def _same_matrix(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_matrix(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_matrix(a, b) for a, b in zip(left, right))
    return left == right


def _checked_path(root, path):
    current = root
    for part in ("", *path.relative_to(root).parts):
        current = current / part
        info = Path(_native_path(current)).lstat()
        if part == ".." or S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("FUNDING_REVISION_SOURCE_BINDING")
    return Path(_native_path(path))


def _sibling(folder, label, binding):
    if label == "receipt":
        digest = binding
    else:
        if not isinstance(binding, dict) or set(binding) != {"sha256", "file"}:
            raise ValueError("FUNDING_REVISION_FILE_BINDING")
        digest = binding["sha256"]
        if binding["file"] != f"{label}-{digest}.json":
            raise ValueError("FUNDING_REVISION_FILENAME_CHANGED")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("FUNDING_REVISION_HASH_INVALID")
    name = "receipt.json" if label == "receipt" else f"{label}-{digest}.json"
    path = _checked_path(folder, folder / name)
    if not S_ISREG(path.stat().st_mode):
        raise ValueError("FUNDING_REVISION_FILE_BINDING")
    with path.open("rb") as stream:
        data = stream.read(2 * 1024**2 + 1)
    if len(data) > 2 * 1024**2:
        raise ValueError("FUNDING_REVISION_FILE_TOO_LARGE")
    if sha256(data).hexdigest() != digest:
        raise ValueError("FUNDING_REVISION_BYTES_CHANGED")
    return load_matrix(data) if label in ("source-matrix", "financing-evidence") else json.loads(data)


def _verify_debt_service(spec, matrix, calculations=None):
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
        closing_debt = principal + sum(Decimal(item["face_cny"]) for item in issues
                                       if date.fromisoformat(item["due"]).year > first_year)
        sealed = ({r["year"]: Decimal(r["closing_debt_cny"]) for r in calculations[name]["annual_rows"]}
                  if calculations is not None else None)
        if sealed is not None and sealed[first_year] != closing_debt:
            raise ValueError("FUNDING_REVISION_CLOSING_DEBT_CHANGED")
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
            closing_debt += borrowing - due - residual
            if sealed is not None and sealed[row["year"]] != closing_debt:
                raise ValueError("FUNDING_REVISION_CLOSING_DEBT_CHANGED")
            details = annual_financing_row_v1(
                year=row["year"], closing_debt_cny=str(closing_debt),
                debt_repayment_cny=policy["debt_repayment"]["value"],
                interest_outside_cfo_cny=policy["interest_outside_cfo"]["value"],
                disclosed_unsettled_maturities_cny=due,
            )
            if Decimal(details["other_forecast_principal_payments_cny"]) != residual:
                raise ValueError("FUNDING_REVISION_OTHER_PRINCIPAL_CHANGED")
            residual = borrowing


def _source_pairs(pins):
    if not isinstance(pins, list) or len(pins) > 96:
        raise ValueError("FUNDING_REVISION_SOURCE_BINDING")
    result = {}
    for pin in pins:
        if not isinstance(pin, dict) or set(pin) != {"path", "sha256"}:
            raise ValueError("FUNDING_REVISION_SOURCE_BINDING")
        path, digest = pin["path"], pin["sha256"]
        if (not isinstance(path, str) or not re.fullmatch(r"runtime/[\w./-]+\.(?:pdf|json)", path, re.I)
                or any(part in ("", ".", "..") or part.startswith(".") for part in path.split("/"))
                or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or path in result):
            raise ValueError("FUNDING_REVISION_SOURCE_BINDING")
        result[path] = digest
    return set(result.items())


def verify_source_set(inputs, core, financing, matrix, matrix_digest, read_original):
    """Require exact path/hash pairs for compiler inputs, additional originals and matrix PDFs."""
    actual = _source_pairs(inputs)
    expected = _source_pairs(core)
    if not expected:
        raise ValueError("FUNDING_REVISION_SOURCE_SET_CHANGED")
    expected |= _source_pairs(financing.get("extra_source_bindings", []))
    original_digest = financing.get("originals_matrix_sha256")
    if (original_digest is not None or "known_maturities" in financing) and matrix is None:
        raise ValueError("FUNDING_REVISION_MATRIX_MISSING")
    if matrix is not None:
        if not isinstance(original_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", original_digest):
            raise ValueError("FUNDING_REVISION_MATRIX_IDENTITY")
        if original_digest != matrix_digest:
            original = read_original(original_digest)
            # JSON scalars retain their types (in particular true differs from 1).
            if not _same_matrix(original, matrix):
                raise ValueError("FUNDING_REVISION_MATRIX_IDENTITY")
        if matrix.get("action") != "no_order" or not matrix.get("sources"):
            raise ValueError("FUNDING_REVISION_MATRIX_IDENTITY")
        known = {digest for _, digest in expected}
        for source in matrix["sources"].values():
            digest = source["pdf_sha256"]
            if digest in known:
                continue
            matches = [(p, h) for p, h in actual if h == digest and p.startswith("runtime/public-evidence/")
                       and Path(p).name == digest + ".pdf"]
            if len(matches) != 1:
                raise ValueError("FUNDING_REVISION_MATRIX_SOURCE_CHANGED")
            expected.add(matches[0])
    if actual != expected:
        raise ValueError("FUNDING_REVISION_SOURCE_SET_CHANGED")


def _verify_parent(root, receipt, task_id):
    service = task.ParentCashTaskServiceV3(root)
    task_input, state, head = service._load(task_id, recover=False)
    # _load verified the entire numbered chain and its current pointer. Follow only
    # its verified previous links, including when the registered parent is historical.
    while head != receipt["parent_head"]:
        head = state["previous"]
        if head is None:
            raise ValueError("FUNDING_REVISION_PARENT_NOT_IN_CHAIN")
        state = service._bound(head)
    registered = task_input["spec_binding"]
    if registered != receipt["registered_spec"] or state["status"] != receipt["previous_task_status"]:
        raise ValueError("FUNDING_REVISION_PARENT_CHANGED")
    entry = _case_entry(root, registered)
    if (not entry or entry["symbol"] != receipt["symbol"]
            or receipt["case_package"] != entry["case_package_binding"]
            or receipt["distribution_receipt"] != entry["implemented_distribution_receipt_binding"]):
        raise ValueError("FUNDING_REVISION_REGISTRATION_CHANGED")
    return service._bound(registered)


# Only these reviewed compiler/kernel versions expose the diagnostic state below.
_DIAGNOSTIC_SOURCES = (
    (compiler, "acc15045890849cac15572bcdbb71634175b2423f642aee286cc19fbb6ffc2c5"),
    (kernel, "d0e8ffaf53a01a502e8cb98d22ca25d201584cd1b55fc0cd9878dd164cd7ee23"),
)


def _rejected_run(error, ordered, first):
    """Read the first scenario's result from the exact v2 compiler/cash-floor exception."""
    trace = error.__traceback__
    while trace and trace.tb_frame.f_code is not compiler.compile_source_bound_owner_cash_v2.__code__:
        trace = trace.tb_next
    if trace is None or trace.tb_frame.f_locals["spec"] is not ordered:
        raise ValueError("FUNDING_REASSESSMENT_DIAGNOSTIC_FRAME") from error
    frame = trace.tb_frame
    reserve = trace.tb_next
    step = reserve.tb_next if reserve else None
    if (not reserve or reserve.tb_frame.f_code is not compiler._reserve_annual_cash_before_optional_payout.__code__
            or not step or step.tb_next or step.tb_frame.f_code is not kernel._step.__code__):
        raise ValueError("FUNDING_REASSESSMENT_DIAGNOSTIC_FRAME") from error
    year = step.tb_frame.f_locals["year"]
    before = step.tb_frame.f_locals["before"]
    floor = step.tb_frame.f_locals["flow"]["cash_floor"]
    scheduled = step.tb_frame.f_locals["scheduled"]
    if (type(year) is not int or str(error) != f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}"
            or not all(isinstance(v, Decimal) and v.is_finite() for v in (before, floor, scheduled))
            or before >= floor):
        raise ValueError("FUNDING_REASSESSMENT_DIAGNOSTIC_VALUES") from error
    failed = frame.f_locals["name"]
    earlier = frame.f_locals["scenarios"]
    order = list(ordered["scenarios"])
    if (failed not in order or frame.f_locals["scenario"] is not ordered["scenarios"][failed]
            or list(earlier) != order[:order.index(failed)]):
        raise ValueError("FUNDING_REASSESSMENT_SCENARIO_IDENTITY") from error
    if first == failed:
        return dict(status="REJECTED", reason=str(error), year=year, before=str(before),
                    floor=str(floor), scheduled=str(scheduled))
    return dict(status="CALCULATED", per_share_value=earlier[first]["calculation"]["per_share_value"])


def _rerun_reassessment(root, spec, completed, distribution):
    for module, digest in _DIAGNOSTIC_SOURCES:
        data = Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
        if sha256(data).hexdigest() != digest:
            raise ValueError("FUNDING_REASSESSMENT_DIAGNOSTIC_VERSION")
    scenarios = spec["scenarios"]
    if set(scenarios) != {"bear", "base", "bull"}:
        raise ValueError("FUNDING_REASSESSMENT_THREE_SCENARIOS_REQUIRED")
    observations = {}
    for first in scenarios:
        names = [first, *(name for name in scenarios if name != first)]
        ordered = dict(spec, scenarios={name: scenarios[name] for name in names})
        try:
            compile_source_bound_owner_cash_v2(root=root, spec=ordered, now=completed,
                                               implemented_distribution=distribution)
        except ValueError as error:
            observations[first] = _rejected_run(error, ordered, first)
        else:
            raise ValueError("FUNDING_REASSESSMENT_REQUIRES_NEW_VERSION")
    return observations


def _compare_rows(claim, observed):
    rows = claim.get("scenario_rows")
    if (claim.get("status") != "REJECTED" or claim.get("current_research_range_adopted") is not False
            or not isinstance(rows, dict) or set(rows) != set(observed)
            or not any(row["status"] == "REJECTED" for row in observed.values())):
        raise ValueError("FUNDING_REASSESSMENT_SCOPE_CHANGED")
    for name, actual in observed.items():
        expected = dict(actual)
        if not isinstance(rows[name], dict):
            raise ValueError(f"FUNDING_REASSESSMENT_SCENARIO_CHANGED:{name}")
        if "scheduled" not in rows[name]:
            expected.pop("scheduled", None)
        if rows[name] != expected or ("year" in expected and type(rows[name]["year"]) is not int):
            raise ValueError(f"FUNDING_REASSESSMENT_SCENARIO_CHANGED:{name}")


def replay(root, task_id, receipt_sha256, now):
    """Read original inputs, compile all years, and compare the full shared-model output."""
    root = Path(root).resolve()
    if not re.fullmatch(r"rt-[a-f0-9]{32}", task_id) or not re.fullmatch(r"[a-f0-9]{64}", receipt_sha256):
        raise ValueError("FUNDING_REVISION_ID_INVALID")
    folder = root / "runtime" / "parent-cash-task-backed-receipts" / task_id / "funding-revisions" / receipt_sha256
    _checked_path(root, folder)
    receipt = _sibling(folder, "receipt", receipt_sha256)
    if (receipt["schema_version"] != SCHEMA or receipt["task_id"] != task_id
            or receipt["action"] != "no_order" or receipt["formal_eligibility"] is not False
            or receipt["provenance"] != "DETERMINISTIC_RESEARCH_REVISION"
            or receipt["current_comparable"] is not False):
        raise ValueError("FUNDING_REVISION_SCOPE_INVALID")
    registered = _verify_parent(root, receipt, task_id)
    revision = receipt["revision_spec"]["sha256"]
    spec = _sibling(folder, "spec", receipt["revision_spec"])
    stored = _sibling(folder, "valuation", receipt["valuation"])
    descriptor = _sibling(folder, "descriptor", receipt["descriptor"])
    matrix = (_sibling(folder, "financing-evidence", receipt["originals_matrix"])
              if "originals_matrix" in receipt else None)
    matrix_digest = receipt.get("originals_matrix", {}).get("sha256")
    def read_original(digest):
        return _sibling(folder, "source-matrix", {"file": f"source-matrix-{digest}.json", "sha256": digest})

    inputs = receipt["inputs"]
    contract = descriptor["source_contract"]
    verify_source_set(inputs, contract["raw_source_bindings"], spec["financing_revision"], matrix, matrix_digest, read_original)
    total = 0
    for pin in inputs:
        path = _checked_path(root, root / pin["path"])
        info = path.stat()
        total += info.st_size
        if not S_ISREG(info.st_mode) or not 0 < info.st_size <= 32 * 1024**2 or total > 128 * 1024**2:
            raise ValueError("FUNDING_REVISION_SOURCE_BINDING")
        with path.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != pin["sha256"]:
                raise ValueError("FUNDING_REVISION_SOURCE_CHANGED")
    at = datetime.fromisoformat(descriptor["point_in_time"]["computed_at"])
    completed = datetime.fromisoformat(receipt["completed_at"])
    basis = receipt["valuation_date"]
    if (any(t.utcoffset() is None for t in (at, completed, now)) or not at <= completed <= now
            or date.fromisoformat(basis).isoformat() != basis or date.fromisoformat(basis) > at.date()
            or not all(obj["valuation_date"] == basis for obj in (spec, stored, registered, descriptor["point_in_time"]))
            or not all(obj["symbol"] == receipt["symbol"] for obj in (registered, spec, stored, descriptor))
            or spec["financing_revision"]["source_spec"] != receipt["registered_spec"]):
        raise ValueError("FUNDING_REVISION_CONTEXT_CHANGED")
    compiled = compile_source_bound_owner_cash_v2(root=root, spec=spec, now=at,
                                                  implemented_distribution=receipt["distribution_receipt"])
    verify_source_set(inputs, compiled["source_bindings"], spec["financing_revision"], matrix, matrix_digest, read_original)
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
    if matrix is not None:
        _verify_debt_service(spec, matrix, stored["assumptions"]["scenario_calculations"])
    reassessment = receipt.get("current_reassessment")
    checked = None
    if "current_reassessment" in receipt:
        if (not isinstance(reassessment, dict) or reassessment.get("current_research_range_adopted") is not False
                or not isinstance(reassessment.get("reason"), str) or not reassessment["reason"].strip()
                or reassessment.get("status") not in ("UNAVAILABLE", "REJECTED")):
            raise ValueError("FUNDING_REASSESSMENT_SCOPE_CHANGED")
        updated = None
        if "revised_spec" in reassessment:
            updated = _sibling(folder, "reassessment-spec", reassessment["revised_spec"])
            # Reusing the historical compiler source set requires identical source selection.
            if ({k: v for k, v in updated.items() if k not in ("scenarios", "financing_revision")}
                    != {k: v for k, v in spec.items() if k not in ("scenarios", "financing_revision")}
                    or updated["financing_revision"]["source_spec"] != receipt["registered_spec"]):
                raise ValueError("FUNDING_REASSESSMENT_SCOPE_CHANGED")
            verify_source_set(inputs, compiled["source_bindings"], updated["financing_revision"], matrix, matrix_digest, read_original)
        if reassessment["status"] == "UNAVAILABLE":
            if reassessment.get("scenario_rows", {}) != {}:
                raise ValueError("FUNDING_REASSESSMENT_UNVERIFIED_ROWS")
            checked = dict(status="UNAVAILABLE", scenario_rows={}, current_research_range_adopted=False)
        else:
            if updated is None:
                raise ValueError("FUNDING_REASSESSMENT_SPEC_REQUIRED")
            if matrix is not None:
                _verify_debt_service(updated, matrix)
            observed = _rerun_reassessment(root, updated, completed, receipt["distribution_receipt"])
            _compare_rows(reassessment, observed)
            checked = dict(status="REJECTED", scenario_rows=observed, current_research_range_adopted=False)
    return dict(receipt_sha256=receipt_sha256, task_id=task_id, input_descriptor_sha256=current.input_sha256,
                valuation_date=basis, verified_source_count=len(inputs), current_reassessment=checked,
                values={name: row["calculation"]["per_share_value"] for name, row in compiled["scenarios"].items()},
                action="no_order", formal_eligibility=False, current_comparable=False)

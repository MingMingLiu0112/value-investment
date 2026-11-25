"""Seal eligible parent-cash valuations after work completes, outside GET handlers."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from pathlib import Path
from tempfile import mkdtemp, mkstemp

from .parent_cash_task_aggregate_receipt_v1 import build as build_aggregate_receipt
from .parent_cash_task_receipt_v3 import build_parent_cash_task_receipt
from .parent_cash_task_distribution_receipt_v1 import (
    build as build_distribution_receipt,
    replay as replay_task_receipt,
)
from ..product.common import require_inside


def valuation_receipt_path(root, task_id):
    directory = root / "runtime" / "parent-cash-task-backed-receipts"
    return require_inside(directory, directory / task_id / "receipt.json", "parent cash task receipt")


def valuation_blockage_path(root, task_id):
    receipt = valuation_receipt_path(root, task_id)
    return require_inside(receipt.parent, receipt.parent / "publication-blocked.json",
                          "parent cash publication blockage")


def _safe_publication_reason(reason):
    return re.fullmatch(
        r"(?:[A-Z0-9_]{3,120}|DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:[0-9]{4})",
        reason,
    ) is not None


def read_valuation_publication(root, task_id, task_head):
    """Read publication metadata only; a receipt always supersedes an old failure."""
    if valuation_receipt_path(root, task_id).is_file():
        return dict(valuation_receipt_status="SEALED_REPLAY_REQUIRED", valuation_blockage=None)
    path = valuation_blockage_path(root, task_id)
    missing = dict(valuation_receipt_status="NOT_SEALED", valuation_blockage=None)
    if not path.is_file():
        return missing
    if path.stat().st_size > 8192:
        raise ValueError("PARENT_TASK_PUBLICATION_STATUS_INVALID")
    row = json.loads(path.read_bytes())
    if (row.get("schema_version") != "parent-cash-publication-blockage-v1"
            or row.get("task_id") != task_id or row.get("status") != "BLOCKED"
            or row.get("action") != "no_order"
            or not _safe_publication_reason(str(row.get("reason_code", "")))):
        raise ValueError("PARENT_TASK_PUBLICATION_STATUS_INVALID")
    if row.get("task_record_binding") != task_head:
        return missing
    return dict(valuation_receipt_status="BLOCKED", valuation_blockage=row)


def _record_publication_blockage(root, task_id, head, error):
    reason = str(error)
    if not _safe_publication_reason(reason):
        reason = ("PARENT_TASK_PUBLICATION_IO_ERROR" if isinstance(error, OSError)
                  else "PARENT_TASK_PUBLICATION_VERIFICATION_FAILED")
    row = dict(schema_version="parent-cash-publication-blockage-v1", task_id=task_id,
               task_record_binding=head, status="BLOCKED", reason_code=reason,
               updated_at=datetime.now(timezone.utc).isoformat(), action="no_order")
    path = valuation_blockage_path(root, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = mkstemp(prefix=".publication-", suffix=".part", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(row, sort_keys=True).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _case_entry(root, spec_binding):
    registry = root / "config" / "parent-cash-task-case-bindings-v1.json"
    if not registry.is_file():
        return None
    entries = json.loads(registry.read_bytes())
    if entries["schema_version"] != "parent-cash-task-case-bindings-v1":
        raise ValueError("PARENT_TASK_CASE_REGISTRY_SCHEMA")
    entry = entries["specs"].get(spec_binding["sha256"])
    if entry is None:
        return None
    if entry["spec_binding"] != spec_binding:
        raise ValueError("PARENT_TASK_SPEC_BINDING_MISMATCH")
    return entry


def _case_binding(root, spec_binding):
    entry = _case_entry(root, spec_binding)
    return None if entry is None else entry["case_package_binding"]


def registered_cash_task_spec(service, symbol):
    root = Path(service.root).resolve()
    registry = root / "config" / "parent-cash-task-case-bindings-v1.json"
    if not registry.is_file():
        return None
    document = json.loads(registry.read_bytes())
    if document["schema_version"] != "parent-cash-task-case-bindings-v1":
        raise ValueError("PARENT_TASK_CASE_REGISTRY_SCHEMA")
    entries = document["specs"]
    active = document.get("active_spec_by_symbol", {})
    if not isinstance(active, dict):
        raise ValueError("PARENT_TASK_ACTIVE_SPEC_INVALID")
    if symbol in active:
        key = active[symbol]
        if not isinstance(key, str) or key not in entries:
            raise ValueError("PARENT_TASK_ACTIVE_SPEC_INVALID")
        entry = entries[key]
        if entry.get("symbol") != symbol or entry.get("spec_binding", {}).get("sha256") != key:
            raise ValueError("PARENT_TASK_ACTIVE_SPEC_INVALID")
    else:
        matches = [entry for entry in entries.values() if entry.get("symbol") == symbol]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("PARENT_TASK_AMBIGUOUS_COMPANY_BINDING")
        entry = matches[0]
    binding = entry["spec_binding"]
    preflight_parent_cash_task(service, binding, symbol=symbol)
    return binding


def preflight_parent_cash_task(service, spec_binding, *, symbol=None):
    """Verify the exact requested registration and pinned inputs before creation."""
    entry = _case_entry(Path(service.root).resolve(), spec_binding)
    if entry is None or not entry.get("case_package_binding"):
        raise ValueError("PARENT_TASK_CASE_BINDING_REQUIRED")
    case_binding = entry["case_package_binding"]
    spec = service._bound(spec_binding)
    case = service._bound(case_binding)
    issuer = spec.get("symbol")
    if (not issuer or (symbol is not None and issuer != symbol)
            or entry.get("symbol", issuer) != issuer
            or spec.get("action") != "no_order" or spec.get("model_applicable") is not True
            or case.get("symbol") != issuer or case.get("profile_id") != "quality_compounder"
            or case.get("schema_version") != "m1-valuation-package-v2"
            or case.get("research_case", {}).get("symbol") != issuer):
        raise ValueError("PARENT_TASK_CASE_PROFILE_OR_ISSUER_MISMATCH")
    distribution_binding = _distribution_binding(entry, spec)
    if distribution_binding is not None:
        from .parent_owner_distribution_successor_v2 import RECEIPT_SCHEMA
        receipt = service._bound(distribution_binding)
        if (receipt.get("schema_version") != RECEIPT_SCHEMA
                or receipt.get("symbol") != issuer or receipt.get("action") != "no_order"
                or receipt.get("formal_eligibility") is not False
                or receipt.get("successor_adopted") is not False
                or receipt.get("main_range_adopted") is not False):
            raise ValueError("PARENT_TASK_DISTRIBUTION_RECEIPT_INVALID")
    return case_binding, distribution_binding


def _distribution_binding(entry, research_spec):
    binding = entry.get("implemented_distribution_receipt_binding")
    if binding is None and research_spec.get("source_adapter_version") in {
        "UNNUMBERED_OFFICIAL_CNINFO_V1", "UNNUMBERED_OFFICIAL_CNINFO_V2",
    }:
        raise ValueError("PARENT_TASK_IMPLEMENTED_DISTRIBUTION_BINDING_REQUIRED")
    return binding


def run_and_seal_parent_cash_task(service, task_id):
    root = Path(service.root).resolve()
    directory = service._directory(task_id)
    with service._lock(directory):
        _, state, _ = service._load(task_id)
    if state["status"] != "SUCCEEDED":
        service.run(task_id)
    seal_completed_parent_cash_task(service, task_id)


def _verify_publication(root, binding, *, task_id, head, now):
    replay = replay_task_receipt(root=root, receipt_binding=binding, now=now)
    provenance = replay["provenance"]
    if (provenance["task_id"] != task_id or provenance["task_record_binding"] != head
            or replay["action"] != "no_order" or replay["formal_eligibility"] is not False):
        raise ValueError("PARENT_TASK_BUILT_RECEIPT_IDENTITY_MISMATCH")


def seal_completed_parent_cash_task(service, task_id):
    """Retry only deterministic publication, even if task state has changed."""
    root = Path(service.root).resolve()
    directory = service._directory(task_id)
    with service._lock(directory, "valuation-publication"):
        with service._lock(directory):
            spec, state, head = service._load(task_id)
        if state["status"] != "SUCCEEDED" or spec["mode"] != "LIVE_PARENT_CASH_V3":
            return
        retained = valuation_receipt_path(root, task_id)
        try:
            now = datetime.now(timezone.utc)
            if retained.exists():
                if not retained.is_file() or retained.stat().st_size > 64 * 1024:
                    raise ValueError("PARENT_TASK_RETAINED_RECEIPT_INVALID")
                binding = dict(path=retained.relative_to(root).as_posix(),
                               sha256=sha256(retained.read_bytes()).hexdigest())
                _verify_publication(root, binding, task_id=task_id, head=head, now=now)
                return
            case_binding, binding = preflight_parent_cash_task(service, spec["spec_binding"])
            retained.parent.mkdir(parents=True, exist_ok=True)
            attempt = Path(mkdtemp(prefix="valuation-attempt-", dir=retained.parent)) / "sealed"
            options = {} if binding is None else {"distribution_binding": binding}
            builder = build_parent_cash_task_receipt if binding is None else build_distribution_receipt
            if spec.get("gross_capex_plan_binding") is not None:
                if binding is None or spec.get("implemented_distribution_receipt_binding") != binding:
                    raise ValueError("GROSS_CAPEX_F1_TASK_OR_DISTRIBUTION_BINDING_MISMATCH")
                builder = build_aggregate_receipt
            built = builder(
                **options,
                root=root, task_id=task_id, task_head=head, case_package_binding=case_binding,
                output_dir=attempt, now=now,
            )
            built_path = require_inside(attempt, root / built["path"], "built parent cash receipt")
            _verify_publication(root, built, task_id=task_id, head=head, now=now)
            with service._lock(directory):
                _, current_state, current_head = service._load(task_id)
                if current_state["status"] != "SUCCEEDED" or current_head != head:
                    raise ValueError("PARENT_TASK_HEAD_CHANGED_BEFORE_PUBLICATION")
                if sha256(built_path.read_bytes()).hexdigest() != built["sha256"]:
                    raise ValueError("PARENT_TASK_BUILT_RECEIPT_HASH_MISMATCH")
                retained.hardlink_to(built_path)
        except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
            _record_publication_blockage(root, task_id, head, error)
            raise

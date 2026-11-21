"""Seal eligible parent-cash valuations after work completes, outside GET handlers."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import mkdtemp

from .parent_cash_task_receipt_v3 import build_parent_cash_task_receipt
from ..product.common import require_inside


def valuation_receipt_path(root, task_id):
    directory = root / "runtime" / "parent-cash-task-backed-receipts"
    return require_inside(directory, directory / task_id / "receipt.json", "parent cash task receipt")


def _case_binding(root, spec_binding):
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
    return entry["case_package_binding"]


def registered_cash_task_spec(service, symbol):
    root = Path(service.root).resolve()
    registry = root / "config" / "parent-cash-task-case-bindings-v1.json"
    if not registry.is_file():
        return None
    document = json.loads(registry.read_bytes())
    if document["schema_version"] != "parent-cash-task-case-bindings-v1":
        raise ValueError("PARENT_TASK_CASE_REGISTRY_SCHEMA")
    matches = [entry for entry in document["specs"].values() if entry.get("symbol") == symbol]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("PARENT_TASK_AMBIGUOUS_COMPANY_BINDING")
    binding = matches[0]["spec_binding"]
    case_binding = _case_binding(root, binding)
    if case_binding != matches[0]["case_package_binding"]:
        raise ValueError("PARENT_TASK_CASE_BINDING_MISMATCH")
    spec = service._bound(binding)
    case = service._bound(case_binding)
    if (spec.get("symbol") != symbol or spec.get("action") != "no_order"
            or spec.get("model_applicable") is not True
            or case.get("symbol") != symbol or case.get("profile_id") != "quality_compounder"
            or case.get("schema_version") != "m1-valuation-package-v2"
            or case.get("research_case", {}).get("symbol") != symbol):
        raise ValueError("PARENT_TASK_CASE_PROFILE_OR_ISSUER_MISMATCH")
    return binding


def run_and_seal_parent_cash_task(service, task_id):
    service.run(task_id)
    root = Path(service.root).resolve()
    directory = service._directory(task_id)
    with service._lock(directory, "valuation-publication"):
        with service._lock(directory):
            spec, state, head = service._load(task_id)
        if state["status"] != "SUCCEEDED" or spec["mode"] != "LIVE_PARENT_CASH_V3":
            return
        retained = valuation_receipt_path(root, task_id)
        if retained.exists():
            return
        case_binding = _case_binding(root, spec["spec_binding"])
        if case_binding is None:
            return
        retained.parent.mkdir(parents=True, exist_ok=True)
        attempt = Path(mkdtemp(prefix="valuation-attempt-", dir=retained.parent)) / "sealed"
        built = build_parent_cash_task_receipt(
            root=root, task_id=task_id, task_head=head, case_package_binding=case_binding,
            output_dir=attempt, now=datetime.now(timezone.utc),
        )
        receipt = (root / built["path"]).read_bytes()
        if sha256(receipt).hexdigest() != built["sha256"]:
            raise ValueError("PARENT_TASK_BUILT_RECEIPT_HASH_MISMATCH")
        # Same-volume hard link publishes an already complete file atomically
        # and refuses to replace a retained result.
        retained.hardlink_to(root / built["path"])

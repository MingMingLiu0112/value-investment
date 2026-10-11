"""Verify a current workbook registration against immutable publication evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
import re
from typing import Any


# These names belong to the persisted native evidence contract, not a renderer.
MANAGED_NATIVE_SHEETS = (
    "01_今日", "02_机会", "决策过程", "03_公司", "04_我的组合", "05_事件", "06_系统与审计",
)


def _bound_bytes(root: Path, value: Any, digest: Any) -> bytes:
    if (not isinstance(value, str) or not value.strip() or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        raise ValueError("CANONICAL_PUBLICATION_BINDING_INVALID")
    path = (root / value).resolve()
    if not path.is_relative_to(root / "runtime") or not path.is_file():
        raise ValueError("CANONICAL_PUBLICATION_EVIDENCE_MISMATCH")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("CANONICAL_PUBLICATION_EVIDENCE_MISMATCH")
    return raw


def _bound_json(root: Path, value: Any, digest: Any) -> dict[str, Any]:
    try:
        document = json.loads(_bound_bytes(root, value, digest).decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("CANONICAL_PUBLICATION_EVIDENCE_INVALID") from error
    if not isinstance(document, dict) or document.get("action") != "no_order":
        raise ValueError("CANONICAL_PUBLICATION_EVIDENCE_INVALID")
    return document


def verify_native_workbook_receipt(root: Path, native: dict[str, Any], expected: str) -> None:
    """Require named managed pages and the actual pinned native PDF exports."""
    sheets = native.get("sheets")
    if (native.get("schema_version") != "m7-product-ux-trial-wps-receipt-v1"
            or native.get("status") != "passed" or native.get("readonly_open") != "PASS"
            or native.get("read_only") is not True or native.get("action") != "no_order"
            or native.get("workbook_sha256") != expected
            or not isinstance(sheets, dict) or set(sheets) != set(MANAGED_NATIVE_SHEETS)):
        raise ValueError("CANONICAL_PUBLICATION_WPS_RECEIPT_MISMATCH")
    exports = set()
    for sheet in sheets.values():
        if (not isinstance(sheet, dict) or not isinstance(sheet.get("pdf"), str)
                or Path(sheet["pdf"]).suffix.lower() != ".pdf"
                or not isinstance(sheet.get("used_range"), str)
                or re.fullmatch(r"[A-Z]+[1-9][0-9]*:[A-Z]+[1-9][0-9]*", sheet["used_range"]) is None):
            raise ValueError("CANONICAL_PUBLICATION_WPS_RECEIPT_MISMATCH")
        export = (root / sheet["pdf"]).resolve()
        if export in exports:
            raise ValueError("CANONICAL_PUBLICATION_WPS_RECEIPT_MISMATCH")
        exports.add(export)
        _bound_bytes(root, sheet["pdf"], sheet.get("pdf_sha256"))


def _publication_quote_floor(root: Path, sources: dict[str, Any]) -> date:
    """Replay only quote evidence actually declared by the pinned published snapshot."""
    from ...quote_session_conversion import quote_snapshot_from_bundle_file
    from ...quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE

    binding = sources.get("publication_input_binding")
    if not isinstance(binding, dict):
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    handoff = _bound_json(root, binding.get("path"), binding.get("sha256"))
    if handoff.get("schema_version") != "research-publication-input-v1":
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    snapshot = handoff.get("snapshot")
    if (not isinstance(snapshot, dict) or snapshot.get("action") != "no_order"
            or snapshot.get("schema_version") != "m7-product-workbench-v1"):
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    declared = sources.get("source_bindings")
    if not isinstance(declared, list) or any(not isinstance(item, dict) for item in declared):
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    if any(not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str)
           for item in declared):
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    pairs = {(item["path"], item["sha256"]) for item in declared}
    # Publication handoffs persist the typed snapshot, not the raw product payload.
    evidence = snapshot.get("audit_evidence")
    if not isinstance(evidence, list):
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    dates = []
    for record in evidence:
        if not isinstance(record, dict) or record.get("artifact_type") != "QUOTE_SESSION_REVALIDATED":
            continue
        if record.get("action") != "no_order" or (record.get("path"), record.get("sha256")) not in pairs:
            raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
        raw = _bound_bytes(root, record.get("path"), record.get("sha256"))
        try:
            bundle = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND") from error
        if not isinstance(bundle, dict) or not isinstance(bundle.get("references"), dict):
            raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
        for symbol in bundle["references"]:
            quote = quote_snapshot_from_bundle_file(root / record["path"], root,
                symbol=symbol, ref_id=record["evidence_id"], expected_sha256=record["sha256"])
            if quote.status == QUOTE_STATUS_VERIFIED_CLOSE and quote.quote_date is not None:
                dates.append(quote.quote_date)
    if not dates:
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_UNBOUND")
    return max(dates)


def verify_workbook_publication(root: Path, contract: dict[str, Any]) -> date | None:
    """V5 registrations must bind both the publication and subsequent native check."""
    if contract.get("schema_version") != "m7-current-trial-workbook-v5":
        return
    if contract.get("action") != "no_order":
        raise ValueError("CANONICAL_PUBLICATION_BINDING_INVALID")
    binding = contract.get("current_publication")
    if not isinstance(binding, dict):
        raise ValueError("CANONICAL_PUBLICATION_BINDING_MISSING")
    root = root.resolve()

    def read(role: str) -> dict[str, Any]:
        return _bound_json(root, binding.get(role), binding.get(role + "_sha256"))

    published, native = read("receipt"), read("wps_receipt")
    expected = contract.get("canonical_workbook_sha256")
    if (published.get("schema_version") != "canonical-reviewed-research-publication-v1"
            or published.get("status") != "PUBLISHED_PENDING_WPS_VERIFICATION"
            or published.get("canonical_written") is not True
            or published.get("after_sha256") != expected
            or published.get("candidate_sha256") != expected
            or published.get("before_sha256") != contract.get("previous_canonical_workbook_sha256")
            or published.get("backup_sha256") != published.get("before_sha256")
            or published.get("workbook_source") != "WORKBOOK_PATH"
            or published.get("workbook_path_unchanged") is not True):
        raise ValueError("CANONICAL_PUBLICATION_RECEIPT_MISMATCH")
    verify_native_workbook_receipt(root, native, expected)
    sources = _bound_json(root, published.get("source_bindings_path"), published.get("source_bindings_sha256"))
    if (sources.get("schema_version") != "existing-workbench-preview-bindings-v1"
            or sources.get("integrated_canonical") is not True
            or sources.get("historical_preview") is not True
            or sources.get("canonical_written") is not False
            or sources.get("workbook_sha256") != expected
            or sources.get("output_manifest_sha256") != published.get("preservation_proof_sha256")):
        raise ValueError("CANONICAL_PUBLICATION_SOURCE_BINDINGS_MISMATCH")
    floor = _publication_quote_floor(root, sources)
    if binding.get("quote_observation_as_of") != floor.isoformat():
        raise ValueError("CANONICAL_PUBLICATION_QUOTE_FLOOR_MISMATCH")
    backup_value = published.get("backup")
    if not isinstance(backup_value, str):
        raise ValueError("CANONICAL_PUBLICATION_BACKUP_MISMATCH")
    backup = (root / backup_value).resolve()
    if (not backup.is_relative_to(root / "runtime/workbook-backups") or not backup.is_file()
            or hashlib.sha256(backup.read_bytes()).hexdigest() != published["backup_sha256"]):
        raise ValueError("CANONICAL_PUBLICATION_BACKUP_MISMATCH")
    return floor

"""Verify a current workbook registration against immutable publication evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


def verify_workbook_publication(root: Path, contract: dict[str, Any]) -> None:
    """V5 registrations must bind both the publication and subsequent native check."""
    if contract.get("schema_version") != "m7-current-trial-workbook-v5":
        return
    binding = contract.get("current_publication")
    if not isinstance(binding, dict):
        raise ValueError("CANONICAL_PUBLICATION_BINDING_MISSING")
    root = root.resolve()

    def read(role: str) -> dict[str, Any]:
        relative, digest = binding.get(role), binding.get(role + "_sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError("CANONICAL_PUBLICATION_BINDING_INVALID")
        path = (root / relative).resolve()
        if (not path.is_relative_to(root / "runtime") or not path.is_file()
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("CANONICAL_PUBLICATION_EVIDENCE_MISMATCH")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict) or value.get("action") != "no_order":
            raise ValueError("CANONICAL_PUBLICATION_EVIDENCE_INVALID")
        return value

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
    if (native.get("schema_version") != "m7-product-ux-trial-wps-receipt-v1"
            or native.get("status") != "passed" or native.get("readonly_open") != "PASS"
            or native.get("read_only") is not True or native.get("workbook_sha256") != expected
            or len(native.get("sheets", {})) != 7):
        raise ValueError("CANONICAL_PUBLICATION_WPS_RECEIPT_MISMATCH")
    backup_value = published.get("backup")
    if not isinstance(backup_value, str):
        raise ValueError("CANONICAL_PUBLICATION_BACKUP_MISMATCH")
    backup = (root / backup_value).resolve()
    if (not backup.is_relative_to(root / "runtime/workbook-backups") or not backup.is_file()
            or hashlib.sha256(backup.read_bytes()).hexdigest() != published["backup_sha256"]):
        raise ValueError("CANONICAL_PUBLICATION_BACKUP_MISMATCH")

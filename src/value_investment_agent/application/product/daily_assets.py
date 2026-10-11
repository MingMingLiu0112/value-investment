"""Inventory and recover pinned daily research inputs without approving research."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Any

from .common import require_inside, sha256_file


def inspect_daily_case_assets(*, root: Path, case: dict[str, Any],
                             agent_mode: str = "offline") -> dict[str, Any]:
    root = root.resolve()
    recoveries = {}
    recovery_records = []
    if "recovery_manifest" in case:
        manifest = require_inside(root, root / case["recovery_manifest"], "recovery manifest")
        if manifest.is_file() and sha256_file(manifest) != case.get("recovery_manifest_sha256"):
            raise ValueError("recovery manifest hash mismatch")
        recovered = json.loads(manifest.read_text(encoding="utf-8-sig")) if manifest.is_file() else None
        if recovered is not None:
            _load_scoped_recoveries(root, case, recovered, recoveries, recovery_records)
    if "publication_input" in case:
        publication = require_inside(root, root / case["publication_input"], "publication asset")
        if publication.is_file() and sha256_file(publication) == case.get("publication_input_sha256"):
            cached = json.loads(publication.read_text(encoding="utf-8-sig"))
            for item in cached.get("verified_source_recoveries", []):
                original = str(item["original_path"]).replace("\\", "/")
                key = (original, item["expected_sha256"])
                if key in recoveries and recoveries[key] != item["recovered_path"]:
                    raise ValueError("conflicting original recovery mappings")
                recoveries[key] = item["recovered_path"]
    return _inventory(root, case, agent_mode, recoveries, recovery_records)


def _load_scoped_recoveries(root, case, recovered, recoveries, recovery_records):
    if (recovered.get("schema_version") != "daily-original-recovery-v1"
            or recovered.get("action") != "no_order"
            or recovered.get("package_sha256") != case.get("package_sha256")
            or recovered.get("research_approval") is not False):
        raise ValueError("unsupported recovery manifest scope")
    package = require_inside(root, root / case["package"], "recovery package")
    if not package.is_file():
        return
    if sha256_file(package) != case["package_sha256"]:
        raise ValueError("recovery package hash mismatch")
    if json.loads(package.read_text(encoding="utf-8-sig")).get("symbol") != recovered.get("symbol"):
        raise ValueError("recovery manifest symbol mismatch")
    for item in recovered.get("recovered_originals", []):
        original = require_inside(root, root / item["original_path"], "recovery original")
        retained = require_inside(root, root / item["recovered_path"], "retained original")
        digest = item["expected_sha256"]
        key = (original.relative_to(root).as_posix(), digest)
        if key in recoveries or not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise ValueError("invalid or duplicate recovered original")
        if retained.is_file() and sha256_file(retained) != digest:
            raise ValueError("retained original hash mismatch")
        recoveries[key] = retained.relative_to(root).as_posix()
        recovery_records.append({**item,
            "original_actual_sha256": sha256_file(original) if original.is_file() else None,
            "status": "IDENTICAL_ORIGINAL_BOUND_WITHOUT_OVERWRITE" if retained.is_file() else "RETAINED_ORIGINAL_MISSING",
            "research_approval": False})


def _inventory(root, case, agent_mode, recoveries, recovery_records):
    pending = []
    for role in ("package", "schedule_request", "publication_input", "previous_workbench",
                 "mock_responses", "recovery_manifest", "agent_excerpts", "financial_review_manifest"):
        if role == "mock_responses" and agent_mode != "mock":
            continue
        if role not in case:
            if role in {"package", "schedule_request"}:
                raise ValueError(f"daily case requires {role}")
            continue
        pending.append((case[role], case.get(role + "_sha256"), root, role,
                        role in {"package", "schedule_request", "recovery_manifest"}, False))
    assets = {}
    scanned = set()
    while pending:
        location, expected, base, role, required, allow_recovery = pending.pop()
        if not isinstance(location, str) or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            if role.startswith("financial_review_manifest"):
                assets[role] = {"path": str(location), "role": role, "expected_sha256": expected,
                    "actual_sha256": None, "status": "INVALID_BINDING", "required_for_research": False}
                continue
            raise ValueError(f"invalid pinned asset: {role}")
        if allow_recovery:
            location = recoveries.get((location.replace("\\", "/"), expected), location)
        try:
            path = require_inside(root, base / location.replace("\\", "/"), "daily research asset")
        except ValueError:
            if not role.startswith("financial_review_manifest"):
                raise
            assets[role] = {"path": location, "role": role, "expected_sha256": expected,
                "actual_sha256": None, "status": "INVALID_BINDING", "required_for_research": False}
            continue
        relative = path.relative_to(root).as_posix()
        if relative in assets:
            if assets[relative]["expected_sha256"] != expected:
                raise ValueError("conflicting asset fingerprints: " + relative)
            if assets[relative]["required_for_research"] or not required:
                continue
        if len(assets) >= 5000:
            raise ValueError("daily asset dependency limit exceeded")
        actual = sha256_file(path) if path.is_file() else None
        status = "VERIFIED_BYTES" if actual == expected else "MISSING" if actual is None else "HASH_MISMATCH"
        assets[relative] = {"path": relative, "role": role, "expected_sha256": expected,
                            "actual_sha256": actual, "status": status,
                            "required_for_research": required}
        if status != "VERIFIED_BYTES" or path.suffix.lower() != ".json" or (relative, required) in scanned:
            continue
        scanned.add((relative, required))
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError):
            if not role.startswith("financial_review_manifest"):
                raise
            assets[relative]["status"] = "INVALID_DOCUMENT"
            continue
        if role == "financial_review_manifest":
            if not isinstance(document, dict) or not isinstance(document.get("outputs"), dict):
                assets[relative]["status"] = "INVALID_DOCUMENT"
                continue
            for name in ("facts.json", "report.md"):
                pending.append((name, (document.get("outputs") or {}).get(name), path.parent,
                                role + ":" + name, False, False))
        values = [(document, None)]
        while values:
            value, key = values.pop()
            if isinstance(value, list):
                values.extend((item, key) for item in value)
            elif isinstance(value, dict):
                values.extend((item, name) for name, item in value.items())
                digest = value.get("sha256")
                if digest is None:
                    continue
                for field in ("path", "location", "local_path"):
                    target = value.get(field)
                    if not isinstance(target, str) or target.startswith(("https://", "http://")):
                        continue
                    normalized = target.replace("\\", "/")
                    parent = path.parent if key == "supersedes" and "/" not in normalized else root
                    child_role = (role + ":" + str(key or "source")
                                  if role.startswith("financial_review_manifest") else str(key or "source"))
                    pending.append((normalized, digest, parent, child_role, required, True))
    rows = [assets[key] for key in sorted(assets)]
    blockers = [row for row in rows if row["status"] != "VERIFIED_BYTES"]
    return {"schema_version": "daily-research-asset-index-v1", "action": "no_order",
            "status": "BLOCKED_RESEARCH_ASSETS" if blockers else "FILE_INTEGRITY_VERIFIED_NOT_RESEARCH_APPROVAL",
            "dependency_inventory_complete": not blockers, "assets": rows,
            "blockers": blockers, "verified_original_recoveries": recovery_records, "recovery": {
                "command_option": "--recover-assets-from PROJECT_RELATIVE_DIRECTORY",
                "method": "Restore identical SHA-256 bytes from the same relative paths; never overwrite existing files.",
                "missing_json": "Reproduce the original registered recipe or restore its exact original bytes; do not fabricate replacement input.",
                "missing_original": "Restore the retained original or independently retrieve the official original and require its registered SHA-256."}}


def recover_daily_case_assets(*, root: Path, case: dict[str, Any], source_root: Path,
                             agent_mode: str = "offline") -> dict[str, Any]:
    source_root = require_inside(root, source_root, "asset recovery source")
    restored = []
    # Newly restored JSON may reveal additional dependencies, so re-inventory.
    for _ in range(32):
        index = inspect_daily_case_assets(root=root, case=case, agent_mode=agent_mode)
        progressed = False
        for row in index["blockers"]:
            if row["status"] != "MISSING":
                continue
            target = require_inside(root, root / row["path"], "asset recovery target")
            source = require_inside(source_root, source_root / row["path"], "asset recovery original")
            if not source.is_file() or sha256_file(source) != row["expected_sha256"]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            created = False
            try:
                with source.open("rb") as incoming, target.open("xb") as outgoing:
                    created = True
                    shutil.copyfileobj(incoming, outgoing)
            except BaseException:
                if created:
                    target.unlink(missing_ok=True)
                raise
            if sha256_file(target) != row["expected_sha256"]:
                target.unlink()
                raise ValueError("asset changed during recovery: " + row["path"])
            restored.append(row["path"])
            progressed = True
        if not progressed:
            index["restored_paths"] = restored
            return index
    raise ValueError("asset recovery depth limit exceeded")

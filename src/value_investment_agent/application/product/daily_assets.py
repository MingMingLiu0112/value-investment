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
    if "publication_input" in case:
        publication = require_inside(root, root / case["publication_input"], "publication asset")
        if publication.is_file() and sha256_file(publication) == case.get("publication_input_sha256"):
            cached = json.loads(publication.read_text(encoding="utf-8-sig"))
            for item in cached.get("verified_source_recoveries", []):
                original = str(item["original_path"]).replace("\\", "/")
                recoveries[(original, item["expected_sha256"])] = item["recovered_path"]
    pending = []
    for role in ("package", "schedule_request", "publication_input", "previous_workbench",
                 "mock_responses"):
        if role == "mock_responses" and agent_mode != "mock":
            continue
        if role not in case:
            if role in {"package", "schedule_request"}:
                raise ValueError(f"daily case requires {role}")
            continue
        pending.append((case[role], case.get(role + "_sha256"), root, role,
                        role in {"package", "schedule_request"}, False))
    assets = {}
    scanned = set()
    while pending:
        location, expected, base, role, required, allow_recovery = pending.pop()
        if not isinstance(location, str) or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            raise ValueError(f"invalid pinned asset: {role}")
        if allow_recovery:
            location = recoveries.get((location.replace("\\", "/"), expected), location)
        path = require_inside(root, base / location.replace("\\", "/"), "daily research asset")
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
        document = json.loads(path.read_text(encoding="utf-8-sig"))
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
                    pending.append((normalized, digest, parent, str(key or "source"), required, True))
    rows = [assets[key] for key in sorted(assets)]
    blockers = [row for row in rows if row["status"] != "VERIFIED_BYTES"]
    return {"schema_version": "daily-research-asset-index-v1", "action": "no_order",
            "status": "BLOCKED_RESEARCH_ASSETS" if blockers else "FILE_INTEGRITY_VERIFIED_NOT_RESEARCH_APPROVAL",
            "dependency_inventory_complete": not blockers, "assets": rows,
            "blockers": blockers, "recovery": {
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

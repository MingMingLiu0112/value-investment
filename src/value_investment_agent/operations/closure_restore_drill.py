"""Isolated encrypted backup and restore drill for the current public chain.

The drill never touches the live runtime, the canonical workbook or PostgreSQL.
It selects the verified publication pointer and every source binding the packet
declares, packages them with the existing AES-256-GCM tool, decrypts them into a
separate directory under `.tmp`, and re-verifies hashes and publication ids.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
from typing import Any

from value_investment_agent.backup_security import decrypt_package, encrypt_package

SCHEMA_VERSION = "closure-restore-drill-v1"
ACTION_NO_ORDER = "no_order"
DEFAULT_POLICY = Path("config/m6-backup-security-v1.json")
RESEARCH_POINTERS = (
    ("config/current-research-funnel-audit.json", "manifest_path", "manifest_sha256"),
    (
        "config/current-hotspot-structure-validation.json",
        "manifest_path",
        "manifest_sha256",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(items):
    return list(dict.fromkeys(items))


def _env_value(root: Path, name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = root / ".env"
    if not env.is_file():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def _copy_item(root: Path, source_root: Path, relative: str) -> dict[str, Any] | None:
    source = root / relative
    if not source.is_file():
        return None
    target = source_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "path": relative,
        "sha256": _sha256(source),
        "size_bytes": source.stat().st_size,
    }


def _current_research_artifacts(root: Path) -> list[str]:
    """Select and verify the current research pointers and their bound outputs."""
    wanted = ["config/current-research-drafts.json"]
    for relative, path_field, hash_field in RESEARCH_POINTERS:
        pointer_path = root / relative
        if not pointer_path.is_file():
            continue
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if pointer.get("action") != ACTION_NO_ORDER:
            raise ValueError(f"current research pointer is not no_order: {relative}")
        manifest_relative = pointer.get(path_field)
        manifest_sha256 = pointer.get(hash_field)
        if not isinstance(manifest_relative, str) or not isinstance(manifest_sha256, str):
            raise ValueError(f"current research pointer is incomplete: {relative}")
        manifest_path = root / manifest_relative
        if not manifest_path.is_file() or _sha256(manifest_path) != manifest_sha256:
            raise ValueError(f"current research manifest hash mismatch: {manifest_relative}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        wanted.extend([relative, manifest_relative])
        for output in (manifest.get("outputs") or {}).values():
            output_relative = output.get("path") if isinstance(output, dict) else None
            output_sha256 = output.get("sha256") if isinstance(output, dict) else None
            if not isinstance(output_relative, str) or not isinstance(output_sha256, str):
                raise ValueError(f"current research manifest output is incomplete: {manifest_relative}")
            output_path = root / output_relative
            if not output_path.is_file() or _sha256(output_path) != output_sha256:
                raise ValueError(f"current research output hash mismatch: {output_relative}")
            wanted.append(output_relative)
    draft_pointer = root / "config/current-research-drafts.json"
    if draft_pointer.is_file():
        drafts = json.loads(draft_pointer.read_text(encoding="utf-8"))
        if drafts.get("action") != ACTION_NO_ORDER:
            raise ValueError("current research draft pointer is not no_order")
        for draft in (drafts.get("drafts") or {}).values():
            draft_relative = draft.get("path") if isinstance(draft, dict) else None
            draft_sha256 = draft.get("sha256") if isinstance(draft, dict) else None
            if not isinstance(draft_relative, str) or not isinstance(draft_sha256, str):
                raise ValueError("current research draft binding is incomplete")
            draft_path = root / draft_relative
            if not draft_path.is_file() or _sha256(draft_path) != draft_sha256:
                raise ValueError(f"current research draft hash mismatch: {draft_relative}")
            wanted.append(draft_relative)
    return _unique(wanted)


def run(root: Path, *, drill_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = (drill_root or root / ".tmp" / "closure-restore-drill" / stamp).resolve()
    source_root = base / "source"
    source_root.mkdir(parents=True, exist_ok=False)

    pointer_path = root / "config" / "current-daily-public-snapshot.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer.get("status") != "VERIFIED" or pointer.get("action") != ACTION_NO_ORDER:
        raise ValueError("current pointer is not a verified no_order publication")
    packet_path = root / pointer["packet_path"]
    if _sha256(packet_path) != pointer.get("packet_sha256"):
        raise ValueError("packet hash differs from the verified pointer")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    wanted = [
        pointer["packet_path"],
        pointer["receipt_path"],
        "config/current-daily-public-snapshot.json",
        "config/current-quote-bridge.json",
        "config/current-trial-workbook.json",
    ]
    for binding in packet.get("source_bindings") or []:
        if binding.get("present") and binding.get("path"):
            wanted.append(str(binding["path"]))
    research_wanted = _current_research_artifacts(root)
    wanted.extend(research_wanted)
    copied = []
    missing = []
    for relative in _unique(wanted):
        item = _copy_item(root, source_root, relative)
        if item is None:
            missing.append(relative)
        else:
            copied.append(item)

    key_path = base / "keys" / "backup.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(secrets.token_hex(32), encoding="utf-8")

    config_paths = [
        root / "config" / "current-daily-public-snapshot.json",
        root / "config" / "current-quote-bridge.json",
        root / "config" / "current-trial-workbook.json",
    ]
    workbook_raw = _env_value(root, "WORKBOOK_PATH")
    workbook = Path(workbook_raw) if workbook_raw else None
    release_paths = [workbook] if workbook and workbook.is_file() else []

    package = base / "packages" / "closure-public-backup.vib"
    package.parent.mkdir(parents=True, exist_ok=True)
    package_result = encrypt_package(
        source_root,
        package,
        key_path,
        root / DEFAULT_POLICY,
        config_paths=config_paths,
        release_paths=release_paths,
        code_version="closure-w2",
    )

    restored = base / "restored"
    restored_result = decrypt_package(package, restored, key_path, root / DEFAULT_POLICY)
    mismatches = []
    for item in copied:
        restored_file = restored / "source" / item["path"]
        if not restored_file.is_file() or _sha256(restored_file) != item["sha256"]:
            mismatches.append(item["path"])

    restored_pointer = json.loads(
        (restored / "source" / "config" / "current-daily-public-snapshot.json").read_text(encoding="utf-8")
    )
    restored_packet_path = restored / "source" / restored_pointer["packet_path"]
    restored_packet = json.loads(restored_packet_path.read_text(encoding="utf-8"))
    publication_match = (
        restored_packet.get("publication_id") == pointer.get("publication_id")
        and _sha256(restored_packet_path) == pointer.get("packet_sha256")
    )

    workbook_check = None
    if release_paths:
        trial = json.loads((root / "config" / "current-trial-workbook.json").read_text(encoding="utf-8"))
        restored_workbook = restored / "release" / release_paths[0].name
        workbook_check = {
            "present": restored_workbook.is_file(),
            "sha256_matches_pointer": restored_workbook.is_file()
            and _sha256(restored_workbook) == trial.get("canonical_workbook_sha256"),
        }

    corrupt = base / "packages" / "corrupted-copy.vib"
    shutil.copy2(package, corrupt)
    raw = bytearray(corrupt.read_bytes())
    if raw:
        raw[len(raw) // 2] ^= 0xFF
        corrupt.write_bytes(bytes(raw))
    corrupted_rejected = False
    corruption_error = None
    try:
        decrypt_package(corrupt, base / "restored-corrupt", key_path, root / DEFAULT_POLICY)
    except Exception as error:  # noqa: BLE001 - the point is that any failure is recorded
        corrupted_rejected = True
        corruption_error = type(error).__name__

    drill_pass = (
        not mismatches
        and not missing
        and publication_match
        and corrupted_rejected
        and (workbook_check is None or (workbook_check["present"] and workbook_check["sha256_matches_pointer"]))
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "action": ACTION_NO_ORDER,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "drill_root": str(base.relative_to(root)),
        "publication_id": pointer.get("publication_id"),
        "packet_sha256": pointer.get("packet_sha256"),
        "files": {
            "source_copied": len(copied),
            "source_missing": missing,
            "config_files": len(config_paths),
            "release_files": len(release_paths),
            "research_files": len(research_wanted),
        },
        "package": {
            "sha256": package_result["sha256"],
            "manifest_sha256": package_result["manifest_sha256"],
            "backup_id": package_result["backup_id"],
            "key_id": package_result["key_id"],
            "key_separated": True,
        },
        "restore": {
            "verified_files": len(restored_result["verified_files"]),
            "mismatches": mismatches,
            "publication_match": publication_match,
            "workbook": workbook_check,
        },
        "corruption": {
            "rejected": corrupted_rejected,
            "error_type": corruption_error,
        },
        "verdicts": {
            "RESTORE_DRILL_PASS": "PASS" if drill_pass else "FAIL",
            "OFF_MACHINE_BACKUP_READY": "PASS" if package_result["sha256"] and release_paths else "PARTIAL",
            "REAL_OFF_MACHINE_COPY_CONFIRMED": "NOT_CONFIRMED",
        },
    }
    return receipt

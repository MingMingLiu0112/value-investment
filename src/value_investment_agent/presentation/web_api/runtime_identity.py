"""Read-only identities for the running API and served Web build."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_head(root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value) else None


def source_worktree_dirty(root: Path) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "src/value_investment_agent",
             "web/src", "web/.umirc.ts", "web/scripts", "web/package.json"],
            cwd=root, capture_output=True, text=True, timeout=3, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())


def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_web_build(root: Path) -> dict | None:
    try:
        value = json.loads((root / "web/dist/build-info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(value, dict) or value.get("schema_version") != "web-build-identity-v1"
            or not isinstance(value.get("commit"), str)
            or not isinstance(value.get("built_at"), str)
            or not isinstance(value.get("source_dirty"), bool)):
        return None
    return value


def runtime_identity(root: Path, *, backend_head: str | None,
                     backend_module: Path, backend_module_sha: str | None) -> dict:
    current_head = git_head(root)
    source_dirty = source_worktree_dirty(root)
    web = read_web_build(root)
    backend_disk_sha = sha256(backend_module)
    reasons = []
    if current_head is None or backend_head is None or backend_head != current_head:
        reasons.append("BACKEND_RESTART_OR_GIT_CHECK_REQUIRED")
    if source_dirty is None or source_dirty:
        reasons.append("SOURCE_WORKTREE_DIRTY_OR_UNVERIFIED")
    if backend_module_sha is None or backend_module_sha != backend_disk_sha:
        reasons.append("BACKEND_SOURCE_CHANGED_ON_DISK")
    if web is None:
        reasons.append("WEB_BUILD_IDENTITY_MISSING")
    elif web["commit"] != current_head or web["source_dirty"]:
        reasons.append("WEB_REBUILD_REQUIRED")
    return {
        "schema_version": "runtime-identity-v1", "action": "no_order",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "MATCHED" if not reasons else "MISMATCH",
        "reasons": reasons,
        "current_source_head": current_head,
        "source_worktree_dirty": source_dirty,
        "backend_loaded_head": backend_head,
        "backend_module_sha256_loaded": backend_module_sha,
        "backend_module_sha256_on_disk": backend_disk_sha,
        "web_build": web,
        "web_index_sha256": sha256(root / "web/dist/index.html"),
    }

"""Read-only identities for the running API and served Web build."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping


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


def config_worktree_changes(root: Path) -> dict[str, list[str]] | None:
    """Split config changes into data pointers and behavior-affecting files.

    ``config/current-*.json`` are publication/data pointers. Updating them on a
    verified trading day is normal data life, not source tampering. Any other
    config change alters behavior and is reported separately.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", "config"],
            cwd=root, capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    behavior: list[str] = []
    data: list[str] = []
    for line in result.stdout.splitlines():
        raw = line[3:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        path = raw.strip('"')
        if re.fullmatch(r"config/current-[^/]+\.json", path):
            data.append(path)
        else:
            behavior.append(path)
    return {"behavior": behavior, "data": data}


def data_freshness(dates: Mapping | None, *, today: date | None = None) -> dict:
    """Report data age separately from code identity.

    This is a weekday-age heuristic for display. Exchange holidays are not
    modeled here; a holiday-aware calendar belongs to the trading pipeline.
    """
    dates = dates if isinstance(dates, Mapping) else {}
    raw = dates.get("quote_trade_date")
    if not isinstance(raw, str):
        return {"status": "UNVERIFIED", "reason": "QUOTE_TRADE_DATE_MISSING"}
    try:
        quote = date.fromisoformat(raw)
    except ValueError:
        return {"status": "UNVERIFIED", "reason": "QUOTE_TRADE_DATE_INVALID"}
    evaluated = today or datetime.now().astimezone().date()
    age = 0
    cursor = quote
    while cursor < evaluated:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            age += 1
    return {
        "status": "FRESH" if age <= 1 else "STALE",
        "quote_trade_date": quote.isoformat(),
        "evaluated_on": evaluated.isoformat(),
        "weekday_age": age,
        "calendar_scope": "WEEKDAY_ONLY_EXCHANGE_HOLIDAYS_NOT_MODELED",
    }


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
    code_status = "MATCHED" if not reasons else "MISMATCH"

    config = config_worktree_changes(root)
    config_reasons: list[str] = []
    if config is None:
        if (root / "config").exists():
            config_reasons.append("CONFIG_WORKTREE_UNVERIFIED")
            config_status = "UNVERIFIED"
        else:
            config_status = "MATCHED"
    elif config["behavior"]:
        config_reasons.append("BEHAVIOR_CONFIG_DIRTY")
        config_status = "DIRTY"
    else:
        config_status = "MATCHED"
    return {
        "schema_version": "runtime-identity-v2", "action": "no_order",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "MATCHED" if code_status == "MATCHED" and config_status == "MATCHED" else "MISMATCH",
        "code_status": code_status,
        "config_status": config_status,
        "reasons": reasons + config_reasons,
        "current_source_head": current_head,
        "source_worktree_dirty": source_dirty,
        "backend_loaded_head": backend_head,
        "backend_module_sha256_loaded": backend_module_sha,
        "backend_module_sha256_on_disk": backend_disk_sha,
        "web_build": web,
        "web_index_sha256": sha256(root / "web/dist/index.html"),
        "config_changes": config or {"behavior": [], "data": []},
    }

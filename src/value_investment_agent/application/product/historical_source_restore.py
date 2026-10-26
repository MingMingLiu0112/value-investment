"""Restore package-bound historical implementation bytes from a fixed Git commit."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Mapping, Any

from .common import require_inside, sha256_file


HISTORICAL_IMPLEMENTATION_COMMIT = "72a52874f5cad5b5b74b9ae8790cce3b22c581c0"
ARCHIVABLE_RESEARCH_PREFIXES = ("src/", "config/", "docs/", "scripts/")


def verify_or_restore_package_sources(
    root: Path, payload: Mapping[str, Any], *, restore_dir: Path, create: bool = True,
) -> tuple[tuple[Path, str], ...]:
    """Verify evidence and retain small repository research dependencies by hash.

    Runtime originals stay at their evidence paths. Repository code/config/docs used
    by a newly generated v3 candidate are copied into its immutable closure, so a
    later checkout does not reinterpret old research through changed live files.
    Historical ``src/`` bytes can additionally be recovered from the bound baseline.
    Retained blobs are evidence only and are never imported or executed.
    """
    root = root.resolve()
    restore_dir = require_inside(root, restore_dir, "historical source restore")
    sources = payload.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise ValueError("source-bound package requires local sources")
    verified: list[tuple[Path, str]] = []
    seen: set[str] = set()
    resolved_by_identity: dict[tuple[str, str], Path] = {}
    for source in sources:
        if (not isinstance(source, Mapping) or not isinstance(source.get("id"), str)
                or not isinstance(source.get("local_path"), str)):
            raise ValueError("source-bound package requires explicit local source identity")
        if source["id"] in seen:
            raise ValueError("source-bound package source ids must be unique")
        seen.add(source["id"])
        expected = source.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("source-bound package source hash is invalid")
        expected = expected.lower()
        relative = source["local_path"].replace("\\", "/")
        if ".." in Path(relative).parts:
            raise ValueError("package source path cannot traverse outside the repository")
        identity = (relative, expected)
        previously_resolved = resolved_by_identity.get(identity)
        if previously_resolved is not None:
            verified.append((previously_resolved, expected))
            continue
        live = require_inside(root, root / relative, "package source bytes")
        retained = restore_dir / f"{expected}.blob"
        retain_by_hash = relative.startswith(ARCHIVABLE_RESEARCH_PREFIXES)
        if retained.is_file():
            if sha256_file(retained) != expected:
                raise ValueError("historical implementation restore drift")
            if retain_by_hash:
                resolved_by_identity[identity] = retained
                verified.append((retained, expected))
                continue
        live_matches = live.is_file() and sha256_file(live) == expected
        if live_matches and not retain_by_hash:
            resolved_by_identity[identity] = live
            verified.append((live, expected))
            continue
        if live_matches and retain_by_hash:
            if create:
                retained.parent.mkdir(parents=True, exist_ok=True)
                if not retained.exists():
                    with retained.open("xb") as handle:
                        handle.write(live.read_bytes())
            if retained.is_file() and sha256_file(retained) == expected:
                resolved_by_identity[identity] = retained
                verified.append((retained, expected))
            else:
                # Backward compatibility for candidates produced before repository
                # dependencies were retained. Drift still fails closed below.
                resolved_by_identity[identity] = live
                verified.append((live, expected))
            continue
        if not relative.startswith("src/"):
            raise ValueError("non-code source drift requires a retained candidate blob")
        process = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob",
             f"{HISTORICAL_IMPLEMENTATION_COMMIT}:{relative}"],
            check=False, capture_output=True,
        )
        if process.returncode or hashlib.sha256(process.stdout).hexdigest() != expected:
            raise ValueError("historical implementation bytes are not recoverable from baseline commit")
        restored = retained
        if create:
            restored.parent.mkdir(parents=True, exist_ok=True)
            if restored.exists():
                if sha256_file(restored) != expected:
                    raise ValueError("historical implementation restore drift")
            else:
                with restored.open("xb") as handle:
                    handle.write(process.stdout)
        if not restored.is_file() or sha256_file(restored) != expected:
            raise ValueError("historical implementation restore is unavailable")
        resolved_by_identity[identity] = restored
        verified.append((restored, expected))
    return tuple(verified)

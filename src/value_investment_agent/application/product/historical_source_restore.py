"""Restore package-bound historical implementation bytes from a fixed Git commit."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Mapping, Any

from .common import require_inside, sha256_file


HISTORICAL_IMPLEMENTATION_COMMIT = "72a52874f5cad5b5b74b9ae8790cce3b22c581c0"


def verify_or_restore_package_sources(
    root: Path, payload: Mapping[str, Any], *, restore_dir: Path, create: bool = True,
) -> tuple[tuple[Path, str], ...]:
    """Verify live evidence; restore only drifted ``src/`` bytes from the bound baseline.

    The restored blob is evidence of the predecessor implementation, not executing
    code. Current v3 implementation identities are bound separately.
    """
    root = root.resolve()
    restore_dir = require_inside(root, restore_dir, "historical source restore")
    sources = payload.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise ValueError("source-bound package requires local sources")
    verified: list[tuple[Path, str]] = []
    seen: set[str] = set()
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
        live = require_inside(root, root / source["local_path"], "package source bytes")
        if live.is_file() and sha256_file(live) == expected:
            verified.append((live, expected))
            continue
        relative = source["local_path"].replace("\\", "/")
        if not relative.startswith("src/") or ".." in Path(relative).parts:
            raise ValueError("non-code source drift cannot use historical restoration")
        process = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob",
             f"{HISTORICAL_IMPLEMENTATION_COMMIT}:{relative}"],
            check=False, capture_output=True,
        )
        if process.returncode or hashlib.sha256(process.stdout).hexdigest() != expected:
            raise ValueError("historical implementation bytes are not recoverable from baseline commit")
        restored = restore_dir / f"{expected}.blob"
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
        verified.append((restored, expected))
    return tuple(verified)

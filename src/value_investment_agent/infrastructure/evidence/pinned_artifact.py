"""Read retained artifacts without weakening their pinned-content contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Mapping


def read_pinned_artifact_bytes(
    path: Path, *, root: Path, pins: Mapping[Path, str],
) -> bytes:
    if path.is_file():
        return path.read_bytes()
    if path not in pins:
        raise FileNotFoundError(path)
    relative = path.relative_to(root).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"], cwd=root,
        capture_output=True, check=True,
    )
    content = result.stdout
    actual = hashlib.sha256(content).hexdigest()
    if actual != pins[path]:
        raise ValueError(f"archived artifact {relative} hash mismatch: {actual}")
    return content


def load_pinned_json(
    path: Path, *, root: Path, pins: Mapping[Path, str], expected_type: type,
) -> dict | list:
    content = read_pinned_artifact_bytes(path, root=root, pins=pins)
    expected = pins[path]
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError(f"{path.relative_to(root)} changed: expected {expected}, got {actual}")
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, expected_type):
        label = "object" if expected_type is dict else "array"
        raise ValueError(f"Expected JSON {label}: {path}")
    if isinstance(payload, dict) and "action" in payload and payload["action"] != "no_order":
        raise ValueError(f"{path.relative_to(root)} is not no_order")
    return payload

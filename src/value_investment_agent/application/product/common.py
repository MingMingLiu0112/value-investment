"""Shared fail-closed helpers for generic product commands."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


ACTION_NO_ORDER = "no_order"
PRODUCT_COMMAND_SCHEMA = "generic-product-command-v1"
_SYMBOL = re.compile(r"^[0-9]{6}$")


def normalize_symbol(value: str) -> str:
    symbol = str(value).strip()
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("symbol must contain exactly six digits")
    return symbol


def load_json_value(path: Path, label: str) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from error
    return payload


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    payload = load_json_value(path, label)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_inside(root: Path, path: Path, label: str) -> Path:
    target = path.resolve()
    project_root = root.resolve()
    if not target.is_relative_to(project_root):
        raise ValueError(f"{label} must remain under the project root")
    return target


def _native_path(path: Path) -> str:
    """Return a Windows extended-length path when the standard API would truncate."""
    raw = os.path.abspath(os.fspath(path))
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        if raw.startswith("\\\\"):
            return "\\\\?\\UNC\\" + raw[2:]
        return "\\\\?\\" + raw
    return raw


def write_new_bytes(path: Path, data: bytes) -> None:
    """Create an immutable file atomically without leaving a partial target."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    path = Path(path)
    target = _native_path(path)
    if os.path.exists(target):
        raise FileExistsError(f"refusing to overwrite: {path}")
    parent = _native_path(path.parent)
    os.makedirs(parent, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".part", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # A hard link publishes the complete inode and fails atomically if
            # another writer won the immutable-output race.
            os.link(_native_path(temporary), target)
        except FileExistsError as error:
            raise FileExistsError(f"refusing to overwrite: {path}") from error
    finally:
        try:
            os.unlink(_native_path(temporary))
        except FileNotFoundError:
            pass


def write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    write_new_bytes(Path(path), encoded)


def receipt(
    *,
    command: str,
    symbol: str,
    input_hashes: Mapping[str, str],
    output_path: Path | None,
    output_bytes: bytes | None,
) -> dict[str, Any]:
    return {
        "schema_version": PRODUCT_COMMAND_SCHEMA,
        "command": command,
        "symbol": symbol,
        "action": ACTION_NO_ORDER,
        "input_sha256": dict(sorted(input_hashes.items())),
        "output_path": str(output_path) if output_path is not None else None,
        "output_sha256": (
            sha256_bytes(output_bytes) if output_bytes is not None else None
        ),
    }


def encode_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

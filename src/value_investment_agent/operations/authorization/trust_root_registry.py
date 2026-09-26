"""Pinned authorization trust-root registry.

Authorization capabilities (M5 ACTUAL approval capabilities and M6 operational
authorization proofs) are only accepted when the trust root they were verified
against appears in a pinned registry.  Verifying a signature with a caller
supplied public key is not enough: without pinning, any caller could mint a
fresh keypair and self-authorize.

The committed registry is intentionally empty until a real operator key is
registered by an explicit, reviewed change, so ACTUAL/M6 authorization is
fail-closed by default. Tests use a process-local test hook to select a
temporary registry file; no environment variable or caller-supplied path can
redirect the production trust-registry lookup.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping

TRUST_REGISTRY_VERSION = "authorization-trust-root-registry-v1"
DEFAULT_TRUST_REGISTRY_PATH = (
    Path(__file__).resolve().parents[4] / "config" / "authorization-trust-roots-v1.json"
)
_TEST_REGISTRY_PATH: Path | None = None


class TrustRootNotPinnedError(ValueError):
    """Raised when a trust root is absent from the pinned registry."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def trust_root_fingerprint(trust_root: object) -> str:
    """Return the canonical SHA-256 fingerprint of a trust root document."""
    if not isinstance(trust_root, Mapping):
        raise ValueError("authorization trust root must be an object")
    return hashlib.sha256(_canonical(dict(trust_root))).hexdigest()


def _validated_test_registry_path(path: Path) -> Path:
    """Validate a test-only registry path without accepting environment data."""
    try:
        resolved = Path(path).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
    except OSError as error:
        raise ValueError("test trust-registry path is not valid") from error
    if not resolved.is_relative_to(temp_root):
        raise ValueError("test trust-registry path must stay in the temporary directory")
    return resolved


def _set_test_trust_registry(path: Path | None) -> None:
    """Set the process-local registry used only by test fixtures."""
    global _TEST_REGISTRY_PATH
    _TEST_REGISTRY_PATH = None if path is None else _validated_test_registry_path(path)


@contextmanager
def _use_test_trust_registry(path: Path) -> Iterator[None]:
    """Temporarily replace the process-local test registry."""
    global _TEST_REGISTRY_PATH
    previous = _TEST_REGISTRY_PATH
    _set_test_trust_registry(path)
    try:
        yield
    finally:
        _TEST_REGISTRY_PATH = previous


def trust_registry_path() -> Path:
    return _TEST_REGISTRY_PATH or DEFAULT_TRUST_REGISTRY_PATH


def pinned_trust_root_fingerprints() -> frozenset[str]:
    """Load the pinned fingerprints, failing closed when unavailable."""
    path = trust_registry_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return frozenset()
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(raw, Mapping) or raw.get("schema_version") != TRUST_REGISTRY_VERSION:
        return frozenset()
    pinned = raw.get("pinned_trust_root_sha256")
    if not isinstance(pinned, list):
        return frozenset()
    fingerprints: set[str] = set()
    for value in pinned:
        if not isinstance(value, str):
            return frozenset()
        text = value.strip().lower()
        if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
            return frozenset()
        fingerprints.add(text)
    return frozenset(fingerprints)


def is_pinned_trust_root(trust_root: object) -> bool:
    try:
        fingerprint = trust_root_fingerprint(trust_root)
    except ValueError:
        return False
    return fingerprint in pinned_trust_root_fingerprints()


def require_pinned_trust_root(trust_root: object) -> str:
    fingerprint = trust_root_fingerprint(trust_root)
    if fingerprint not in pinned_trust_root_fingerprints():
        raise TrustRootNotPinnedError(
            "authorization trust root is not pinned by the trust root registry"
        )
    return fingerprint


__all__ = [
    "DEFAULT_TRUST_REGISTRY_PATH",
    "TRUST_REGISTRY_VERSION",
    "TrustRootNotPinnedError",
    "is_pinned_trust_root",
    "pinned_trust_root_fingerprints",
    "require_pinned_trust_root",
    "trust_registry_path",
    "trust_root_fingerprint",
]

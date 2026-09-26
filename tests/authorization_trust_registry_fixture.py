"""Test-only pinned trust-root registry.

Production code reads the committed ``config/authorization-trust-roots-v1.json``
registry, which stays empty until a real operator key is registered. Tests use
an explicit process-local hook to a temporary registry file so a synthetic
fixture can be pinned. That is what makes the negative tests meaningful: a
freshly generated keypair is *not* pinned and must be rejected by the default
verification path.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import tempfile
from pathlib import Path
from typing import Any, Iterator

from value_investment_agent.operations.authorization.trust_root_registry import (
    TRUST_REGISTRY_VERSION,
    _set_test_trust_registry,
    _use_test_trust_registry,
    trust_root_fingerprint,
)

_STATE: dict[str, Any] = {"path": None, "pinned": []}


def _write() -> None:
    path = _STATE["path"]
    assert isinstance(path, Path)
    payload = {
        "schema_version": TRUST_REGISTRY_VERSION,
        "note": "temporary test registry",
        "pinned_trust_root_sha256": sorted(_STATE["pinned"]),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def configure_test_trust_registry() -> Path:
    """Point the process-local test hook at a temporary registry file."""
    if _STATE["path"] is None:
        directory = Path(tempfile.mkdtemp(prefix="via-trust-registry-"))
        _STATE["path"] = directory / "trust-roots.json"
        _STATE["pinned"] = []
        _write()
    _set_test_trust_registry(_STATE["path"])
    return _STATE["path"]


def reset_test_trust_registry() -> Path:
    """Start each test with a fresh temporary registry and pin set."""
    _STATE["path"] = None
    _STATE["pinned"] = []
    return configure_test_trust_registry()


@contextmanager
def use_test_trust_registry(path: Path) -> Iterator[None]:
    """Temporarily use an explicit test registry for one test block."""
    with _use_test_trust_registry(path):
        yield


def pin_test_trust_root(trust_root: object) -> str:
    """Pin one synthetic trust root for the duration of the test session."""
    configure_test_trust_registry()
    fingerprint = trust_root_fingerprint(trust_root)
    if fingerprint not in _STATE["pinned"]:
        _STATE["pinned"].append(fingerprint)
        _write()
    return fingerprint


def pinned_test_registry_fingerprints() -> frozenset[str]:
    configure_test_trust_registry()
    return frozenset(_STATE["pinned"])


__all__ = [
    "configure_test_trust_registry",
    "pin_test_trust_root",
    "pinned_test_registry_fingerprints",
    "reset_test_trust_registry",
    "use_test_trust_registry",
]

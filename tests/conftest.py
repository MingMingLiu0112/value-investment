"""Shared pytest configuration."""
from __future__ import annotations

import hashlib

import pytest

from authorization_trust_registry_fixture import (
    clear_test_trust_registry,
    reset_test_trust_registry,
)


@pytest.fixture(autouse=True)
def _isolate_test_trust_registry(
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
):
    """Prevent synthetic pins from leaking into the next test."""
    registry_dir = (
        tmp_path_factory.getbasetemp()
        / "trust-registries"
        / hashlib.sha256(request.node.nodeid.encode("utf-8")).hexdigest()
    )
    reset_test_trust_registry(registry_dir)
    try:
        yield
    finally:
        clear_test_trust_registry()

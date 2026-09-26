"""Shared pytest configuration."""
from __future__ import annotations

from authorization_trust_registry_fixture import configure_test_trust_registry


def pytest_configure(config) -> None:  # noqa: ARG001 - pytest hook signature
    # Every test process uses a temporary pinned trust-root registry.  The
    # committed production registry stays empty and fail-closed.
    configure_test_trust_registry()

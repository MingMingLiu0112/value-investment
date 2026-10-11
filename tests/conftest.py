"""Shared pytest configuration."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from authorization_trust_registry_fixture import (
    clear_test_trust_registry,
    reset_test_trust_registry,
)


@pytest.fixture
def synthetic_pending_candidate_clock(monkeypatch):
    """Opt-in candidate clock; signing, expiry and production clocks stay live."""
    from value_investment_agent.application.product import pending_research_candidate

    fixed = datetime(2026, 10, 11, 4, tzinfo=timezone.utc)

    class SyntheticCandidateClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=None) if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(pending_research_candidate, 'datetime', SyntheticCandidateClock)
    return fixed


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

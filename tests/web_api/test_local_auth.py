"""Unit tests for the local operator authorization primitives (WEB-D3 P0.2)."""
from __future__ import annotations

import pytest

from value_investment_agent.presentation.web_api.local_auth import (
    LocalAuthorizationError,
    LocalOperatorSession,
    host_header_allowed,
    origin_allowed,
)


def test_host_header_must_match_the_bound_loopback_port():
    assert host_header_allowed("127.0.0.1:8001", port=8001)
    assert host_header_allowed("localhost:8001", port=8001)
    assert host_header_allowed("[::1]:8001", port=8001)
    assert not host_header_allowed("127.0.0.1:8002", port=8001)
    assert not host_header_allowed("127.0.0.1", port=8001)
    assert not host_header_allowed("127.0.0.1.evil.example:8001", port=8001)
    assert not host_header_allowed("evil.example:8001", port=8001)
    assert not host_header_allowed("127.0.0.1:8001/path", port=8001)
    assert not host_header_allowed("user@127.0.0.1:8001", port=8001)
    assert not host_header_allowed("", port=8001)
    assert not host_header_allowed(None, port=8001)


def test_origin_must_be_exactly_the_workbench_origin():
    assert origin_allowed("http://127.0.0.1:8001", port=8001)
    assert origin_allowed("http://localhost:8001", port=8001)
    assert origin_allowed("https://localhost:8001", port=8001)
    assert not origin_allowed("http://127.0.0.1:9999", port=8001)
    assert not origin_allowed("http://localhost.evil.example:8001", port=8001)
    assert not origin_allowed("https://evil.example", port=8001)
    assert not origin_allowed("file:///etc/passwd", port=8001)
    assert not origin_allowed("null", port=8001)
    assert not origin_allowed(None, port=8001)


def test_session_starts_locked_and_unlocks_only_with_the_launcher_secret():
    now = [1000.0]
    secret = "launcher-secret"
    session = LocalOperatorSession(bootstrap_secret=secret, ttl_seconds=60.0, clock=lambda: now[0])
    assert session.token == ""
    assert not session.unlocked
    assert not session.accepts("0" * 64)
    with pytest.raises(LocalAuthorizationError) as rejected:
        session.unlock("not-the-secret")
    assert rejected.value.code == "LOCAL_UNLOCK_REJECTED"
    assert session.token == ""

    first = session.unlock(secret)
    assert session.accepts(first)
    assert session.unlocked
    assert not session.accepts("0" * 64)
    assert not session.accepts(None)

    session.invalidate()
    assert not session.accepts(first)
    assert session.token == ""
    assert not session.unlocked
    second = session.unlock(secret)
    assert second != first
    assert session.accepts(second)
    now[0] += 61.0
    assert not session.accepts(second)
    assert session.token == ""


def test_session_without_a_launcher_secret_can_never_unlock():
    session = LocalOperatorSession(ttl_seconds=60.0)
    assert not session.has_bootstrap_secret
    with pytest.raises(LocalAuthorizationError) as rejected:
        session.unlock("anything")
    assert rejected.value.code == "LOCAL_AUTHORIZATION_REQUIRED"
    assert session.token == ""

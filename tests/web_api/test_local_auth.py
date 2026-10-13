"""Unit tests for the local operator authorization primitives (WEB-D2 P0.1)."""
from __future__ import annotations

from value_investment_agent.presentation.web_api.local_auth import (
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


def test_session_tokens_rotate_invalidate_and_expire():
    now = [1000.0]
    session = LocalOperatorSession(ttl_seconds=60.0, clock=lambda: now[0])
    first = session.token
    assert session.accepts(first)
    assert not session.accepts("0" * 64)
    assert not session.accepts(None)
    second = session.rotate()
    assert second != first
    assert not session.accepts(first)
    assert session.accepts(second)
    session.invalidate()
    assert not session.accepts(second)
    third = session.rotate()
    now[0] += 61.0
    assert not session.accepts(third)

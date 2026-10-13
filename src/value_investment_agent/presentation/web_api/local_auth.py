"""Local operator authorization for the private portfolio API (WEB-D2 P0.1).

The private write surface is single-user and loopback-only. Checking that an
``Origin``/``Referer`` hostname is "localhost" is not authorization: every page
in the user's browser can reach 127.0.0.1, and any local process can call the
API directly. This module adds the missing layers:

* the TCP peer address must be loopback;
* the ``Host`` header must be exactly the bound loopback host and port;
* ``Origin``/``Referer``, when present, must match that origin exactly;
* private reads and writes must carry the process-scoped session token handed
  out by ``GET /api/v1/private/session``.

The token only lives in server memory. Restarting the service, or calling
logout, invalidates it; it is never written to disk, logs or Git.
"""
from __future__ import annotations

import ipaddress
import secrets
import time
from typing import Callable
from urllib.parse import urlsplit

from fastapi import Request

SESSION_HEADER = "x-local-session"
SESSION_TTL_SECONDS = 12 * 60 * 60.0
TOKEN_BYTES = 32

HOST_REJECTED = "HOST_REJECTED"
CLIENT_NOT_LOOPBACK = "CLIENT_NOT_LOOPBACK"
ORIGIN_REJECTED = "ORIGIN_REJECTED"
AUTHORIZATION_REQUIRED = "LOCAL_AUTHORIZATION_REQUIRED"


class LocalAuthorizationError(Exception):
    """A private request did not prove it came from the local operator."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def is_loopback_name(value: str | None) -> bool:
    if not value:
        return False
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value.casefold() == "localhost"


def _authority(value: str | None):
    if not value:
        return None
    try:
        parsed = urlsplit("//" + value)
        _ = parsed.port  # an invalid port raises ValueError here
    except ValueError:
        return None
    return parsed


def host_header_allowed(value: str | None, *, port: int) -> bool:
    """The Host header must name the loopback interface and port we bound."""
    parsed = _authority(value)
    if parsed is None or parsed.username or parsed.password or parsed.path:
        return False
    if not is_loopback_name(parsed.hostname):
        return False
    return (parsed.port if parsed.port is not None else 80) == port


def origin_allowed(value: str | None, *, port: int) -> bool:
    """Browser origins must be exactly the workbench origin, scheme included."""
    if value is None:
        return False
    try:
        parsed = urlsplit(value)
        explicit = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not is_loopback_name(parsed.hostname):
        return False
    default = 443 if parsed.scheme == "https" else 80
    return (explicit if explicit is not None else default) == port


class LocalOperatorSession:
    """A single process-scoped bearer token for the local operator."""

    def __init__(
        self,
        *,
        ttl_seconds: float = SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._token = ""
        self._expires_at = 0.0
        self.rotate()

    @property
    def token(self) -> str:
        return self._token

    def rotate(self) -> str:
        self._token = secrets.token_hex(TOKEN_BYTES)
        self._expires_at = self._clock() + self.ttl_seconds
        return self._token

    def ensure_active(self) -> str:
        """Return a usable token, minting a fresh one after logout or expiry."""
        if not self._token or self._clock() >= self._expires_at:
            return self.rotate()
        return self._token

    def invalidate(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    def accepts(self, presented: str | None) -> bool:
        if not presented or not self._token:
            return False
        if self._clock() >= self._expires_at:
            return False
        return secrets.compare_digest(presented, self._token)


def authorize(
    request: Request,
    *,
    session: LocalOperatorSession,
    port: int,
    require_token: bool = True,
) -> None:
    """Raise LocalAuthorizationError unless the caller may act as the operator."""
    if request.headers.get("sec-fetch-site", "").casefold() == "cross-site":
        raise LocalAuthorizationError(ORIGIN_REJECTED, "跨站请求被拒绝")
    peer = request.client.host if request.client else None
    if not is_loopback_name(peer):
        raise LocalAuthorizationError(CLIENT_NOT_LOOPBACK, "私人接口只接受本机回环连接")
    if not host_header_allowed(request.headers.get("host"), port=port):
        raise LocalAuthorizationError(HOST_REJECTED, f"Host 不是本机工作台 127.0.0.1:{port}")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if origin is not None:
        if not origin_allowed(origin, port=port):
            raise LocalAuthorizationError(ORIGIN_REJECTED, "Origin 与工作台不同源")
    elif referer is not None and not origin_allowed(referer, port=port):
        raise LocalAuthorizationError(ORIGIN_REJECTED, "Referer 与工作台不同源")
    if require_token and not session.accepts(request.headers.get(SESSION_HEADER)):
        raise LocalAuthorizationError(
            AUTHORIZATION_REQUIRED,
            "缺少或无效的本地操作会话，请刷新工作台页面重新授权",
        )

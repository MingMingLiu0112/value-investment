"""Local operator authorization for the private portfolio API (WEB-D3 P0.2).

The private write surface is single-user and loopback-only. Checking that an
``Origin``/``Referer`` hostname is "localhost" is not authorization: every page
in the user's browser can reach 127.0.0.1, and any local process can call the
API directly. This module adds the missing layers:

* the TCP peer address must be loopback;
* the ``Host`` header must be exactly the bound loopback host and port;
* ``Origin``/``Referer``, when present, must match that origin exactly;
* the workbench starts locked: the launcher mints a per-run bootstrap secret
  and hands it to the browser through the URL fragment, and the server only
  ever *verifies* it - no anonymous endpoint returns or mints a token;
* ``POST /api/v1/private/session/unlock`` exchanges that secret for the
  process-scoped session token;
* private reads and writes must carry the session token on every request.

The bootstrap secret and the session token only live in server memory. Logout
leaves the workbench locked, restarting the service generates a new secret that
invalidates every old session, and neither value is written to disk, logs or
Git.
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
BOOTSTRAP_ENV = "VALUE_INVESTMENT_WEB_BOOTSTRAP"

HOST_REJECTED = "HOST_REJECTED"
CLIENT_NOT_LOOPBACK = "CLIENT_NOT_LOOPBACK"
ORIGIN_REJECTED = "ORIGIN_REJECTED"
AUTHORIZATION_REQUIRED = "LOCAL_AUTHORIZATION_REQUIRED"
UNLOCK_REJECTED = "LOCAL_UNLOCK_REJECTED"


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
    """A locked-by-default session unlocked only by the launcher secret.

    ``unlock`` is the only path that mints a bearer token, and it requires the
    per-run secret that the launcher passes to both the server process and the
    browser URL fragment. Nothing mints implicitly, so logout and restart are
    real revocations rather than a re-fetch away from the previous token.
    """

    def __init__(
        self,
        *,
        bootstrap_secret: str | None = None,
        ttl_seconds: float = SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._bootstrap_secret = bootstrap_secret or ""
        self._token = ""
        self._expires_at = 0.0

    @property
    def token(self) -> str:
        return self._token if self._is_active() else ""

    @property
    def unlocked(self) -> bool:
        return self._is_active()

    @property
    def has_bootstrap_secret(self) -> bool:
        return bool(self._bootstrap_secret)

    def _is_active(self) -> bool:
        return bool(self._token) and self._clock() < self._expires_at

    def unlock(self, presented: str | None) -> str:
        """Exchange the launcher's per-run secret for a session token."""
        if not self._bootstrap_secret:
            raise LocalAuthorizationError(
                AUTHORIZATION_REQUIRED,
                "工作台未配置启动凭证，请通过 scripts/current/start_web_workbench.ps1 启动",
            )
        if not presented or not secrets.compare_digest(presented, self._bootstrap_secret):
            raise LocalAuthorizationError(
                UNLOCK_REJECTED, "启动凭证无效或已失效，请重新运行启动脚本"
            )
        return self.rotate()

    def rotate(self) -> str:
        self._token = secrets.token_hex(TOKEN_BYTES)
        self._expires_at = self._clock() + self.ttl_seconds
        return self._token

    def invalidate(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    def accepts(self, presented: str | None) -> bool:
        if not presented or not self._is_active():
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

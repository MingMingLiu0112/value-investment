"""Local-only HTTP adapter for the private portfolio journal.

Every route is deliberately thin: it checks the request origin, delegates to
`PrivatePortfolioService`, and maps domain exceptions onto the frozen contract in
`docs/current/web-private-api-contract.md`. No cash, cost, sellable-share or PnL
arithmetic is allowed to live here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.portfolio.private_portfolio_service import (
    JournalConflict,
    JournalValidationError,
    PrivateJournal,
    PrivatePortfolioService,
    PrivateStoreUnavailable,
    resolve_private_root,
)

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})
ORIGIN_REJECTED = "ORIGIN_REJECTED"
VALIDATION_FAILED = "VALIDATION_FAILED"


def _host_is_local(value: str) -> bool:
    host = urlsplit(value).hostname
    return host is not None and host.casefold() in LOCAL_HOSTS


def origin_allowed(request: Request) -> bool:
    """Reject browsers on any other site, keep non-browser local callers working."""
    if request.headers.get("sec-fetch-site", "").casefold() == "cross-site":
        return False
    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if value is not None:
            return _host_is_local(value)
    return True


def _refusal() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"action": "no_order", "status": ORIGIN_REJECTED,
                 "detail": "Origin/Referer 不是本机工作台"},
    )


def disconnected_view(*, reason: str, blockers: tuple[str, ...]) -> dict:
    return {
        "action": "no_order",
        "status": "NOT_CONNECTED",
        "revision": 0,
        "as_of": None,
        "cash_cny": None,
        "realized_pnl_cny": None,
        "positions": [],
        "trades": [],
        "policy": None,
        "pending_draft": None,
        "latest_snapshot": None,
        "valuation": {"status": "NOT_CONNECTED", "reason": reason},
        "blockers": list(blockers),
    }


def portfolio_connection(project: Path) -> str:
    """Report only the connection state; never leak amounts or positions."""
    try:
        records = PrivatePortfolioService(
            PrivateJournal(resolve_private_root(repository_root=project))).records()
    except PrivateStoreUnavailable:
        return "UNAVAILABLE"
    except JournalValidationError:
        return "INVALID"
    return "CONNECTED" if records else "NOT_CONNECTED"


def register_private_routes(api: FastAPI, project: Path) -> None:
    def service() -> PrivatePortfolioService:
        return PrivatePortfolioService(PrivateJournal(resolve_private_root(repository_root=project)))

    def emit(call: Callable[[], tuple[dict, str]]):
        try:
            payload, digest = call()
        except PrivateStoreUnavailable as error:
            return JSONResponse(status_code=503, content={
                "action": "no_order", "status": "PRIVATE_ROOT_UNAVAILABLE", "detail": str(error)})
        except JournalConflict as error:
            return JSONResponse(status_code=409, content={
                "action": "no_order", "status": error.code, "detail": str(error)})
        except JournalValidationError as error:
            return JSONResponse(status_code=422, content={
                "action": "no_order", "status": VALIDATION_FAILED, "detail": str(error)})
        body = dict(payload)
        body["record_sha256"] = digest
        return body

    @api.get("/api/v1/portfolio")
    def portfolio_view():
        try:
            return service().portfolio_view()
        except PrivateStoreUnavailable:
            return disconnected_view(
                reason="尚未配置可用的私人目录，无法读取成交台账",
                blockers=("PRIVATE_ROOT_UNAVAILABLE", "PRICE_NOT_ADMITTED"))
        except JournalValidationError:
            return disconnected_view(
                reason="私人流水校验失败，已停止投影任何持仓",
                blockers=("PRIVATE_JOURNAL_INVALID", "PRICE_NOT_ADMITTED"))

    @api.post("/api/v1/private/portfolio/initialize")
    def initialize(request: Request, payload: dict = Body(...)):
        if not origin_allowed(request):
            return _refusal()
        return emit(lambda: service().initialize(payload))

    @api.post("/api/v1/private/fills/prepare")
    def prepare_fill(request: Request, payload: dict = Body(...)):
        if not origin_allowed(request):
            return _refusal()
        return emit(lambda: service().prepare_fill(payload))

    @api.post("/api/v1/private/fills/confirm")
    def confirm_fill(request: Request, payload: dict = Body(...)):
        if not origin_allowed(request):
            return _refusal()
        return emit(lambda: service().confirm_fill(payload))

    @api.post("/api/v1/private/portfolio/reconcile")
    def reconcile(request: Request, payload: dict = Body(...)):
        if not origin_allowed(request):
            return _refusal()
        return emit(lambda: service().reconcile(payload))

    @api.post("/api/v1/private/fills/cancel")
    def cancel_fill(request: Request, payload: dict = Body(...)):
        if not origin_allowed(request):
            return _refusal()
        return emit(lambda: service().cancel_fill(payload))

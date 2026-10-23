"""Local-only HTTP adapter for the private portfolio journal.

Every route is deliberately thin: it checks local operator authorization,
delegates to `PrivatePortfolioService`, and maps domain exceptions onto the
frozen contract in `docs/current/web-private-api-contract.md`. No cash, cost,
sellable-share or PnL arithmetic is allowed to live here.

Authorization lives in `local_auth.py` (WEB-D3 P0.2): loopback peer, exact Host
allowlist, exact same-origin Origin/Referer, and a process-scoped session token
that every private read and write must present. The session starts locked; the
per-run secret minted by the launcher is exchanged once at
``POST /api/v1/private/session/unlock`` and is never returned by any anonymous
endpoint. Non-browser clients (for example curl) may omit Origin on purpose,
but they must unlock with the same launcher secret and then present the token.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

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
from ...application.portfolio.private_risk_projection import review_private_risk_rehearsal
from ...application.portfolio.held_continuity import review_held_continuity, refresh_held_continuity, review_private_held_sell
from ...application.portfolio.private_risk_preview import preview_private_hotspot_risk
from ...application.portfolio.private_risk_experience import PrivateRiskExperienceService
from ...application.portfolio.personal_entry_thesis import PersonalEntryThesisService
from ...application.portfolio.private_committed_risk import PrivateCommittedRiskService
from ...application.research.agent_review.daily_retrospective import run_daily_retrospective_mock
from .local_auth import (
    AUTHORIZATION_REQUIRED,
    SESSION_HEADER,
    UNLOCK_REJECTED,
    LocalAuthorizationError,
    LocalOperatorSession,
    authorize,
)

VALIDATION_FAILED = "VALIDATION_FAILED"
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_PRIVATE_RESPONSE_HEADERS = (
    ("Cache-Control", "no-store"),
    ("Pragma", "no-cache"),
    ("Expires", "0"),
    ("Vary", "Origin, X-Local-Session"),
)
_LOGGER = logging.getLogger(__name__)


def _is_private_response_path(path: str) -> bool:
    return path == "/api/v1/portfolio" or path.startswith(
        ("/api/v1/portfolio/", "/api/v1/private/")
    )


def _set_private_privacy_headers(response) -> None:
    for name, value in _PRIVATE_RESPONSE_HEADERS:
        response.headers[name] = value


def _refusal(error: LocalAuthorizationError) -> JSONResponse:
    status = _UNAUTHORIZED if error.code in {AUTHORIZATION_REQUIRED, UNLOCK_REJECTED} else _FORBIDDEN
    return JSONResponse(status_code=status, content={
        "action": "no_order", "status": error.code, "detail": error.detail})


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
        "reconciliation": None,
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


def register_private_routes(
    api: FastAPI,
    project: Path,
    *,
    sessions: LocalOperatorSession | None = None,
    port: int = 8001,
) -> None:
    session_state = sessions if sessions is not None else LocalOperatorSession()

    @api.middleware("http")
    async def private_response_privacy(request: Request, call_next):
        if not _is_private_response_path(request.url.path):
            return await call_next(request)
        try:
            response = await call_next(request)
        except Exception:
            _LOGGER.exception("Unhandled private route error")
            response = JSONResponse(
                status_code=500,
                content={
                    "action": "no_order",
                    "status": "INTERNAL_ERROR",
                    "detail": "私人接口执行失败，未提供任何交易动作",
                },
            )
        _set_private_privacy_headers(response)
        return response

    def service() -> PrivatePortfolioService:
        return PrivatePortfolioService(PrivateJournal(resolve_private_root(repository_root=project)))

    def risk_experience() -> PrivateRiskExperienceService:
        return PrivateRiskExperienceService(service().journal)

    def entry_thesis() -> PersonalEntryThesisService:
        return PersonalEntryThesisService(service().journal)

    def committed_risk() -> PrivateCommittedRiskService:
        journal = service().journal
        return PrivateCommittedRiskService(journal, repository_root=project,
            private_root=journal.path.parent.parent)

    def committed_source(now):
        records = service().records()
        if not records or records[-1]["kind"] != "COMMITTED_RISK_CONFIRMED":
            return None
        return committed_risk().source(authenticated_subject="LOCAL_OPERATOR", now=now)

    def calculate_risk_preview(payload):
        now = datetime.now(timezone.utc)
        return preview_private_hotspot_risk(service().journal, repository_root=project,
            generated_at=now, payload=payload,
            authenticated_subject="LOCAL_OPERATOR", committed_risk_source=committed_source(now))

    def refuse(request: Request, *, require_token: bool = True) -> JSONResponse | None:
        try:
            authorize(request, session=session_state, port=port, require_token=require_token)
        except LocalAuthorizationError as error:
            return _refusal(error)
        return None

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

    @api.get("/api/v1/private/session")
    def session_status(request: Request):
        """Report the session state without ever handing out a token.

        The workbench is locked until the launcher secret is exchanged at
        ``/api/v1/private/session/unlock``; this endpoint used to mint a token
        for any local caller, which made local-process access indistinguishable
        from the actual operator.
        """
        refusal = refuse(request, require_token=False)
        if refusal is not None:
            return refusal
        if session_state.accepts(request.headers.get(SESSION_HEADER)):
            return JSONResponse(status_code=200, content={
                "action": "no_order", "status": "AUTHORIZED",
                "header": SESSION_HEADER, "ttl_seconds": session_state.ttl_seconds},
                headers={"Cache-Control": "no-store"})
        return JSONResponse(status_code=200, content={
            "action": "no_order", "status": "LOCKED",
            "detail": "工作台已锁定：请通过本机启动脚本打开页面完成一次性解锁",
            "unlock_path": "/api/v1/private/session/unlock"},
            headers={"Cache-Control": "no-store"})

    @api.post("/api/v1/private/session/unlock")
    def unlock_session(request: Request, payload: dict = Body(...)):
        refusal = refuse(request, require_token=False)
        if refusal is not None:
            return refusal
        try:
            token = session_state.unlock(payload.get("bootstrap_token"))
        except LocalAuthorizationError as error:
            return _refusal(error)
        return JSONResponse(status_code=200, content={
            "action": "no_order", "status": "AUTHORIZED",
            "header": SESSION_HEADER, "token": token,
            "ttl_seconds": session_state.ttl_seconds},
            headers={"Cache-Control": "no-store"})

    @api.post("/api/v1/private/session/logout")
    def close_session(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        session_state.invalidate()
        return {"action": "no_order", "status": "SIGNED_OUT"}

    @api.get("/api/v1/private/portfolio/retrospective")
    def retrospective(request: Request, review_date: date):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return run_daily_retrospective_mock(journal=service().journal,
                review_date=review_date, generated_at=datetime.now(timezone.utc))
        except PrivateStoreUnavailable:
            return JSONResponse(status_code=503, content={"action": "no_order",
                "status": "PRIVATE_ROOT_UNAVAILABLE", "detail": "私人台账目录尚不可用"})
        except JournalValidationError:
            return JSONResponse(status_code=409, content={"action": "no_order",
                "status": "JOURNAL_INVALID", "detail": "台账校验失败，未生成复盘草稿"})
        except ValueError:
            return JSONResponse(status_code=422, content={"action": "no_order",
                "status": VALIDATION_FAILED, "detail": "复盘日期或证据不符合读取条件"})

    @api.get("/api/v1/portfolio")
    def portfolio_view(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return service().portfolio_view(repository_root=project)
        except PrivateStoreUnavailable:
            return disconnected_view(
                reason="尚未配置可用的私人目录，无法读取成交台账",
                blockers=("PRIVATE_ROOT_UNAVAILABLE", "PRICE_NOT_ADMITTED"))
        except JournalValidationError:
            return disconnected_view(
                reason="私人流水校验失败，已停止投影任何持仓",
                blockers=("PRIVATE_JOURNAL_INVALID", "PRICE_NOT_ADMITTED"))

    @api.get("/api/v1/private/portfolio/account-observations")
    def account_observations(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        from ...application.portfolio.account_observations import load_account_observations
        try:
            payload = load_account_observations(private_root=service().journal.path.parent.parent,
                repository_root=project)
            return JSONResponse(payload, headers={'Cache-Control': 'no-store'})
        except (PrivateStoreUnavailable, ValueError, OSError):
            return JSONResponse(status_code=409, content={'action': 'no_order',
                'status': 'ACCOUNT_OBSERVATIONS_UNAVAILABLE'}, headers={'Cache-Control': 'no-store'})

    @api.get("/api/v1/private/portfolio/risk")
    def portfolio_risk(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            now = datetime.now(timezone.utc)
            source_rejected = False
            try:
                source = committed_source(now)
            except (JournalValidationError, ValueError, OSError):
                source, source_rejected = None, True
            result = review_private_risk_rehearsal(
                PrivateJournal(resolve_private_root(repository_root=project)),
                generated_at=now, repository_root=project,
                committed_risk_source=source)
            if source_rejected:
                result["blockers"] = list(dict.fromkeys([*result["blockers"], "COMMITTED_RISK_SOURCE_REJECTED"]))
                result["committed_risk"]["status"] = "SOURCE_REJECTED"
            return result
        except PrivateStoreUnavailable as error:
            return {
                "action": "no_order", "status": "PRIVATE_ROOT_UNAVAILABLE",
                "blockers": ["PRIVATE_ROOT_UNAVAILABLE", "PRICE_NOT_ADMITTED"],
                "engine": None, "facts": None, "detail": str(error),
            }
        except JournalValidationError:
            return {
                "action": "no_order", "status": "PRIVATE_JOURNAL_INVALID",
                "blockers": ["PRIVATE_JOURNAL_INVALID", "PRICE_NOT_ADMITTED"],
                "engine": None, "facts": None,
            }

    @api.get("/api/v1/private/portfolio/held-continuity")
    def holdings_continuity(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            now = datetime.now(timezone.utc)
            result = review_held_continuity(service().journal, repository_root=project,
                generated_at=now, authenticated_subject="LOCAL_OPERATOR",
                committed_risk_source=committed_source(now))
            return JSONResponse(content=result, headers={"Cache-Control": "no-store"})
        except PrivateStoreUnavailable:
            status, code = 503, "PRIVATE_ROOT_UNAVAILABLE"
        except JournalValidationError:
            status, code = 422, "PRIVATE_JOURNAL_INVALID"
        except ValueError:
            status, code = 409, "HELD_REVIEW_RETRY_REQUIRED"
        return JSONResponse(status_code=status, headers={"Cache-Control": "no-store"},
            content={"schema_version": "private-held-continuity-v1", "action": "no_order",
                     "sensitivity": "PRIVATE", "status": code, "blockers": [code],
                     "revision": None, "items": [], "risk": None, "position_guidance": None})

    @api.post("/api/v1/private/portfolio/held-continuity/sell-review")
    def held_sell_review(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            now = datetime.now(timezone.utc)
            result = review_private_held_sell(service().journal, repository_root=project,
                generated_at=now, payload=payload, authenticated_subject="LOCAL_OPERATOR",
                committed_risk_source=committed_source(now))
            return JSONResponse(content=result, headers={"Cache-Control": "no-store"})
        except PrivateStoreUnavailable as error:
            status, code, detail = 503, "PRIVATE_ROOT_UNAVAILABLE", str(error)
        except JournalConflict as error:
            status, code, detail = 409, error.code, str(error)
        except (JournalValidationError, ValueError) as error:
            status, code, detail = 422, VALIDATION_FAILED, str(error)
        return JSONResponse(status_code=status, headers={"Cache-Control": "no-store"},
            content={"action": "no_order", "status": code, "detail": detail,
                     "ledger_written": False, "broker_execution_permission": False})

    @api.post("/api/v1/private/portfolio/held-continuity/refresh")
    def refresh_held(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            result = refresh_held_continuity(service().journal, repository_root=project,
                payload=payload, generated_at=datetime.now(timezone.utc))
            return JSONResponse(content=result, headers={"Cache-Control": "no-store"})
        except JournalConflict as error:
            status, code = 409, error.code
        except JournalValidationError:
            status, code = 422, VALIDATION_FAILED
        except PrivateStoreUnavailable:
            status, code = 503, "PRIVATE_ROOT_UNAVAILABLE"
        return JSONResponse(status_code=status, headers={"Cache-Control": "no-store"},
            content={"action": "no_order", "status": code, "revision": None})

    @api.post("/api/v1/private/portfolio/risk-preview")
    def risk_preview(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return calculate_risk_preview(payload)
        except PrivateStoreUnavailable as error:
            return JSONResponse(status_code=503, content={"action": "no_order",
                "status": "PRIVATE_ROOT_UNAVAILABLE", "detail": str(error)})
        except (JournalValidationError, ValueError) as error:
            return JSONResponse(status_code=422, content={"action": "no_order",
                "status": "VALIDATION_FAILED", "detail": str(error)})

    @api.get("/api/v1/private/portfolio/committed-risk")
    def committed_risk_view(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return committed_risk().read(authenticated_subject="LOCAL_OPERATOR", now=datetime.now(timezone.utc))
        except PrivateStoreUnavailable:
            status, code = 503, "PRIVATE_ROOT_UNAVAILABLE"
        except JournalConflict as error:
            status, code = 409, error.code
        except (JournalValidationError, ValueError):
            status, code = 422, VALIDATION_FAILED
        return JSONResponse(status_code=status, content={"action": "no_order", "status": code,
            "detail": "风险依据暂不能安全读取；请先核对当前账户及未完成草稿。"})

    @api.post("/api/v1/private/portfolio/committed-risk/confirm")
    def confirm_committed_risk(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            result = committed_risk().confirm(payload, authenticated_subject="LOCAL_OPERATOR", now=datetime.now(timezone.utc))
            return {**result, "request_binding": {key: payload[key] for key in
                ("expected_revision", "account_scope", "journal_tip_sha256")}}
        except PrivateStoreUnavailable:
            status, code = 503, "PRIVATE_ROOT_UNAVAILABLE"
        except JournalConflict as error:
            status, code = 409, error.code
        except (JournalValidationError, ValueError):
            status, code = 422, VALIDATION_FAILED
        return JSONResponse(status_code=status, content={"action": "no_order", "status": code,
            "detail": "未保存风险依据；请重新读取当前持仓、金额及明确确认。"})

    @api.get("/api/v1/private/portfolio/entry-thesis")
    def entry_thesis_view(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return entry_thesis().view(repository_root=project,
                authenticated_subject="LOCAL_OPERATOR", now=datetime.now(timezone.utc))
        except PrivateStoreUnavailable as error:
            return JSONResponse(status_code=503, content={"action": "no_order",
                "status": "PRIVATE_ROOT_UNAVAILABLE", "detail": str(error)})
        except (JournalValidationError, ValueError) as error:
            return JSONResponse(status_code=422, content={"action": "no_order",
                "status": VALIDATION_FAILED, "detail": str(error)})

    @api.post("/api/v1/private/portfolio/entry-thesis/confirm")
    def confirm_entry_thesis(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        # This single-user principal comes from the authenticated server route,
        # never a form field, session token persisted in a journal, or a name claim.
        return emit(lambda: entry_thesis().confirm(payload, repository_root=project,
            authenticated_subject="LOCAL_OPERATOR", now=datetime.now(timezone.utc)))

    @api.post("/api/v1/private/portfolio/entry-thesis/revoke")
    def revoke_entry_thesis(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: entry_thesis().revoke(payload,
            authenticated_subject="LOCAL_OPERATOR", now=datetime.now(timezone.utc)))

    @api.post("/api/v1/private/portfolio/initialize")
    def initialize(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().initialize(payload))

    @api.get("/api/v1/private/portfolio/policy")
    def policy_view(request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return service().policy_view()
        except PrivateStoreUnavailable as error:
            return JSONResponse(status_code=503, content={"action": "no_order",
                "status": "PRIVATE_ROOT_UNAVAILABLE", "detail": str(error)})
        except JournalValidationError as error:
            return JSONResponse(status_code=422, content={"action": "no_order",
                "status": "PRIVATE_JOURNAL_INVALID", "detail": str(error)})

    @api.post("/api/v1/private/portfolio/policy/prepare")
    def prepare_policy(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().prepare_policy(payload))

    @api.post("/api/v1/private/portfolio/policy/confirm")
    def confirm_policy(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().confirm_policy(payload))

    @api.post("/api/v1/private/fills/prepare")
    def prepare_fill(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().prepare_fill(payload, repository_root=project,
            risk_capture_provider=calculate_risk_preview))

    @api.post("/api/v1/private/fills/confirm")
    def confirm_fill(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().confirm_fill(payload))

    @api.post("/api/v1/private/portfolio/reconcile")
    def reconcile(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().reconcile(payload))

    @api.get("/api/v1/private/portfolio/risk-context/{symbol}")
    def risk_context(symbol: str, request: Request):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        try:
            return risk_experience().context(symbol=symbol, repository_root=project,
                now=datetime.now(timezone.utc))
        except (PrivateStoreUnavailable, JournalValidationError, ValueError) as error:
            return JSONResponse(status_code=422, content={"action": "no_order",
                "status": VALIDATION_FAILED, "detail": str(error)})

    @api.post("/api/v1/private/portfolio/costs/confirm")
    def confirm_costs(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: risk_experience().confirm_costs(payload, now=datetime.now(timezone.utc)))

    @api.post("/api/v1/private/portfolio/reconciliation/confirm")
    def confirm_reconciliation(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: risk_experience().confirm_reconciliation(payload))

    @api.post("/api/v1/private/fills/cancel")
    def cancel_fill(request: Request, payload: dict = Body(...)):
        refusal = refuse(request)
        if refusal is not None:
            return refusal
        return emit(lambda: service().cancel_fill(payload))

"""Authenticated isolated reminder interaction; no scheduler or approvals."""
from datetime import datetime, timezone

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.hotspot.intraday_monitor import read_intraday_monitor
from ...application.hotspot.public_observation_session import PublicObservationSession
from ...application.hotspot.current_registry import load_price_conditions
from .local_auth import AUTHORIZATION_REQUIRED, LocalAuthorizationError, authorize


def register_condition_alert_routes(api: FastAPI, *, project, sessions, port,
                                    clock=lambda: datetime.now(timezone.utc)):
    observation_session = PublicObservationSession(project, clock=clock)
    api.router.add_event_handler("shutdown", observation_session.close)

    def observation_view():
        state = observation_session.read()
        candidates = load_price_conditions(project, now=clock(), research_version=None)
        choices = [{"symbol": item["symbol"], "company_name": item["company_name"]}
            for item in candidates.get("items", [])
            if item.get("price_action_plan", {}).get("candidate_lifecycle")
                != "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"]
        return {**state, "choices": choices}

    @api.post("/api/v1/condition-alerts/public-observation/{operation}")
    def control_observation(operation: str, request: Request, payload: dict = Body(...)):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        expected = {"acknowledged", "symbol"} if operation == "start" else {"acknowledged", "expected_session_id"}
        if (operation not in {"start", "stop"} or set(payload) != expected
                or payload.get("acknowledged") is not True):
            return JSONResponse(dict(action="no_order", status="INVALID_REQUEST",
                detail="仅支持明确确认的本地公开行情观测。"), status_code=422, headers=headers)
        try:
            if operation == "start":
                view = observation_view()
                if payload["symbol"] not in {item["symbol"] for item in view["choices"]}:
                    return JSONResponse(dict(action="no_order", status="INVALID_CANDIDATE",
                        detail="请从当前已核验的公开候选中选择证券。"), status_code=422, headers=headers)
                state = observation_session.start(payload["symbol"])
            else:
                if not isinstance(payload["expected_session_id"], str) or not payload["expected_session_id"]:
                    raise ValueError("Exact observed session identity required")
                state = observation_session.stop(expected_session_id=payload["expected_session_id"])
            return JSONResponse(state, headers=headers)
        except (ValueError, KeyError, TypeError):
            return JSONResponse(dict(action="no_order", status="OBSERVATION_CONFLICT",
                detail="观测状态已变化或记录无法核验，请刷新后重试。"), status_code=409, headers=headers)
        except OSError:
            return JSONResponse(dict(action="no_order", status="UNAVAILABLE",
                detail="观测记录暂不可用。"), status_code=503, headers=headers)

    @api.get("/api/v1/condition-alerts")
    def condition_alerts(request: Request, test_only: bool = False):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        # Public source observation is not M5 event ingestion. Never promote
        # SIMULATED records or unadmitted observations into actual alerts.
        if not test_only:
            try:
                view = observation_view()
                return JSONResponse(dict(action="no_order", status="NOT_STARTED", test_only=False,
                    monitor_running=view["monitor_running"], alerts=[], history=[],
                    public_observation=view,
                    detail="公开报价观测不等于条件提醒；正式 M5 事件监控仍未启动。"), headers=headers)
            except (OSError, ValueError, KeyError, TypeError):
                return JSONResponse(dict(action="no_order", status="UNAVAILABLE", test_only=False,
                    monitor_running=False, alerts=[], history=[],
                    detail="公开观测记录无法核验；未授予任何投资资格。"), status_code=503, headers=headers)
        try:
            result = read_intraday_monitor(project / "runtime/intraday-monitor/test-only.json")
            return JSONResponse({**result, "monitor_running": False}, headers=headers)
        except (OSError, ValueError, KeyError, TypeError):
            return JSONResponse(dict(action="no_order", status="UNAVAILABLE", test_only=True,
                monitor_running=False, alerts=[], history=[], detail="隔离提醒记录无法核验。"),
                status_code=503, headers=headers)

    @api.post("/api/v1/condition-alerts/test-only/{alert_id}/{operation}")
    def transition(alert_id: str, operation: str, request: Request, payload: dict = Body(...)):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        if (operation not in {"acknowledge", "cancel", "expire"}
                or set(payload) != {"test_only", "acknowledged", "expected_snapshot_sha256"}
                or payload["test_only"] is not True or payload["acknowledged"] is not True
                or not isinstance(payload["expected_snapshot_sha256"], str)
                or len(payload["expected_snapshot_sha256"]) != 64):
            return JSONResponse(dict(action="no_order", status="INVALID_REQUEST",
                detail="仅可办理本人明确确认的隔离演练提醒，请刷新后重试。"),
                status_code=422, headers=headers)
        # No caller can select a production path, clock or namespace.
        from ...application.hotspot.intraday_monitor import transition_intraday_alert
        try:
            result = transition_intraday_alert(project / "runtime/intraday-monitor/test-only.json",
                alert_id=alert_id, operation=operation.upper(),
                expected_snapshot_sha256=payload["expected_snapshot_sha256"], now=clock())
            return JSONResponse({**result, "monitor_running": False}, headers=headers)
        except (ValueError, KeyError, TypeError):
            return JSONResponse(dict(action="no_order", status="ALERT_CONFLICT",
                detail="提醒版本、状态或到期条件不符，未变更；请刷新记录后重试。"),
                status_code=409, headers=headers)
        except OSError:
            return JSONResponse(dict(action="no_order", status="UNAVAILABLE",
                detail="提醒记录暂不可用，请重新读取后核对确认结果。"),
                status_code=503, headers=headers)

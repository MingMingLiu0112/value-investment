"""Authenticated isolated reminder interaction; no scheduler or approvals."""
from datetime import datetime, timezone

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.hotspot.intraday_monitor import read_intraday_monitor
from .local_auth import AUTHORIZATION_REQUIRED, LocalAuthorizationError, authorize


def register_condition_alert_routes(api: FastAPI, *, project, sessions, port,
                                    clock=lambda: datetime.now(timezone.utc)):
    @api.get("/api/v1/condition-alerts")
    def condition_alerts(request: Request, test_only: bool = False):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        # The current persistence adapter is explicitly SIMULATED-only. Never
        # promote its data into the normal monitoring view or public packet.
        if not test_only:
            return JSONResponse(dict(action="no_order", status="NOT_STARTED", test_only=False,
                monitor_running=False, alerts=[], history=[],
                detail="实际盘中监控尚未接通；当前不会持续检查价格条件。"), headers=headers)
        try:
            result = read_intraday_monitor(project / "runtime/intraday-monitor/test-only.json")
            return JSONResponse({**result, "monitor_running": False}, headers=headers)
        except (OSError, ValueError, KeyError, TypeError):
            return JSONResponse(dict(action="no_order", status="UNAVAILABLE", test_only=True,
                monitor_running=False, alerts=[], history=[], detail="隔离提醒记录无法核验。"),
                status_code=503, headers=headers)

    @api.post("/api/v1/condition-alerts/test-only/{alert_id}/acknowledge")
    def acknowledge(alert_id: str, request: Request, payload: dict = Body(...)):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        if (set(payload) != {"test_only", "acknowledged", "expected_snapshot_sha256"}
                or payload["test_only"] is not True or payload["acknowledged"] is not True
                or not isinstance(payload["expected_snapshot_sha256"], str)
                or len(payload["expected_snapshot_sha256"]) != 64):
            return JSONResponse(dict(action="no_order", status="INVALID_REQUEST",
                detail="仅可确认本人已阅读的隔离演练提醒，请刷新后重试。"),
                status_code=422, headers=headers)
        # No caller can select a production path, clock or namespace.
        from ...application.hotspot.intraday_monitor import transition_intraday_alert
        try:
            result = transition_intraday_alert(project / "runtime/intraday-monitor/test-only.json",
                alert_id=alert_id, operation="ACKNOWLEDGE",
                expected_snapshot_sha256=payload["expected_snapshot_sha256"], now=clock())
            return JSONResponse({**result, "monitor_running": False}, headers=headers)
        except (ValueError, KeyError, TypeError):
            return JSONResponse(dict(action="no_order", status="ALERT_CONFLICT",
                detail="提醒版本或状态已变化，未确认；请刷新记录后重试。"),
                status_code=409, headers=headers)
        except OSError:
            return JSONResponse(dict(action="no_order", status="UNAVAILABLE",
                detail="提醒记录暂不可用，请重新读取后核对确认结果。"),
                status_code=503, headers=headers)

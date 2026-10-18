"""Authenticated read-only condition history; no scheduler or authorization."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.hotspot.intraday_monitor import read_intraday_monitor
from .local_auth import AUTHORIZATION_REQUIRED, LocalAuthorizationError, authorize


def register_condition_alert_routes(api: FastAPI, *, project, sessions, port):
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

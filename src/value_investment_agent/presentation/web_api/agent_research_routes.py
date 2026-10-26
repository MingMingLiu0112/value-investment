"""Read-only registered research packets, behind the local session boundary."""
from datetime import datetime, timezone
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.research.agent_review.web_research import read_web_agent_research, WORKFLOWS
from ...application.research.agent_review.status import read_agent_research_status
from .local_auth import AUTHORIZATION_REQUIRED, LocalAuthorizationError, authorize


def register_agent_research_routes(api: FastAPI, *, project, sessions, port,
                                   clock=lambda: datetime.now(timezone.utc)):
    @api.get("/api/v1/agent-research-status")
    def agent_research_status(request: Request):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        return JSONResponse(read_agent_research_status(project, now=clock()), headers=headers)

    @api.get("/api/v1/agent-research/{symbol}")
    def agent_research(symbol: str, request: Request, workflow: str | None = None):
        headers = {"Cache-Control": "no-store"}
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse(dict(action="no_order", status=error.code, detail=error.detail),
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403, headers=headers)
        if not re.fullmatch(r"[0-9]{6}", symbol) or (workflow is not None and workflow not in WORKFLOWS):
            return JSONResponse(dict(action="no_order", status="INVALID_SYMBOL"),
                status_code=422, headers=headers)
        return JSONResponse(read_web_agent_research(project, symbol=symbol, now=clock(), workflow=workflow), headers=headers)

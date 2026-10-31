"""Explicit bounded saved-response research tasks; GET never starts work."""
from datetime import datetime, timezone
import hashlib
import json
import re

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.research.agent_review.web_research import read_web_agent_research, _binding, _raw, MAX_JSON
from ...application.portfolio.private_journal_lock import LockTimeout
from .local_auth import authorize, LocalAuthorizationError, AUTHORIZATION_REQUIRED


def registered_task_inputs(project, symbol, workflow, now):
    """Only server-registered, independently reverified inputs may be executed."""
    view = read_web_agent_research(project, symbol=symbol, workflow=workflow, now=now)
    if view.get("status") != "VERIFIED":
        raise ValueError("REGISTERED_SOURCE_NOT_VERIFIED")
    ref = view["bindings"]["packet"]
    raw = _raw(_binding(project, ref), MAX_JSON)
    if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("REGISTERED_PACKET_CHANGED")
    packet = json.loads(raw)
    responses = packet.get("raw_responses")
    if not isinstance(responses, dict) or set(responses) != {"FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"}:
        raise ValueError("NO_THREE_ROLE_SAVED_RESPONSES")
    wb = view["bindings"]["workbench"]
    return wb, responses


def register_research_task_routes(api: FastAPI, *, project, sessions, port,
                                 clock=lambda: datetime.now(timezone.utc)):
    # Imported lazily at application construction, not by presentation consumers.
    from ...application.research.agent_review.task_execution_v1 import ResearchTaskService
    service = ResearchTaskService(project)

    def denied(request):
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return JSONResponse({"action": "no_order", "status": error.code, "detail": error.detail},
                status_code=401 if error.code == AUTHORIZATION_REQUIRED else 403,
                headers={"Cache-Control": "no-store"})
        return None

    def reply(value, status=200):
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    @api.get("/api/v1/research-tasks")
    def list_tasks(request: Request, symbol: str):
        error = denied(request)
        if error is not None:
            return error
        try:
            items = service.list_for_symbol(symbol)
            return reply({"action": "no_order", "symbol": symbol, "items": items,
                          "scope": "BOUNDED_TASK_HISTORY"})
        except (LockTimeout, RuntimeError) as exc:
            return reply({"action": "no_order", "status": "TASK_BUSY", "detail": str(exc)}, 409)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return reply({"action": "no_order", "status": "TASK_HISTORY_UNAVAILABLE", "detail": str(exc)}, 422)

    @api.post("/api/v1/research-tasks")
    async def create_task(request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        try:
            raw = await request.body()
            if len(raw) > 2048:
                raise ValueError("TASK_REQUEST_TOO_LARGE")
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {"symbol", "workflow", "request_key"}:
                raise ValueError("INVALID_TASK_FIELDS")
            if (not re.fullmatch(r"[0-9]{6}", str(body["symbol"]))
                    or body["workflow"] not in {"legacy", "event", "financial"}
                    or not isinstance(body["request_key"], str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", body["request_key"])):
                raise ValueError("INVALID_TASK_IDENTITY")
            wb, responses = registered_task_inputs(project, body["symbol"], body["workflow"], clock())
            task = service.create(symbol=body["symbol"], workbench=project / wb["path"],
                workbench_sha256=wb["sha256"], responses=responses, request_key=body["request_key"], workflow=body["workflow"])
            if task["status"] == "QUEUED":
                background.add_task(service.run, task["task_id"])
            return reply(task, 202)
        except (LockTimeout, RuntimeError) as exc:
            return reply({"action": "no_order", "status": "TASK_BUSY", "detail": "请稍后重试；任务未丢失"}, 409)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return reply({"action": "no_order", "status": "TASK_REJECTED", "detail": str(exc)}, 422)

    @api.get("/api/v1/research-tasks/{task_id}")
    def read_task(task_id: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        try:
            return reply(service.read(task_id))
        except (LockTimeout, RuntimeError) as exc:
            return reply({"action": "no_order", "status": "TASK_BUSY", "detail": "请稍后重试；任务未丢失"}, 409)
        except (ValueError, OSError, KeyError) as exc:
            return reply({"action": "no_order", "status": "TASK_UNAVAILABLE", "detail": str(exc)}, 404)

    @api.post("/api/v1/research-tasks/{task_id}/{operation}")
    def control_task(task_id: str, operation: str, request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        try:
            if operation == "cancel":
                task = service.cancel(task_id)
            elif operation == "resume":
                task = service.resume(task_id)
                if task["status"] == "QUEUED":
                    background.add_task(service.run, task_id)
            else:
                raise ValueError("UNSUPPORTED_TASK_OPERATION")
            return reply(task)
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            return reply({"action": "no_order", "status": "TASK_CONTROL_REJECTED", "detail": str(exc)}, 409)

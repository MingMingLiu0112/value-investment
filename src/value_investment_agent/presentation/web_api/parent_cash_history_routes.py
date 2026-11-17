"""Bounded, read-only projection of existing parent cash task checkpoints."""
import re
import json
from itertools import islice
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from .live_operating_research_routes import resolve_research_task_root
from .local_auth import authorize, LocalAuthorizationError, AUTHORIZATION_REQUIRED
from ...application.research.agent_review.parent_cash_task_v2 import ParentCashTaskServiceV2, STAGE_ORDER
from ...application.research.agent_review.parent_cash_task_v3 import ParentCashTaskServiceV3


def register_parent_cash_history_routes(api: FastAPI, *, project, sessions, port):
    root = resolve_research_task_root(project)
    service = ParentCashTaskServiceV2(root)
    numbered_service = ParentCashTaskServiceV3(root)
    # When execution uses a sibling worktree, retain read-only access to V3
    # history created in the code checkout. Writes and budget stay at root.
    code_root = Path(project).resolve()
    archived_numbered_service = (ParentCashTaskServiceV3(code_root)
                                 if code_root != Path(root).resolve() else None)

    def reply(value, status=200):
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    def denied(request):
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return reply({"action": "no_order", "status": error.code},
                         401 if error.code == AUTHORIZATION_REQUIRED else 403)
        return None

    @api.post("/api/v1/operating-research/parent-cash-tasks/v3")
    async def create_numbered(request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        try:
            raw = await request.body()
            if len(raw) > 2048:
                raise ValueError("PARENT_V3_REQUEST_TOO_LARGE")
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {"spec_binding", "request_key"}:
                raise ValueError("PARENT_V3_REQUEST_INVALID")
            task = numbered_service.create(**body)
            if task["status"] == "QUEUED":
                background.add_task(numbered_service.run, task["task_id"])
            return reply(task, 202)
        except (ValueError, TypeError, KeyError, OSError, PermissionError) as exc:
            return reply({"action": "no_order", "status": "PARENT_V3_TASK_REJECTED",
                          "reason": str(exc)}, 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}")
    def read_numbered(task_id: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id):
            return reply({"action": "no_order", "status": "INVALID_TASK_ID"}, 422)
        try:
            primary_base = getattr(numbered_service, "base", None)
            if (primary_base is None or (Path(primary_base) / task_id).exists()
                    or archived_numbered_service is None):
                return reply(numbered_service.read(task_id))
            return reply(archived_numbered_service.read(task_id))
        except (ValueError, TypeError, KeyError, OSError, PermissionError):
            return reply({"action": "no_order", "status": "PARENT_V3_TASK_UNAVAILABLE"}, 422)

    @api.post("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/{operation}")
    def control_numbered(task_id: str, operation: str, request: Request,
                         background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id) or operation not in {"cancel", "resume"}:
            return reply({"action": "no_order", "status": "INVALID_TASK_CONTROL"}, 422)
        primary_base = getattr(numbered_service, "base", None)
        if (primary_base is not None and archived_numbered_service is not None
                and not (Path(primary_base) / task_id).exists()
                and (archived_numbered_service.base / task_id).exists()):
            return reply({"action": "no_order", "status": "ARCHIVED_TASK_READ_ONLY"}, 422)
        try:
            task = (numbered_service.cancel(task_id) if operation == "cancel"
                    else numbered_service.resume(task_id))
            if operation == "resume" and task["status"] == "QUEUED":
                background.add_task(numbered_service.run, task_id)
            return reply(task)
        except (ValueError, TypeError, KeyError, OSError, PermissionError):
            return reply({"action": "no_order", "status": "PARENT_V3_TASK_UNAVAILABLE"}, 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/history")
    def history(request: Request, symbol: str):
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return reply({"action": "no_order", "status": error.code},
                         401 if error.code == AUTHORIZATION_REQUIRED else 403)
        if not re.fullmatch(r"[0-9]{6}", symbol):
            return reply({"action": "no_order", "status": "INVALID_SYMBOL"}, 422)
        try:
            children = list(islice(service.base.iterdir(), 101)) if service.base.exists() else []
            if len(children) > 100:
                raise ValueError("PARENT_TASK_DISCOVERY_LIMIT_EXCEEDED")
            items = []
            for directory in sorted(children):
                if not directory.is_dir() or not re.fullmatch(r"rt-[0-9a-f]{32}", directory.name):
                    continue
                if not (directory / "input.json").is_file():
                    continue
                spec, state, binding = service._load(directory.name)
                source_path = spec["spec_binding"]["path"]
                if not source_path.startswith("runtime/"):
                    raise ValueError("PARENT_TASK_SOURCE_OUTSIDE_RUNTIME")
                source = service._bound(spec["spec_binding"])
                if source.get("action") != "no_order":
                    raise ValueError("PARENT_TASK_SOURCE_INVALID")
                if source.get("symbol") != symbol:
                    continue
                if state["status"] == "SUCCEEDED" and len(state.get("responses", {})) == 9:
                    continue
                years = sorted({ref["period_end"][:4] for ref in source.get("fact_anchors", {}).values()
                                if isinstance(ref, dict) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                                                         str(ref.get("period_end", "")))})
                reservations = state.get("reservations", {})
                if len(reservations) > 32 or len(state.get("responses", {})) > 9:
                    raise ValueError("PARENT_TASK_PROJECTION_LIMIT_EXCEEDED")
                error_code = state.get("error_code")
                error_stage = next((stage for stage in STAGE_ORDER
                                    if isinstance(error_code, str) and error_code.startswith(
                                        stage.upper().replace(".", "_") + "_")), None)
                items.append({"task_id": directory.name, "status": state["status"],
                    "task_contract": "parent-cash-task-v2",
                    "stage": next((row.get("scenario") for row in reservations.values()
                                   if row.get("status") == "RESERVED"), error_stage),
                    "completed_stages": sorted(state.get("responses", {})),
                    "error_code": state.get("error_code"), "source_years": years,
                    "source_binding": spec["spec_binding"], "record_binding": binding,
                    "reserved_cost_cny": state.get("reserved_cost"),
                    "settled_cost_cny": state.get("settled_cost"),
                    "charges": [{"stage": row.get("scenario"), "status": row.get("status"),
                                 "reserved_cny": row.get("cost"), "settled_cny": row.get("actual_cost")}
                                for row in reservations.values()],
                    "e2_consumption": "UNVERIFIED", "formal": False, "action": "no_order"})
            seen_numbered = set()
            for numbered, archived in ((numbered_service, False),
                                       (archived_numbered_service, True)):
                if numbered is None or not numbered.base.exists():
                    continue
                numbered_children = list(islice(numbered.base.iterdir(), 101))
                if len(numbered_children) > 100:
                    raise ValueError("PARENT_V3_TASK_DISCOVERY_LIMIT_EXCEEDED")
                for directory in sorted(numbered_children):
                    if (not directory.is_dir()
                            or not re.fullmatch(r"rt-[0-9a-f]{32}", directory.name)
                            or not (directory / "input.json").is_file()):
                        continue
                    if directory.name in seen_numbered:
                        raise ValueError("PARENT_V3_DUPLICATE_TASK_ACROSS_ROOTS")
                    seen_numbered.add(directory.name)
                    spec, state, binding = numbered._load(directory.name)
                    source = numbered._bound(spec["spec_binding"])
                    if (source.get("action") != "no_order"
                            or not spec["spec_binding"]["path"].startswith("runtime/")):
                        raise ValueError("PARENT_V3_TASK_SOURCE_INVALID")
                    if source.get("symbol") != symbol:
                        continue
                    reservations = state.get("reservations", {})
                    if len(reservations) > 32 or len(state.get("responses", {})) > 9:
                        raise ValueError("PARENT_V3_TASK_PROJECTION_LIMIT_EXCEEDED")
                    items.append({"task_id": directory.name, "task_contract": "parent-cash-task-v3",
                        "read_only_archive": archived,
                        "status": state["status"],
                        "stage": next((row.get("scenario") for row in reservations.values()
                                       if row.get("status") == "RESERVED"), None),
                        "completed_stages": sorted(state.get("responses", {})),
                        "error_code": state.get("error_code"),
                        "source_years": sorted({ref["period_end"][:4]
                            for ref in source.get("fact_anchors", {}).values()
                            if isinstance(ref, dict) and re.fullmatch(
                                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(ref.get("period_end", "")))}),
                        "source_binding": spec["spec_binding"], "record_binding": binding,
                        "reserved_cost_cny": state.get("reserved_cost"),
                        "settled_cost_cny": state.get("settled_cost"),
                        "charges": [{"stage": row.get("scenario"), "status": row.get("status"),
                                     "reserved_cny": row.get("cost"),
                                     "settled_cny": row.get("actual_cost")}
                                    for row in reservations.values()],
                        "candidate_status": ("COMPILED_CONDITIONAL_NOT_MAIN" if state["status"] == "SUCCEEDED"
                                             else "NOT_COMPILED"),
                        "e2_consumption": "UNVERIFIED", "formal": False, "action": "no_order"})
            return reply({"action": "no_order", "symbol": symbol, "items": items, "formal": False})
        except (ValueError, OSError, KeyError, TypeError, RuntimeError):
            return reply({"action": "no_order", "status": "PARENT_TASK_HISTORY_UNAVAILABLE"}, 422)

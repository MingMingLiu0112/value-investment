"""Explicit real operating research, existing local authorization and D1 workflow."""
from datetime import datetime,timezone
import json,re
from fastapi import FastAPI,Request,BackgroundTasks
from fastapi.responses import JSONResponse
from .local_auth import authorize,LocalAuthorizationError,AUTHORIZATION_REQUIRED
from ...application.research.agent_review.operating_task_v2 import LiveOperatingTaskService,model_status,ROLES
from ...application.research.agent_review.operating_task_v2 import LiveOperatingTaskService as _NativeLiveService
from ...operations.live_task_controller_v1 import supervise_live_task, read_pending_live_task, finalize_pending_live_task
from ...application.portfolio.private_journal_lock import LockTimeout


def register_live_operating_routes(api:FastAPI,*,project,sessions,port):
    service=LiveOperatingTaskService(project)
    def enqueue(background,task_id):
        # Execution resource supervision only; frozen research inputs/providers
        # and financial implementation fingerprints remain byte-identical.
        if type(service) is _NativeLiveService and service.test_provider is None:
            background.add_task(supervise_live_task,project,task_id)
        else:
            background.add_task(service.run,task_id)

    def pending(task_id):
        if type(service) is not _NativeLiveService or service.test_provider is not None:
            return None
        value=read_pending_live_task(project,task_id)
        return value if value["status"]!="NO_PENDING_FINALIZATION" else None
    def pending_response(value):
        return reply(dict(action="no_order",status="FINALIZATION_PENDING",
            detail="工作进程已停止，状态写入尚未完成；请使用完成状态写入，不会调用模型。",
            controller_finalization=value),409)

    def reply(value,status=200):
        return JSONResponse(value,status_code=status,headers={"Cache-Control":"no-store"})
    def review_projection(value):
        # Response-only copy: never edit an immutable task or its role pins.
        projected=dict(value)
        projected.pop("independent_review_status",None)
        if "independent_review" not in value:return projected
        review=projected.pop("independent_review")
        roles=value.get("roles")
        valid=(isinstance(review,dict) and isinstance(roles,dict) and bool(roles)
            and isinstance(value.get("context_fingerprint"),str) and bool(value["context_fingerprint"])
            and review.get("source_context_fingerprint")==value["context_fingerprint"]
            and review.get("reviewed_role_responses")==roles
            and review.get("status")=="REVIEW_REQUIRED_NOT_APPROVAL"
            and isinstance(review.get("findings"),list))
        projected["independent_review_status"]=("REVIEW_REQUIRED_NOT_APPROVAL" if valid
            else "REVIEW_BINDING_INVALID")
        if valid:
            projected["independent_review"]={key:review[key] for key in
                ("source_context_fingerprint","reviewed_role_responses","status","findings")}
        return projected

    def denied(request):
        try:authorize(request,session=sessions,port=port)
        except LocalAuthorizationError as error:
            return reply(dict(action="no_order",status=error.code,detail=error.detail),
                         401 if error.code==AUTHORIZATION_REQUIRED else 403)
        return None

    # Annual supplements share source verification, authorization and the live daily budget.
    # They do not replace the existing three-role task or grant research approval.
    from ...application.research.agent_review.operating_horizon_task_v2 import OperatingHorizonTaskService
    horizon = OperatingHorizonTaskService(project)

    @api.post("/api/v1/operating-research/horizon-tasks")
    async def create_horizon(request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            raw=await request.body()
            if len(raw)>1024:raise ValueError("HORIZON_REQUEST_TOO_LARGE")
            body=json.loads(raw)
            if not isinstance(body,dict) or set(body)!={"symbol","request_key","years"}:
                raise ValueError("HORIZON_REQUEST_INVALID")
            task=horizon.create(**body)
            if task["status"]=="QUEUED":background.add_task(horizon.run,task["task_id"])
            return reply(task,202)
        except (PermissionError,ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASK_REJECTED",reason=str(error)),422)

    @api.get("/api/v1/operating-research/horizon-tasks/{task_id}")
    def read_horizon(task_id:str,request:Request):
        error=denied(request)
        if error is not None:return error
        try:return reply(horizon.read(task_id))
        except LockTimeout:return reply(dict(action="no_order",status="LIVE_STATE_BUSY"),503)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_TASK_UNAVAILABLE",reason=str(error)),422)

    @api.post("/api/v1/operating-research/horizon-tasks/{task_id}/{operation}")
    def control_horizon(task_id:str,operation:str,request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=horizon.cancel(task_id)
            elif operation=="resume":
                task=horizon.resume(task_id)
                if task["status"]=="QUEUED":background.add_task(horizon.run,task_id)
            else:raise ValueError("UNSUPPORTED_HORIZON_OPERATION")
            return reply(task)
        except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
            return reply(dict(action="no_order",status="HORIZON_CONTROL_REJECTED",reason=str(error)),409)

    @api.get("/api/v1/operating-research/model-status")
    def availability():
        return reply(model_status(project))

    @api.get("/api/v1/operating-research/tasks")
    def history(request:Request,symbol:str):
        error=denied(request)
        if error is not None:return error
        try:return reply(dict(action="no_order",symbol=symbol,items=[review_projection(row) for row in service.list_for_symbol(symbol)]))
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_HISTORY_UNAVAILABLE"),422)

    @api.post("/api/v1/operating-research/tasks")
    async def create(request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            raw=await request.body()
            if len(raw)>1024:raise ValueError("LIVE_REQUEST_TOO_LARGE")
            body=json.loads(raw)
            if (not isinstance(body,dict) or set(body)!={"symbol","request_key"}
                    or not isinstance(body["symbol"],str) or re.fullmatch("[0-9]{6}",body["symbol"]) is None):
                raise ValueError("LIVE_REQUEST_INVALID")
            task=service.create(symbol=body["symbol"],request_key=body["request_key"])
            if task["status"]=="QUEUED":enqueue(background,task["task_id"])
            return reply(review_projection(task),202)
        except PermissionError as error:
            return reply(dict(action="no_order",status=str(error)),409)
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_TASK_REJECTED_SOURCE_CONFIG_OR_BUDGET"),422)

    @api.get("/api/v1/operating-research/tasks/{task_id}")
    def read(task_id:str,request:Request):
        error=denied(request)
        if error is not None:return error
        try:
            waiting=pending(task_id)
            if waiting is not None:
                spec,state,pin=service._load(task_id,recover=False)
                value=service._view(spec,state,pin,datetime.now(timezone.utc))
                value["controller_finalization"]=waiting
                return reply(review_projection(value))
            return reply(review_projection(service.read(task_id)))
        except LockTimeout:
            return JSONResponse(dict(action="no_order",status="LIVE_STATE_BUSY",
                detail="任务正在封存状态，请稍后继续读取；这不表示任务不存在或失败。"),
                status_code=503,headers={"Cache-Control":"no-store","Retry-After":"3"})
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_TASK_UNAVAILABLE"),404)

    @api.post("/api/v1/operating-research/tasks/{task_id}/{operation}")
    def control(task_id:str,operation:str,request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=service.cancel(task_id)
            elif operation=="finalize":
                if type(service) is not _NativeLiveService or service.test_provider is not None:
                    raise ValueError("NATIVE_FINALIZATION_REQUIRED")
                finalize_pending_live_task(project,task_id)
                waiting=pending(task_id)
                if waiting is not None:return pending_response(waiting)
                task=service.read(task_id)
            elif operation=="resume":
                if pending(task_id) is not None:
                    finalize_pending_live_task(project,task_id)
                    waiting=pending(task_id)
                    if waiting is not None:return pending_response(waiting)
                # The controller owns the worker until termination/finalization.
                # Recover a stranded RUNNING task only after that owner is gone;
                # the native execution lock then protects against a surviving worker.
                if type(service) is _NativeLiveService and service.test_provider is None:
                    with service._lock(service._directory(task_id), "controller"):
                        task=service.resume(task_id)
                else:
                    task=service.resume(task_id)
                if task["status"]=="QUEUED":enqueue(background,task_id)
            else:raise ValueError("UNSUPPORTED_OPERATION")
            return reply(review_projection(task))
        except LockTimeout:
            return reply(dict(action="no_order",status="LIVE_EXECUTION_STILL_ACTIVE",
                detail="任务仍由执行进程持有，请读取状态；不会启动重复模型调用。"),409)
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_CONTROL_REJECTED"),409)

    @api.get("/api/v1/operating-research/companies/{symbol}")
    def public_result(symbol:str):
        if re.fullmatch("[0-9]{6}",symbol) is None:
            return reply(dict(action="no_order",status="INVALID_SYMBOL"),422)
        try:
            tasks=service.list_for_symbol(symbol)
            if not tasks:return reply(dict(action="no_order",symbol=symbol,status="NOT_STARTED",
                reason="NO_VERIFIED_LIVE_RESEARCH_RESULT",formal_eligibility=False))
            value=tasks[0]
            draft=value.get("research_draft")
            verified_partial=(isinstance(draft,dict) and bool(draft) and set(draft)<=set(ROLES)
                and value.get("error_code") not in {"SOURCE_OR_IMPLEMENTATION_CHANGED","LIVE_CHECKPOINT_INVALID"})
            if (value["scope"]!="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED"
                    or (value["status"]!="SUCCEEDED" and not verified_partial)):
                return reply(dict(action="no_order",symbol=symbol,status="UNASSESSABLE",
                    reason=value.get("error_code") or "LATEST_TASK_NOT_VERIFIED_LIVE_RESEARCH",
                    task_id=value["task_id"],latest_task_status=value["status"],formal_eligibility=False))

            keys=("symbol","status","task_id","scope","model_id","new_llm_calls","research_draft",
                  "context_fingerprint","source_binding","research_as_of","formal_fact_count",
                  "approval_changed","main_range_adopted","condition_price","personal_quantity","research_completeness")
            public={k:value[k] for k in keys}
            if "operating_driver_bridge" in value:
                public["operating_driver_bridge"]=value["operating_driver_bridge"]
            if value["status"]!="SUCCEEDED":
                public.update(status="PARTIAL",execution_status=value["status"],
                    reason=value.get("error_code") or "LATEST_TASK_INCOMPLETE_VERIFIED_PARTIAL_RESEARCH",
                    error_code=value.get("error_code"),
                    completed_roles=[role for role in ROLES if role in draft],
                    pending_roles=[role for role in ROLES if role not in draft])
            # A new read-model consumer, outside the immutable paid research task.
            # Failure here does not erase valid public operating research.
            try:
                from ...application.research.operating_cash_consumption_v4 import read_operating_cash_consumption
                public["cash_consumption"]=read_operating_cash_consumption(
                    root=project,task=value,now=datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError):
                public["cash_consumption"]=dict(status="UNASSESSABLE",
                    reason="CASH_SOURCE_OR_MAPPING_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            # Public native observations are independent of approval/private accounts.
            try:
                from ...application.research.current_capital_observation_v1 import read_current_capital_observation
                public["current_capital_observation"] = read_current_capital_observation(
                    project, symbol, datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError):
                public["current_capital_observation"] = dict(status="UNASSESSABLE",
                    reason="CURRENT_CAPITAL_SOURCE_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            try:
                from ...application.research.operating_distribution_review_v1 import read_operating_distribution_review
                public["fiscal_distribution_review"] = read_operating_distribution_review(
                    root=project,task=value,now=datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError):
                public["fiscal_distribution_review"] = dict(status="UNASSESSABLE",
                    reason="FISCAL_POLICY_SOURCE_OR_PERIOD_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            try:
                from ...application.research.parent_funding_review_v1 import read_registered_parent_funding_review
                public["parent_funding_review"] = read_registered_parent_funding_review(
                    root=project,symbol=symbol,now=datetime.now(timezone.utc))
                from ...application.research.parent_funding_review_v1 import compare_parent_cash_opening
                public["parent_funding_review"]["cash_input_comparison"] = compare_parent_cash_opening(
                    public["parent_funding_review"],public.get("cash_consumption",{}))
            except (ValueError,OSError,KeyError,TypeError):
                public["parent_funding_review"] = dict(status="UNASSESSABLE",
                    reason="PARENT_FUNDING_SOURCE_NOT_VERIFIED",action="no_order",formal_eligibility=False)
            # This is an E2 input-preparation projection only.  It intentionally
            # exposes retained parent-cash observations before any policy,
            # valuation or price consumer is allowed to use them.
            try:
                from ...application.research.operating_cash_followup_v1 import read_registered_operating_cash_followup
                public["parent_cash_followup"] = read_registered_operating_cash_followup(
                    root=project, task=value, now=datetime.now(timezone.utc))
            except (ValueError, OSError, KeyError, TypeError):
                public["parent_cash_followup"] = dict(status="UNASSESSABLE",
                    reason="PARENT_CASH_FOLLOWUP_SOURCE_NOT_VERIFIED", action="no_order",
                    formal_eligibility=False)
            # Versioned public revalidation never changes the paid task or approval.
            try:
                from ...application.research.main_valuation_revalidation_v1 import read_main_valuation_revalidation
                public["main_valuation_revalidation"] = read_main_valuation_revalidation(
                    root=project,symbol=symbol,now=datetime.now(timezone.utc))
            except (ValueError,OSError,KeyError,TypeError) as error:
                public["main_valuation_revalidation"] = dict(status="UNASSESSABLE",
                    reason=str(error),action="no_order",formal_eligibility=False,
                    current_comparable=False,personal_quantity=None)
            reviewed=review_projection(value)
            for key in ("independent_review","independent_review_status"):
                if key in reviewed:public[key]=reviewed[key]
            return reply(dict(action="no_order",formal_eligibility=False,**public))
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",symbol=symbol,status="UNASSESSABLE",
                reason="LIVE_SOURCE_OR_CHECKPOINT_NOT_VERIFIED",formal_eligibility=False))

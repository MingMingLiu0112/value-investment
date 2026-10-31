"""Explicit real operating research, existing local authorization and D1 workflow."""
from datetime import datetime,timezone
import json,re
from fastapi import FastAPI,Request,BackgroundTasks
from fastapi.responses import JSONResponse
from .local_auth import authorize,LocalAuthorizationError,AUTHORIZATION_REQUIRED
from ...application.research.agent_review.operating_task_v2 import LiveOperatingTaskService,model_status,ROLES

def register_live_operating_routes(api:FastAPI,*,project,sessions,port):
    service=LiveOperatingTaskService(project)
    def reply(value,status=200):
        return JSONResponse(value,status_code=status,headers={"Cache-Control":"no-store"})
    def denied(request):
        try:authorize(request,session=sessions,port=port)
        except LocalAuthorizationError as error:
            return reply(dict(action="no_order",status=error.code,detail=error.detail),
                         401 if error.code==AUTHORIZATION_REQUIRED else 403)
        return None

    @api.get("/api/v1/operating-research/model-status")
    def availability():
        return reply(model_status(project))

    @api.get("/api/v1/operating-research/tasks")
    def history(request:Request,symbol:str):
        error=denied(request)
        if error is not None:return error
        try:return reply(dict(action="no_order",symbol=symbol,items=service.list_for_symbol(symbol)))
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
            if task["status"]=="QUEUED":background.add_task(service.run,task["task_id"])
            return reply(task,202)
        except PermissionError as error:
            return reply(dict(action="no_order",status=str(error)),409)
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_TASK_REJECTED_SOURCE_CONFIG_OR_BUDGET"),422)

    @api.get("/api/v1/operating-research/tasks/{task_id}")
    def read(task_id:str,request:Request):
        error=denied(request)
        if error is not None:return error
        try:return reply(service.read(task_id))
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",status="LIVE_TASK_UNAVAILABLE"),404)

    @api.post("/api/v1/operating-research/tasks/{task_id}/{operation}")
    def control(task_id:str,operation:str,request:Request,background:BackgroundTasks):
        error=denied(request)
        if error is not None:return error
        try:
            if operation=="cancel":task=service.cancel(task_id)
            elif operation=="resume":
                task=service.resume(task_id)
                if task["status"]=="QUEUED":background.add_task(service.run,task_id)
            else:raise ValueError("UNSUPPORTED_OPERATION")
            return reply(task)
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
            if value["status"]!="SUCCEEDED":
                public.update(status="PARTIAL",execution_status=value["status"],
                    reason=value.get("error_code") or "LATEST_TASK_INCOMPLETE_VERIFIED_PARTIAL_RESEARCH",
                    error_code=value.get("error_code"),
                    completed_roles=[role for role in ROLES if role in draft],
                    pending_roles=[role for role in ROLES if role not in draft])
            if "independent_review" in value:
                review=value["independent_review"]
                roles=value.get("roles")
                valid=(isinstance(review,dict) and isinstance(roles,dict) and bool(roles)
                    and isinstance(value.get("context_fingerprint"),str) and bool(value["context_fingerprint"])
                    and review.get("source_context_fingerprint")==value["context_fingerprint"]
                    and review.get("reviewed_role_responses")==roles
                    and review.get("status")=="REVIEW_REQUIRED_NOT_APPROVAL"
                    and isinstance(review.get("findings"),list))
                public["independent_review_status"]=("REVIEW_REQUIRED_NOT_APPROVAL" if valid
                    else "REVIEW_BINDING_INVALID")
                if valid:
                    public["independent_review"]={key:review[key] for key in
                        ("source_context_fingerprint","reviewed_role_responses","status","findings")}
            return reply(dict(action="no_order",formal_eligibility=False,**public))
        except (ValueError,OSError,KeyError,RuntimeError,TypeError):
            return reply(dict(action="no_order",symbol=symbol,status="UNASSESSABLE",
                reason="LIVE_SOURCE_OR_CHECKPOINT_NOT_VERIFIED",formal_eligibility=False))

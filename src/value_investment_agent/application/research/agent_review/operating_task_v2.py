"""Live operating-research workflow on the existing D1 append/lock primitives."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import re
from urllib.error import HTTPError
from .task_execution_v1 import ResearchTaskService, VERSION, STATES, _bytes, _hash, _now
from .operating_sources_v1 import build_operating_source_context
from ....infrastructure.agent_runtime.provider import OpenAICompatibleChatProvider, LLMResponse
from ...product.common import require_inside, write_new_bytes

ROLES=("FUNDAMENTAL","COUNTER_EVIDENCE","EVENT")
CONFIG="config/agent-research-provider.local.json"

def model_configuration(root):
    path=Path(root)/CONFIG
    if not path.is_file(): raise PermissionError("MODEL_AUTHORIZATION_REQUIRED")
    value=json.loads(path.read_bytes())
    required={"endpoint","model_id","api_key_env","timeout_seconds","max_completion_tokens_cap",
              "max_run_cost","input_cost_per_million","output_cost_per_million","authorized",
              "authorization_reference","currency","daily_cost_limit"}
    if set(value)!=required or value["authorized"] is not True:
        raise PermissionError("MODEL_AUTHORIZATION_REQUIRED")
    if (not isinstance(value["authorization_reference"],str)
            or not 1<=len(value["authorization_reference"])<=300):
        raise PermissionError("MODEL_AUTHORIZATION_REFERENCE_REQUIRED")
    for key in ("max_run_cost","input_cost_per_million","output_cost_per_million","daily_cost_limit"):
        try: number=Decimal(str(value[key]))
        except Exception: raise ValueError("MODEL_BUDGET_INVALID") from None
        if not number.is_finite() or not Decimal("0")<number<=Decimal("100"):
            raise ValueError("MODEL_BUDGET_INVALID")
    if value["currency"]!="CNY" or not Decimal("0")<Decimal(str(value["daily_cost_limit"]))<=Decimal("10"):
        raise ValueError("DAILY_CNY_AUTHORIZATION_LIMIT_INVALID")
    if Decimal(str(value["max_run_cost"]))>Decimal(str(value["daily_cost_limit"])):
        raise ValueError("TASK_LIMIT_EXCEEDS_DAILY_LIMIT")
    if type(value["max_completion_tokens_cap"]) is not int or not 512<=value["max_completion_tokens_cap"]<=4096:
        raise ValueError("MODEL_COMPLETION_CAP_INVALID")
    OpenAICompatibleChatProvider(**{k:value[k] for k in ("endpoint","model_id","api_key_env","timeout_seconds","max_completion_tokens_cap")})
    return value

def model_status(root):
    try:
        cfg=model_configuration(root)
        ready=bool(os.environ.get(cfg["api_key_env"]))
        return dict(status="READY" if ready else "MODEL_CREDENTIAL_REQUIRED",
            model_id=cfg["model_id"],max_run_cost=str(cfg["max_run_cost"]),
            currency=cfg["currency"],daily_cost_limit=str(cfg["daily_cost_limit"]),
            credential_present=ready,action="no_order",real_calls_started=False)
    except (PermissionError,ValueError,OSError,KeyError,TypeError):
        return dict(status="MODEL_AUTHORIZATION_REQUIRED",model_id=None,
                    credential_present=False,action="no_order",real_calls_started=False)

def research_context(context):
    """Projection for the model: verified public data only, no old forecast package."""
    cutoff=context["as_of"]
    if len(cutoff)>10:
        cutoff=datetime.fromisoformat(cutoff).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    fields=("id","source_id","pdf_sha256","available_at","period","scope","unit","text")
    evidence=[dict(**{k:row[k] for k in fields},**({"value":row["value"]} if "value" in row else {}))
              for row in context["evidence"]]
    return dict(symbol=context["symbol"],issuer_name=context["issuer_name"],as_of=cutoff,
                snapshot_fingerprint=context["snapshot_fingerprint"],evidence=evidence)

def implementation():
    from . import operating_draft_v1, operating_sources_v1, task_execution_v1
    from ....infrastructure.agent_runtime import provider
    modules=(operating_draft_v1,operating_sources_v1,provider,task_execution_v1)
    return {**{m.__name__:_hash(Path(m.__file__).read_bytes()) for m in modules},
            __name__:_hash(Path(__file__).read_bytes())}

class LiveOperatingTaskService(ResearchTaskService):
    """Versioned workflow, sharing D1 locks, immutable versions and atomic head writes."""
    def __init__(self,root,*,test_provider=None,source_loader=None):
        super().__init__(root)
        self.base=require_inside(self.root,self.base/"live-operating-v1","live workflow")
        self.test_provider=test_provider
        self.source_loader=source_loader or build_operating_source_context

    def _daily_budget(self,day,reservation,amount,cfg,*,settle=False):
        """Cross-task durable CNY cap. Unsettled requests remain charged after crashes."""
        directory=require_inside(self.base,self.base/"budget"/day,"daily research budget")
        with self._lock(directory):
            files=sorted((directory/"versions").glob("*.json"))
            if len(files)>512:raise ValueError("DAILY_BUDGET_RECORD_LIMIT")
            previous=None;records={}
            for number,path in enumerate(files,1):
                ref=self._binding(path);row=self._bound(ref)
                if (path.name!=f'{number:04d}-{ref["sha256"]}.json' or row.get("previous")!=previous
                        or row.get("day")!=day or row.get("currency")!="CNY" or row.get("version")!=number):
                    raise ValueError("DAILY_BUDGET_CHAIN_INVALID")
                records=row["records"];previous=ref
            head=directory/"current.json"
            if files and (not head.exists() or json.loads(head.read_bytes())!=previous):
                raise ValueError("DAILY_BUDGET_HEAD_UNPUBLISHED_FAIL_CLOSED")
            if not files and head.exists():raise ValueError("DAILY_BUDGET_HEAD_INVALID")
            records=deepcopy(records)
            if settle:
                if reservation not in records or records[reservation]["status"]!="RESERVED":
                    raise ValueError("DAILY_BUDGET_RESERVATION_MISSING")
                if amount>Decimal(records[reservation]["cost"]):
                    raise ValueError("DAILY_BUDGET_PROVIDER_USAGE_EXCEEDED_RESERVATION")
                records[reservation]=dict(status="SETTLED",cost=str(amount))
            else:
                if reservation in records:raise ValueError("DAILY_BUDGET_RESERVATION_DUPLICATE")
                charged=sum((Decimal(r["cost"]) for r in records.values()),Decimal("0"))
                if charged+amount>Decimal(str(cfg["daily_cost_limit"])):
                    raise ValueError("DAILY_BUDGET_EXHAUSTED_BEFORE_CALL")
                records[reservation]=dict(status="RESERVED",cost=str(amount))
            row=dict(day=day,currency="CNY",version=len(files)+1,previous=previous,
                     records=records,action="no_order")
            raw=_bytes(row);path=directory/"versions"/f'{row["version"]:04d}-{_hash(raw)}.json'
            path.parent.mkdir(parents=True,exist_ok=True);write_new_bytes(path,raw)
            self._head(directory,self._binding(path))

    def _context(self,spec):
        if spec["implementation_sha256"]!=implementation():
            raise ValueError("LIVE_IMPLEMENTATION_CHANGED_NEW_TASK_REQUIRED")
        ctx=self.source_loader(root=self.root,symbol=spec["symbol"],
            binding=spec["source_binding"],now=datetime.fromisoformat(spec["created_at"]))
        if ctx["snapshot_fingerprint"]!=spec["context_fingerprint"]:
            raise ValueError("LIVE_SOURCE_CONTEXT_CHANGED")
        return ctx

    def _load(self,task_id,*,recover=False):
        directory=self._directory(task_id); raw=(directory/"input.json").read_bytes()
        spec=json.loads(raw)
        if (spec.get("schema_version")!=VERSION or spec.get("task_id")!=task_id
                or spec.get("workflow")!="operating_research" or spec.get("action")!="no_order"
                or spec.get("mode") not in {"LIVE_OPERATING","TEST_ONLY_LIVE_CONTRACT"}):
            raise ValueError("INVALID_LIVE_TASK")
        files=sorted((directory/"versions").glob("*.json"))
        if not files or len(files)>256:raise ValueError("LIVE_VERSION_CHAIN_MISSING_OR_UNBOUNDED")
        previous=None; chain=[]
        for number,path in enumerate(files,1):
            pin=self._binding(path);row=self._bound(pin)
            if (path.name!=f'{number:04d}-{pin["sha256"]}.json'
                    or row.get("schema_version")!=VERSION or row.get("version")!=number
                    or row.get("previous")!=previous or row.get("task_id")!=task_id
                    or row.get("input_sha256")!=_hash(raw) or row.get("status") not in STATES
                    or row.get("action")!="no_order" or row.get("formal_eligibility") is not False
                    or type(row.get("new_llm_calls")) is not int or row["new_llm_calls"]<0):
                raise ValueError("LIVE_VERSION_CHAIN_INVALID")
            chain.append(pin);previous=pin
        head=directory/"current.json"
        if not head.exists() and not recover:raise ValueError("LIVE_HEAD_MISSING_EXPLICIT_RESUME_REQUIRED")
        if head.exists() and json.loads(head.read_bytes()) not in chain:raise ValueError("LIVE_HEAD_INVALID")
        if not head.exists() or json.loads(head.read_bytes())!=previous:
            if not recover:raise ValueError("LIVE_UNPUBLISHED_VERSION_EXPLICIT_RESUME_REQUIRED")
            self._head(directory,previous)
        return spec,row,previous

    def _check(self,spec,now):
        try:return self._context(spec),None,None
        except FileNotFoundError:return None,"WAITING_EVIDENCE","EVIDENCE_MISSING"
        except (ValueError,OSError,KeyError,TypeError):return None,"FAILED","SOURCE_OR_IMPLEMENTATION_CHANGED"

    def _result(self,spec,state,context):
        from .operating_draft_v1 import validate_response, build_request
        context=research_context(context)
        roles={}
        if set(state["roles"])-set(ROLES):raise ValueError("LIVE_UNEXPECTED_ROLE_CHECKPOINT")
        for role in ROLES:
            if role not in state["roles"]:continue
            if role!="FUNDAMENTAL" and "FUNDAMENTAL" not in roles:
                raise ValueError("LIVE_FUNDAMENTAL_DEPENDENCY_MISSING")
            pin=state["roles"][role]
            packet=self._bound(pin)
            req=build_request(role,context,max_completion_tokens=spec["config"]["max_completion_tokens_cap"],
                fundamental_draft=roles.get("FUNDAMENTAL") if role!="FUNDAMENTAL" else None)
            if packet["request_sha256"]!=_hash(_bytes(req.__dict__)) or packet["role"]!=role:
                raise ValueError("LIVE_RESPONSE_REQUEST_BINDING_INVALID")
            roles[role]=validate_response(LLMResponse(**packet["response"]),role=role,context=context,
                generated_at=datetime.fromisoformat(packet["generated_at"]))
        return roles

    def _view(self,spec,state,binding,now):
        value=deepcopy(state);context,status,error=self._check(spec,now)
        value.update(record_binding=binding,symbol=spec["symbol"],execution_mode=spec["mode"],
            currency=spec["config"]["currency"],daily_cost_limit=str(spec["config"]["daily_cost_limit"]),
            model_id=spec["config"]["model_id"],workflow=spec["workflow"],max_run_cost=str(spec["config"]["max_run_cost"]),
            scope="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED" if spec["mode"]=="LIVE_OPERATING" else "TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH",
            formal_fact_count=0,approval_changed=False,main_range_adopted=False,
            condition_price=None,personal_quantity=None,context_fingerprint=spec["context_fingerprint"],
            source_binding=spec["source_binding"],research_as_of=spec["created_at"],
            usage_basis="CONFIGURED_RATE_ESTIMATE_NOT_PROVIDER_BILL",
            recovery_boundary="PUBLISHED_ROLE_CHECKPOINTS_ONLY_AMBIGUOUS_CALLS_REMAIN_RESERVED")
        if status and state["status"]!="CANCELLED":value.update(status=status,error_code=error)
        elif context is not None:
            try:
                value["research_draft"]=self._result(spec,state,context)
                fundamental=value["research_draft"].get("FUNDAMENTAL",{}).get("draft",{})
                scenarios=fundamental.get("scenarios",{})
                assumptions=[item for items in scenarios.values() for item in items]
                numeric=sum(item.get("classification")=="FORECAST" for item in assumptions)
                unknown=sum(item.get("classification")=="UNKNOWN" for item in assumptions)
                value["research_completeness"]=dict(scenario_count=len(scenarios),
                    numeric_assumption_count=numeric,unknown_assumption_count=unknown,
                    status="REVIEW_REQUIRED" if numeric else "INSUFFICIENT_FOR_NUMERIC_SCENARIOS",
                    economic_validation="NOT_APPROVED")
                if state["status"]=="SUCCEEDED" and set(value["research_draft"])!=set(ROLES):
                    raise ValueError("LIVE_RESULT_INCOMPLETE")
            except (ValueError,OSError,KeyError,TypeError):
                value.update(status="FAILED",error_code="LIVE_CHECKPOINT_INVALID")
        return value

    def create(self,*,symbol,request_key,now=None):
        now=_now(now)
        if not isinstance(request_key,str) or re.fullmatch(r"[A-Za-z0-9_-]{8,80}",request_key) is None:
            raise ValueError("INVALID_LIVE_REQUEST_KEY")
        cfg=model_configuration(self.root)
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context=self.source_loader(root=self.root,symbol=symbol,now=now)
        task_id="rt-"+_hash(request_key.encode())[:32]
        spec=dict(schema_version=VERSION,task_id=task_id,workflow="operating_research",
            mode="TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING",symbol=symbol,
            request_key_sha256=_hash(request_key.encode()),created_at=now.isoformat(),
            source_binding=context["source_binding"],context_fingerprint=context["snapshot_fingerprint"],
            config=cfg,implementation_sha256=implementation(),action="no_order")
        directory=self._directory(task_id)
        with self._lock(directory):
            if (directory/"input.json").exists():
                old,state,pin=self._load(task_id)
                # Idempotent request pins the original cutoff; new source/config requires a new key.
                comparable=lambda s:{k:v for k,v in s.items() if k not in {"created_at","context_fingerprint"}}
                if comparable(old)!=comparable(spec):raise ValueError("LIVE_REQUEST_KEY_CONFLICT")
                return self._view(old,state,pin,now)
            write_new_bytes(directory/"input.json",_bytes(spec))
            state=dict(status="QUEUED",attempts=0,provider_requests=0,new_llm_calls=0,
                usage=dict(prompt_tokens=0,completion_tokens=0),reserved_cost="0",settled_cost="0",
                reservations={},roles={},created_at=now.isoformat(),action="no_order",
                formal_eligibility=False,error_code=None)
            state,pin=self._save(spec,state,None,now)
            return self._view(spec,state,pin,now)

    def _provider(self,spec):
        current=model_configuration(self.root)
        if current!=spec["config"]:raise PermissionError("MODEL_AUTHORIZATION_CHANGED")
        if self.test_provider is not None:return self.test_provider
        cfg=spec["config"]
        if not os.environ.get(cfg["api_key_env"]):raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        return OpenAICompatibleChatProvider(**{k:cfg[k] for k in ("endpoint","model_id","api_key_env","timeout_seconds","max_completion_tokens_cap")})

    def _drive(self,task_id,now,*,resume):
        from .operating_draft_v1 import build_request, validate_response
        directory=self._directory(task_id)
        with self._lock(directory,"execution"):
            with self._lock(directory):
                spec,state,pin=self._load(task_id,recover=resume)
                context,status,error=self._check(spec,now)
                if state["status"] in {"CANCELLED","SUCCEEDED"}:return self._view(spec,state,pin,now)
                if status:
                    state,pin=self._save(spec,state,pin,now,status=status,error_code=error)
                    return self._view(spec,state,pin,now)
                if resume:
                    if state["attempts"]>=2:raise ValueError("LIVE_ATTEMPT_BUDGET_EXHAUSTED")
                    self._result(spec,state,context)
                    state,pin=self._save(spec,state,pin,now,status="QUEUED",error_code=None)
                    return self._view(spec,state,pin,now)
                if state["status"]!="QUEUED":return self._view(spec,state,pin,now)
                if state["attempts"]>=2:raise ValueError("LIVE_ATTEMPT_BUDGET_EXHAUSTED")
                state,pin=self._save(spec,state,pin,now,status="RUNNING",attempts=state["attempts"]+1,error_code=None)
            try:
                provider=self._provider(spec)
                context=research_context(context)
                for role in ROLES:
                    prior=self._result(spec,state,context)
                    req=build_request(role,context,max_completion_tokens=spec["config"]["max_completion_tokens_cap"],
                        fundamental_draft=prior.get("FUNDAMENTAL") if role!="FUNDAMENTAL" else None)
                    reservation=_hash(os.urandom(32))
                    # UTF-8 bytes + schema + framing is a conservative configured-rate reservation,
                    # not an assertion about the model tokenizer or the provider's final invoice.
                    prompt_cap=len(_bytes(req.__dict__))+4096
                    cfg=spec["config"]
                    reserve=(Decimal(prompt_cap)*Decimal(str(cfg["input_cost_per_million"]))+
                             Decimal(req.max_completion_tokens)*Decimal(str(cfg["output_cost_per_million"])))/Decimal(1000000)
                    with self._lock(directory):
                        spec,state,pin=self._load(task_id)
                        if state["status"]=="CANCELLED":return self._view(spec,state,pin,_now())
                        if role in state["roles"]:continue
                        self._context(spec)
                        provider=self._provider(spec)
                        charged=Decimal(state["reserved_cost"])+Decimal(state["settled_cost"])
                        if state["provider_requests"]>=6 or charged+reserve>Decimal(str(cfg["max_run_cost"])):
                            raise ValueError("LIVE_BUDGET_EXHAUSTED_BEFORE_CALL")
                        budget_day=_now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                        self._daily_budget(budget_day,reservation,reserve,cfg)
                        reservations=deepcopy(state["reservations"])
                        reservations[reservation]=dict(role=role,cost=str(reserve),status="RESERVED",budget_day=budget_day)
                        state,pin=self._save(spec,state,pin,_now(),provider_requests=state["provider_requests"]+1,
                            new_llm_calls=state["new_llm_calls"]+(0 if self.test_provider is not None else 1),
                            reserved_cost=str(Decimal(state["reserved_cost"])+reserve),reservations=reservations)
                    response=provider.complete(req)
                    if (type(response.prompt_tokens) is not int or type(response.completion_tokens) is not int
                            or not 0<=response.prompt_tokens<=prompt_cap or not 0<=response.completion_tokens<=req.max_completion_tokens
                            or response.tool_calls or not isinstance(response.model_id,str) or not response.model_id.strip()):
                        raise ValueError("LIVE_PROVIDER_USAGE_INVALID")
                    # Usage is settled even if the structured research answer is rejected.
                    actual=(Decimal(response.prompt_tokens)*Decimal(str(cfg["input_cost_per_million"]))+
                            Decimal(response.completion_tokens)*Decimal(str(cfg["output_cost_per_million"])))/Decimal(1000000)
                    with self._lock(directory):
                        spec,state,pin=self._load(task_id);reservations=deepcopy(state["reservations"])
                        self._daily_budget(reservations[reservation]["budget_day"],reservation,actual,cfg,settle=True)
                        reservations[reservation].update(status="SETTLED",actual_cost=str(actual))
                        usage={k:state["usage"][k]+getattr(response,k) for k in ("prompt_tokens","completion_tokens")}
                        state,pin=self._save(spec,state,pin,_now(),reservations=reservations,usage=usage,
                            reserved_cost=str(Decimal(state["reserved_cost"])-reserve),
                            settled_cost=str(Decimal(state["settled_cost"])+actual))
                    generated=_now()
                    validate_response(response,role=role,context=context,generated_at=generated)
                    with self._lock(directory):
                        spec,state,pin=self._load(task_id)
                        if state["status"]=="CANCELLED":return self._view(spec,state,pin,_now())
                        self._context(spec)
                        packet=dict(role=role,request_sha256=_hash(_bytes(req.__dict__)),response=response.__dict__,
                            generated_at=generated.isoformat(),context_fingerprint=spec["context_fingerprint"],
                            action="no_order")
                        path=directory/("response-"+reservation+".json");write_new_bytes(path,_bytes(packet))
                        roles=deepcopy(state["roles"]);roles[role]=self._binding(path)
                        state,pin=self._save(spec,state,pin,_now(),roles=roles)
                with self._lock(directory):
                    spec,state,pin=self._load(task_id);self._context(spec);self._result(spec,state,context)
                    if state["status"]!="CANCELLED":
                        state,pin=self._save(spec,state,pin,_now(),status="SUCCEEDED",error_code=None)
                    return self._view(spec,state,pin,_now())
            except Exception as error:
                if isinstance(error,HTTPError):code="PROVIDER_HTTP_"+str(error.code)
                elif isinstance(error,TimeoutError):code="PROVIDER_TIMEOUT_UNSETTLED_RESERVATION_RETAINED"
                elif isinstance(error,(ValueError,PermissionError)) and re.fullmatch("[A-Z0-9_]+",str(error)):code=str(error)
                elif isinstance(error,ValueError):code="STRUCTURED_RESEARCH_OR_SOURCE_REFERENCE_REJECTED"
                else:code="LIVE_PROVIDER_OR_VALIDATION_FAILED"
                with self._lock(directory):
                    spec,state,pin=self._load(task_id)
                    if state["status"]!="CANCELLED":
                        state,pin=self._save(spec,state,pin,_now(),status="FAILED",error_code=code)
                    return self._view(spec,state,pin,_now())

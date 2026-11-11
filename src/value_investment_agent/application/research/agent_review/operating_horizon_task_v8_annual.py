"""V8 annual D2 task; V7 durability helpers, cash-v2 handoff closed."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v7_split as v7
from . import operating_horizon_annual_v3 as annual
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v8-annual-v3"
STORE = "oh-v8-annual-v3"
STAGES = ("annual",)


def implementation():
    return {**v7.implementation(), annual.__name__: _hash(Path(annual.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v7.OperatingHorizonTaskService):
    def __init__(self, root, *, source_loader, source_loader_version, test_provider=None):
        if not callable(source_loader) or not source_loader_version:
            raise ValueError("V8_EXPLICIT_SOURCE_LOADER_REQUIRED")
        super().__init__(root, test_provider=test_provider, allow_live=False,
                         source_loader=source_loader, source_loader_version=source_loader_version)
        self.base = require_inside(self.root, self.base.parent / STORE, "v8 annual tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [spec.get("year")]
                or spec.get("mode") != "TEST_ONLY_LIVE_CONTRACT"
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)
                or set(state.get("stage_validated", [])) - set(STAGES)
                or state.get("cash_binding") is not None):
            raise ValueError("V8_TASK_BINDING_INVALID")
        return spec, state, pin

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("V8_IMPLEMENTATION_CHANGED")
        if spec["source_loader_binding"] != self._loader_binding():
            raise ValueError("V8_SOURCE_LOADER_CHANGED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context.get("symbol") != spec["symbol"]
                or context.get("source_binding") != spec["source_binding"]
                or context.get("snapshot_fingerprint") != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("V8_SOURCE_CONTEXT_CHANGED")
        enriched = live.research_context(context, drivers=True)
        if _hash(_bytes(enriched)) != spec["enriched_context_sha256"]:
            raise ValueError("V8_ENRICHED_CONTEXT_CHANGED")
        request = annual.build_request(enriched, spec["years"],
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        if _hash(_bytes(request.__dict__)) != spec["annual_request_sha256"]:
            raise ValueError("V8_ANNUAL_REQUEST_CHANGED")
        return enriched

    def _request_for_stage(self, spec, state, context, stage):
        if stage != "annual":
            raise ValueError("V8_CASH_V2_CONTRACT_REQUIRED")
        return annual.build_request(context, spec["years"],
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"]), None

    def _verify_annual_checkpoint(self, spec, state, context):
        packet = self._packet(spec, state, "annual")
        if packet is None or "annual" not in state["stage_validated"]:
            raise ValueError("V8_ANNUAL_CHECKPOINT_REQUIRED")
        request, _ = self._request_for_stage(spec, state, context, "annual")
        if packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V8_ANNUAL_REQUEST_CHANGED")
        self._usage(LLMResponse(**packet["response"]), request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "annual", packet)
        return annual.validate_response(LLMResponse(**packet["response"]), context,
                                        spec["years"], datetime.fromisoformat(packet["generated_at"]))

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, task_id=spec["task_id"], symbol=spec["symbol"],
            workflow=CONTRACT, execution_mode=spec["mode"], source_binding=spec["source_binding"],
            research_as_of=spec["created_at"], action="no_order", formal_eligibility=False,
            condition_price=None, research_result=None,
            annual_status=self._stage_status(state, "annual"), cash_status="WAITING_FOR_CASH_V2")
        try:
            context = self._context(spec)
            if "annual" in state["stage_validated"]:
                value["annual_result"] = self._verify_annual_checkpoint(spec, state, context)
        except (ValueError, OSError, KeyError, TypeError):
            value.update(status="FAILED", error_code="V8_REPLAY_INVALID", annual_result=None)
        return value

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        if (self.test_provider is None or type(years) is not list or len(years) != 1
                or type(years[0]) is not int or not isinstance(symbol, str)
                or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V8_TEST_ONLY_IDENTITY_INVALID")
        cfg = live.model_configuration(self.root)
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        enriched = live.research_context(context, drivers=True)
        request = annual.build_request(enriched, years, cfg["max_completion_tokens_cap"])
        mode = "TEST_ONLY_LIVE_CONTRACT"
        task_id = "rt-" + _hash(_bytes([CONTRACT, mode, symbol, years, context["source_binding"]]))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if (spec["config"] != cfg or spec["implementation_sha256"] != implementation()
                        or spec["request_key_sha256"] != _hash(request_key.encode("utf-8"))):
                    raise ValueError("V8_REQUEST_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT, mode=mode, symbol=symbol, year=years[0], years=years,
                request_key_sha256=_hash(request_key.encode("utf-8")), created_at=now.isoformat(),
                source_binding=context["source_binding"], context_fingerprint=context["snapshot_fingerprint"],
                context_sha256=_hash(_bytes(context)), enriched_context_sha256=_hash(_bytes(enriched)),
                source_loader_binding=self._loader_binding(), config=cfg,
                annual_request_sha256=_hash(_bytes(request.__dict__)),
                implementation_sha256=implementation(), action="no_order")
            self._context(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0", settled_cost="0",
                reservations={}, stage_intents={}, stage_responses={}, stage_validated=[],
                cash_binding=None, created_at=now.isoformat(), action="no_order",
                formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _drive(self, task_id, now, *, resume):
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            with self._lock(directory):
                spec, state, pin = self._load(task_id, recover=resume)
                context = self._context(spec)
                if "annual" in state["stage_validated"]:
                    self._verify_annual_checkpoint(spec, state, context)
                    return self._view(spec, state, pin, now)
                if "annual" in state["stage_intents"]:
                    return self._view(spec, state, pin, now)  # ambiguous: never repeat
                if resume or state["status"] != "QUEUED":
                    return self._view(spec, state, pin, now)
                request, _ = self._request_for_stage(spec, state, context, "annual")
                provider = self._provider(spec)
                cfg = spec["config"]
                reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                                     request.max_completion_tokens, cfg)
                if reserve > Decimal(str(cfg["max_run_cost"])):
                    raise ValueError("V8_RUN_BUDGET_EXHAUSTED")
                request_sha = _hash(_bytes(request.__dict__))
                reservation = _hash(_bytes([CONTRACT, task_id, "annual", request_sha]))
                day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                intent = dict(request_sha256=request_sha, reservation=reservation, budget_day=day)
                state, pin = self._save(spec, state, pin, now, status="RUNNING",
                    stage_intents={"annual": intent}, reservations={reservation: dict(
                        status="RESERVED", cost=str(reserve), budget_day=day)},
                    reserved_cost=str(reserve), provider_requests=1, attempts=1)
                self._daily_budget(day, reservation, reserve, cfg)
            response = provider.complete(request)
            generated = _now()
            packet = dict(stage="annual", request_sha256=request_sha,
                context_sha256=spec["enriched_context_sha256"],
                implementation_sha256=spec["implementation_sha256"],
                response=response.__dict__, generated_at=generated.isoformat(), action="no_order")
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                path = directory / "response-annual.json"
                write_new_bytes(path, _bytes(packet))
                state, pin = self._save(spec, state, pin, generated,
                    stage_responses={"annual": self._binding(path)})
                self._usage(response, request, cfg["model_id"])
                actual = self._cost(response.prompt_tokens, response.completion_tokens, cfg)
                self._daily_budget(day, reservation, actual, cfg, settle=True)
                state, pin = self._save(spec, state, pin, generated,
                    reservations={reservation: dict(status="SETTLED", cost=str(reserve),
                        budget_day=day, actual_cost=str(actual))},
                    reserved_cost="0", settled_cost=str(actual),
                    usage=dict(prompt_tokens=response.prompt_tokens,
                               completion_tokens=response.completion_tokens))
                self._verify_stage_settlement(spec, state, "annual", packet)
                annual.validate_response(response, self._context(spec), spec["years"], generated)
                state, pin = self._save(spec, state, pin, generated,
                    stage_validated=["annual"], status="WAITING_EVIDENCE",
                    error_code="V8_CASH_V2_CONTRACT_REQUIRED")
                return self._view(spec, state, pin, generated)

"""Versioned durable 2027 annual and cash D2 research task."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v7_split as v7
from . import operating_horizon_annual_v3 as annual
from . import operating_horizon_split_v8 as split
from . import operating_horizon_request_v11 as request_v11
from . import operating_q3_issuer_plan_loader_v8_600519 as official
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v11-2027-live"
STORE = "oh-v11-2027-live"
STAGES = ("annual", "cash")


def implementation():
    return {**v7.implementation(), **official.implementation(),
            split.__name__: _hash(Path(split.__file__).read_bytes()),
            request_v11.__name__: _hash(Path(request_v11.__file__).read_bytes()),
            annual.__name__: _hash(Path(annual.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v7.OperatingHorizonTaskService):
    def __init__(self, root, *, source_loader=official.load_current,
                 source_loader_version=official.VERSION, test_provider=None):
        if not callable(source_loader) or not source_loader_version:
            raise ValueError("V8_EXPLICIT_SOURCE_LOADER_REQUIRED")
        super().__init__(root, test_provider=test_provider, allow_live=test_provider is None,
                         source_loader=source_loader, source_loader_version=source_loader_version)
        self.base = require_inside(self.root, self.base.parent / STORE, "v8 annual tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [spec.get("year")]
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING")
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)
                or set(state.get("stage_validated", [])) - set(STAGES)
                or (state.get("cash_binding") is not None and
                    not isinstance(state["cash_binding"], dict))):
            raise ValueError("V8_TASK_BINDING_INVALID")
        return spec, state, pin

    def _provider(self, spec):
        if self.test_provider is None and spec["config"].get("model_id") != "deepseek-flash":
            raise PermissionError("V10_EXACT_MODEL_REQUIRED")
        return super()._provider(spec)

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
        enriched = official.project_research_context(context)
        if _hash(_bytes(enriched)) != spec["enriched_context_sha256"]:
            raise ValueError("V8_ENRICHED_CONTEXT_CHANGED")
        request = request_v11.build_annual_request(context, spec["years"],
            source_binding=spec["source_binding"],
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        if _hash(_bytes(request.__dict__)) != spec["annual_request_sha256"]:
            raise ValueError("V8_ANNUAL_REQUEST_CHANGED")
        return context

    def _request_for_stage(self, spec, state, context, stage):
        if stage == "annual":
            return request_v11.build_annual_request(context, spec["years"],
                source_binding=spec["source_binding"],
                max_completion_tokens=spec["config"]["max_completion_tokens_cap"]), None
        if stage != "cash":
            raise ValueError("V9_STAGE_INVALID")
        packet = self._packet(spec, state, "annual")
        self._verify_annual_checkpoint(spec, state, context)
        requests = split.build_requests(context, spec["years"],
            source_binding=spec["source_binding"],
            annual_response=LLMResponse(**packet["response"]),
            annual_generated_at=datetime.fromisoformat(packet["generated_at"]),
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        return requests.cash, requests.binding

    def _verify_annual_checkpoint(self, spec, state, context):
        packet = self._packet(spec, state, "annual")
        if packet is None or "annual" not in state["stage_validated"]:
            raise ValueError("V8_ANNUAL_CHECKPOINT_REQUIRED")
        request, _ = self._request_for_stage(spec, state, context, "annual")
        if packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V8_ANNUAL_REQUEST_CHANGED")
        self._usage(LLMResponse(**packet["response"]), request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "annual", packet)
        return annual.validate_response(LLMResponse(**packet["response"]),
                                        split._annual_context(split._project(context, spec["source_binding"])),
                                        spec["years"], datetime.fromisoformat(packet["generated_at"]))

    def _result(self, spec, state, context):
        if not set(STAGES).issubset(state["stage_responses"]):
            return None
        annual_packet = self._packet(spec, state, "annual")
        cash_packet = self._packet(spec, state, "cash")
        request, binding = self._request_for_stage(spec, state, context, "cash")
        if (binding != state["cash_binding"] or
                _hash(_bytes(request.__dict__)) != cash_packet["request_sha256"]):
            raise ValueError("V9_CASH_BINDING_CHANGED")
        self._usage(LLMResponse(**cash_packet["response"]), request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", cash_packet)
        return split.validate_responses(
            LLMResponse(**annual_packet["response"]), LLMResponse(**cash_packet["response"]),
            context=context, years=spec["years"], source_binding=spec["source_binding"],
            binding=binding, annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            cash_generated_at=datetime.fromisoformat(cash_packet["generated_at"]))

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, task_id=spec["task_id"], symbol=spec["symbol"],
            workflow=CONTRACT, execution_mode=spec["mode"], source_binding=spec["source_binding"],
            research_as_of=spec["created_at"], action="no_order", formal_eligibility=False,
            condition_price=None, research_result=None, annual_result=None,
            annual_status=self._stage_status(state, "annual"),
            cash_status=self._stage_status(state, "cash"))
        try:
            context = self._context(spec)
            if "annual" in state["stage_validated"]:
                value["annual_result"] = self._verify_annual_checkpoint(spec, state, context)
            if state["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}:
                try:
                    value["research_result"] = self._result(spec, state, context)
                except split.FullValidatorBlocked as blocked:
                    if (state["status"] != "WAITING_EVIDENCE"
                            or state.get("cash_policy_status") != blocked.cash_policy_status
                            or state.get("full_validator_reason") != blocked.full_validator_reason):
                        raise
                    value["cash_policy_status"] = blocked.cash_policy_status
                    value["full_validator_reason"] = blocked.full_validator_reason
        except (ValueError, OSError, KeyError, TypeError):
            value.update(status="FAILED", error_code="V9_REPLAY_INVALID",
                         annual_result=None, research_result=None)
        return value

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        if (years != [2027] or symbol != "600519"
                or not isinstance(symbol, str)
                or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V10_IDENTITY_INVALID")
        cfg = live.model_configuration(self.root)
        if self.test_provider is None:
            if cfg["model_id"] != "deepseek-flash":
                raise PermissionError("V10_EXACT_MODEL_REQUIRED")
            if not os.environ.get(cfg["api_key_env"]):
                raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        enriched = official.project_research_context(context)
        request = request_v11.build_annual_request(context, years,
            source_binding=context["source_binding"],
            max_completion_tokens=cfg["max_completion_tokens_cap"])
        mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
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
        try:
            return self._drive_once(task_id, now, resume=resume)
        except Exception:
            # A provider intent is irreversible. Keep its response and budget
            # settlement, if present, and never turn failure into a retry.
            directory = self._directory(task_id)
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, pin, _now())
                stage = "cash" if "annual" in state["stage_validated"] else "annual"
                intent = stage in state["stage_intents"]
                returned = stage in state["stage_responses"]
                code = ("V9_" + stage.upper() + "_RESPONSE_REJECTED" if returned else
                        "V9_" + stage.upper() + "_PROVIDER_AMBIGUOUS" if intent else
                        "V9_TASK_EXECUTION_FAILED")
                state, pin = self._save(spec, state, pin, _now(),
                    status="FAILED", error_code=code)
                return self._view(spec, state, pin, _now())

    def _drive_once(self, task_id, now, *, resume):
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
          for stage in STAGES:
            with self._lock(directory):
                spec, state, pin = self._load(task_id, recover=resume)
                if state["status"] in {"CANCELLED", "SUCCEEDED", "FAILED", "WAITING_EVIDENCE"}:
                    return self._view(spec, state, pin, now)
                context = self._context(spec)
                if "annual" in state["stage_validated"]:
                    self._verify_annual_checkpoint(spec, state, context)
                if stage in state["stage_validated"]:
                    continue
                if stage in state["stage_intents"]:
                    return self._view(spec, state, pin, now)
                if resume or state["status"] not in {"QUEUED", "RUNNING"}:
                    return self._view(spec, state, pin, now)
                request, cash_binding = self._request_for_stage(spec, state, context, stage)
                provider = self._provider(spec)
                cfg = spec["config"]
                reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                                     request.max_completion_tokens, cfg)
                if Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"])):
                    raise ValueError("V9_RUN_BUDGET_EXHAUSTED")
                request_sha = _hash(_bytes(request.__dict__))
                reservation = _hash(_bytes([CONTRACT, task_id, stage, request_sha]))
                day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                intent = dict(request_sha256=request_sha, reservation=reservation, budget_day=day)
                intents = deepcopy(state["stage_intents"])
                intents[stage] = intent
                reservations = deepcopy(state["reservations"])
                reservations[reservation] = dict(status="RESERVED", cost=str(reserve), budget_day=day)
                state, pin = self._save(spec, state, pin, now, status="RUNNING",
                    stage_intents=intents, cash_binding=cash_binding or state["cash_binding"],
                    reservations=reservations, reserved_cost=str(reserve),
                    provider_requests=state["provider_requests"] + 1,
                    attempts=state["attempts"] + 1)
                self._daily_budget(day, reservation, reserve, cfg)
            response = provider.complete(request)
            generated = _now()
            packet = dict(stage=stage, request_sha256=request_sha,
                context_sha256=spec["enriched_context_sha256"],
                implementation_sha256=spec["implementation_sha256"],
                response=response.__dict__, generated_at=generated.isoformat(), action="no_order")
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                path = directory / ("response-" + stage + ".json")
                write_new_bytes(path, _bytes(packet))
                responses = deepcopy(state["stage_responses"])
                responses[stage] = self._binding(path)
                state, pin = self._save(spec, state, pin, generated,
                    stage_responses=responses)
                self._usage(response, request, cfg["model_id"])
                actual = self._cost(response.prompt_tokens, response.completion_tokens, cfg)
                self._daily_budget(day, reservation, actual, cfg, settle=True)
                reservations = deepcopy(state["reservations"])
                reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                state, pin = self._save(spec, state, pin, generated,
                    reservations=reservations, reserved_cost="0",
                    settled_cost=str(Decimal(state["settled_cost"]) + actual),
                    usage=dict(prompt_tokens=state["usage"]["prompt_tokens"] + response.prompt_tokens,
                               completion_tokens=state["usage"]["completion_tokens"] + response.completion_tokens))
                self._verify_stage_settlement(spec, state, stage, packet)
                context = self._context(spec)
                if stage == "annual":
                    self._verify_annual_checkpoint(spec, {**state, "stage_validated": ["annual"]}, context)
                else:
                  try:
                    split.validate_responses(
                        LLMResponse(**self._packet(spec, state, "annual")["response"]), response,
                        context=context, years=spec["years"], source_binding=spec["source_binding"],
                        binding=state["cash_binding"],
                        annual_generated_at=datetime.fromisoformat(self._packet(spec, state, "annual")["generated_at"]),
                        cash_generated_at=generated)
                  except split.FullValidatorBlocked as blocked:
                    state, pin = self._save(spec, state, pin, generated,
                        stage_validated=list(state["stage_validated"]) + [stage],
                        status="WAITING_EVIDENCE", error_code="V9_FULL_VALIDATOR_BLOCKED",
                        cash_policy_status=blocked.cash_policy_status,
                        full_validator_reason=blocked.full_validator_reason)
                    return self._view(spec, state, pin, generated)
                state, pin = self._save(spec, state, pin, generated,
                    stage_validated=list(state["stage_validated"]) + [stage])
          with self._lock(directory):
            spec, state, pin = self._load(task_id)
            self._result(spec, state, self._context(spec))
            state, pin = self._save(spec, state, pin, _now(), status="SUCCEEDED", error_code=None)
            return self._view(spec, state, pin, _now())

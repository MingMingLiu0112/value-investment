"""Versioned durable 2027 annual-citation D2 research task."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v7_split as v7
from . import operating_horizon_annual_v3 as annual
from . import operating_horizon_split_v13 as split
from . import operating_cash_policy_draft_v3 as cash_v3
from . import operating_cash_policy_draft_v14 as cash_v14
from . import operating_cash_policy_draft_v15 as cash_v15
from . import operating_horizon_request_v11 as request_v11
from . import operating_horizon_request_v13 as request_v13
from . import operating_horizon_request_v16 as request_v16
from . import operating_horizon_carryover_v13 as carryover
from . import operating_q3_issuer_plan_loader_v8_600519 as official
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import (
    LLMResponse, OpenAICompatibleChatProvider,
)

CONTRACT = "operating-horizon-task-v16-2027-live"
STORE = "oh-v16-2027-live"
STAGES = ("annual", "cash")


def implementation():
    return {**v7.implementation(), **official.implementation(),
            split.__name__: _hash(Path(split.__file__).read_bytes()),
            cash_v14.__name__: _hash(Path(cash_v14.__file__).read_bytes()),
            cash_v15.__name__: _hash(Path(cash_v15.__file__).read_bytes()),
            request_v11.__name__: _hash(Path(request_v11.__file__).read_bytes()),
            request_v13.__name__: _hash(Path(request_v13.__file__).read_bytes()),
            request_v16.__name__: _hash(Path(request_v16.__file__).read_bytes()),
            annual.__name__: _hash(Path(annual.__file__).read_bytes()),
            carryover.__name__: _hash(Path(carryover.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def _v15_cash_request(request, context, source_binding):
    """Retain V13 annual binding and append the V15 cash-only prompt delta."""
    projected = split._project(context, source_binding)
    before = cash_v3.build_request(projected, [2027], request.max_completion_tokens)
    after = cash_v15.build_request(projected, [2027], request.max_completion_tokens)
    if not after.system.startswith(before.system) or after.user != before.user:
        raise ValueError("V16_CASH_PROMPT_BASE_CHANGED")
    return replace(request, system=request.system + after.system[len(before.system):])


class OperatingHorizonTaskService(v7.OperatingHorizonTaskService):
    def __init__(self, root, *, source_loader=official.load_current,
                 source_loader_version=official.VERSION, test_provider=None,
                 test_v12_service=None):
        if not callable(source_loader) or not source_loader_version:
            raise ValueError("V8_EXPLICIT_SOURCE_LOADER_REQUIRED")
        super().__init__(root, test_provider=test_provider, allow_live=test_provider is None,
                         source_loader=source_loader, source_loader_version=source_loader_version)
        self.base = require_inside(self.root, self.base.parent / STORE, "v16 annual tasks")
        if test_v12_service is not None and (test_provider is None
                or test_v12_service.root.resolve() != self.root.resolve()
                or test_v12_service.test_provider is None):
            raise ValueError("V16_TEST_V12_SERVICE_INVALID")
        self.test_v12_service = test_v12_service

    def _replay_cash(self, source_task_id, **expected):
        if self.test_v12_service is None:
            return carryover.replay_cash(self.root, source_task_id, **expected)
        # Test-only annual admission uses real V12 service and sealed records.
        source = self.test_v12_service
        spec, state, head = source._load(source_task_id)
        if (spec.get("mode") != "TEST_ONLY_LIVE_CONTRACT"
                or spec.get("years") != [2027]
                or spec.get("task_contract") != carryover.v12.CONTRACT
                or state.get("action") != "no_order"
                or state.get("provider_requests", 0) < 1
                or spec.get("source_binding") != expected["expected_source_binding"]
                or spec.get("context_sha256") != expected["expected_context_sha256"]
                or state.get("status") != "FAILED"
                or state.get("error_code") != "V12_TASK_EXECUTION_FAILED"
                or state.get("stage_validated") != ["annual"]
                or "cash" in state.get("stage_intents", {})
                or "cash" in state.get("stage_responses", {})):
            raise ValueError("V16_TEST_V12_ANNUAL_INVALID")
        context = source._context(spec)
        annual = source._verify_annual_checkpoint(spec, state, context)
        packet = source._packet(spec, state, "annual")
        pin = state["stage_responses"]["annual"]
        response = LLMResponse(**packet["response"])
        intent = state["stage_intents"]["annual"]
        settlement = state["reservations"][intent["reservation"]]
        if (_hash(response.text.encode("utf-8")) != expected["expected_annual_response_sha256"]
                or settlement.get("budget_day") != expected["expected_budget_day"]
                or settlement.get("status") != "SETTLED"
                or packet["request_sha256"] != spec["annual_request_sha256"]):
            raise ValueError("V16_TEST_V12_PIN_INVALID")
        request, binding = request_v13.build_cash_request(context, [2027],
            source_binding=spec["source_binding"], annual_response=response,
            annual_generated_at=datetime.fromisoformat(packet["generated_at"]))
        lineage = dict(version="V16_TEST_ONLY_V12_ANNUAL", action="no_order",
            source_task_id=source_task_id, source_contract=carryover.v12.CONTRACT,
            source_record_binding=head, source_binding=spec["source_binding"],
            source_context_sha256=spec["context_sha256"],
            source_annual_response_binding=pin,
            source_annual_response_sha256=_hash(response.text.encode("utf-8")),
            source_annual_result_sha256=_hash(_bytes(annual)),
            source_budget_day=settlement["budget_day"],
            v13_cash_binding=binding,
            v13_cash_request_sha256=_hash(_bytes(request.__dict__)))
        return request, lineage, context, packet

    def _imported(self, spec):
        pin = spec["imported_annual"]
        request, lineage, context, packet = self._replay_cash(pin["source_task_id"],
            expected_source_binding=pin["source_binding"],
            expected_context_sha256=pin["source_context_sha256"],
            expected_annual_response_sha256=pin["source_annual_response_sha256"],
            expected_budget_day=pin["source_budget_day"])
        if (lineage != pin or spec["source_binding"] != lineage["source_binding"]
                or spec["context_sha256"] != lineage["source_context_sha256"]
                or spec["cash_request_sha256"] != _hash(_bytes(_v15_cash_request(request, context, lineage["source_binding"]).__dict__))
                or spec["symbol"] != context["symbol"]):
            raise ValueError("V16_IMPORTED_LINEAGE_CHANGED")
        return _v15_cash_request(request, context, lineage["source_binding"]), lineage, context, packet

    def create_imported(self, *, source_task_id, request_key, expected_source_binding,
                        expected_context_sha256, expected_annual_response_sha256,
                        expected_budget_day, now=None):
        """Create a separate V13 cash task without an annual provider intent."""
        now = _now(now)
        if (not isinstance(request_key, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V16_IDENTITY_INVALID")
        request, lineage, context, _ = self._replay_cash(source_task_id,
            expected_source_binding=expected_source_binding,
            expected_context_sha256=expected_context_sha256,
            expected_annual_response_sha256=expected_annual_response_sha256,
            expected_budget_day=expected_budget_day)
        request = _v15_cash_request(request, context, lineage["source_binding"])
        cfg = self._configuration()
        if self.test_provider is None and cfg["model_id"] != "deepseek-flash":
            raise PermissionError("V16_EXACT_MODEL_REQUIRED")
        task_id = "rt-" + _hash(_bytes([CONTRACT, "IMPORTED_V12", source_task_id,
            lineage["source_record_binding"], context["symbol"]]))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if (spec.get("imported_annual") != lineage or spec["config"] != cfg
                        or spec["request_key_sha256"] != _hash(request_key.encode("utf-8"))):
                    raise ValueError("V16_IMPORT_REQUEST_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT,
                mode="TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING",
                symbol=context["symbol"],
                year=2027, years=[2027], request_key_sha256=_hash(request_key.encode("utf-8")),
                created_at=now.isoformat(), source_binding=lineage["source_binding"],
                context_sha256=lineage["source_context_sha256"],
                cash_request_sha256=_hash(_bytes(request.__dict__)),
                enriched_context_sha256=_hash(_bytes(official.project_research_context(context))),
                config=cfg, implementation_sha256=implementation(),
                imported_annual=lineage, action="no_order")
            self._imported(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0",
                settled_cost="0", reservations={}, stage_intents={}, stage_responses={},
                stage_validated=["annual"], cash_binding=None, created_at=now.isoformat(),
                action="no_order", formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [spec.get("year")]
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING")
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)
                or set(state.get("stage_validated", [])) - set(STAGES)
                or (state.get("cash_binding") is not None and
                    not isinstance(state["cash_binding"], dict))
                or ("imported_annual" in spec and
                    (state.get("stage_validated") not in (["annual"], ["annual", "cash"])
                     or "annual" in state["stage_intents"]
                     or "annual" in state["stage_responses"]
                     or spec["imported_annual"].get("action") != "no_order"))):
            raise ValueError("V8_TASK_BINDING_INVALID")
        if "imported_annual" in spec:
            self._imported(spec)
        return spec, state, pin

    def _provider(self, spec):
        if self.test_provider is None and spec["config"].get("model_id") != "deepseek-flash":
            raise PermissionError("V16_EXACT_MODEL_REQUIRED")
        if self._configuration() != spec["config"]:
            raise PermissionError("MODEL_AUTHORIZATION_CHANGED")
        if self.test_provider is not None:
            return self.test_provider
        cfg = spec["config"]
        if not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        return OpenAICompatibleChatProvider(**{k: cfg[k] for k in (
            "endpoint", "model_id", "api_key_env", "timeout_seconds",
            "max_completion_tokens_cap", "response_format_mode", "thinking_mode") if k in cfg})

    def _configuration(self):
        # Existing configuration loader remains the authorization gate. Its
        # 4096 limit is retained on disk; V13 explicitly raises only the
        # effective per-request cap while preserving all cost limits/rates.
        cfg = live.model_configuration(self.root)
        if cfg["max_completion_tokens_cap"] != 4096:
            raise ValueError("V16_BASE_CAP_MUST_BE_4096")
        return {**cfg, "max_completion_tokens_cap": request_v13.COMPLETION_CAP}

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("V8_IMPLEMENTATION_CHANGED")
        if "imported_annual" in spec:
            _, _, context, _ = self._imported(spec)
            return context
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
        request = request_v16.build_annual_request(context, spec["years"],
            source_binding=spec["source_binding"])
        if _hash(_bytes(request.__dict__)) != spec["annual_request_sha256"]:
            raise ValueError("V8_ANNUAL_REQUEST_CHANGED")
        return context

    def _request_for_stage(self, spec, state, context, stage):
        if "imported_annual" in spec:
            if stage != "cash":
                raise ValueError("V16_IMPORTED_ANNUAL_HAS_NO_LOCAL_REQUEST")
            request, lineage, _, _ = self._imported(spec)
            return request, lineage["v13_cash_binding"]
        if stage == "annual":
            return request_v16.build_annual_request(context, spec["years"],
                source_binding=spec["source_binding"]), None
        if stage != "cash":
            raise ValueError("V9_STAGE_INVALID")
        packet = self._packet(spec, state, "annual")
        self._verify_annual_checkpoint(spec, state, context)
        request, binding = request_v13.build_cash_request(context, spec["years"],
            source_binding=spec["source_binding"],
            annual_response=LLMResponse(**packet["response"]),
            annual_generated_at=datetime.fromisoformat(packet["generated_at"]))
        return _v15_cash_request(request, context, spec["source_binding"]), binding

    def _verify_annual_checkpoint(self, spec, state, context):
        if "imported_annual" in spec:
            _, lineage, imported_context, _ = self._imported(spec)
            if ("annual" not in state["stage_validated"]
                    or _hash(_bytes(imported_context)) != _hash(_bytes(context))):
                raise ValueError("V16_IMPORTED_ANNUAL_CHANGED")
            return {"origin": "V12_EXTERNAL", "source_task_id": lineage["source_task_id"],
                    "source_annual_result_sha256": lineage["source_annual_result_sha256"]}
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
        if "imported_annual" in spec:
            if "cash" not in state["stage_responses"]:
                return None
            _, _, _, annual_packet = self._imported(spec)
        elif not set(STAGES).issubset(state["stage_responses"]):
            return None
        else:
            annual_packet = self._packet(spec, state, "annual")
        cash_packet = self._packet(spec, state, "cash")
        request, binding = self._request_for_stage(spec, state, context, "cash")
        if (binding != state["cash_binding"] or
                _hash(_bytes(request.__dict__)) != cash_packet["request_sha256"]):
            raise ValueError("V9_CASH_BINDING_CHANGED")
        self._usage(LLMResponse(**cash_packet["response"]), request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", cash_packet)
        cash_v15_result = cash_v15.validate_response(LLMResponse(**cash_packet["response"]),
            split._project(context, spec["source_binding"]), spec["years"],
            datetime.fromisoformat(cash_packet["generated_at"]))
        result = split.validate_responses(
            LLMResponse(**annual_packet["response"]), LLMResponse(**cash_packet["response"]),
            context=context, years=spec["years"], source_binding=spec["source_binding"],
            binding=binding, annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            cash_generated_at=datetime.fromisoformat(cash_packet["generated_at"]))
        result["cash_policy_v15"] = cash_v15_result
        return result

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
                checked = self._verify_annual_checkpoint(spec, state, context)
                if "imported_annual" in spec:
                    value["imported_annual"] = checked
                    value["annual_status"] = "IMPORTED_V12"
                else:
                    value["annual_result"] = checked
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
        if (years != [2027]
                or not isinstance(symbol, str)
                or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V10_IDENTITY_INVALID")
        cfg = self._configuration()
        if self.test_provider is None:
            if cfg["model_id"] != "deepseek-flash":
                raise PermissionError("V10_EXACT_MODEL_REQUIRED")
            if not os.environ.get(cfg["api_key_env"]):
                raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        enriched = official.project_research_context(context)
        request = request_v16.build_annual_request(context, years,
            source_binding=context["source_binding"])
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
        except Exception as error:
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
                cap_rejected = (intent and not returned and isinstance(error, ValueError)
                    and str(error) == "LLM response incomplete: completion token cap reached")
                code = ("V16_" + stage.upper() + "_RESPONSE_REJECTED" if returned else
                        "V16_" + stage.upper() + "_COMPLETION_CAP_REJECTED" if cap_rejected else
                        "V16_" + stage.upper() + "_PROVIDER_AMBIGUOUS" if intent else
                        "V16_TASK_EXECUTION_FAILED")
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
                    annual_packet = (self._imported(spec)[3] if "imported_annual" in spec
                                     else self._packet(spec, state, "annual"))
                    cash_v15.validate_response(response,
                        split._project(context, spec["source_binding"]), spec["years"], generated)
                    split.validate_responses(
                        LLMResponse(**annual_packet["response"]), response,
                        context=context, years=spec["years"], source_binding=spec["source_binding"],
                        binding=state["cash_binding"],
                        annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
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

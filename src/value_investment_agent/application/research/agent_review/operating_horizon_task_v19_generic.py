"""Durable, plan-neutral 2027 operating-horizon task."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v16_live as v16
from . import operating_horizon_annual_v3 as annual
from . import operating_cash_policy_draft_v16_generic as cash
from . import operating_task_v2 as live
from . import operating_horizon_sources_v1 as generic_sources
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v19-generic-2027"
STORE = "oh-v19-generic-2027"
STAGES = ("annual", "cash")


def implementation():
    return {**v16.implementation(), **generic_sources.implementation(),
            cash.__name__: _hash(Path(cash.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v16.OperatingHorizonTaskService):
    def __init__(self, root, *, source_loader=generic_sources.build_operating_horizon_source_context,
                 source_loader_version=generic_sources.VERSION, test_provider=None):
        super().__init__(root, source_loader=source_loader,
                         source_loader_version=source_loader_version, test_provider=test_provider)
        self.base = require_inside(self.root, self.base.parent / STORE, "v19 generic tasks")

    def _daily_budget(self, day, reservation, amount, cfg, *, settle=False):
        # The D1 ledger is shared across research task versions.
        return live.LiveOperatingTaskService(self.root)._daily_budget(
            day, reservation, amount, cfg, settle=settle)

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [2027]
                or spec.get("action") != "no_order" or state.get("action") != "no_order"
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING")
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)
                or state.get("stage_validated") not in ([], ["annual"], ["annual", "cash"])):
            raise ValueError("V19_TASK_BINDING_INVALID")
        self._context(spec)
        return spec, state, pin

    def _context(self, spec):
        if (spec["implementation_sha256"] != implementation()
                or spec["source_loader_binding"] != self._loader_binding()):
            raise ValueError("V19_IMPLEMENTATION_OR_LOADER_CHANGED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context.get("symbol") != spec["symbol"]
                or context.get("source_binding") != spec["source_binding"]
                or context.get("snapshot_fingerprint") != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("V19_SOURCE_CHANGED")
        cash._source(context, spec["source_binding"])
        request, _ = self._request_for_stage(spec, {}, context, "annual")
        if _hash(_bytes(request.__dict__)) != spec["annual_request_sha256"]:
            raise ValueError("V19_ANNUAL_REQUEST_CHANGED")
        return context

    def _request_for_stage(self, spec, state, context, stage):
        if stage == "annual":
            return annual.build_request(cash._source(context, spec["source_binding"]), [2027],
                spec["config"]["max_completion_tokens_cap"]), None
        if stage != "cash":
            raise ValueError("V19_STAGE_INVALID")
        packet = self._packet(spec, state, "annual")
        self._verify_annual_checkpoint(spec, state, context)
        return cash.build_staged_cash_request(context, spec["source_binding"],
            LLMResponse(**packet["response"]), datetime.fromisoformat(packet["generated_at"]))

    def _verify_annual_checkpoint(self, spec, state, context):
        packet = self._packet(spec, state, "annual")
        if packet is None or "annual" not in state["stage_validated"]:
            raise ValueError("V19_ANNUAL_CHECKPOINT_REQUIRED")
        request, _ = self._request_for_stage(spec, state, context, "annual")
        if packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V19_ANNUAL_REQUEST_CHANGED")
        response = LLMResponse(**packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "annual", packet)
        return annual.validate_response(response, cash._source(context, spec["source_binding"]),
            [2027], datetime.fromisoformat(packet["generated_at"]))

    def _result(self, spec, state, context):
        if not set(STAGES).issubset(state["stage_responses"]):
            return None
        annual_packet = self._packet(spec, state, "annual")
        cash_packet = self._packet(spec, state, "cash")
        request, binding = self._request_for_stage(spec, state, context, "cash")
        if binding != state["cash_binding"] or cash_packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V19_CASH_BINDING_CHANGED")
        response = LLMResponse(**cash_packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", cash_packet)
        return cash.validate_staged_responses(LLMResponse(**annual_packet["response"]), response,
            context=context, source_binding=spec["source_binding"], binding=binding,
            annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            cash_generated_at=datetime.fromisoformat(cash_packet["generated_at"]))

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, task_id=spec["task_id"], symbol=spec["symbol"],
            workflow=CONTRACT, execution_mode=spec["mode"], source_binding=spec["source_binding"],
            research_as_of=spec["created_at"], action="no_order", formal_eligibility=False,
            condition_price=None, annual_result=None, research_result=None,
            annual_status=self._stage_status(state, "annual"), cash_status=self._stage_status(state, "cash"))
        try:
            context = self._context(spec)
            if "annual" in state["stage_validated"]:
                value["annual_result"] = self._verify_annual_checkpoint(spec, state, context)
            if state["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}:
                value["research_result"] = self._result(spec, state, context)
        except (ValueError, OSError, KeyError, TypeError):
            value.update(status="FAILED", error_code="V19_REPLAY_INVALID",
                         annual_result=None, research_result=None)
        return value

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        if (years != [2027] or not isinstance(symbol, str) or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V19_IDENTITY_INVALID")
        cfg = self._configuration()
        if self.test_provider is None:
            if cfg["model_id"] != "deepseek-flash":
                raise PermissionError("V19_EXACT_MODEL_REQUIRED")
            if not os.environ.get(cfg["api_key_env"]):
                raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        projected = cash._source(context, context["source_binding"])
        request = annual.build_request(projected, years, cfg["max_completion_tokens_cap"])
        mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING"
        task_id = "rt-" + _hash(_bytes([CONTRACT, mode, symbol, years, context["source_binding"]]))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if spec["config"] != cfg or spec["request_key_sha256"] != _hash(request_key.encode("utf-8")):
                    raise ValueError("V19_REQUEST_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT, mode=mode, symbol=symbol, year=2027, years=years,
                request_key_sha256=_hash(request_key.encode("utf-8")), created_at=now.isoformat(),
                source_binding=context["source_binding"], context_sha256=_hash(_bytes(context)),
                context_fingerprint=context["snapshot_fingerprint"],
                enriched_context_sha256=_hash(_bytes(context)), source_loader_binding=self._loader_binding(),
                config=cfg, annual_request_sha256=_hash(_bytes(request.__dict__)),
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
            directory = self._directory(task_id)
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, pin, _now())
                stage = "cash" if "annual" in state["stage_validated"] else "annual"
                code = ("V19_" + stage.upper() + "_RESPONSE_REJECTED" if stage in state["stage_responses"] else
                        "V19_" + stage.upper() + "_PROVIDER_AMBIGUOUS" if stage in state["stage_intents"] else
                        "V19_TASK_EXECUTION_FAILED")
                state, pin = self._save(spec, state, pin, _now(), status="FAILED", error_code=code)
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
                    if stage in state["stage_intents"] or state["status"] not in {"QUEUED", "RUNNING"}:
                        return self._view(spec, state, pin, now)
                    request, cash_binding = self._request_for_stage(spec, state, context, stage)
                    provider = self._provider(spec)
                    cfg = spec["config"]
                    reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                                         request.max_completion_tokens, cfg)
                    if Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"])):
                        raise ValueError("V19_RUN_BUDGET_EXHAUSTED")
                    request_sha = _hash(_bytes(request.__dict__))
                    reservation = _hash(_bytes([CONTRACT, task_id, stage, request_sha]))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    intents = deepcopy(state["stage_intents"])
                    intents[stage] = dict(request_sha256=request_sha, reservation=reservation, budget_day=day)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation] = dict(status="RESERVED", cost=str(reserve), budget_day=day)
                    # An exhausted shared budget is a preflight rejection, not
                    # an ambiguous provider call. Reserve before recording intent.
                    self._daily_budget(day, reservation, reserve, cfg)
                    state, pin = self._save(spec, state, pin, now, status="RUNNING",
                        stage_intents=intents, cash_binding=cash_binding or state["cash_binding"],
                        reservations=reservations, reserved_cost=str(reserve),
                        provider_requests=state["provider_requests"] + 1, attempts=state["attempts"] + 1)
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
                    state, pin = self._save(spec, state, pin, generated, stage_responses=responses)
                    self._usage(response, request, cfg["model_id"])
                    actual = self._cost(response.prompt_tokens, response.completion_tokens, cfg)
                    self._daily_budget(day, reservation, actual, cfg, settle=True)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                    state, pin = self._save(spec, state, pin, generated, reservations=reservations,
                        reserved_cost="0", settled_cost=str(Decimal(state["settled_cost"]) + actual),
                        usage=dict(prompt_tokens=state["usage"]["prompt_tokens"] + response.prompt_tokens,
                                   completion_tokens=state["usage"]["completion_tokens"] + response.completion_tokens))
                    self._verify_stage_settlement(spec, state, stage, packet)
                    context = self._context(spec)
                    if stage == "annual":
                        annual.validate_response(response, cash._source(context, spec["source_binding"]),
                            [2027], generated)
                    else:
                        result = self._result(spec, state, context)
                        if result.get("status") == "WAITING_EVIDENCE":
                            state, pin = self._save(spec, state, pin, generated,
                                stage_validated=["annual", "cash"], status="WAITING_EVIDENCE",
                                error_code="V19_EVIDENCE_INCOMPLETE")
                            return self._view(spec, state, pin, generated)
                    state, pin = self._save(spec, state, pin, generated,
                        stage_validated=list(state["stage_validated"]) + [stage])
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                self._result(spec, state, self._context(spec))
                state, pin = self._save(spec, state, pin, _now(), status="SUCCEEDED", error_code=None)
                return self._view(spec, state, pin, _now())

"""Opt-in, two-stage durable D2 task; never retries an ambiguous provider call."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v5_wc as v5
from . import operating_horizon_split_v6 as split
from . import operating_q3_cash_source_loader_v1 as q3_loader
from . import parent_wc_balance_request_v1 as wc_request
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v6-split"
STORE = "oh-v6-split"
STAGES = ("annual", "cash")


def implementation():
    return {**v5.implementation(), **q3_loader.implementation(),
            split.__name__: _hash(Path(split.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v5.OperatingHorizonTaskService):
    def __init__(self, root, *, test_provider=None, allow_live=False,
                 source_loader=q3_loader.load_current,
                 source_loader_version=q3_loader.VERSION):
        super().__init__(root, test_provider=test_provider, allow_live=allow_live,
                         source_loader=source_loader,
                         source_loader_version=source_loader_version)
        self.base = require_inside(self.root, self.base.parent / STORE, "v6 split tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [spec.get("year")]
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)):
            raise ValueError("V6_SPLIT_TASK_INVALID")
        return spec, state, pin

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("V6_SPLIT_IMPLEMENTATION_CHANGED")
        if spec["source_loader_binding"] != self._loader_binding():
            raise ValueError("V6_SPLIT_SOURCE_LOADER_CHANGED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context["symbol"] != spec["symbol"]
                or context["source_binding"] != spec["source_binding"]
                or context["snapshot_fingerprint"] != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("V6_SPLIT_CONTEXT_CHANGED")
        history, pin = self._history(datetime.fromisoformat(spec["created_at"]))
        if pin != spec["wc_source_binding"]:
            raise ValueError("V6_SPLIT_WC_SOURCE_CHANGED")
        enriched, _ = wc_request.attach_parent_wc_balance_anchor(
            live.research_context(context, drivers=True), history=history,
            as_of=datetime.fromisoformat(spec["created_at"]))
        if _hash(_bytes(enriched)) != spec["enriched_context_sha256"]:
            raise ValueError("V6_SPLIT_ENRICHED_CONTEXT_CHANGED")
        request = split.build_annual_request(enriched, spec["years"],
            source_binding=self._source_binding(spec),
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        if _hash(_bytes(request.__dict__)) != spec["annual_request_sha256"]:
            raise ValueError("V6_SPLIT_ANNUAL_REQUEST_CHANGED")
        return enriched

    @staticmethod
    def _source_binding(spec):
        return dict(base=spec["source_binding"], wc=spec["wc_source_binding"])

    def _packet(self, spec, state, stage):
        pin = state["stage_responses"].get(stage)
        if pin is None:
            return None
        packet = self._bound(pin)
        intent = state["stage_intents"].get(stage)
        if (intent is None or packet.get("request_sha256") != intent["request_sha256"]
                or packet.get("context_sha256") != spec["enriched_context_sha256"]
                or packet.get("implementation_sha256") != spec["implementation_sha256"]
                or packet.get("stage") != stage or packet.get("action") != "no_order"):
            raise ValueError("V6_SPLIT_RESPONSE_BINDING_INVALID")
        return packet

    def _request_for_stage(self, spec, state, context, stage):
        if stage == "annual":
            return split.build_annual_request(context, spec["years"],
                source_binding=self._source_binding(spec),
                max_completion_tokens=spec["config"]["max_completion_tokens_cap"]), None
        annual_packet = self._packet(spec, state, "annual")
        if annual_packet is None:
            raise ValueError("V6_SPLIT_ANNUAL_CHECKPOINT_REQUIRED")
        self._verify_annual_checkpoint(spec, state, context)
        requests = split.build_requests(context, spec["years"],
            source_binding=self._source_binding(spec),
            annual_response=LLMResponse(**annual_packet["response"]),
            annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        return requests.cash, requests.binding

    def _verify_annual_checkpoint(self, spec, state, context):
        if "annual" not in state.get("stage_validated", []):
            raise ValueError("V6_SPLIT_ANNUAL_CHECKPOINT_UNVERIFIED")
        packet = self._packet(spec, state, "annual")
        if packet is None:
            raise ValueError("V6_SPLIT_ANNUAL_CHECKPOINT_MISSING")
        request = split.build_annual_request(context, spec["years"],
            source_binding=self._source_binding(spec),
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        if _hash(_bytes(request.__dict__)) != packet["request_sha256"]:
            raise ValueError("V6_SPLIT_ANNUAL_REQUEST_CHANGED")
        response = LLMResponse(**packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "annual", packet)
        split.annual.validate_response(response, context, spec["years"],
            datetime.fromisoformat(packet["generated_at"]))

    def _verify_stage_settlement(self, spec, state, stage, packet):
        intent = state["stage_intents"][stage]
        response = LLMResponse(**packet["response"])
        actual = self._cost(response.prompt_tokens, response.completion_tokens, spec["config"])
        reservation = intent["reservation"]
        charged = state["reservations"].get(reservation, {})
        if (charged.get("status") != "SETTLED" or Decimal(charged.get("actual_cost", "-1")) != actual):
            raise ValueError("V6_SPLIT_SETTLEMENT_UNVERIFIED")
        budget = self._budget_service
        directory = require_inside(budget.base,
            budget.base / "budget" / charged["budget_day"], "daily research budget")
        with budget._lock(directory):
            files = sorted((directory / "versions").glob("*.json"))
            if not files or len(files) > 512:
                raise ValueError("V6_SPLIT_DAILY_BUDGET_MISSING")
            previous = None
            for number, path in enumerate(files, 1):
                pin = budget._binding(path)
                row = budget._bound(pin)
                if (path.name != f'{number:04d}-{pin["sha256"]}.json'
                        or row.get("previous") != previous or row.get("version") != number):
                    raise ValueError("V6_SPLIT_DAILY_BUDGET_CHANGED")
                previous = pin
            if (directory / "current.json").read_bytes() != _bytes(previous):
                raise ValueError("V6_SPLIT_DAILY_BUDGET_HEAD_CHANGED")
            if row["records"].get(reservation) != dict(status="SETTLED", cost=str(actual)):
                raise ValueError("V6_SPLIT_DAILY_BUDGET_SETTLEMENT_CHANGED")

    def _result(self, spec, state, context):
        if set(state["stage_responses"]) != set(STAGES):
            if state["status"] == "SUCCEEDED":
                raise ValueError("V6_SPLIT_SUCCEEDED_WITHOUT_BOTH_RESPONSES")
            return None
        annual_packet = self._packet(spec, state, "annual")
        cash_packet = self._packet(spec, state, "cash")
        for stage, packet in (("annual", annual_packet), ("cash", cash_packet)):
            request, _ = self._request_for_stage(spec, state, context, stage)
            if _hash(_bytes(request.__dict__)) != state["stage_intents"][stage]["request_sha256"]:
                raise ValueError("V6_SPLIT_REQUEST_CHANGED")
            self._usage(LLMResponse(**packet["response"]), request, spec["config"]["model_id"])
            self._verify_stage_settlement(spec, state, stage, packet)
        annual_response = LLMResponse(**annual_packet["response"])
        cash_response = LLMResponse(**cash_packet["response"])
        requests = split.build_requests(context, spec["years"],
            source_binding=self._source_binding(spec), annual_response=annual_response,
            annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
        if requests.binding != state["cash_binding"]:
            raise ValueError("V6_SPLIT_CASH_BINDING_CHANGED")
        result = split.validate_responses(annual_response, cash_response, context=context,
            years=spec["years"], source_binding=self._source_binding(spec),
            binding=requests.binding,
            annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            cash_generated_at=datetime.fromisoformat(cash_packet["generated_at"]))
        if result["action"] != "no_order" or result["formal_eligibility"] is not False:
            raise ValueError("V6_SPLIT_RESULT_BOUNDARY_INVALID")
        return result

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, task_id=spec["task_id"], symbol=spec["symbol"],
            workflow=CONTRACT, execution_mode=spec["mode"], source_binding=spec["source_binding"],
            wc_source_binding=spec["wc_source_binding"], research_as_of=spec["created_at"],
            model_id=spec["config"]["model_id"], action="no_order", formal_eligibility=False,
            condition_price=None, research_result=None,
            annual_status=self._stage_status(state, "annual"),
            cash_status=self._stage_status(state, "cash"))
        if state["status"] == "CANCELLED":
            return value
        try:
            context = self._context(spec)
            if "annual" in state.get("stage_validated", []):
                self._verify_annual_checkpoint(spec, state, context)
            if state["status"] == "SUCCEEDED":
                value["research_result"] = self._result(spec, state, context)
        except (ValueError, OSError, KeyError, TypeError):
            value.update(status="FAILED", error_code="V6_SPLIT_REPLAY_INVALID")
            value["research_result"] = None
        return value

    @staticmethod
    def _stage_status(state, stage):
        if stage in state["stage_responses"]:
            return "SETTLED_VALIDATED" if stage in state.get("stage_validated", []) else "RETURNED_UNVERIFIED"
        if stage in state["stage_intents"]:
            return "AMBIGUOUS_CALL_NO_RETRY"
        return "PENDING"

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        if (years is None or type(years) is not list or len(years) != 1
                or type(years[0]) is not int or not isinstance(symbol, str)
                or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str)
                or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V6_SPLIT_IDENTITY_INVALID")
        cfg = live.model_configuration(self.root)
        if self.test_provider is None and cfg["model_id"] != "deepseek-flash":
            raise PermissionError("V6_SPLIT_MODEL_NOT_AUTHORIZED")
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        history, wc_pin = self._history(now)
        if history["symbol"] != symbol:
            raise ValueError("V6_SPLIT_WC_SYMBOL_MISMATCH")
        enriched, _ = wc_request.attach_parent_wc_balance_anchor(
            live.research_context(context, drivers=True), history=history, as_of=now)
        mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
        identity = _bytes([CONTRACT, mode, symbol, years, context["source_binding"], wc_pin])
        task_id = "rt-" + _hash(identity)[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if (spec["config"] != cfg or spec["implementation_sha256"] != implementation()
                        or spec["mode"] != mode or spec["symbol"] != symbol or spec["years"] != years):
                    raise ValueError("V6_SPLIT_REQUEST_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id,
                workflow="operating_research", task_contract=CONTRACT,
                mode=mode, symbol=symbol, year=years[0], years=years,
                request_key_sha256=_hash(request_key.encode("utf-8")), created_at=now.isoformat(),
                source_binding=context["source_binding"],
                context_fingerprint=context["snapshot_fingerprint"],
                context_sha256=_hash(_bytes(context)), wc_source_binding=wc_pin,
                enriched_context_sha256=_hash(_bytes(enriched)),
                source_loader_binding=self._loader_binding(), config=cfg,
                implementation_sha256=implementation(), action="no_order")
            annual_request = split.build_annual_request(enriched, years,
                source_binding=self._source_binding(spec),
                max_completion_tokens=cfg["max_completion_tokens_cap"])
            spec["annual_request_sha256"] = _hash(_bytes(annual_request.__dict__))
            self._context(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0",
                settled_cost="0", reservations={}, stage_intents={}, stage_responses={},
                stage_validated=[], cash_binding=None, created_at=now.isoformat(),
                action="no_order", formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _drive(self, task_id, now, *, resume):
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            try:
                with self._lock(directory):
                    spec, state, pin = self._load(task_id, recover=resume)
                    if state["status"] in {"CANCELLED", "SUCCEEDED"}:
                        return self._view(spec, state, pin, now)
                    context = self._context(spec)
                    if (set(state["stage_responses"]) == set(STAGES)
                            and set(state["stage_validated"]) == set(STAGES)):
                        self._result(spec, state, context)
                        state, pin = self._save(spec, state, pin, now,
                            status="SUCCEEDED", error_code=None)
                        return self._view(spec, state, pin, now)
                    for stage in STAGES:
                        if stage in state["stage_intents"] and stage not in state["stage_validated"]:
                            raise ValueError("V6_SPLIT_AMBIGUOUS_STAGE_NO_REPEAT")
                    if resume:
                        state, pin = self._save(spec, state, pin, now,
                            status="QUEUED", error_code=None)
                        return self._view(spec, state, pin, now)
                    if state["status"] != "QUEUED":
                        return self._view(spec, state, pin, now)
                for stage in STAGES:
                    with self._lock(directory):
                        spec, state, pin = self._load(task_id)
                        if state["status"] == "CANCELLED":
                            return self._view(spec, state, pin, _now())
                        if stage in state["stage_validated"]:
                            continue
                        context = self._context(spec)
                        request, cash_binding = self._request_for_stage(spec, state, context, stage)
                        provider = self._provider(spec)
                        cfg = spec["config"]
                        reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                            request.max_completion_tokens, cfg)
                        if Decimal(state["reserved_cost"]) + Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"])):
                            raise ValueError("V6_SPLIT_RUN_BUDGET_EXHAUSTED")
                        request_sha = _hash(_bytes(request.__dict__))
                        reservation = _hash(_bytes([CONTRACT, task_id, stage, request_sha]))
                        day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                        intents = deepcopy(state["stage_intents"])
                        intents[stage] = dict(request_sha256=request_sha,
                            reservation=reservation, budget_day=day)
                        reservations = deepcopy(state["reservations"])
                        reservations[reservation] = dict(status="RESERVED", cost=str(reserve),
                            budget_day=day)
                        state, pin = self._save(spec, state, pin, _now(), status="RUNNING",
                            stage_intents=intents, cash_binding=cash_binding or state["cash_binding"],
                            reservations=reservations, reserved_cost=str(Decimal(state["reserved_cost"]) + reserve),
                            provider_requests=state["provider_requests"] + 1,
                            attempts=state["attempts"] + 1)
                        self._daily_budget(day, reservation, reserve, cfg)
                        if self.test_provider is None:
                            state, pin = self._save(spec, state, pin, _now(),
                                new_llm_calls=state["new_llm_calls"] + 1)
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
                        usage = {key: state["usage"][key] + getattr(response, key)
                                 for key in ("prompt_tokens", "completion_tokens")}
                        state, pin = self._save(spec, state, pin, generated,
                            reservations=reservations,
                            reserved_cost=str(Decimal(state["reserved_cost"]) - reserve),
                            settled_cost=str(Decimal(state["settled_cost"]) + actual), usage=usage)
                        self._verify_stage_settlement(spec, state, stage, packet)
                        if stage == "annual":
                            split.annual.validate_response(response, context, spec["years"], generated)
                        else:
                            self._result(spec, state, context)
                        validated = list(state["stage_validated"]) + [stage]
                        state, pin = self._save(spec, state, pin, generated,
                            stage_validated=validated)
                        if state["status"] == "CANCELLED":
                            return self._view(spec, state, pin, generated)
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    context = self._context(spec)
                    self._result(spec, state, context)
                    if state["status"] != "CANCELLED":
                        state, pin = self._save(spec, state, pin, _now(),
                            status="SUCCEEDED", error_code=None)
                    return self._view(spec, state, pin, _now())
            except Exception as error:
                from .operating_horizon_task_v1 import _error_code
                message = str(error)
                code = (message if re.fullmatch(r"V6_SPLIT_[A-Z0-9_]{1,80}", message)
                        else _error_code(error))
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    if state["status"] != "CANCELLED":
                        state, pin = self._save(spec, state, pin, _now(),
                            status="FAILED", error_code=code[:100])
                    return self._view(spec, state, pin, _now())

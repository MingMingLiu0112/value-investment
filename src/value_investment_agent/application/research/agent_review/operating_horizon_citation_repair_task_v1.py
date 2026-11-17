"""One-call, source-bound V7 citation repair. Output is never research admission."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_citation_repair_v1 as repair
from . import operating_horizon_task_v7_split as v7
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, STATES, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-citation-repair-task-v1"
STORE = "oh-v7-citation-repair-v1"


def implementation():
    return {repair.__name__: _hash(Path(repair.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class CitationRepairTaskService(v7.OperatingHorizonTaskService):
    def __init__(self, root, *, test_provider=None, allow_live=False, **kwargs):
        super().__init__(root, test_provider=test_provider, allow_live=allow_live, **kwargs)
        self.original = v7.OperatingHorizonTaskService(root, test_provider=test_provider,
            allow_live=allow_live, **kwargs)
        self.base = require_inside(self.root, self.base.parent / STORE, "citation repair tasks")

    def _load(self, task_id, *, recover=False):
        # Reuse the existing immutable chain validator, then check our contract.
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("action") != "no_order"
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING")
                or state.get("provider_requests", 0) not in (0, 1)
                or set(state.get("reservations", {})) - {spec.get("reservation_id")}):
            raise ValueError("REPAIR_TASK_CONTRACT_INVALID")
        return spec, state, pin

    def _original(self, spec):
        old, state, pin = self.original._load(spec["original_task_id"])
        if (pin != spec["original_state_binding"] or
                _hash(_bytes(old)) != spec["original_input_sha256"]):
            raise ValueError("REPAIR_ORIGINAL_TASK_CHANGED")
        return old, state

    def _request(self, spec):
        self._original(spec)
        if implementation() != spec["implementation_sha256"]:
            raise ValueError("REPAIR_IMPLEMENTATION_CHANGED")
        request = repair.build_request(self.original, spec["original_task_id"],
            max_completion_tokens=spec["max_completion_tokens"])
        if _hash(_bytes(request.__dict__)) != spec["request_sha256"]:
            raise ValueError("REPAIR_REQUEST_CHANGED")
        return request

    def _verified_packet(self, spec, state):
        pin = state.get("response_binding")
        if pin is None:
            return None
        packet = self._bound(pin)
        if (packet.get("request_sha256") != spec["request_sha256"]
                or packet.get("implementation_sha256") != spec["implementation_sha256"]
                or packet.get("original_state_binding") != spec["original_state_binding"]
                or packet.get("action") != "no_order"):
            raise ValueError("REPAIR_RESPONSE_BINDING_INVALID")
        response = LLMResponse(**packet["response"])
        request = self._request(spec)
        self._usage(response, request, spec["config"]["model_id"])
        charged = state["reservations"].get(spec["reservation_id"], {})
        actual = self._cost(response.prompt_tokens, response.completion_tokens, spec["config"])
        if charged.get("status") != "SETTLED" or charged.get("actual_cost") != str(actual):
            raise ValueError("REPAIR_SETTLEMENT_INVALID")
        # The shared budget chain is independently checked by the original V7 verifier.
        budget = self._budget_service
        day = charged["budget_day"]
        directory = require_inside(budget.base, budget.base / "budget" / day, "daily research budget")
        with budget._lock(directory):
            files = sorted((directory / "versions").glob("*.json"))
            previous = None
            for number, path in enumerate(files, 1):
                binding = budget._binding(path)
                row = budget._bound(binding)
                if (path.name != f'{number:04d}-{binding["sha256"]}.json'
                        or row.get("previous") != previous or row.get("version") != number):
                    raise ValueError("REPAIR_BUDGET_CHAIN_INVALID")
                previous = binding
            if not files or (directory / "current.json").read_bytes() != _bytes(previous):
                raise ValueError("REPAIR_BUDGET_HEAD_INVALID")
            if row["records"].get(spec["reservation_id"]) != dict(status="SETTLED", cost=str(actual)):
                raise ValueError("REPAIR_BUDGET_SETTLEMENT_INVALID")
        return packet

    def _view(self, spec, state, pin, now):
        view = deepcopy(state)
        view.update(task_id=spec["task_id"], original_task_id=spec["original_task_id"],
                    record_binding=pin, workflow=CONTRACT, action="no_order",
                    formal_eligibility=False, research_admission=False,
                    e2_promotion=False, requires_semantic_evidence_review=True,
                    repair_result=None)
        try:
            packet = self._verified_packet(spec, state)
            if packet is not None:
                result = repair.validate_repair(self.original, spec["original_task_id"],
                    packet["response"]["text"],
                    repair_generated_at=datetime.fromisoformat(packet["generated_at"]))
                view["repair_result"] = result
                if state["status"] == "SUCCEEDED" and result["research_admission"] is not False:
                    raise ValueError("REPAIR_UNAPPROVED_RESULT")
            elif state["status"] == "SUCCEEDED":
                raise ValueError("REPAIR_RESPONSE_MISSING")
        except (ValueError, OSError, KeyError, TypeError):
            view.update(status="FAILED", error_code="REPAIR_REPLAY_INVALID", repair_result=None)
        return view

    def create(self, *, original_task_id, request_key, max_completion_tokens=512, now=None):
        now = _now(now)
        if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key):
            raise ValueError("REPAIR_REQUEST_KEY_INVALID")
        old, state, pin = self.original._load(original_task_id)
        request = repair.build_request(self.original, original_task_id,
            max_completion_tokens=max_completion_tokens)
        cfg = live.model_configuration(self.root)
        if cfg != old["config"] or (self.test_provider is None and
                (cfg["model_id"] != "deepseek-flash" or not os.environ.get(cfg["api_key_env"]))):
            raise PermissionError("REPAIR_MODEL_AUTHORIZATION_REQUIRED")
        identity = _bytes([CONTRACT, original_task_id, pin, _hash(_bytes(request.__dict__))])
        task_id = "rt-" + _hash(identity)[:32]
        spec = dict(schema_version=VERSION, workflow="operating_research", task_contract=CONTRACT,
            task_id=task_id, original_task_id=original_task_id, original_state_binding=pin,
            original_input_sha256=_hash(_bytes(old)), request_key_sha256=_hash(request_key.encode()),
            request_sha256=_hash(_bytes(request.__dict__)), max_completion_tokens=max_completion_tokens,
            config=cfg, implementation_sha256=implementation(),
            mode="TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING",
            reservation_id=_hash(identity + b"reservation"), created_at=now.isoformat(), action="no_order")
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                existing, state, binding = self._load(task_id)
                # Creation time belongs to the first request, not the identity.
                if ({k: v for k, v in existing.items() if k != "created_at"}
                        != {k: v for k, v in spec.items() if k != "created_at"}):
                    raise ValueError("REPAIR_TASK_ID_CONFLICT")
                return self._view(existing, state, binding, now)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0,
                new_llm_calls=0, usage=dict(prompt_tokens=0, completion_tokens=0),
                reservations={}, response_binding=None, reserved_cost="0", settled_cost="0",
                error_code=None, action="no_order", formal_eligibility=False,
                created_at=now.isoformat())
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def read(self, task_id):
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, pin = self._load(task_id)
            return self._view(spec, state, pin, _now())

    def cancel(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, pin = self._load(task_id)
            if state["status"] not in ("SUCCEEDED", "CANCELLED"):
                state, pin = self._save(spec, state, pin, now, status="CANCELLED")
            return self._view(spec, state, pin, now)

    def resume(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, pin = self._load(task_id, recover=True)
            self._request(spec)
            if state["response_binding"]:
                packet = self._verified_packet(spec, state)
                try:
                    repair.validate_repair(self.original, spec["original_task_id"],
                        packet["response"]["text"],
                        repair_generated_at=datetime.fromisoformat(packet["generated_at"]))
                    status, error = "SUCCEEDED", None
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    status, error = "FAILED", str(exc)[:100]
                if state["status"] != "CANCELLED":
                    state, pin = self._save(spec, state, pin, now, status=status, error_code=error)
            elif state["provider_requests"] and state["status"] != "CANCELLED":
                state, pin = self._save(spec, state, pin, now, status="FAILED",
                    error_code="REPAIR_AMBIGUOUS_CALL_NO_REPEAT")
            return self._view(spec, state, pin, now)

    def run(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                if state["status"] != "QUEUED" or state["provider_requests"]:
                    return self._view(spec, state, pin, now)
                request = self._request(spec)
                cfg = spec["config"]
                reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                    request.max_completion_tokens, cfg)
                if reserve > Decimal(str(cfg["max_run_cost"])):
                    raise ValueError("REPAIR_RUN_BUDGET_EXHAUSTED")
                provider = self._provider(spec)
                day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                self._daily_budget(day, spec["reservation_id"], reserve, cfg)
                reservations = {spec["reservation_id"]: dict(status="RESERVED", cost=str(reserve), budget_day=day)}
                state, pin = self._save(spec, state, pin, now, status="RUNNING",
                    attempts=1, provider_requests=1,
                    new_llm_calls=0 if self.test_provider is not None else 1,
                    reservations=reservations, reserved_cost=str(reserve))
            try:
                response = provider.complete(request)
                generated = _now()
                packet = dict(request_sha256=spec["request_sha256"],
                    original_state_binding=spec["original_state_binding"],
                    implementation_sha256=spec["implementation_sha256"],
                    response=response.__dict__, generated_at=generated.isoformat(), action="no_order")
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    path = directory / "repair-response.json"
                    write_new_bytes(path, _bytes(packet))
                    state, pin = self._save(spec, state, pin, generated,
                        response_binding=self._binding(path))
                    self._usage(response, request, cfg["model_id"])
                    actual = self._cost(response.prompt_tokens, response.completion_tokens, cfg)
                    self._daily_budget(day, spec["reservation_id"], actual, cfg, settle=True)
                    reservations = deepcopy(state["reservations"])
                    reservations[spec["reservation_id"]].update(status="SETTLED", actual_cost=str(actual))
                    state, pin = self._save(spec, state, pin, generated,
                        reservations=reservations, reserved_cost="0", settled_cost=str(actual),
                        usage=dict(prompt_tokens=response.prompt_tokens,
                                   completion_tokens=response.completion_tokens))
                    try:
                        repair.validate_repair(self.original, spec["original_task_id"],
                            response.text, repair_generated_at=generated)
                        status, error = "SUCCEEDED", None
                    except (ValueError, OSError, KeyError, TypeError) as exc:
                        status, error = "FAILED", str(exc)[:100]
                    if state["status"] != "CANCELLED":
                        state, pin = self._save(spec, state, pin, generated,
                            status=status, error_code=error)
                    return self._view(spec, state, pin, generated)
            except Exception:
                # Unsettled reservations stay charged; the intent forbids a repeat call.
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    if state["status"] != "CANCELLED":
                        state, pin = self._save(spec, state, pin, _now(), status="FAILED",
                            error_code="REPAIR_CALL_OR_SETTLEMENT_AMBIGUOUS_NO_REPEAT")
                    return self._view(spec, state, pin, _now())

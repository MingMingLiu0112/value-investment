"""Bounded, source-bound D1 execution for three unapproved parent-cash drafts."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .task_execution_v1 import ResearchTaskService, _bytes, _hash, _now
from .operating_task_v2 import LiveOperatingTaskService, model_configuration
from ..direct_owner_cash_agent_facts_v1 import read_parent_cash_agent_facts
from ..direct_owner_cash_agent_request_v1 import parent_cash_request, parse_parent_cash_response
from ..direct_owner_cash_agent_draft_v1 import SCENARIOS, assemble_parent_cash_drafts
from ....infrastructure.agent_runtime.provider import LLMResponse, OpenAICompatibleChatProvider
from ...product.common import require_inside, write_new_bytes

VERSION = "parent-cash-task-v1"
STATES = {"QUEUED", "RUNNING", "FAILED", "SUCCEEDED", "CANCELLED"}


def _implementation():
    from .. import (direct_owner_cash_agent_draft_v1 as draft,
                    direct_owner_cash_agent_facts_v1 as facts,
                    direct_owner_cash_agent_request_v1 as request,
                    direct_owner_cash_compilation_v1 as compiler)
    return {module.__name__: _hash(Path(module.__file__).read_bytes())
            for module in (draft, facts, request, compiler)} | {
        __name__: _hash(Path(__file__).read_bytes())}


class ParentCashTaskService(ResearchTaskService):
    def __init__(self, root, *, test_provider=None):
        super().__init__(root)
        self.base = require_inside(self.root, self.base / VERSION, "parent cash tasks")
        self.test_provider = test_provider
        shared = os.environ.get("VALUE_AGENT_SHARED_RESEARCH_ROOT")
        self.shared_budget_root = (self.root if test_provider is not None else
            Path(shared).resolve() if shared and Path(shared).is_absolute() else None)
        # Reuse the exact ledger root used by the existing live horizon tasks.
        self.daily = (LiveOperatingTaskService(self.shared_budget_root)
            if self.shared_budget_root is not None and self.shared_budget_root.is_dir() else None)

    def _configuration(self):
        if self.daily is None:
            raise PermissionError("PARENT_SHARED_BUDGET_ROOT_REQUIRED")
        cfg = model_configuration(self.shared_budget_root)
        if cfg["model_id"] != "deepseek-flash" or Decimal(str(cfg["daily_cost_limit"])) > 10:
            raise PermissionError("PARENT_SHARED_MODEL_CONFIGURATION_INVALID")
        # The same shared D1 gateway is configured for 4096; the established
        # V19 horizon task expands only its per-request completion ceiling.
        if cfg["max_completion_tokens_cap"] != 4096:
            raise PermissionError("PARENT_SHARED_COMPLETION_CONFIG_INVALID")
        return {**cfg, "max_completion_tokens_cap": 8192}

    def _context(self, spec, now):
        if (self._configuration() != spec["config"]
                or spec.get("implementation_sha256") != _implementation()
                or spec.get("shared_budget_root") != str(self.shared_budget_root)):
            raise PermissionError("MODEL_AUTHORIZATION_CHANGED")
        context = read_parent_cash_agent_facts(root=self.root,
            spec_binding=spec["spec_binding"], now=now)
        if context["input_fingerprint"] != spec["source_fingerprint"]:
            raise ValueError("PARENT_SOURCE_CHANGED")
        return context

    def _load(self, task_id, *, recover=False):
        directory = self._directory(task_id)
        raw = (directory / "input.json").read_bytes()
        spec = json.loads(raw)
        if (spec.get("schema_version") != VERSION or spec.get("task_id") != task_id
                or spec.get("action") != "no_order" or spec.get("mode") not in
                {"LIVE_PARENT_CASH", "TEST_ONLY_PARENT_CASH"}):
            raise ValueError("PARENT_TASK_INPUT_INVALID")
        files = sorted((directory / "versions").glob("*.json"))
        if not 1 <= len(files) <= 128:
            raise ValueError("PARENT_TASK_CHAIN_MISSING_OR_UNBOUNDED")
        previous = None
        for number, path in enumerate(files, 1):
            binding = self._binding(path)
            row = self._bound(binding)
            if (path.name != f'{number:04d}-{binding["sha256"]}.json'
                    or row.get("schema_version") != VERSION or row.get("task_id") != task_id
                    or row.get("version") != number or row.get("previous") != previous
                    or row.get("input_sha256") != _hash(raw)
                    or row.get("status") not in STATES or row.get("action") != "no_order"
                    or row.get("formal_eligibility") is not False):
                raise ValueError("PARENT_TASK_CHAIN_INVALID")
            previous = binding
        head = directory / "current.json"
        if head.exists():
            published = json.loads(head.read_bytes())
            if published not in [self._binding(path) for path in files]:
                raise ValueError("PARENT_TASK_HEAD_INVALID")
        elif not recover:
            raise ValueError("PARENT_TASK_HEAD_MISSING_EXPLICIT_RESUME")
        if not head.exists() or published != previous:
            if not recover:
                raise ValueError("PARENT_TASK_UNPUBLISHED_EXPLICIT_RESUME")
            self._head(directory, previous)
        return spec, row, previous

    def _save(self, spec, state, previous, now, **changes):
        row = deepcopy(state)
        row.update(changes)
        row.update(schema_version=VERSION, task_id=spec["task_id"],
                   input_sha256=_hash(_bytes(spec)), previous=previous,
                   version=state.get("version", 0) + 1, updated_at=now.isoformat())
        raw = _bytes(row)
        directory = self._directory(spec["task_id"])
        path = directory / "versions" / f'{row["version"]:04d}-{_hash(raw)}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new_bytes(path, raw)
        binding = self._binding(path)
        self._head(directory, binding)
        return row, binding

    def _drafts(self, spec, state, now):
        context = self._context(spec, now)
        self._verify_charges(state)
        drafts = {}
        for scenario, binding in state["responses"].items():
            packet = self._bound(binding)
            request = parent_cash_request(root=self.root, spec_binding=spec["spec_binding"],
                scenario=scenario, generated_at=datetime.fromisoformat(spec["created_at"]),
                max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
            if (packet.get("scenario") != scenario or packet.get("request_sha256") !=
                    _hash(_bytes(request.__dict__)) or packet.get("source_fingerprint") !=
                    context["input_fingerprint"]):
                raise ValueError("PARENT_RESPONSE_BINDING_INVALID")
            drafts[scenario] = parse_parent_cash_response(LLMResponse(**packet["response"]),
                scenario=scenario, source_fingerprint=context["input_fingerprint"])
        return drafts

    def _verify_charges(self, state):
        """Read the existing shared ledger before trusting any published response."""
        reserved = settled = Decimal(0)
        by_day = {}
        for reservation, charge in state["reservations"].items():
            if (not re.fullmatch(r"[0-9a-f]{64}", reservation)
                    or charge.get("scenario") not in SCENARIOS
                    or charge.get("status") not in {"RESERVED", "SETTLED"}
                    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", charge.get("day", ""))):
                raise ValueError("PARENT_CHARGE_RECORD_INVALID")
            amount = Decimal(charge["cost"])
            if not amount.is_finite() or amount < 0:
                raise ValueError("PARENT_CHARGE_AMOUNT_INVALID")
            if charge["status"] == "RESERVED":
                reserved += amount
                if charge["scenario"] in state["responses"]:
                    raise ValueError("PARENT_RESPONSE_NOT_SETTLED")
            else:
                actual = Decimal(charge["actual_cost"])
                if not actual.is_finite() or not 0 <= actual <= amount:
                    raise ValueError("PARENT_CHARGE_SETTLEMENT_INVALID")
                settled += actual
            by_day.setdefault(charge["day"], []).append((reservation, charge))
        if (Decimal(state["reserved_cost"]) != reserved
                or Decimal(state["settled_cost"]) != settled):
            raise ValueError("PARENT_CHARGE_TOTAL_MISMATCH")
        for day, charges in by_day.items():
            directory = require_inside(self.daily.base,
                self.daily.base / "budget" / day, "parent cash shared budget")
            with self.daily._lock(directory):
                files = sorted((directory / "versions").glob("*.json"))
                if not 1 <= len(files) <= 512:
                    raise ValueError("PARENT_BUDGET_CHAIN_INVALID")
                previous = None
                for number, path in enumerate(files, 1):
                    pin = self.daily._binding(path)
                    row = self.daily._bound(pin)
                    if (path.name != f'{number:04d}-{pin["sha256"]}.json'
                            or row.get("previous") != previous
                            or row.get("version") != number
                            or row.get("day") != day or row.get("currency") != "CNY"):
                        raise ValueError("PARENT_BUDGET_CHAIN_INVALID")
                    previous = pin
                if (directory / "current.json").read_bytes() != _bytes(previous):
                    raise ValueError("PARENT_BUDGET_HEAD_INVALID")
                for reservation, charge in charges:
                    expected = (dict(status="RESERVED", cost=charge["cost"])
                        if charge["status"] == "RESERVED" else
                        dict(status="SETTLED", cost=charge["actual_cost"]))
                    if row["records"].get(reservation) != expected:
                        raise ValueError("PARENT_BUDGET_CHARGE_MISMATCH")

    def _view(self, spec, state, binding, now):
        view = deepcopy(state)
        view.update(record_binding=binding, mode=spec["mode"],
            spec_binding=spec["spec_binding"], source_fingerprint=spec["source_fingerprint"],
            recovery_boundary="PUBLISHED_RESPONSES_ONLY_NO_AUTOMATIC_RESEND",
            approval_changed=False, main_range_adopted=False)
        try:
            drafts = self._drafts(spec, state, now)
            view["completed_scenarios"] = sorted(drafts)
            if state["status"] == "SUCCEEDED":
                if set(drafts) != set(SCENARIOS):
                    raise ValueError("PARENT_RESULT_INCOMPLETE")
                view["candidate"] = assemble_parent_cash_drafts(root=self.root,
                    spec_binding=spec["spec_binding"], drafts=drafts, generated_at=now)
        except (ValueError, OSError, KeyError, TypeError, PermissionError):
            view.update(status="FAILED", error_code="PARENT_SOURCE_OR_CHECKPOINT_INVALID")
        return view

    def create(self, *, spec_binding, request_key, now=None):
        now = _now(now)
        if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key):
            raise ValueError("PARENT_REQUEST_KEY_INVALID")
        cfg = self._configuration()
        if cfg["model_id"] != "deepseek-flash" or cfg["max_completion_tokens_cap"] < 1024:
            raise ValueError("PARENT_MODEL_CONTRACT_INVALID")
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = read_parent_cash_agent_facts(root=self.root, spec_binding=spec_binding, now=now)
        task_id = "rt-" + _hash(request_key.encode("utf-8"))[:32]
        spec = dict(schema_version=VERSION, task_id=task_id, mode="TEST_ONLY_PARENT_CASH"
            if self.test_provider is not None else "LIVE_PARENT_CASH", spec_binding=spec_binding,
            source_fingerprint=context["input_fingerprint"], config=cfg,
            shared_budget_root=str(self.shared_budget_root),
            implementation_sha256=_implementation(),
            created_at=now.isoformat(), action="no_order")
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                old, state, binding = self._load(task_id)
                if {k:v for k,v in old.items() if k != "created_at"} != {k:v for k,v in spec.items() if k != "created_at"}:
                    raise ValueError("PARENT_REQUEST_KEY_CONFLICT")
                return self._view(old, state, binding, now)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", responses={}, reservations={}, provider_requests=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0",
                settled_cost="0", action="no_order", formal_eligibility=False,
                error_code=None, new_llm_calls=0)
            state, binding = self._save(spec, state, None, now)
            return self._view(spec, state, binding, now)

    def read(self, task_id):
        directory = self._directory(task_id)
        if not (directory / "input.json").exists():
            raise FileNotFoundError(task_id)
        with self._lock(directory):
            return self._view(*self._load(task_id), _now())

    def cancel(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, binding = self._load(task_id)
            if state["status"] not in {"CANCELLED", "SUCCEEDED"}:
                state, binding = self._save(spec, state, binding, now,
                    status="CANCELLED", error_code="USER_CANCELLED")
            return self._view(spec, state, binding, now)

    def resume(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory):
            spec, state, binding = self._load(task_id, recover=True)
            if state["status"] in {"SUCCEEDED", "CANCELLED"}:
                return self._view(spec, state, binding, now)
            self._drafts(spec, state, now)
            if any(row["scenario"] not in state["responses"] for row in state["reservations"].values()):
                return self._view(spec, state, binding, now)
            state, binding = self._save(spec, state, binding, now, status="QUEUED", error_code=None)
            return self._view(spec, state, binding, now)

    def run(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state["status"] != "QUEUED":
                    return self._view(spec, state, binding, now)
                if any(row["scenario"] not in state["responses"] for row in state["reservations"].values()):
                    raise ValueError("PARENT_AMBIGUOUS_CALL_NO_RESEND")
                self._drafts(spec, state, now)
                state, binding = self._save(spec, state, binding, now, status="RUNNING")
            for scenario in SCENARIOS:
                with self._lock(directory):
                    spec, state, binding = self._load(task_id)
                    if state["status"] == "CANCELLED":
                        return self._view(spec, state, binding, _now())
                    if scenario in state["responses"]:
                        continue
                    if any(row["scenario"] == scenario for row in state["reservations"].values()):
                        raise ValueError("PARENT_AMBIGUOUS_CALL_NO_RESEND")
                    self._context(spec, _now())
                    cfg = spec["config"]
                    request = parent_cash_request(root=self.root, spec_binding=spec["spec_binding"],
                        scenario=scenario, generated_at=datetime.fromisoformat(spec["created_at"]),
                        max_completion_tokens=cfg["max_completion_tokens_cap"])
                    prompt_cap = len(_bytes(request.__dict__)) + 4096
                    reserve = (Decimal(prompt_cap) * Decimal(str(cfg["input_cost_per_million"])) +
                        Decimal(request.max_completion_tokens) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)
                    if (state["provider_requests"] >= 3 or Decimal(state["reserved_cost"]) +
                            Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"]))):
                        raise ValueError("PARENT_TASK_BUDGET_EXHAUSTED")
                    reservation = _hash(os.urandom(32))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    self.daily._daily_budget(day, reservation, reserve, cfg)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation] = dict(scenario=scenario, status="RESERVED",
                        cost=str(reserve), day=day)
                    state, binding = self._save(spec, state, binding, _now(),
                        reservations=reservations, reserved_cost=str(Decimal(state["reserved_cost"]) + reserve),
                        provider_requests=state["provider_requests"] + 1,
                        new_llm_calls=state["new_llm_calls"] + (self.test_provider is None))
                response_recorded = False
                try:
                    provider = self.test_provider or OpenAICompatibleChatProvider(**{k:cfg[k]
                        for k in ("endpoint", "model_id", "api_key_env", "timeout_seconds",
                                  "max_completion_tokens_cap", "response_format_mode", "thinking_mode") if k in cfg})
                    response = provider.complete(request)
                    if (not isinstance(response, LLMResponse) or response.tool_calls
                            or type(response.prompt_tokens) is not int or type(response.completion_tokens) is not int
                            or not 0 <= response.prompt_tokens <= prompt_cap
                            or not 0 <= response.completion_tokens <= request.max_completion_tokens
                            or response.model_id != cfg["model_id"]):
                        raise ValueError("PARENT_PROVIDER_RESPONSE_INVALID")
                    actual = (Decimal(response.prompt_tokens) * Decimal(str(cfg["input_cost_per_million"])) +
                        Decimal(response.completion_tokens) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        self.daily._daily_budget(day, reservation, actual, cfg, settle=True)
                        reservations = deepcopy(state["reservations"])
                        reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                        usage = {key:state["usage"][key] + getattr(response, key)
                            for key in ("prompt_tokens", "completion_tokens")}
                        state, binding = self._save(spec, state, binding, _now(), reservations=reservations,
                            usage=usage, reserved_cost=str(Decimal(state["reserved_cost"]) - reserve),
                            settled_cost=str(Decimal(state["settled_cost"]) + actual))
                        packet = dict(scenario=scenario, request_sha256=_hash(_bytes(request.__dict__)),
                            source_fingerprint=spec["source_fingerprint"], response=response.__dict__, action="no_order")
                        path = directory / ("response-" + reservation + ".json")
                        write_new_bytes(path, _bytes(packet))
                        response_recorded = True
                        response_binding = self._binding(path)
                        state, binding = self._save(spec, state, binding, _now(),
                            returned_responses=state.get("returned_responses", []) + [response_binding])
                    parse_parent_cash_response(response, scenario=scenario,
                        source_fingerprint=spec["source_fingerprint"])
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        if state["status"] == "CANCELLED":
                            return self._view(spec, state, binding, _now())
                        responses = deepcopy(state["responses"])
                        responses[scenario] = response_binding
                        state, binding = self._save(spec, state, binding, _now(), responses=responses)
                except Exception as error:
                    if response_recorded:
                        code = "PARENT_DRAFT_REJECTED_OR_UNPUBLISHED"
                    elif isinstance(error, TimeoutError):
                        code = "PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
                    elif isinstance(error, ValueError) and "completion token cap" in str(error):
                        code = "PARENT_PROVIDER_COMPLETION_CAP_REACHED"
                    elif isinstance(error, ValueError) and "truncated" in str(error):
                        code = "PARENT_PROVIDER_RESPONSE_INCOMPLETE"
                    else:
                        code = "PARENT_PROVIDER_OR_SETTLEMENT_AMBIGUOUS"
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        if state["status"] != "CANCELLED":
                            state, binding = self._save(spec, state, binding, _now(),
                                status="FAILED", error_code=code)
                        return self._view(spec, state, binding, _now())
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, binding, _now())
                drafts = self._drafts(spec, state, _now())
                assemble_parent_cash_drafts(root=self.root, spec_binding=spec["spec_binding"],
                    drafts=drafts, generated_at=_now())
                state, binding = self._save(spec, state, binding, _now(), status="SUCCEEDED")
                return self._view(spec, state, binding, _now())

"""Single-call annual operating supplement; never a three-role D2 completion.

Task versions reuse the live service's chain verifier and D1 persistence. Budget
reservations always use the *existing* live-operating-v1 ledger. Ambiguous calls
are never retried; resume only admits an already published response.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
import json
from zoneinfo import ZoneInfo
from urllib.error import HTTPError

from . import operating_horizon_draft_v1 as draft
from . import operating_horizon_sources_v1 as sources
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v1"


def _strict_json_decoder():
    """Parse only bounded JSON objects without duplicate keys or nonfinite values."""
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("HORIZON_DUPLICATE_JSON_KEY")
            value[key] = item
        return value

    def constant(value):
        raise ValueError("HORIZON_NONFINITE_JSON_CONSTANT")

    return json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant)


def _normalize_exact_extra_closing_brace(text):
    """Return the unique object span only for one harmless transport suffix.

    The original provider bytes stay in ``response.json``.  This helper does
    not repair content, add defaults, or make a partial document admissible.
    """
    if not isinstance(text, str) or not 1 <= len(text) <= 65536:
        raise ValueError("HORIZON_BOUNDED_JSON_REQUIRED")
    leading = len(text) - len(text.lstrip(" \t\r\n"))
    raw = text[leading:]
    if not raw.startswith("{"):
        raise ValueError("HORIZON_JSON_PREFIX_INVALID")
    _, end = _strict_json_decoder().raw_decode(raw)
    if raw[end:].strip(" \t\r\n") != "}":
        raise ValueError("HORIZON_JSON_NOT_EXACT_ONE_EXTRA_CLOSING_BRACE")
    normalized = text[:leading] + raw[:end]
    _strict_json_decoder().decode(normalized)
    return normalized


# Only exact, locally defined messages may become persisted error codes.
_SAFE_CODES = frozenset("""
HORIZON_IMPLEMENTATION_CHANGED_NEW_TASK_REQUIRED HORIZON_SOURCE_CONTEXT_CHANGED
HORIZON_REQUEST_CHANGED HORIZON_RESPONSE_MISSING HORIZON_RESPONSE_BINDING_INVALID
HORIZON_SETTLEMENT_UNVERIFIED HORIZON_DAILY_SETTLEMENT_MISMATCH
HORIZON_RESULT_BOUNDARY_INVALID HORIZON_PROVIDER_USAGE_INVALID HORIZON_PROVIDER_MODEL_MISMATCH
HORIZON_BUDGET_EXHAUSTED_BEFORE_CALL MODEL_AUTHORIZATION_CHANGED MODEL_AUTHORIZATION_REQUIRED
MODEL_CREDENTIAL_REQUIRED DAILY_BUDGET_EXHAUSTED_BEFORE_CALL DAILY_BUDGET_CHAIN_INVALID
DAILY_BUDGET_HEAD_UNPUBLISHED_FAIL_CLOSED DAILY_BUDGET_HEAD_INVALID
DAILY_BUDGET_RESERVATION_DUPLICATE DAILY_BUDGET_RESERVATION_MISSING
DAILY_BUDGET_PROVIDER_USAGE_EXCEEDED_RESERVATION DAILY_BUDGET_RECORD_LIMIT
COMPLETE_FY_BASELINE_REQUIRED ONE_TO_THREE_ORDERED_UNIQUE_YEARS_REQUIRED
YEAR_OUTSIDE_EXPLICIT_RESEARCH_HORIZON BOUNDED_HORIZON_PROMPT_EXCEEDED
UNKNOWN_MISSING_DUPLICATE_HORIZON_CITATION INVALID_HORIZON_GENERATION_TIME
CURRENT_YEAR_ESTIMATE_CANNOT_BECOME_ACTUAL HORIZON_CALENDAR_OR_BASELINE_MISMATCH
HORIZON_DRIVER_LOWER_EXCEEDS_UPPER THREE_CAPITAL_ASSUMPTIONS_REQUIRED
CAPITAL_PERIOD_INVALID CAPITAL_OPERATING_PERIOD_MISMATCH UNKNOWN_CAPITAL_MUST_REMAIN_NULL
CAPITAL_FORECAST_RANGE_INVALID MODEL_CANNOT_EMIT_CAPITAL_FACTS EXACT_DECIMAL_STRING_REQUIRED
FINITE_DECIMAL_REQUIRED FINITE_BOUNDED_DECIMAL_REQUIRED ECONOMIC_AMOUNT_UNSUPPORTED
VERIFIED_BASELINE_REQUIRED FORECAST_MUST_FOLLOW_BASELINE FORECAST_BASELINE_PERIOD_MISMATCH
EXPLICIT_SEVEN_OPERATING_DRIVERS_REQUIRED DRIVER_LOWER_EXCEEDS_UPPER
NONPOSITIVE_SALES_ACTIVITY_NOT_SUPPORTED NEGATIVE_COST_MULTIPLIER
INVALID_COST_SHARE_OR_SURCHARGE_RATIO INVALID_THRESHOLD_DIRECTION
HORIZON_JSON_PREFIX_INVALID HORIZON_JSON_NOT_EXACT_ONE_EXTRA_CLOSING_BRACE
HORIZON_NORMALIZED_RESPONSE_BINDING_INVALID
""".split())
_SAFE_MESSAGES = {
    "Bounded JSON response required": "HORIZON_BOUNDED_JSON_REQUIRED",
    "Duplicate response JSON key": "HORIZON_DUPLICATE_JSON_KEY",
    "Nonfinite JSON constant": "HORIZON_NONFINITE_JSON_CONSTANT",
    "Exact operating driver fields required": "HORIZON_EXACT_FIELDS_REQUIRED",
    "LLM response is truncated, filtered, refused or incomplete": "HORIZON_PROVIDER_RESPONSE_INCOMPLETE",
    "LLM response incomplete: completion token cap reached": "HORIZON_PROVIDER_COMPLETION_CAP_REACHED",
    "LLM response incomplete: provider content filter": "HORIZON_PROVIDER_CONTENT_FILTERED",
    "LLM response usage must contain integer token counts": "HORIZON_PROVIDER_USAGE_INVALID",
    "LLM response content is missing": "HORIZON_PROVIDER_CONTENT_MISSING",
    "LLM credential is absent": "MODEL_CREDENTIAL_REQUIRED",
}


def _error_code(error):
    if isinstance(error, HTTPError):
        return "PROVIDER_HTTP_" + str(error.code) if type(error.code) is int else "PROVIDER_HTTP_ERROR"
    if isinstance(error, TimeoutError):
        return "PROVIDER_TIMEOUT_UNSETTLED_RESERVATION_RETAINED"
    if isinstance(error, (ValueError, PermissionError)):
        message = str(error)
        if message in _SAFE_CODES:
            return message
        return _SAFE_MESSAGES.get(message, "HORIZON_STRUCTURED_RESPONSE_OR_SOURCE_REJECTED")
    if isinstance(error, FileNotFoundError):
        return "HORIZON_EVIDENCE_OR_CHECKPOINT_MISSING"
    return "HORIZON_EXECUTION_FAILED"


def implementation():
    # One-way dependency: the legacy implementation never imports this module.
    return {**live.implementation(),
            draft.__name__: _hash(Path(draft.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def _years(years):
    if (not isinstance(years, list) or not 1 <= len(years) <= 3
            or any(type(y) is not int for y in years)
            or any(b != a + 1 for a, b in zip(years, years[1:]))):
        raise ValueError("EXPLICIT_ONE_TO_THREE_CONSECUTIVE_YEARS_REQUIRED")
    return list(years)


class OperatingHorizonTaskService(live.LiveOperatingTaskService):
    """Annual supplemental research with one durable provider intent per task."""

    def __init__(self, root, *, test_provider=None, source_loader=None):
        super().__init__(root, test_provider=test_provider,
            source_loader=source_loader or sources.build_operating_horizon_source_context)
        self._budget_service = live.LiveOperatingTaskService(root)
        self.base = require_inside(self.root, self.base.parent / CONTRACT, "horizon tasks")

    def _daily_budget(self, *args, **kwargs):
        return self._budget_service._daily_budget(*args, **kwargs)

    def _load(self, task_id, *, recover=False):
        spec, state, pin = super()._load(task_id, recover=recover)
        if spec.get("task_contract") != CONTRACT:
            raise ValueError("INVALID_HORIZON_TASK")
        _years(spec["years"])
        return spec, state, pin

    def _request(self, spec, context):
        return draft.build_request(live.research_context(context, drivers=True),
            spec["years"], max_completion_tokens=spec["config"]["max_completion_tokens_cap"])

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("HORIZON_IMPLEMENTATION_CHANGED_NEW_TASK_REQUIRED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context["symbol"] != spec["symbol"]
                or context["source_binding"] != spec["source_binding"]
                or context["snapshot_fingerprint"] != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("HORIZON_SOURCE_CONTEXT_CHANGED")
        if _hash(_bytes(self._request(spec, context).__dict__)) != spec["request_sha256"]:
            raise ValueError("HORIZON_REQUEST_CHANGED")
        return context

    def _result(self, spec, state, context):
        pin = state.get("response_binding")
        if pin is None:
            if state["status"] == "SUCCEEDED":
                raise ValueError("HORIZON_RESPONSE_MISSING")
            return None
        raw_packet = self._bound(pin)
        packet = raw_packet
        normalized_pin = state.get("normalized_response_binding")
        if normalized_pin is not None:
            packet = self._bound(normalized_pin)
            transport = packet.get("transport_normalization")
            raw_response = raw_packet.get("response", {}).get("text")
            if (not isinstance(transport, dict)
                    or transport.get("original_response_binding") != pin
                    or transport.get("original_response_sha256") != _hash(raw_response.encode("utf-8"))
                    or transport.get("normalized_response_sha256") != _hash(packet.get("response", {}).get("text", "").encode("utf-8"))
                    or _normalize_exact_extra_closing_brace(raw_response) != packet.get("response", {}).get("text")):
                raise ValueError("HORIZON_NORMALIZED_RESPONSE_BINDING_INVALID")
        if (packet["request_sha256"] != spec["request_sha256"]
                or packet["context_sha256"] != spec["context_sha256"]
                or packet["implementation_sha256"] != spec["implementation_sha256"]
                or packet["years"] != spec["years"] or packet["action"] != "no_order"):
            raise ValueError("HORIZON_RESPONSE_BINDING_INVALID")
        response = LLMResponse(**packet["response"])
        self._usage(response, self._request(spec, context), spec["config"]["model_id"])
        result = draft.validate_response(response,
            context=live.research_context(context, drivers=True), years=spec["years"],
            generated_at=datetime.fromisoformat(packet["generated_at"]))
        if result.get("action") != "no_order" or result.get("formal_eligibility") is not False:
            raise ValueError("HORIZON_RESULT_BOUNDARY_INVALID")
        self._verify_settlement(spec, state, response)
        return result

    def _verify_settlement(self, spec, state, response):
        """Read-only audit: response publication alone never proves settled usage.

        A crash between ledger settlement and the local save stays failed closed;
        recovery cannot guess accounting state or issue another provider call.
        """
        reservations = state.get("reservations", {})
        actual = self._cost(response.prompt_tokens, response.completion_tokens, spec["config"])
        if len(reservations) != 1:
            raise ValueError("HORIZON_SETTLEMENT_UNVERIFIED")
        reservation, charged = next(iter(reservations.items()))
        if (charged.get("status") != "SETTLED"
                or Decimal(charged.get("actual_cost", "-1")) != actual
                or Decimal(state["reserved_cost"]) != 0
                or Decimal(state["settled_cost"]) != actual
                or state["usage"] != dict(prompt_tokens=response.prompt_tokens,
                                          completion_tokens=response.completion_tokens)):
            raise ValueError("HORIZON_SETTLEMENT_UNVERIFIED")
        day = charged["budget_day"]
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            raise ValueError("HORIZON_DAILY_SETTLEMENT_MISMATCH")
        budget = self._budget_service
        directory = require_inside(budget.base, budget.base / "budget" / day, "daily research budget")
        with budget._lock(directory):
            files = sorted((directory / "versions").glob("*.json"))
            if not files or len(files) > 512:
                raise ValueError("DAILY_BUDGET_CHAIN_INVALID")
            previous = None
            for number, path in enumerate(files, 1):
                pin = budget._binding(path)
                row = budget._bound(pin)
                if (path.name != f'{number:04d}-{pin["sha256"]}.json'
                        or row.get("previous") != previous or row.get("version") != number
                        or row.get("day") != day or row.get("currency") != "CNY"):
                    raise ValueError("DAILY_BUDGET_CHAIN_INVALID")
                previous = pin
            head = directory / "current.json"
            if not head.is_file() or head.read_bytes() != _bytes(previous):
                raise ValueError("DAILY_BUDGET_HEAD_UNPUBLISHED_FAIL_CLOSED")
            record = row["records"].get(reservation, {})
            if record.get("status") != "SETTLED" or Decimal(record.get("cost", "-1")) != actual:
                raise ValueError("HORIZON_DAILY_SETTLEMENT_MISMATCH")

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, persisted_status=state["status"],
            symbol=spec["symbol"], years=spec["years"], workflow=CONTRACT,
            execution_mode=spec["mode"], source_binding=spec["source_binding"],
            context_fingerprint=spec["context_fingerprint"], request_sha256=spec["request_sha256"],
            research_as_of=spec["created_at"], model_id=spec["config"]["model_id"],
            currency="CNY", daily_cost_limit=str(spec["config"]["daily_cost_limit"]),
            scope="ANNUAL_OPERATING_SUPPLEMENT_REQUIRES_INDEPENDENT_REVIEW",
            review_status="PENDING", d2_three_role_complete=False,
            approval_changed=False, main_range_adopted=False, valuation_produced=False,
            formal_fact_count=0, condition_price=None, personal_quantity=None,
            usage_basis="CONFIGURED_RATE_ESTIMATE_NOT_PROVIDER_BILL",
            recovery_boundary="PUBLISHED_RESPONSE_ONLY_NO_AUTOMATIC_REPEAT_CALL",
            research_result=None)
        context, status, error = self._check(spec, now)
        if status and state["status"] != "CANCELLED":
            if state["status"] == "FAILED":
                # Historical failures remain auditable after source or code changes.
                # The old request still cannot be resumed or treated as research.
                value["current_replay_error"] = error
            else:
                value.update(status=status, error_code=error)
        elif context is not None and state["status"] != "CANCELLED":
            try:
                value["research_result"] = self._result(spec, state, context)
            except (ValueError, OSError, KeyError, TypeError) as error:
                value.update(status="FAILED", error_code=state.get("error_code") or _error_code(error))
        return value

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        years = _years(years)
        if (not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
                or not isinstance(request_key, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key)):
            raise ValueError("INVALID_HORIZON_IDENTITY")
        cfg = live.model_configuration(self.root)
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        task_id = "rt-" + _hash(request_key.encode("utf-8"))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
                if (spec["symbol"] != symbol or spec["years"] != years
                        or spec["config"] != cfg or spec["mode"] != mode
                        or spec["implementation_sha256"] != implementation()):
                    raise ValueError("HORIZON_REQUEST_KEY_CONFLICT")
                return self._view(spec, state, pin, now)
            context = self.source_loader(root=self.root, symbol=symbol, now=now)
            spec = dict(schema_version=VERSION, task_id=task_id,
                # Storage contract reused unchanged; public workflow is CONTRACT.
                workflow="operating_research", task_contract=CONTRACT,
                mode="TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING",
                symbol=symbol, years=years, request_key_sha256=_hash(request_key.encode("utf-8")),
                created_at=now.isoformat(), source_binding=context["source_binding"],
                context_fingerprint=context["snapshot_fingerprint"], context_sha256=_hash(_bytes(context)),
                config=cfg, implementation_sha256=implementation(), action="no_order")
            spec["request_sha256"] = _hash(_bytes(self._request(spec, context).__dict__))
            self._context(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0", settled_cost="0",
                reservations={}, response_binding=None, normalized_response_binding=None, created_at=now.isoformat(),
                action="no_order", formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    @staticmethod
    def _usage(response, request, model_id):
        if response.model_id != model_id:
            raise ValueError("HORIZON_PROVIDER_MODEL_MISMATCH")
        prompt_cap = len(_bytes(request.__dict__)) + 4096
        if (type(response.prompt_tokens) is not int or type(response.completion_tokens) is not int
                or not 0 <= response.prompt_tokens <= prompt_cap
                or not 0 <= response.completion_tokens <= request.max_completion_tokens
                or response.tool_calls or not isinstance(response.model_id, str)
                or not response.model_id.strip()):
            raise ValueError("HORIZON_PROVIDER_USAGE_INVALID")

    @staticmethod
    def _cost(prompt, completion, cfg):
        return (Decimal(prompt) * Decimal(str(cfg["input_cost_per_million"]))
                + Decimal(completion) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)

    def _drive(self, task_id, now, *, resume):
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            try:
                with self._lock(directory):
                    spec, state, pin = self._load(task_id, recover=resume)
                    if state["status"] in {"CANCELLED", "SUCCEEDED"}:
                        return self._view(spec, state, pin, now)
                    context = self._context(spec)
                    if state.get("response_binding"):
                        self._result(spec, state, context)
                        state, pin = self._save(spec, state, pin, now, status="SUCCEEDED", error_code=None)
                        return self._view(spec, state, pin, now)
                    if state["provider_requests"]:
                        state, pin = self._save(spec, state, pin, now, status="FAILED",
                            error_code="HORIZON_CALL_ALREADY_ATTEMPTED_NEW_KEY_REQUIRED")
                        return self._view(spec, state, pin, now)
                    if resume:
                        state, pin = self._save(spec, state, pin, now, status="QUEUED", error_code=None)
                        return self._view(spec, state, pin, now)
                    if state["status"] != "QUEUED":
                        return self._view(spec, state, pin, now)
                    provider = self._provider(spec)
                    request = self._request(spec, context)
                    cfg = spec["config"]
                    reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                                         request.max_completion_tokens, cfg)
                    if reserve > Decimal(str(cfg["max_run_cost"])):
                        raise ValueError("HORIZON_BUDGET_EXHAUSTED_BEFORE_CALL")
                    # Stable reservation prevents repeat calls even if the task save crashes.
                    reservation = _hash(_bytes([CONTRACT, task_id, spec["request_sha256"]]))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    # Intent precedes budget publication; either crash conservatively blocks retry.
                    state, pin = self._save(spec, state, pin, now, status="RUNNING", attempts=1,
                        provider_requests=1, reserved_cost=str(reserve),
                        reservations={reservation: dict(status="RESERVED", cost=str(reserve), budget_day=day)},
                        new_llm_calls=0)
                    self._daily_budget(day, reservation, reserve, cfg)
                    state, pin = self._save(spec, state, pin, now,
                        new_llm_calls=0 if self.test_provider is not None else 1)
                response = provider.complete(request)
                generated = _now()
                packet = dict(request_sha256=spec["request_sha256"], context_sha256=spec["context_sha256"],
                    implementation_sha256=spec["implementation_sha256"], years=spec["years"],
                    response=response.__dict__, generated_at=generated.isoformat(), action="no_order")
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    # Retain returned bytes before usage or semantic admission, including rejection.
                    path = directory / "response.json"
                    write_new_bytes(path, _bytes(packet))
                    state, pin = self._save(spec, state, pin, generated, response_binding=self._binding(path))
                    # A provider occasionally appends exactly one closing brace after a
                    # complete object.  Preserve that raw response and create a separate
                    # hash-bound view only when strict parsing proves no semantic edit.
                    try:
                        _strict_json_decoder().decode(response.text)
                        normalized = None
                    except json.JSONDecodeError:
                        normalized = _normalize_exact_extra_closing_brace(response.text)
                    if normalized is not None:
                        normalized_packet = dict(packet,
                            response=dict(response.__dict__, text=normalized),
                            transport_normalization=dict(
                                schema_version="horizon-json-transport-v1",
                                kind="EXACT_ONE_EXTRA_CLOSING_BRACE",
                                original_response_binding=self._binding(path),
                                original_response_sha256=_hash(response.text.encode("utf-8")),
                                normalized_response_sha256=_hash(normalized.encode("utf-8")),
                            ))
                        normalized_path = directory / "normalized-response.json"
                        write_new_bytes(normalized_path, _bytes(normalized_packet))
                        state, pin = self._save(spec, state, pin, generated,
                            normalized_response_binding=self._binding(normalized_path))
                    self._usage(response, request, cfg["model_id"])
                    actual = self._cost(response.prompt_tokens, response.completion_tokens, cfg)
                    self._daily_budget(day, reservation, actual, cfg, settle=True)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                    state, pin = self._save(spec, state, pin, generated,
                        reservations=reservations, reserved_cost="0", settled_cost=str(actual),
                        usage=dict(prompt_tokens=response.prompt_tokens, completion_tokens=response.completion_tokens))
                    if state["status"] == "CANCELLED":
                        return self._view(spec, state, pin, generated)
                    context = self._context(spec)
                    self._result(spec, state, context)
                    state, pin = self._save(spec, state, pin, generated, status="SUCCEEDED", error_code=None)
                    return self._view(spec, state, pin, generated)
            except Exception as error:
                # Never persist provider/validation exception text: it can contain secrets.
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    if state["status"] != "CANCELLED":
                        state, pin = self._save(spec, state, pin, _now(), status="FAILED",
                            error_code=_error_code(error))
                    return self._view(spec, state, pin, _now())


# Explicit live naming for consumers that mirror operating_task_v2.
LiveOperatingHorizonTaskService = OperatingHorizonTaskService



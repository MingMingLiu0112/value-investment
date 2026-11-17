"""Durable, budgeted D2 cash-policy follow-up using the existing task engine."""
from datetime import datetime
from pathlib import Path
import os
import re

from . import operating_horizon_task_v2 as v2
from .operating_horizon_task_v1 import _normalize_exact_extra_closing_brace
from . import operating_cash_policy_draft_v1 as draft
from . import dividend_policy_anchor_v1 as dividend_anchor
from . import parent_cash_conversion_anchor_v1 as cash_conversion
from . import operating_horizon_sources_v1 as sources
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse


CONTRACT = "operating-cash-policy-task-v1"
STORE = "cash-policy-v1"


def implementation():
    return {**v2.v1.implementation(), **sources.implementation(),
            draft.__name__: _hash(Path(draft.__file__).read_bytes()),
            dividend_anchor.__name__: _hash(Path(dividend_anchor.__file__).read_bytes()),
            cash_conversion.__name__: _hash(Path(cash_conversion.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingCashPolicyTaskService(v2.OperatingHorizonTaskService):
    """A policy-only D2 task; it never creates valuation or an action plan."""
    def __init__(self, root, *, test_provider=None, source_loader=None):
        super().__init__(root, test_provider=test_provider,
            source_loader=source_loader or sources.build_operating_horizon_source_context)
        self.base = require_inside(self.root, self.base.parent / STORE, "cash policy v1 tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if spec.get("task_contract") != CONTRACT:
            raise ValueError("INVALID_CASH_POLICY_TASK")
        v2.v1._years(spec["years"])
        return spec, state, pin

    def _request(self, spec, context):
        prior = context.get("prior_conditional_hypothesis")
        return draft.build_request(live.research_context(context, drivers=True), spec["years"],
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"],
            prior_hypothesis=(prior if isinstance(prior, dict)
                and spec["years"] == [prior.get("forecast_year")] else None))

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("CASH_POLICY_IMPLEMENTATION_CHANGED_NEW_TASK_REQUIRED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context["symbol"] != spec["symbol"] or context["source_binding"] != spec["source_binding"]
                or context["snapshot_fingerprint"] != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("CASH_POLICY_SOURCE_CONTEXT_CHANGED")
        if _hash(_bytes(self._request(spec, context).__dict__)) != spec["request_sha256"]:
            raise ValueError("CASH_POLICY_REQUEST_CHANGED")
        return context

    def _result(self, spec, state, context):
        pin = state.get("response_binding")
        if pin is None:
            if state["status"] == "SUCCEEDED":
                raise ValueError("CASH_POLICY_RESPONSE_MISSING")
            return None
        raw_packet = self._bound(pin)
        packet = raw_packet
        normalized_pin = state.get("normalized_response_binding")
        if normalized_pin is not None:
            packet = self._bound(normalized_pin)
            transport = packet.get("transport_normalization")
            raw_text = raw_packet.get("response", {}).get("text")
            normalized_text = packet.get("response", {}).get("text")
            if (not isinstance(raw_text, str) or not isinstance(normalized_text, str)
                    or not isinstance(transport, dict)
                    or transport.get("original_response_binding") != pin
                    or transport.get("original_response_sha256") != _hash(raw_text.encode("utf-8"))
                    or transport.get("normalized_response_sha256") != _hash(normalized_text.encode("utf-8"))
                    or _normalize_exact_extra_closing_brace(raw_text) != normalized_text):
                raise ValueError("CASH_POLICY_NORMALIZED_RESPONSE_BINDING_INVALID")
        if (packet["request_sha256"] != spec["request_sha256"]
                or packet["context_sha256"] != spec["context_sha256"]
                or packet["implementation_sha256"] != spec["implementation_sha256"]
                or packet["years"] != spec["years"] or packet["action"] != "no_order"):
            raise ValueError("CASH_POLICY_RESPONSE_BINDING_INVALID")
        response = LLMResponse(**packet["response"])
        self._usage(response, self._request(spec, context), spec["config"]["model_id"])
        result = draft.validate_response(response, context=live.research_context(context, drivers=True),
            years=spec["years"], generated_at=datetime.fromisoformat(packet["generated_at"]))
        if result.get("action") != "no_order" or result.get("formal_eligibility") is not False:
            raise ValueError("CASH_POLICY_RESULT_BOUNDARY_INVALID")
        self._verify_settlement(spec, state, response)
        return result

    def _prior_schema_failure(self, *, symbol, source_binding, config):
        """Refuse an identical paid retry after a provider schema failure.

        A different model/configuration can be used only through a new explicit
        authorization; this guard prevents repeatedly charging the same model
        for a contract it has already failed on the same sealed source input.
        """
        if not self.base.exists():
            return False
        for directory in self.base.iterdir():
            if not directory.is_dir() or not (directory / "input.json").is_file():
                continue
            try:
                with self._lock(directory):
                    old, state, _ = self._load(directory.name)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if (old.get("symbol") == symbol and old.get("source_binding") == source_binding
                    and old.get("config", {}).get("model_id") == config.get("model_id")
                    and state.get("status") == "FAILED"
                    and state.get("error_code") in {"HORIZON_EXACT_FIELDS_REQUIRED",
                                                     "HORIZON_STRUCTURED_RESPONSE_OR_SOURCE_REJECTED"}
                    and old.get("config", {}).get("authorization_reference")
                    == config.get("authorization_reference")):
                return True
        return False

    def _prior_equivalent_research(self, *, symbol, years, context, config, mode):
        """Do not charge again for the same sealed economic input and authority.

        An incomplete *successful* response is still a completed paid study. A
        new request key must not turn it into an unbounded retry. New evidence
        or an independently changed authorization can start a distinct study.
        """
        if not self.base.exists():
            return False
        children = list(self.base.iterdir())
        if len(children) > 100:
            raise ValueError("CASH_POLICY_TASK_DISCOVERY_LIMIT_EXCEEDED")
        # Source selection is sealed on each run, but its as_of and derived
        # base_context_sha256 change every time the same evidence is read.
        # Compare the source receipt/config/selection instead of that clock.
        stable = ("schema_version", "symbol", "base_binding", "selected_from",
                  "selection", "implementation_sha256", "action")
        current = self._bound(context["source_binding"])
        current_key = {key: current[key] for key in stable}
        for directory in children:
            if not directory.is_dir() or not (directory / "input.json").is_file():
                continue
            with self._lock(directory):
                old, state, _ = self._load(directory.name)
            if (old.get("symbol") == symbol and old.get("years") == years
                    and old.get("mode") == mode
                    and old.get("config", {}).get("model_id") == config.get("model_id")
                    and old.get("config", {}).get("authorization_reference")
                    == config.get("authorization_reference")
                    and (state.get("status") in {"QUEUED", "RUNNING", "SUCCEEDED"}
                         or state.get("provider_requests", 0) > 0)):
                prior = self._bound(old["source_binding"])
                if {key: prior[key] for key in stable} == current_key:
                    return True
        return False

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        years = v2.v1._years(years)
        if (not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
                or not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key)):
            raise ValueError("INVALID_CASH_POLICY_IDENTITY")
        cfg = live.model_configuration(self.root)
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        task_id = "rt-" + _hash((CONTRACT + ":" + request_key).encode("utf-8"))[:32]
        directory = self._directory(task_id)
        # The shared admission lock covers discovery and input creation; two
        # distinct request keys cannot both pass the same-source preflight.
        with self._lock(self.base, name="admission"), self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
                if (spec["symbol"] != symbol or spec["years"] != years or spec["config"] != cfg
                        or spec["mode"] != mode or spec["implementation_sha256"] != implementation()):
                    raise ValueError("CASH_POLICY_REQUEST_KEY_CONFLICT")
                return self._view(spec, state, pin, now)
            context = self.source_loader(root=self.root, symbol=symbol, now=now)
            if self._prior_schema_failure(symbol=symbol, source_binding=context["source_binding"], config=cfg):
                raise PermissionError("CASH_POLICY_PROVIDER_SCHEMA_FAILURE_REQUIRES_NEW_MODEL_OR_AUTHORIZATION")
            mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
            if self._prior_equivalent_research(symbol=symbol, years=years, context=context,
                                               config=cfg, mode=mode):
                raise PermissionError("CASH_POLICY_UNCHANGED_SOURCE_ALREADY_RESEARCHED")
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT,
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
                reservations={}, response_binding=None, created_at=now.isoformat(), action="no_order",
                formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _view(self, spec, state, binding, now):
        value = super()._view(spec, state, binding, now)
        value["workflow"] = CONTRACT
        value["scope"] = "SOURCE_BOUND_CASH_POLICY_ONLY_NOT_VALUATION_OR_PRICE"
        return value

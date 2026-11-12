"""Versioned D2 runner for the shareholder-cash-policy appendix.

V2 task artifacts remain frozen.  This runner shares its bounded provider,
source context and durable execution engine, but produces a distinct task
contract so an older annual forecast can never be mistaken for cash-policy
research.
"""
from datetime import datetime
from pathlib import Path
import os
import re

from . import operating_horizon_task_v2 as v2
from . import operating_horizon_draft_v3 as draft
from . import dividend_policy_anchor_v1 as dividend_anchor
from . import parent_cash_conversion_anchor_v1 as parent_cash_anchor
from . import operating_horizon_sources_v1 as sources
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse


CONTRACT = "operating-horizon-task-v4-cash-policy"
STORE = "oh-v4"


def implementation():
    return {**v2.v1.implementation(), **sources.implementation(),
            draft.__name__: _hash(Path(draft.__file__).read_bytes()),
            dividend_anchor.__name__: _hash(Path(dividend_anchor.__file__).read_bytes()),
            parent_cash_anchor.__name__: _hash(Path(parent_cash_anchor.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v2.OperatingHorizonTaskService):
    def __init__(self, root, *, test_provider=None, source_loader=None):
        super().__init__(root, test_provider=test_provider,
            source_loader=source_loader or sources.build_operating_horizon_source_context)
        # Keep the immutable task contract descriptive but keep the on-disk
        # namespace short enough that Windows can re-read version filenames
        # without relying on a caller's long-path process setting.
        self.base = require_inside(self.root, self.base.parent / STORE, "horizon v4 cash-policy tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if spec.get("task_contract") != CONTRACT:
            raise ValueError("INVALID_HORIZON_TASK")
        v2.v1._years(spec["years"])
        return spec, state, pin

    def _request(self, spec, context):
        return draft.build_request(live.research_context(context, drivers=True), spec["years"],
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("HORIZON_IMPLEMENTATION_CHANGED_NEW_TASK_REQUIRED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context["symbol"] != spec["symbol"] or context["source_binding"] != spec["source_binding"]
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
        packet = self._bound(pin)
        if (packet["request_sha256"] != spec["request_sha256"]
                or packet["context_sha256"] != spec["context_sha256"]
                or packet["implementation_sha256"] != spec["implementation_sha256"]
                or packet["years"] != spec["years"] or packet["action"] != "no_order"):
            raise ValueError("HORIZON_RESPONSE_BINDING_INVALID")
        response = LLMResponse(**packet["response"])
        self._usage(response, self._request(spec, context), spec["config"]["model_id"])
        result = draft.validate_response(response, context=live.research_context(context, drivers=True),
            years=spec["years"], generated_at=datetime.fromisoformat(packet["generated_at"]))
        if result.get("action") != "no_order" or result.get("formal_eligibility") is not False:
            raise ValueError("HORIZON_RESULT_BOUNDARY_INVALID")
        self._verify_settlement(spec, state, response)
        return result

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        years = v2.v1._years(years)
        if (not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
                or not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key)):
            raise ValueError("INVALID_HORIZON_IDENTITY")
        cfg = live.model_configuration(self.root)
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        task_id = "rt-" + _hash((CONTRACT + ":" + request_key).encode("utf-8"))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
                if (spec["symbol"] != symbol or spec["years"] != years or spec["config"] != cfg
                        or spec["mode"] != mode or spec["implementation_sha256"] != implementation()):
                    raise ValueError("HORIZON_REQUEST_KEY_CONFLICT")
                return self._view(spec, state, pin, now)
            context = self.source_loader(root=self.root, symbol=symbol, now=now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT, mode=("TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"),
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
        return value


LiveOperatingHorizonTaskService = OperatingHorizonTaskService

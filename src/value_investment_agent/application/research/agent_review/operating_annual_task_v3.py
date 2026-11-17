"""New annual D2 task contract with explicit source-bound residual citations.

The v2 store, requests and archived results are untouched. The durable task
engine, source loader and shared daily model budget are reused.
"""
from datetime import datetime
from pathlib import Path
import os
import re

from . import operating_horizon_task_v2 as v2
from . import operating_annual_draft_v3 as draft
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes

CONTRACT = "operating-horizon-task-v3"
STORE = "oh-v3"


def implementation():
    return {**v2.implementation(),
            draft.__name__: _hash(Path(draft.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v2.OperatingHorizonTaskService):
    def __init__(self, root, *, test_provider=None, source_loader=None):
        super().__init__(root, test_provider=test_provider, source_loader=source_loader)
        self.base = require_inside(self.root, self.base.parent / STORE,
                                   "horizon v3 annual tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(
            self, task_id, recover=recover)
        if spec.get("task_contract") != CONTRACT:
            raise ValueError("INVALID_HORIZON_TASK")
        v2.v1._years(spec["years"])
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
        # The v2 validator and settlement chain remain exact; v3 changes the
        # instruction carrying an already-required evidence citation.
        result = super()._result(spec, state, context)
        if result is not None:
            result["schema_version"] = draft.VERSION
            result["prompt_version"] = draft.VERSION
        return result

    def _prior_equivalent_research(self, *, symbol, years, context, config, mode):
        if not self.base.exists():
            return False
        directories = list(self.base.iterdir())
        if len(directories) > 100:
            raise ValueError("HORIZON_TASK_DISCOVERY_LIMIT_EXCEEDED")
        stable = ("schema_version", "symbol", "base_binding", "selected_from",
                  "selection", "implementation_sha256", "action")
        current = self._bound(context["source_binding"])
        identity = {key: current[key] for key in stable}
        for directory in directories:
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
                previous = self._bound(old["source_binding"])
                if {key: previous[key] for key in stable} == identity:
                    return True
        return False

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        years = v2.v1._years(years)
        if (not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
                or not isinstance(request_key, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key)):
            raise ValueError("INVALID_HORIZON_IDENTITY")
        cfg = live.model_configuration(self.root)
        if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        task_id = "rt-" + _hash((CONTRACT + ":" + request_key).encode("utf-8"))[:32]
        directory = self._directory(task_id)
        with self._lock(self.base, name="admission"), self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
                if (spec["symbol"] != symbol or spec["years"] != years
                        or spec["config"] != cfg or spec["mode"] != mode
                        or spec["implementation_sha256"] != implementation()):
                    raise ValueError("HORIZON_REQUEST_KEY_CONFLICT")
                return self._view(spec, state, pin, now)
            context = self.source_loader(root=self.root, symbol=symbol, now=now)
            mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
            if self._prior_equivalent_research(symbol=symbol, years=years,
                                               context=context, config=cfg, mode=mode):
                raise PermissionError("HORIZON_UNCHANGED_SOURCE_ALREADY_RESEARCHED")
            spec = dict(schema_version=VERSION, task_id=task_id,
                workflow="operating_research", task_contract=CONTRACT,
                mode="TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING",
                symbol=symbol, years=years,
                request_key_sha256=_hash(request_key.encode("utf-8")),
                created_at=now.isoformat(), source_binding=context["source_binding"],
                context_fingerprint=context["snapshot_fingerprint"],
                context_sha256=_hash(_bytes(context)), config=cfg,
                implementation_sha256=implementation(), action="no_order")
            spec["request_sha256"] = _hash(_bytes(self._request(spec, context).__dict__))
            self._context(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0,
                new_llm_calls=0, usage=dict(prompt_tokens=0, completion_tokens=0),
                reserved_cost="0", settled_cost="0", reservations={},
                response_binding=None, created_at=now.isoformat(), action="no_order",
                formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _view(self, spec, state, binding, now):
        value = super()._view(spec, state, binding, now)
        value["workflow"] = CONTRACT
        return value

"""Versioned D2 task with source-bound historical parent WC balances."""
from datetime import datetime
from pathlib import Path
import inspect
import os
import re

from . import operating_horizon_task_v4 as v4
from . import operating_horizon_task_v2 as v2
from . import operating_horizon_draft_v3 as draft
from . import operating_task_v2 as live
from . import parent_wc_balance_request_v1 as wc_request
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import parent_wc_history_600519_v1 as wc_source
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v5-parent-wc-balance"
STORE = "oh-v5-wc"


def implementation():
    return {**v4.implementation(),
        wc_request.__name__: _hash(Path(wc_request.__file__).read_bytes()),
        wc_source.__name__: _hash(Path(wc_source.__file__).read_bytes()),
        __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v4.OperatingHorizonTaskService):
    """Isolated task; live execution requires explicit construction."""
    def __init__(self, root, *, test_provider=None, allow_live=False,
                 source_loader=None, source_loader_version=None):
        if (test_provider is None and not allow_live) or (test_provider is not None and allow_live):
            raise PermissionError("V5_WC_EXECUTION_MODE_REQUIRED")
        if (source_loader is None) != (source_loader_version is None):
            raise ValueError("V5_WC_EXPLICIT_SOURCE_VERSION_REQUIRED")
        if allow_live and source_loader is None:
            raise ValueError("V5_WC_LIVE_EXPLICIT_SOURCE_REQUIRED")
        super().__init__(root, test_provider=test_provider, source_loader=source_loader)
        self.source_loader_version = source_loader_version or "operating-horizon-sources-v1"
        self.base = require_inside(self.root, self.base.parent / STORE, "v5 WC tasks")

    def _loader_binding(self):
        module = inspect.getmodule(self.source_loader)
        path = inspect.getsourcefile(self.source_loader)
        if (not isinstance(self.source_loader_version, str) or not self.source_loader_version
                or module is None or path is None):
            raise ValueError("V5_WC_SOURCE_LOADER_UNBOUND")
        details = module.implementation() if callable(getattr(module, "implementation", None)) else {
            module.__name__: _hash(Path(path).read_bytes())}
        declared = getattr(module, "VERSION", None)
        if isinstance(declared, str) and declared != self.source_loader_version:
            raise ValueError("V5_WC_SOURCE_LOADER_VERSION_MISMATCH")
        return dict(version=self.source_loader_version, module=module.__name__,
                    callable=self.source_loader.__qualname__, implementation=details)

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
        if spec.get("task_contract") != CONTRACT or spec.get("mode") != mode or len(spec.get("years", [])) != 1:
            raise ValueError("V5_WC_TASK_CONTRACT_INVALID")
        v2.v1._years(spec["years"])
        return spec, state, pin

    def _history(self, as_of):
        history = wc_source.read_parent_wc_history(self.root, as_of)
        if history.get("status") != "PARENT_BALANCE_MOVEMENTS_ONLY":
            raise ValueError("V5_WC_HISTORY_NOT_VERIFIED")
        registry_path = require_inside(self.root, self.root / wc_source.REGISTRY, "WC registry")
        raw = registry_path.read_bytes()
        registry = wc_source._json(raw)
        sources = registry.get("sources")
        if not isinstance(sources, list) or len(sources) < 2:
            raise ValueError("V5_WC_SOURCE_REGISTRY_INVALID")
        bindings = []
        for source in sources:
            path = require_inside(self.root, self.root / source["path"], "WC original")
            if wc_source._sha(path) != source["sha256"]:
                raise ValueError("V5_WC_SOURCE_CHANGED")
            bindings.append(dict(path=source["path"], sha256=source["sha256"]))
        pin = dict(registry=dict(path=wc_source.REGISTRY, sha256=_hash(raw)),
                   originals=bindings, history_sha256=_hash(_bytes(history)))
        return history, pin

    def _request_parts(self, spec, context):
        as_of = datetime.fromisoformat(spec["created_at"])
        history, pin = self._history(as_of)
        if pin != spec["wc_source_binding"]:
            raise ValueError("V5_WC_SOURCE_BINDING_CHANGED")
        return wc_request.build_request_with_parent_wc_balance(
            live.research_context(context, drivers=True), spec["years"],
            history=history, as_of=as_of,
            max_completion_tokens=spec["config"]["max_completion_tokens_cap"])

    def _request(self, spec, context):
        return self._request_parts(spec, context)[1]

    def _context(self, spec):
        if spec["implementation_sha256"] != implementation():
            raise ValueError("V5_WC_IMPLEMENTATION_CHANGED")
        if spec.get("source_loader_binding") != self._loader_binding():
            raise ValueError("V5_WC_SOURCE_LOADER_CHANGED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context["symbol"] != spec["symbol"]
                or context["source_binding"] != spec["source_binding"]
                or context["snapshot_fingerprint"] != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("V5_WC_CONTEXT_CHANGED")
        if _hash(_bytes(self._request(spec, context).__dict__)) != spec["request_sha256"]:
            raise ValueError("V5_WC_REQUEST_CHANGED")
        return context

    def _result(self, spec, state, context):
        pin = state.get("response_binding")
        if pin is None:
            if state["status"] == "SUCCEEDED":
                raise ValueError("V5_WC_RESPONSE_MISSING")
            return None
        packet = self._bound(pin)
        if (packet["request_sha256"] != spec["request_sha256"]
                or packet["context_sha256"] != spec["context_sha256"]
                or packet["implementation_sha256"] != spec["implementation_sha256"]
                or packet["years"] != spec["years"] or packet["action"] != "no_order"):
            raise ValueError("V5_WC_RESPONSE_BINDING_INVALID")
        response = LLMResponse(**packet["response"])
        enriched, request, anchor = self._request_parts(spec, context)
        self._usage(response, request, spec["config"]["model_id"])
        result = draft.validate_response(response, context=enriched, years=spec["years"],
                                         generated_at=datetime.fromisoformat(packet["generated_at"]))
        if (result.get("action") != "no_order" or result.get("formal_eligibility") is not False
                or anchor["operating_wc_cash_cny"] != "UNKNOWN"):
            raise ValueError("V5_WC_RESULT_BOUNDARY_INVALID")
        self._verify_settlement(spec, state, response)
        return result

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        years = v2.v1._years(years)
        if (len(years) != 1 or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
                or not isinstance(request_key, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key)):
            raise ValueError("INVALID_HORIZON_IDENTITY")
        cfg = live.model_configuration(self.root)
        mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider is not None else "LIVE_OPERATING"
        if mode == "LIVE_OPERATING" and not os.environ.get(cfg["api_key_env"]):
            raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        history, wc_pin = self._history(now)
        if history["symbol"] != symbol:
            raise ValueError("V5_WC_SYMBOL_MISMATCH")
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        identity = ((CONTRACT + ":" + request_key).encode("utf-8") if self.test_provider is not None
            else _bytes([CONTRACT, symbol, years, context["source_binding"],
                         context["snapshot_fingerprint"], wc_pin]))
        task_id = "rt-" + _hash(identity)[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if (spec["symbol"] != symbol or spec["years"] != years
                        or spec["config"] != cfg or spec["mode"] != mode
                        or spec["implementation_sha256"] != implementation()):
                    raise ValueError("V5_WC_REQUEST_KEY_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT, mode=mode, symbol=symbol,
                years=years, request_key_sha256=_hash(request_key.encode("utf-8")),
                created_at=now.isoformat(), source_binding=context["source_binding"],
                context_fingerprint=context["snapshot_fingerprint"],
                context_sha256=_hash(_bytes(context)), wc_source_binding=wc_pin,
                source_loader_binding=self._loader_binding(),
                config=cfg, implementation_sha256=implementation(), action="no_order")
            spec["request_sha256"] = _hash(_bytes(self._request(spec, context).__dict__))
            self._context(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0",
                settled_cost="0", reservations={}, response_binding=None,
                created_at=now.isoformat(), action="no_order", formal_eligibility=False,
                error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _view(self, spec, state, binding, now):
        value = super()._view(spec, state, binding, now)
        value["workflow"] = CONTRACT
        value["wc_source_binding"] = spec["wc_source_binding"]
        value["operating_wc_cash_cny"] = "UNKNOWN"
        result = value.get("research_result")
        ready = (value.get("status") == "SUCCEEDED" and isinstance(result, dict)
            and result.get("schema_version") == draft.VERSION
            and result.get("cash_policy_appendix_status") == "COMPLETE_UNAPPROVED"
            and isinstance(result.get("years"), dict)
            and set(result["years"]) == {str(year) for year in spec["years"]})
        if ready:
            for row in result["years"].values():
                cash = row.get("shareholder_cash_paths", {})
                operating = row.get("operating_paths", {})
                if (set(cash) != {"bear", "base", "bull"}
                        or set(operating) != {"bear", "base", "bull"}):
                    ready = False
                    break
                for scenario in ("bear", "base", "bull"):
                    capital = operating[scenario].get("capital_assumptions", [])
                    if (cash[scenario].get("complete") is not True
                            or len(capital) != 3
                            or any(item.get("classification") != "FORECAST" for item in capital)):
                        ready = False
                        break
                if not ready:
                    break
        value["d2_handoff_readiness"] = (
            "VALIDATED_COMPLETE_UNAPPROVED_FOR_E2_REVIEW" if ready
            else "INCOMPLETE_OR_UNVERIFIED")
        return value

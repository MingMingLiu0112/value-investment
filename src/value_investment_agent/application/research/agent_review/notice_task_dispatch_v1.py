"""Route old and notice-augmented D2 tasks through one durable task store.

Task IDs and records are not copied or rewritten. The source manifest version
chooses the loader used for read/replay; new configured issuers use the
highest explicitly configured source version.
"""
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v2 as notice_sources
from . import operating_horizon_sources_v3 as implementation_sources
from . import operating_horizon_sources_v4 as prior_stress_sources
from . import operating_horizon_sources_v5 as quarterly_sources
from . import operating_horizon_sources_v6 as approved_plan_sources
from . import operating_horizon_sources_v7 as return_plan_sources
from . import operating_horizon_sources_v8 as conditioned_plan_sources
from . import operating_horizon_sources_v9 as critique_stress_sources
from .operating_policy_denominator_review_v1 import review_task_view
from .operating_annual_task_v3 import OperatingHorizonTaskService as AnnualTask
from .operating_cash_policy_task_v1 import OperatingCashPolicyTaskService as CashTask
from .operating_cash_policy_task_v3 import OperatingCashPolicyTaskServiceV3 as CashTaskV3

_CASH_POLICY_TERMS = (
    "target_payout_ratio", "accessible_profit_ratio", "reserve_ratio",
    "net_maintenance_cash_cny", "operating_wc_cash_cny", "commitment_cash_cny",
)


def _sealed_failure_diagnostic(service, task_id, row):
    """Describe a rejected sealed response without treating it as research.

    Only fixed contract field names leave this projection. Model supplied
    prose, numbers and evidence IDs remain untrusted and are never promoted.
    """
    if (row.get("status") != "FAILED"
            or row.get("error_code") != "HORIZON_EXACT_FIELDS_REQUIRED"):
        return None
    try:
        _, state, _ = service._load(task_id)
        binding = state.get("response_binding")
        if not isinstance(binding, dict):
            return None
        packet = service._bound(binding)
        raw = packet.get("response", {}).get("text")
        if not isinstance(raw, str) or len(raw) > 100000:
            return None
        draft = json.loads(raw)
        years = draft.get("years") if isinstance(draft, dict) else None
        if not isinstance(years, dict) or len(years) > 3:
            return None
        missing = []
        for year, result in years.items():
            if not isinstance(year, str) or not re.fullmatch(r"20[0-9]{2}", year):
                return None
            paths = result.get("shareholder_cash_paths") if isinstance(result, dict) else None
            if not isinstance(paths, dict):
                return None
            for scenario in ("bear", "base", "bull"):
                path = paths.get(scenario)
                if not isinstance(path, dict):
                    return None
                for term in _CASH_POLICY_TERMS:
                    item = path.get(term)
                    if not isinstance(item, dict):
                        reason = "ABSENT"
                    elif item.get("classification") != "FORECAST_ASSUMPTION":
                        reason = "NOT_QUANTIFIED"
                    else:
                        continue
                    missing.append(dict(year=year, scenario=scenario,
                                        term=term, reason=reason))
        return dict(status="REJECTED_RESPONSE_DIAGNOSTIC_ONLY",
                    response_binding=binding, missing_terms=missing,
                    action="no_order", formal_eligibility=False,
                    e2_usable=False)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _conditioned_research_view(row):
    """Explain sealed v8 research without changing its persisted task outcome."""
    value = review_task_view(row)
    years = (value.get("research_result") or {}).get("years") or {}
    missing = []
    for year, result in years.items():
        for scenario, path in result.get("shareholder_cash_paths", {}).items():
            terms = path.get("terms", {})
            for name in _CASH_POLICY_TERMS:
                if terms.get(name, {}).get("classification") != "FORECAST_ASSUMPTION":
                    missing.append(dict(year=year, scenario=scenario, term=name))
    accepted = (value.get("status") == "SUCCEEDED"
                and value.get("economic_validation", {}).get("status") != "REJECTED")
    value["cash_policy_completeness"] = dict(
        status=("INCOMPLETE_UNKNOWN_TERMS" if missing else
                "COMPLETE_UNAPPROVED_RESEARCH" if years and accepted else "NO_VALIDATED_RESULT"),
        missing_terms=missing, source_scope="SEALED_RESPONSE_READ_ONLY",
        task_accepted=accepted,
        formal_eligibility=False, action="no_order")
    return value


class NoticeAwareTaskService:
    def __init__(self, root, *, kind):
        if kind not in {"annual", "cash"}:
            raise ValueError("NOTICE_TASK_KIND_INVALID")
        self.kind = kind
        cls = AnnualTask if kind == "annual" else CashTask
        self.legacy = cls(root)
        self.notice = cls(root, source_loader=notice_sources.build_operating_horizon_source_context)
        self.implemented = cls(root, source_loader=implementation_sources.build_operating_horizon_source_context)
        self.prior_stress = cls(root, source_loader=prior_stress_sources.build_operating_horizon_source_context)
        self.quarterly = cls(root, source_loader=quarterly_sources.build_operating_horizon_source_context)
        self.approved_plan = cls(root, source_loader=approved_plan_sources.build_operating_horizon_source_context)
        self.return_plan = cls(root, source_loader=return_plan_sources.build_operating_horizon_source_context)
        self.conditioned_plan = (cls if kind == "annual" else CashTaskV3)(
            root, source_loader=conditioned_plan_sources.build_operating_horizon_source_context)
        self.critique_stress = (cls if kind == "annual" else CashTaskV3)(
            root, source_loader=critique_stress_sources.build_operating_horizon_source_context)
        self.root = Path(root).resolve()
        self.base = self.legacy.base

    @staticmethod
    def _version(binding):
        path = binding.get("path") if isinstance(binding, dict) else None
        if not isinstance(path, str):
            raise ValueError("NOTICE_TASK_SOURCE_BINDING_INVALID")
        if path.startswith("runtime/operating-horizon-sources-v9/"):
            return "v9"
        if path.startswith("runtime/operating-horizon-sources-v8/"):
            return "v8"
        if path.startswith("runtime/operating-horizon-sources-v7/"):
            return "v7"
        if path.startswith("runtime/operating-horizon-sources-v6/"):
            return "v6"
        if path.startswith("runtime/operating-horizon-sources-v5/"):
            return "v5"
        if path.startswith("runtime/operating-horizon-sources-v4/"):
            return "v4"
        if path.startswith("runtime/operating-horizon-sources-v3/"):
            return "v3"
        if path.startswith("runtime/operating-horizon-sources-v2/"):
            return "v2"
        if path.startswith("runtime/operating-horizon-sources-v1/"):
            return "v1"
        raise ValueError("NOTICE_TASK_SOURCE_VERSION_UNSUPPORTED")

    def source_loader(self, *, root, symbol, now, binding=None):
        if binding is None:
            raise ValueError("NOTICE_TASK_SOURCE_BINDING_REQUIRED_FOR_REPLAY")
        service = self._by_version(binding)
        return service.source_loader(root=root, symbol=symbol, now=now, binding=binding)

    def _service(self, task_id):
        directory = self.legacy._directory(task_id)
        input_path = directory / "input.json"
        if not input_path.is_file():
            raise FileNotFoundError(task_id)
        spec = json.loads(input_path.read_text(encoding="utf-8"))
        return self._by_version(spec.get("source_binding"))

    def _by_version(self, binding):
        return {"v1": self.legacy, "v2": self.notice,
                "v3": self.implemented, "v4": self.prior_stress,
                "v5": self.quarterly, "v6": self.approved_plan,
                "v7": self.return_plan, "v8": self.conditioned_plan,
                "v9": self.critique_stress}[self._version(binding)]

    def create(self, *, symbol, request_key, years, now=None):
        if self.kind == "cash" and symbol in self._configured_symbols(
                critique_stress_sources.CONFIG, "operating-critique-stress-selection-v1"):
            critique_stress_sources._selection(self.root, symbol)
            service = self.critique_stress
        elif symbol in self._configured_symbols(return_plan_sources.CONFIG,
                                              "operating-return-plan-text-selection-v1"):
            return_plan_sources._selection(self.root, symbol)
            service = self.conditioned_plan if self.kind == "cash" else self.return_plan
        elif symbol in self._configured_symbols(approved_plan_sources.CONFIG,
                                              "operating-approved-dividend-plan-selection-v1"):
            approved_plan_sources._selection(self.root, symbol)
            service = self.approved_plan
        elif symbol in self._configured_symbols(quarterly_sources.CONFIG,
                                              "operating-quarterly-source-selection-v1"):
            quarterly_sources._selection(self.root, symbol)
            service = self.quarterly
        elif symbol in self._configured_symbols(prior_stress_sources.CONFIG,
                                               "operating-prior-stress-selection-v1"):
            prior_stress_sources._selection(self.root, symbol)
            service = self.prior_stress
        elif symbol in self._configured_symbols(implementation_sources.CONFIG,
                                               "operating-distribution-implementation-selection-v1"):
            implementation_sources._selection(self.root, symbol)
            service = self.implemented
        elif symbol in self._configured_symbols(notice_sources.CONFIG,
                                                "operating-public-notice-selection-v1"):
            notice_sources._selection(self.root, symbol)
            service = self.notice
        else:
            service = self.legacy
        return service.create(symbol=symbol, request_key=request_key, years=years, now=now)

    def _configured_symbols(self, config_path, schema_version):
        path = self.root / config_path
        if not path.is_file():
            return set()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != schema_version or payload.get("action") != "no_order":
            raise ValueError("PUBLIC_NOTICE_CONFIG_INVALID")
        return set(payload.get("cases", {}))

    def read(self, task_id):
        service = self._service(task_id)
        row = service.read(task_id)
        if service is self.return_plan:
            return review_task_view(row)
        if service in (self.conditioned_plan, self.critique_stress):
            view = _conditioned_research_view(row)
            if self.kind == "cash":
                diagnostic = _sealed_failure_diagnostic(service, task_id, view)
                if diagnostic is not None:
                    view["sealed_response_diagnostic"] = diagnostic
            return view
        return row

    def run(self, task_id):
        service = self._service(task_id)
        result = service.run(task_id)
        if service is self.return_plan:
            return review_task_view(result)
        return _conditioned_research_view(result) if service in (self.conditioned_plan, self.critique_stress) else result

    def resume(self, task_id):
        service = self._service(task_id)
        result = service.resume(task_id)
        if service is self.return_plan:
            return review_task_view(result)
        return _conditioned_research_view(result) if service in (self.conditioned_plan, self.critique_stress) else result

    def cancel(self, task_id):
        return self._service(task_id).cancel(task_id)

    def list_for_symbol(self, symbol):
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
            raise ValueError("NOTICE_TASK_SYMBOL_INVALID")
        if not self.base.exists():
            return []
        children = list(self.base.iterdir())
        if len(children) > 100:
            raise ValueError("RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED")
        rows = []
        for path in sorted(children):
            if path.is_dir() and path.name.startswith("rt-") and (path / "input.json").is_file():
                # Discovery reads only the immutable input identity first. A task
                # for another issuer must not force replay of its PDFs (or make
                # this issuer's list fail because that other source changed).
                spec = json.loads((path / "input.json").read_text(encoding="utf-8"))
                if spec.get("symbol") != symbol:
                    continue
                item = self.read(path.name)
                if item["symbol"] != symbol:
                    raise ValueError("RESEARCH_TASK_INPUT_IDENTITY_MISMATCH")
                rows.append(item)
                if len(rows) > 20:
                    raise ValueError("RESEARCH_TASK_RESULT_LIMIT_EXCEEDED")
        return sorted(rows, key=lambda row: (row["updated_at"], row["task_id"]), reverse=True)

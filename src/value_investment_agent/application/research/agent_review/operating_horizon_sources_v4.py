"""Bind a prior unapproved stress for critique, never as an official fact.

The v3 official-source corpus remains intact. The older proposal is checked
byte-for-byte with its source closure, and its year-one cash terms are supplied
only through the existing D2 prior-hypothesis channel. No old valuation is
copied into a new candidate.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v3 as v3
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes

VERSION = "operating-horizon-sources-v4"
CONFIG = "config/current-operating-prior-stress-v1.json"
TERMS = ("target_payout_ratio", "accessible_profit_ratio", "reserve_ratio",
         "net_maintenance_cash_cny", "operating_wc_cash_cny", "commitment_cash_cny")
MAX_CONTEXT_CHARS = 71000


def implementation():
    return {**v3.implementation(), __name__: _hash(Path(__file__).read_bytes())}


def _selection(root, symbol):
    raw = (root / CONFIG).read_bytes()
    config = json.loads(raw)
    if (config.get("schema_version") != "operating-prior-stress-selection-v1"
            or config.get("action") != "no_order"):
        raise ValueError("PRIOR_STRESS_CONFIG_INVALID")
    selected = config.get("cases", {}).get(symbol)
    if (not isinstance(selected, dict)
            or set(selected) != {"proposal_path", "proposal_sha256", "choice_id"}
            or not isinstance(selected["proposal_path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", selected["proposal_sha256"])
            or not isinstance(selected["choice_id"], str)):
        raise ValueError("PRIOR_STRESS_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def _prior(root, selected, base, now):
    path = require_inside(root, root / selected["proposal_path"], "prior stress proposal")
    if _hash(path.read_bytes()) != selected["proposal_sha256"]:
        raise ValueError("PRIOR_STRESS_PROPOSAL_CHANGED")
    value = json.loads(path.read_bytes())
    if (value.get("schema_version") != "joint-capital-cash-path-proposal-v4"
            or value.get("symbol") != base["symbol"] or value.get("action") != "no_order"
            or value.get("status") != "NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW"
            or value.get("assumptions_approved") is not False
            or value.get("g3_approved") is not False
            or value.get("price_admitted") is not False
            or value.get("joint_historical", {}).get("currency") != "CNY"):
        raise ValueError("PRIOR_STRESS_IDENTITY_OR_APPROVAL_INVALID")
    generated = datetime.fromisoformat(value["generated_at"])
    if generated.tzinfo is None or generated > now:
        raise ValueError("PRIOR_STRESS_NOT_AVAILABLE_AS_OF")
    refs = value.get("source_bindings")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 250:
        raise ValueError("PRIOR_STRESS_SOURCE_CLOSURE_INVALID")
    seen = {}
    for ref in refs:
        if (not isinstance(ref, dict) or not {"path", "sha256"} <= set(ref)
                or not isinstance(ref["path"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])):
            raise ValueError("PRIOR_STRESS_SOURCE_REF_INVALID")
        source = require_inside(root, root / ref["path"], "prior stress source")
        if _hash(source.read_bytes()) != ref["sha256"]:
            raise ValueError("PRIOR_STRESS_SOURCE_CHANGED")
        if ref["path"] in seen and seen[ref["path"]] != ref["sha256"]:
            raise ValueError("PRIOR_STRESS_SOURCE_CONFLICT")
        seen[ref["path"]] = ref["sha256"]
    choices = [row for row in value.get("choices", [])
               if isinstance(row, dict) and row.get("id") == selected["choice_id"]]
    if len(choices) != 1 or selected["choice_id"] != "FUNDING_PRESSURE":
        raise ValueError("PRIOR_STRESS_CHOICE_INVALID")
    choice = choices[0]
    paths = {}
    for scenario in ("bear", "base", "bull"):
        years = choice.get("joint_drivers", {}).get(scenario, {}).get("years")
        if not isinstance(years, list) or not years or years[0].get("year") != 1:
            raise ValueError("PRIOR_STRESS_YEAR_INVALID")
        terms = {}
        for key in TERMS:
            raw = years[0].get(key)
            if not isinstance(raw, str):
                raise ValueError("PRIOR_STRESS_TERM_INVALID")
            try:
                number = Decimal(raw)
            except InvalidOperation:
                raise ValueError("PRIOR_STRESS_TERM_INVALID") from None
            if not number.is_finite() or number < 0 or (key.endswith("_ratio") and number > 1):
                raise ValueError("PRIOR_STRESS_TERM_INVALID")
            terms[key] = raw
        paths[scenario] = terms
    return dict(binding=dict(path=selected["proposal_path"], sha256=selected["proposal_sha256"]),
        generated_at=value["generated_at"], financial_basis=base["financial_basis"],
        forecast_year=int(base["financial_basis"][:4]) + 1,
        scenario_first_year=paths,
        scope="OLDER_UNAPPROVED_CONDITIONAL_STRESS_FOR_CRITICAL_REVIEW_ONLY",
        limitation=("Funding-pressure numbers are an older unapproved stress, not official facts, "
                    "current main-range assumptions, approval, or defaults. Each term must be "
                    "independently justified or rejected against the newer official corpus."))


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("PRIOR_STRESS_AS_OF_INVALID")
    if binding is None:
        selected, config_pin = _selection(root, symbol)
        base = v3.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol,
            as_of=now.isoformat(), base_binding=deepcopy(base["source_binding"]),
            base_context_sha256=_hash(_bytes(base)), selection=deepcopy(selected),
            selected_from=config_pin, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root, root / "runtime" / VERSION / (_hash(raw) + ".json"),
                              "prior stress manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = v3.v2.v1._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("PRIOR_STRESS_MANIFEST_CHANGED")
        selected, config_pin = _selection(root, symbol)
        if manifest.get("selection") != selected or manifest.get("selected_from") != config_pin:
            raise ValueError("PRIOR_STRESS_SELECTION_CHANGED")
        base = v3.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if (base["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(base)) != manifest["base_context_sha256"]):
        raise ValueError("PRIOR_STRESS_BASE_CHANGED")
    prior = _prior(root, selected, base, now)
    value = deepcopy(base)
    if value.get("prior_conditional_hypothesis") is not None:
        raise ValueError("PRIOR_STRESS_DUPLICATE_HYPOTHESIS")
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
                 implementation_sha256=manifest["implementation_sha256"],
                 prior_conditional_hypothesis=prior)
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items()
                                                  if k != "snapshot_fingerprint"}))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("PRIOR_STRESS_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            v3.v2.v1._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value

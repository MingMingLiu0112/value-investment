"""Attach an old, unapproved issuer cash stress for D2 critique only.

This extends v8's official corpus without changing historical v8 manifests.
The old proposal is a hypothesis, never an evidence row or E2 input.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v8 as previous
from . import operating_horizon_sources_v1 as base_sources
from . import operating_policy_denominator_review_v1 as denominator_review
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes

VERSION = "operating-horizon-sources-v9"
CONFIG = "config/current-operating-critique-stress-v1.json"
TERMS = ("target_payout_ratio", "accessible_profit_ratio", "reserve_ratio",
         "net_maintenance_cash_cny", "operating_wc_cash_cny", "commitment_cash_cny")
MAX_CONTEXT_CHARS = 79000


def implementation():
    return {**previous.implementation(),
        denominator_review.__name__: _hash(Path(denominator_review.__file__).read_bytes()),
        __name__: _hash(Path(__file__).read_bytes())}


def _selection(root, symbol):
    raw = (root / CONFIG).read_bytes()
    config = json.loads(raw)
    if config.get("schema_version") != "operating-critique-stress-selection-v1" or config.get("action") != "no_order":
        raise ValueError("V9_CRITIQUE_CONFIG_INVALID")
    selected = config.get("cases", {}).get(symbol)
    if (not isinstance(selected, dict)
            or set(selected) != {"proposal_path", "proposal_sha256", "choice_id"}
            or not isinstance(selected["proposal_path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", selected["proposal_sha256"])
            or not isinstance(selected["choice_id"], str)):
        raise ValueError("V9_CRITIQUE_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def _prior(root, selected, base, now):
    path = require_inside(root, root / selected["proposal_path"], "critique proposal")
    raw = path.read_bytes()
    if _hash(raw) != selected["proposal_sha256"]:
        raise ValueError("V9_CRITIQUE_PROPOSAL_CHANGED")
    proposal = json.loads(raw)
    if (proposal.get("schema_version") != "joint-capital-cash-path-proposal-v4"
            or proposal.get("symbol") != base["symbol"] or proposal.get("action") != "no_order"
            or proposal.get("status") != "NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW"
            or proposal.get("assumptions_approved") is not False
            or proposal.get("g3_approved") is not False
            or proposal.get("price_admitted") is not False
            or proposal.get("joint_historical", {}).get("currency") != "CNY"):
        raise ValueError("V9_CRITIQUE_IDENTITY_OR_APPROVAL_INVALID")
    generated = datetime.fromisoformat(proposal["generated_at"])
    if generated.utcoffset() is None or generated > now:
        raise ValueError("V9_CRITIQUE_NOT_AVAILABLE_AS_OF")
    refs = proposal.get("source_bindings")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 250:
        raise ValueError("V9_CRITIQUE_SOURCE_CLOSURE_INVALID")
    seen = {}
    for ref in refs:
        if (not isinstance(ref, dict) or not isinstance(ref.get("path"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", str(ref.get("sha256")))):
            raise ValueError("V9_CRITIQUE_SOURCE_REF_INVALID")
        source = require_inside(root, root / ref["path"], "critique source")
        if _hash(source.read_bytes()) != ref["sha256"]:
            raise ValueError("V9_CRITIQUE_SOURCE_CHANGED")
        if ref["path"] in seen and seen[ref["path"]] != ref["sha256"]:
            raise ValueError("V9_CRITIQUE_SOURCE_CONFLICT")
        seen[ref["path"]] = ref["sha256"]
    choices = [row for row in proposal.get("choices", [])
               if isinstance(row, dict) and row.get("id") == selected["choice_id"]]
    if len(choices) != 1:
        raise ValueError("V9_CRITIQUE_CHOICE_INVALID")
    paths = {}
    for scenario in ("bear", "base", "bull"):
        years = choices[0].get("joint_drivers", {}).get(scenario, {}).get("years")
        if not isinstance(years, list) or not years or years[0].get("year") != 1:
            raise ValueError("V9_CRITIQUE_YEAR_INVALID")
        terms = {}
        for key in TERMS:
            value = years[0].get(key)
            if not isinstance(value, str):
                raise ValueError("V9_CRITIQUE_TERM_INVALID")
            try:
                number = Decimal(value)
            except InvalidOperation:
                raise ValueError("V9_CRITIQUE_TERM_INVALID") from None
            if not number.is_finite() or number < 0 or (key.endswith("_ratio") and number > 1):
                raise ValueError("V9_CRITIQUE_TERM_INVALID")
            terms[key] = value
        paths[scenario] = terms
    return dict(binding=dict(path=selected["proposal_path"], sha256=selected["proposal_sha256"]),
        generated_at=proposal["generated_at"], financial_basis=base["financial_basis"],
        forecast_year=int(base["financial_basis"][:4]) + 1, scenario_first_year=paths,
        scope="OLDER_UNAPPROVED_CONDITIONAL_STRESS_FOR_CRITICAL_REVIEW_ONLY",
        limitation=("Older low-confidence issuer stress; its numeric cash terms are neither official facts "
                    "nor current forecasts, defaults, main valuation or approval. Independently justify, "
                    "revise or reject each term against the newer official corpus."))


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("V9_AS_OF_INVALID")
    selected, config_pin = _selection(root, symbol)
    if binding is None:
        base = previous.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(base["source_binding"]), base_context_sha256=_hash(_bytes(base)),
            selection=deepcopy(selected), selected_from=config_pin, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"), "v9 manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = base_sources._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("selection") != selected or manifest.get("selected_from") != config_pin
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("V9_MANIFEST_CHANGED")
        base = previous.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if base["source_binding"] != manifest["base_binding"] or _hash(_bytes(base)) != manifest["base_context_sha256"]:
        raise ValueError("V9_BASE_CHANGED")
    if base.get("prior_conditional_hypothesis") is not None:
        raise ValueError("V9_DUPLICATE_PRIOR_HYPOTHESIS")
    value = deepcopy(base)
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
        implementation_sha256=manifest["implementation_sha256"],
        prior_conditional_hypothesis=_prior(root, selected, base, now))
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items() if k != "snapshot_fingerprint"}))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("V9_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            base_sources._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value

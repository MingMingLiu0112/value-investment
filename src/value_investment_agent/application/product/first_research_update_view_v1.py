"""Read a registered E1 successor without adopting it as current valuation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

from ..research.first_research_input_v1 import replay_first_research_input
from .common import require_inside, sha256_file

REGISTRY = "config/current-first-research-updates-v1.json"
SCHEMA = "current-first-research-updates-v1"


def _bound(root: Path, ref: dict, label: str) -> dict:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError(label + " binding invalid")
    if not isinstance(ref["path"], str) or not isinstance(ref["sha256"], str):
        raise ValueError(label + " binding fields invalid")
    path = require_inside(root / "runtime", root / ref["path"], label)
    if sha256_file(path) != ref["sha256"]:
        raise ValueError(label + " hash changed")
    return json.loads(path.read_text(encoding="utf-8"))


def read_first_research_update(*, root: Path, symbol: str, now: datetime,
                               predecessor_binding: dict | None = None,
                               displayed_binding: dict | None = None) -> dict:
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit():
        raise ValueError("Invalid E1 update symbol")
    base = dict(schema_version="first-research-update-view-v1", action="no_order",
                symbol=symbol, status="NOT_STARTED", formal_eligibility=False,
                main_range_adopted=False, price_admitted=False,
                condition_price=None, personal_quantity=None)
    path = root / REGISTRY
    if not path.exists():
        return base
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
        if (registry.get("schema_version") != SCHEMA or registry.get("action") != "no_order"
                or not isinstance(registry.get("cases"), dict)):
            raise ValueError("E1 update registry invalid")
        ref = registry["cases"].get(symbol)
        if ref is None:
            return base
        update = _bound(root, ref, "E1 update")
        if (update.get("schema_version") not in {"first-research-input-update-v1", "first-research-input-update-v2", "direct-owner-cash-update-v1"}
                or update.get("symbol") != symbol or update.get("action") != "no_order"
                or update.get("status") != "SUCCESSOR_CONDITIONAL_RESEARCH_PENDING_REVIEW"
                or any(update.get(key) is not False for key in
                       ("formal_eligibility", "main_range_adopted", "price_admitted"))):
            raise ValueError("E1 update boundary invalid")
        if predecessor_binding is not None and predecessor_binding != update["predecessor_binding"]:
            raise ValueError("E1 predecessor differs from the currently displayed first input")
        if displayed_binding is not None and displayed_binding not in (
                update["predecessor_binding"], update["successor_binding"]):
            raise ValueError("E1 predecessor differs from the currently displayed first input")
        relation = ("SUCCESSOR" if displayed_binding == update["successor_binding"]
                    else "PREDECESSOR" if displayed_binding == update["predecessor_binding"]
                    else None)
        if update["schema_version"] == "direct-owner-cash-update-v1":
            from ..research.agent_review.web_research import _binding
            from ..research.direct_owner_cash_update_v1 import replay_direct_owner_cash_update
            # Apply the same public-path checks as first-input reads before replay.
            _binding(root, update["change_binding"])
            for key in ("predecessor_binding", "successor_binding"):
                _binding(root, update[key])
                receipt = _bound(root, update[key], "E1 direct receipt")
                for item in receipt.get("source_bindings", []):
                    _binding(root, item, runtime_only=False)
                for field in ("spec_binding", "result_binding"):
                    _binding(root, receipt[field])
            verified = replay_direct_owner_cash_update(root=root, update_binding=ref, now=now)
            return dict(base, status="SOURCE_BOUND_CONDITIONAL_SUCCESSOR",
                        displayed_version_role=relation,
                        yearly_changes=verified["yearly_changes"],
                        changed_assumptions=verified["changed_assumptions"],
                        **{key: verified[key] for key in (
                            "changed_input_fields", "change_rationale", "countercase",
                            "predecessor_input_fingerprint", "successor_input_fingerprint",
                            "predecessor_valuation", "successor_valuation", "valuation_changed",
                            "research_as_of", "financial_basis", "source_bindings")},
                        scope="CONDITIONAL_CASH_RESEARCH_NOT_CURRENT_PRICE_REVIEW")
        if update["schema_version"] == "first-research-input-update-v2":
            from ..research.first_research_input_v2 import replay_first_research_input_v2
            replay = replay_first_research_input_v2
        else:
            replay = replay_first_research_input
        old = replay(root=root, receipt_binding=update["predecessor_binding"], now=now)
        new = replay(root=root, receipt_binding=update["successor_binding"], now=now)
        if (old["research_case"]["symbol"] != symbol or new["research_case"]["symbol"] != symbol
                or old["input_fingerprint"] != update["predecessor_input_fingerprint"]
                or new["input_fingerprint"] != update["successor_input_fingerprint"]
                or old["valuation"] != update["predecessor_valuation"]
                or new["valuation"] != update["successor_valuation"]):
            raise ValueError("E1 update does not match cold recompiled versions")
        successor_receipt = _bound(root, update["successor_binding"], "E1 successor receipt")
        successor_spec = _bound(root, successor_receipt["spec_binding"], "E1 successor spec")
        successor_assumptions = _bound(root, successor_spec["assumption_binding"], "E1 successor assumptions")
        if (successor_spec.get("symbol") != symbol or successor_assumptions.get("symbol") != symbol
                or successor_assumptions.get("schema_version") != "first-research-assumptions-v1"
                or successor_assumptions.get("action") != "no_order"
                or successor_assumptions.get("financial_basis") != new["research_case"]["financial_period"]):
            raise ValueError("E1 successor rationale identity invalid")
        choice = successor_assumptions.get("choice")
        if not isinstance(choice, dict):
            raise ValueError("E1 successor rationale incomplete")
        change_rationale = choice.get("rationale")
        countercase = choice.get("countercase")
        if update["schema_version"] == "first-research-input-update-v2" and (
                change_rationale != update.get("change_rationale")
                or countercase != update.get("countercase")):
            raise ValueError("E1 v2 change rationale differs from bound assumptions")
        if (not isinstance(change_rationale, str) or not change_rationale.strip()
                or not isinstance(countercase, str) or not countercase.strip()):
            raise ValueError("E1 successor rationale incomplete")
        return dict(base, status="SOURCE_BOUND_CONDITIONAL_SUCCESSOR", changed_input_fields=update["changed_input_fields"],
                    displayed_version_role=relation,
                    predecessor_input_fingerprint=old["input_fingerprint"],
                    successor_input_fingerprint=new["input_fingerprint"],
                    predecessor_valuation=old["valuation"], successor_valuation=new["valuation"],
                    valuation_changed=old["valuation"] != new["valuation"],
                    research_as_of=new["research_case"]["as_of"],
                    financial_basis=new["research_case"]["financial_period"],
                    source_bindings=new["source_bindings"],
                    change_rationale=change_rationale, countercase=countercase,
                    scope="CONDITIONAL_STRESS_RESEARCH_NOT_CURRENT_PRICE_REVIEW")
    except (ValueError, OSError, KeyError, TypeError, OverflowError, json.JSONDecodeError) as error:
        return dict(base, status="UNASSESSABLE", reason=str(error))

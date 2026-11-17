"""Link two immutable v2 E2 compilations after a real economic input change.

This records a research assumption revision, not a new filing, approval,
current-price assessment, or trade. Both inputs are independently cold replayed.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..product.common import load_json_object, require_inside, sha256_file, write_new_json
from .first_research_input_v2 import replay_first_research_input_v2

SCHEMA = "first-research-input-update-v2"


def _read(root: Path, binding: dict, label: str) -> dict:
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or not all(isinstance(binding[key], str) for key in ("path", "sha256"))):
        raise ValueError(label + " binding invalid")
    path = require_inside(root, root / binding["path"], label)
    if sha256_file(path) != binding["sha256"]:
        raise ValueError(label + " hash changed")
    return load_json_object(path, label)


def link_first_research_input_update_v2(*, root: Path, predecessor_binding: dict,
                                        successor_binding: dict, output_dir: Path,
                                        now: datetime, fact_replay=None) -> dict:
    root = root.resolve()
    if now.utcoffset() is None:
        raise ValueError("Aware successor review time required")
    output = require_inside(root / "runtime", output_dir, "first input successor")
    if output.exists():
        raise FileExistsError("First input successor output already exists")
    old_receipt = _read(root, predecessor_binding, "predecessor receipt")
    new_receipt = _read(root, successor_binding, "successor receipt")
    if (old_receipt.get("schema_version") != "first-research-input-receipt-v2"
            or new_receipt.get("schema_version") != "first-research-input-receipt-v2"
            or old_receipt.get("status") != "FIRST_INPUT_COMPILED"
            or new_receipt.get("status") != "FIRST_INPUT_COMPILED"):
        raise ValueError("E1 v2 requires two compiled v2 receipts")
    old_spec = _read(root, old_receipt["spec_binding"], "predecessor spec")
    new_spec = _read(root, new_receipt["spec_binding"], "successor spec")
    symbol = old_spec.get("symbol")
    if symbol != new_spec.get("symbol") or symbol != old_receipt.get("symbol") or symbol != new_receipt.get("symbol"):
        raise ValueError("First input successor issuer differs")
    old_pit, new_pit = old_spec["point_in_time"], new_spec["point_in_time"]
    if date.fromisoformat(new_pit["research_as_of"]) < date.fromisoformat(old_pit["research_as_of"]):
        raise ValueError("Successor research cutoff moves backward")
    old_assumptions = _read(root, old_spec["assumption_binding"], "predecessor assumptions")
    new_assumptions = _read(root, new_spec["assumption_binding"], "successor assumptions")
    def economics(payload):
        return {key: value for key, value in payload.items()
                if key not in {"generated_at", "choice"}}
    changed = [key for key in ("native_facts_binding", "assumption_binding",
                               "capital_bindings", "share_basis")
               if old_spec[key] != new_spec[key]]
    if (economics(old_assumptions) == economics(new_assumptions)
            and old_spec["native_facts_binding"]["sha256"] == new_spec["native_facts_binding"]["sha256"]
            and not any(old_spec[key] != new_spec[key] for key in ("capital_bindings", "share_basis"))):
        raise ValueError("Successor requires changed source-bound economic input")
    if not new_assumptions.get("choice", {}).get("rationale") or not new_assumptions.get("choice", {}).get("countercase"):
        raise ValueError("Successor change rationale and countercase required")
    old = replay_first_research_input_v2(root=root, receipt_binding=predecessor_binding,
                                         now=now, fact_replay=fact_replay)
    new = replay_first_research_input_v2(root=root, receipt_binding=successor_binding,
                                         now=now, fact_replay=fact_replay)
    if old["research_case"]["symbol"] != symbol or new["research_case"]["symbol"] != symbol:
        raise ValueError("Cold recompiled issuer differs")
    receipt = dict(schema_version=SCHEMA, action="no_order", symbol=symbol,
                   status="SUCCESSOR_CONDITIONAL_RESEARCH_PENDING_REVIEW",
                   predecessor_binding=dict(predecessor_binding), successor_binding=dict(successor_binding),
                   changed_input_fields=changed, change_rationale=new_assumptions["choice"]["rationale"],
                   countercase=new_assumptions["choice"]["countercase"],
                   predecessor_input_fingerprint=old["input_fingerprint"],
                   successor_input_fingerprint=new["input_fingerprint"],
                   valuation_changed=old["valuation"] != new["valuation"],
                   predecessor_valuation=old["valuation"], successor_valuation=new["valuation"],
                   formal_eligibility=False, main_range_adopted=False, price_admitted=False,
                   approvals_created=0)
    write_new_json(output / "update.json", receipt)
    return receipt

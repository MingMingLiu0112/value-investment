"""E1 successor for an existing, source-bound E2 first input.

The old first-input compiler and receipt remain immutable. This adapter only
checks the predecessor, invokes that same compiler with changed bound inputs,
and records the relationship and actual computed difference.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..product.common import load_json_object, require_inside, sha256_file, write_new_json
from .first_research_input_v1 import build_first_research_input, replay_first_research_input

SCHEMA = "first-research-input-update-v1"


def _read_bound(root: Path, binding: dict, label: str) -> dict:
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or not isinstance(binding["path"], str) or not isinstance(binding["sha256"], str)):
        raise ValueError(label + " binding invalid")
    path = require_inside(root, root / binding["path"], label)
    if sha256_file(path) != binding["sha256"]:
        raise ValueError(label + " hash changed")
    return load_json_object(path, label)


def build_first_research_input_update(*, root: Path, predecessor_binding: dict,
                                      successor_spec_binding: dict, output_dir: Path,
                                      now: datetime, fact_replay=None) -> dict:
    """Build a changed, unapproved E2 version without modifying its predecessor.

    Re-dating a spec or changing only its narrative is insufficient. At least
    one bound fact/assumption input (or capital/share mapping) must change.
    The caller still has to supply and justify the complete revised input.
    """
    root = root.resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Aware successor review time required")
    output = require_inside(root / "runtime", output_dir, "first input successor")
    if output.exists():
        raise FileExistsError("First input successor output already exists")
    predecessor_receipt = _read_bound(root, predecessor_binding, "predecessor receipt")
    if predecessor_receipt.get("status") != "FIRST_INPUT_COMPILED":
        raise ValueError("Predecessor is not a compiled first input")
    predecessor_spec = _read_bound(root, predecessor_receipt["spec_binding"], "predecessor spec")
    successor_spec = _read_bound(root, successor_spec_binding, "successor spec")
    if (predecessor_spec.get("symbol") != successor_spec.get("symbol")
            or predecessor_receipt.get("symbol") != successor_spec.get("symbol")):
        raise ValueError("First input successor issuer differs")
    old_pit = predecessor_spec.get("point_in_time") or {}
    new_pit = successor_spec.get("point_in_time") or {}
    if date.fromisoformat(new_pit["research_as_of"]) < date.fromisoformat(old_pit["research_as_of"]):
        raise ValueError("Successor research cutoff moves backward")
    changed = [key for key in ("native_facts_binding", "assumption_binding",
                               "capital_bindings", "share_basis")
               if successor_spec.get(key) != predecessor_spec.get(key)]
    # Descriptive edits, byte formatting and path relocations are not input changes.
    def assumptions(spec):
        payload = _read_bound(root, spec["assumption_binding"], "assumptions")
        return {key: value for key, value in payload.items() if key not in {"choice", "generated_at"}}

    economic_change = (
        assumptions(predecessor_spec) != assumptions(successor_spec)
        or predecessor_spec["native_facts_binding"]["sha256"]
           != successor_spec["native_facts_binding"]["sha256"]
        or any(successor_spec.get(key) != predecessor_spec.get(key)
               for key in ("capital_bindings", "share_basis"))
    )
    if not economic_change:
        raise ValueError("Successor requires changed source-bound economic input")
    old = replay_first_research_input(root=root, receipt_binding=predecessor_binding,
                                      now=now, fact_replay=fact_replay)
    new = build_first_research_input(root=root, spec_binding=successor_spec_binding,
                                     output_dir=output / "compiled", now=now,
                                     fact_replay=fact_replay)
    if new.get("status") != "FIRST_INPUT_COMPILED":
        raise ValueError("Successor did not compile")
    current = new["cold_recompile"]
    receipt = {
        "schema_version": SCHEMA, "action": "no_order", "symbol": successor_spec["symbol"],
        "status": "SUCCESSOR_CONDITIONAL_RESEARCH_PENDING_REVIEW",
        "predecessor_binding": dict(predecessor_binding),
        "successor_binding": dict(new["receipt_binding"]),
        "changed_input_fields": changed,
        "predecessor_input_fingerprint": old["input_fingerprint"],
        "successor_input_fingerprint": current["input_fingerprint"],
        "valuation_changed": old["valuation"] != current["valuation"],
        "predecessor_valuation": old["valuation"],
        "successor_valuation": current["valuation"],
        "formal_eligibility": False, "main_range_adopted": False,
        "price_admitted": False, "approvals_created": 0,
    }
    write_new_json(output / "update.json", receipt)
    return receipt

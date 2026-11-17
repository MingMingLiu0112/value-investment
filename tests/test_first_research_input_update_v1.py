"""E1 successor reuses the first-input compiler, without adopting a buy range."""
from copy import deepcopy
import json

import pytest

from test_first_research_input_v1 import NOW, first, put, run
from value_investment_agent.application.research.first_research_input_update_v1 import (
    build_first_research_input_update,
)


def _update(first, *, revise=True):
    root, spec, _, assumptions, cold, _, _ = first
    old = run(first)
    previous_bytes = (root / old["receipt_binding"]["path"]).read_bytes()
    next_spec = deepcopy(spec)
    next_spec["run_id"] = "TEST_ONLY-revised-input"
    if revise:
        changed = deepcopy(assumptions)
        changed["choice"]["rationale"] += " TEST_ONLY reviewed new capital cost."
        changed["scenarios"]["base"]["cost_of_equity"] = "0.095"
        next_spec["assumption_binding"] = put(root, "runtime/TEST_ONLY-revised-assumptions.json", changed)
    spec_binding = put(root, "runtime/TEST_ONLY-revised-spec.json", next_spec)
    return root, old, previous_bytes, spec_binding, cold


def test_changed_bound_assumption_recomputes_f1_and_preserves_old_e2(first):
    root, old, original, spec_binding, cold = _update(first)
    result = build_first_research_input_update(
        root=root, predecessor_binding=old["receipt_binding"],
        successor_spec_binding=spec_binding, output_dir=root / "runtime/successor",
        now=NOW, fact_replay=cold,
    )
    assert result["status"] == "SUCCESSOR_CONDITIONAL_RESEARCH_PENDING_REVIEW"
    assert result["changed_input_fields"] == ["assumption_binding"]
    assert result["valuation_changed"] is True
    assert result["predecessor_valuation"]["base_value"] != result["successor_valuation"]["base_value"]
    assert result["predecessor_input_fingerprint"] != result["successor_input_fingerprint"]
    assert result["formal_eligibility"] is result["main_range_adopted"] is result["price_admitted"] is False
    assert result["approvals_created"] == 0 and result["action"] == "no_order"
    assert (root / old["receipt_binding"]["path"]).read_bytes() == original
    assert (root / "runtime/successor/update.json").is_file()


def test_redate_or_rename_without_new_economic_input_is_not_an_e1_update(first):
    root, old, _, spec_binding, cold = _update(first, revise=False)
    with pytest.raises(ValueError, match="changed source-bound economic input"):
        build_first_research_input_update(
            root=root, predecessor_binding=old["receipt_binding"],
            successor_spec_binding=spec_binding, output_dir=root / "runtime/successor",
            now=NOW, fact_replay=cold,
        )
    assert not (root / "runtime/successor").exists()


def test_copying_both_bound_files_to_new_paths_does_not_create_successor(first):
    root, spec, _, assumptions, cold, _, _ = first
    old = run(first)
    duplicate = deepcopy(spec)
    native = json.loads((root / spec["native_facts_binding"]["path"]).read_text(encoding="utf-8"))
    duplicate["native_facts_binding"] = put(
        root, "runtime/TEST_ONLY-copied-facts.json", native,
    )
    duplicate["assumption_binding"] = put(
        root, "runtime/TEST_ONLY-copied-assumptions.json", assumptions,
    )
    binding = put(root, "runtime/TEST_ONLY-copied-spec.json", duplicate)
    with pytest.raises(ValueError, match="changed source-bound economic input"):
        build_first_research_input_update(
            root=root, predecessor_binding=old["receipt_binding"],
            successor_spec_binding=binding, output_dir=root / "runtime/copied",
            now=NOW, fact_replay=cold,
        )
    assert not (root / "runtime/copied").exists()


def test_changed_predecessor_or_foreign_issuer_refuses_successor(first):
    root, old, _, spec_binding, cold = _update(first)
    foreign = deepcopy(first[1])
    foreign["symbol"] = "000568"
    foreign_binding = put(root, "runtime/TEST_ONLY-foreign-spec.json", foreign)
    with pytest.raises(ValueError, match="issuer differs"):
        build_first_research_input_update(
            root=root, predecessor_binding=old["receipt_binding"],
            successor_spec_binding=foreign_binding, output_dir=root / "runtime/foreign",
            now=NOW, fact_replay=cold,
        )
    (root / old["receipt_binding"]["path"]).write_bytes(b"TEST_ONLY tampered")
    with pytest.raises(ValueError, match="hash changed"):
        build_first_research_input_update(
            root=root, predecessor_binding=old["receipt_binding"],
            successor_spec_binding=spec_binding, output_dir=root / "runtime/successor",
            now=NOW, fact_replay=cold,
        )


def test_descriptive_assumption_edit_cannot_create_successor(first):
    root, spec, _, assumptions, cold, _, _ = first
    old = run(first)
    revised = deepcopy(assumptions)
    revised["choice"]["rationale"] += " TEST_ONLY copy edit."
    candidate = deepcopy(spec)
    candidate["assumption_binding"] = put(root, "runtime/TEST_ONLY-described-assumptions.json", revised)
    binding = put(root, "runtime/TEST_ONLY-described-spec.json", candidate)
    with pytest.raises(ValueError, match="changed source-bound economic input"):
        build_first_research_input_update(
            root=root, predecessor_binding=old["receipt_binding"],
            successor_spec_binding=binding, output_dir=root / "runtime/described",
            now=NOW, fact_replay=cold,
        )
    assert not (root / "runtime/described").exists()


def test_successor_rejects_backward_research_cutoff(first):
    root, old, _, spec_binding, cold = _update(first)
    spec = json.loads((root / spec_binding["path"]).read_text(encoding="utf-8"))
    spec["point_in_time"]["research_as_of"] = "2000-01-01"
    binding = put(root, "runtime/TEST_ONLY-backdated-spec.json", spec)
    with pytest.raises(ValueError, match="cutoff moves backward"):
        build_first_research_input_update(
            root=root, predecessor_binding=old["receipt_binding"],
            successor_spec_binding=binding, output_dir=root / "runtime/backdated",
            now=NOW, fact_replay=cold,
        )
    assert not (root / "runtime/backdated").exists()

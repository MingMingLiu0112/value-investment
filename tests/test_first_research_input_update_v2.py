"""TEST_ONLY v2 E1 links real changed calculations, not revised prose."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path

import pytest

from value_investment_agent.application.research.first_research_input_v2 import build_first_research_input_v2
from value_investment_agent.application.research.first_research_input_update_v2 import (
    link_first_research_input_update_v2,
)
from value_investment_agent.application.product import first_research_update_view_v1 as public_view
from value_investment_agent.application.research import first_research_input_v2 as engine_v2

_spec = importlib.util.spec_from_file_location("e1_v2_fixture", Path(__file__).with_name("test_first_research_input_v1.py"))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


def _versions(tmp_path, *, economic_change=True):
    root, spec, _, assumptions, cold, _, save = _fixture.first.__wrapped__(tmp_path)
    old = build_first_research_input_v2(root=root, spec_binding=save(),
        output_dir=root / "runtime/old", now=_fixture.NOW, fact_replay=cold)
    revised = deepcopy(assumptions)
    revised["choice"]["rationale"] += " TEST_ONLY review of capital cost."
    if economic_change:
        revised["scenarios"]["base"]["cost_of_equity"] = "0.095"
    second_spec = deepcopy(spec)
    second_spec["run_id"] = "TEST_ONLY-v2-successor"
    second_spec["assumption_binding"] = _fixture.put(root, "runtime/revised-assumptions.json", revised)
    successor = build_first_research_input_v2(root=root,
        spec_binding=_fixture.put(root, "runtime/revised-spec.json", second_spec),
        output_dir=root / "runtime/new", now=_fixture.NOW, fact_replay=cold)
    return root, old, successor, cold


def test_v2_e1_changes_valuation_and_keeps_both_immutable(tmp_path):
    root, old, new, cold = _versions(tmp_path)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    update = link_first_research_input_update_v2(root=root,
        predecessor_binding=old["receipt_binding"], successor_binding=new["receipt_binding"],
        output_dir=root / "runtime/update", now=_fixture.NOW, fact_replay=cold)
    assert update["schema_version"] == "first-research-input-update-v2"
    assert update["valuation_changed"] is True
    assert update["predecessor_valuation"]["base_value"] != update["successor_valuation"]["base_value"]
    assert update["formal_eligibility"] is update["main_range_adopted"] is update["price_admitted"] is False
    assert update["action"] == "no_order" and update["approvals_created"] == 0
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*")
                      if p.is_file() and p != root / "runtime/update/update.json"}


def test_v2_e1_rejects_text_only_change_and_tampered_receipt(tmp_path):
    root, old, new, cold = _versions(tmp_path, economic_change=False)
    with pytest.raises(ValueError, match="changed source-bound economic input"):
        link_first_research_input_update_v2(root=root, predecessor_binding=old["receipt_binding"],
            successor_binding=new["receipt_binding"], output_dir=root / "runtime/update",
            now=_fixture.NOW, fact_replay=cold)
    assert not (root / "runtime/update").exists()
    path = root / old["receipt_binding"]["path"]
    path.write_bytes(b"TEST_ONLY tampered")
    with pytest.raises(ValueError, match="hash changed"):
        link_first_research_input_update_v2(root=root, predecessor_binding=old["receipt_binding"],
            successor_binding=new["receipt_binding"], output_dir=root / "runtime/update",
            now=_fixture.NOW, fact_replay=cold)


def test_v2_e1_registered_reader_cold_replays_both_versions(tmp_path, monkeypatch):
    root, old, new, cold = _versions(tmp_path)
    update = link_first_research_input_update_v2(root=root,
        predecessor_binding=old["receipt_binding"], successor_binding=new["receipt_binding"],
        output_dir=root / "runtime/update", now=_fixture.NOW, fact_replay=cold)
    _fixture.put(root, public_view.REGISTRY, dict(schema_version=public_view.SCHEMA,
        action="no_order", cases={"600887": {"path": "runtime/update/update.json",
        "sha256": hashlib.sha256((root / "runtime/update/update.json").read_bytes()).hexdigest()}}))
    real_replay = engine_v2.replay_first_research_input_v2
    monkeypatch.setattr(engine_v2, "replay_first_research_input_v2",
        lambda **kwargs: real_replay(**kwargs, fact_replay=cold))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    view = public_view.read_first_research_update(root=root, symbol="600887", now=_fixture.NOW,
        predecessor_binding=old["receipt_binding"])
    assert view["status"] == "SOURCE_BOUND_CONDITIONAL_SUCCESSOR", view.get("reason")
    assert view["valuation_changed"] is True and view["change_rationale"] == update["change_rationale"]
    assert view["formal_eligibility"] is view["main_range_adopted"] is view["price_admitted"] is False
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

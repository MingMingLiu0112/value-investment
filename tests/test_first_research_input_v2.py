"""TEST_ONLY v2 compiler contract with explicit v2 replay injection."""
import importlib.util
import json
from pathlib import Path

import pytest

from value_investment_agent.application.research import first_research_input_v1 as v1
from value_investment_agent.application.research import first_research_input_v2 as v2
from value_investment_agent.infrastructure.filings import first_research_fact_replay_v2 as native_v2
from value_investment_agent.application.product import first_research_input_view_v1 as public_view

_spec = importlib.util.spec_from_file_location("first_v1_test_fixture", Path(__file__).with_name("test_first_research_input_v1.py"))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


def test_v2_receipt_and_cold_replay(tmp_path):
    root, _, _, _, cold, calls, save = _fixture.first.__wrapped__(tmp_path)
    result = v2.build_first_research_input_v2(root=root, spec_binding=save(),
        output_dir=root / "runtime/v2", now=_fixture.NOW, fact_replay=cold)
    assert result["schema_version"] == v2.RECEIPT_SCHEMA == "first-research-input-receipt-v2"
    assert v1.RECEIPT_SCHEMA != v2.RECEIPT_SCHEMA
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["predecessor_package"] is None and result["approvals_created"] == 0
    assert result["cold_recompile"]["status"] == "COLD_RECOMPILED"
    assert len(calls) == 2
    assert v2._prepare is v1._prepare
    assert v2._default_fact_replay.__code__.co_names[-1] == "replay_first_research_facts"
    implementations = result["implementation_sha256"]
    assert v1.__name__ in implementations and v2.__name__ in implementations
    assert native_v2.__name__ in implementations
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    replay = v2.replay_first_research_input_v2(root=root,
        receipt_binding=result["receipt_binding"], now=_fixture.NOW, fact_replay=cold)
    assert replay["input_fingerprint"] == result["input_fingerprint"]
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        v2.build_first_research_input_v2(root=root, spec_binding=save(),
            output_dir=root / "runtime/v2", now=_fixture.NOW, fact_replay=cold)


def test_v1_receipt_rejected_before_native_replay(tmp_path):
    root, _, _, _, cold, calls, save = _fixture.first.__wrapped__(tmp_path)
    result = v1.build_first_research_input(root=root, spec_binding=save(),
        output_dir=root / "runtime/v1", now=_fixture.NOW, fact_replay=cold)
    before = len(calls)
    with pytest.raises(ValueError, match="Invalid first compilation receipt"):
        v2.replay_first_research_input_v2(root=root, receipt_binding=result["receipt_binding"],
            now=_fixture.NOW, fact_replay=cold)
    assert len(calls) == before


def test_v2_registered_public_view_replays_without_upgrading_eligibility(tmp_path, monkeypatch):
    root, _, _, _, cold, _, save = _fixture.first.__wrapped__(tmp_path)
    result = v2.build_first_research_input_v2(root=root, spec_binding=save(),
        output_dir=root / "runtime/v2", now=_fixture.NOW, fact_replay=cold)
    _fixture.put(root, public_view.REGISTRY, dict(schema_version=public_view.SCHEMA,
        action="no_order", cases={"600887": {"receipt": result["receipt_binding"]}}))
    real_replay = v2.replay_first_research_input_v2
    monkeypatch.setattr(v2, "replay_first_research_input_v2",
        lambda **kwargs: real_replay(**kwargs, fact_replay=cold))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    view = public_view.read_first_research_input(root=root, symbol="600887", now=_fixture.NOW)
    assert view["status"] == "SOURCE_BOUND_FIRST_INPUT_COMPILED", view.get("reason")
    assert view["input_fingerprint"] == result["input_fingerprint"]
    assert view["formal_eligibility"] is False and view["main_range_adopted"] is False
    assert view["action"] == "no_order" and view["current_price"] is None
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

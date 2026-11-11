"""TEST_ONLY transport and fail-closed E1 public projection."""
import json
from datetime import datetime, timezone

from value_investment_agent.application.product import first_research_update_view_v1 as view
from value_investment_agent.application.product.common import sha256_file


NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def _registered(root):
    path = root / "runtime" / "TEST_ONLY-update.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema_version": "first-research-input-update-v1", "symbol": "000568",
        "action": "no_order", "status": "SUCCESSOR_CONDITIONAL_RESEARCH_PENDING_REVIEW",
        "formal_eligibility": False, "main_range_adopted": False, "price_admitted": False,
        "predecessor_binding": {"path": "runtime/TEST_ONLY-old.json", "sha256": "a"},
        "successor_binding": {"path": "runtime/TEST_ONLY-new.json", "sha256": "b"},
        "predecessor_input_fingerprint": "old", "successor_input_fingerprint": "new",
        "predecessor_valuation": {"bear_value": 12},
        "successor_valuation": {"bear_value": 9},
        "changed_input_fields": ["assumption_binding"],
    }), encoding="utf-8")
    registry = root / view.REGISTRY
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"schema_version": view.SCHEMA, "action": "no_order",
                                    "cases": {"000568": {"path": path.relative_to(root).as_posix(),
                                                         "sha256": sha256_file(path)}}}), encoding="utf-8")
    return path


def test_e1_projection_requires_matching_cold_versions(tmp_path, monkeypatch):
    path = _registered(tmp_path)
    def replay(*, receipt_binding, **_):
        old = receipt_binding["sha256"] == "a"
        return {"research_case": {"symbol": "000568", "as_of": "2026-11-11",
                                  "financial_period": "2026-06-30"},
                "input_fingerprint": "old" if old else "new",
                "valuation": {"bear_value": 12 if old else 9}, "source_bindings": [{"path": "x"}]}
    monkeypatch.setattr(view, "replay_first_research_input", replay)
    original_bound = view._bound
    def bound(root, ref, label):
        if label == "E1 successor receipt":
            return {"spec_binding": {"path": "runtime/spec.json", "sha256": "c"}}
        if label == "E1 successor spec":
            return {"symbol": "000568", "assumption_binding": {"path": "runtime/assumptions.json", "sha256": "d"}}
        if label == "E1 successor assumptions":
            return {"schema_version": "first-research-assumptions-v1", "symbol": "000568",
                    "action": "no_order", "financial_basis": "2026-06-30",
                    "choice": {"rationale": "Q3 revenue stress hypothesis", "countercase": "Q4 recovery"}}
        return original_bound(root, ref, label)
    monkeypatch.setattr(view, "_bound", bound)
    result = view.read_first_research_update(root=tmp_path, symbol="000568", now=NOW)
    assert result["status"] == "SOURCE_BOUND_CONDITIONAL_SUCCESSOR"
    assert result["predecessor_valuation"]["bear_value"] == 12
    assert result["successor_valuation"]["bear_value"] == 9
    assert result["action"] == "no_order" and result["price_admitted"] is False
    assert result["change_rationale"] == "Q3 revenue stress hypothesis"
    path.write_text("{}", encoding="utf-8")
    refused = view.read_first_research_update(root=tmp_path, symbol="000568", now=NOW)
    assert refused["status"] == "UNASSESSABLE" and "hash changed" in refused["reason"]


def test_e1_projection_rejects_mismatched_replay(tmp_path, monkeypatch):
    _registered(tmp_path)
    monkeypatch.setattr(view, "replay_first_research_input", lambda **_: {
        "research_case": {"symbol": "000568"}, "input_fingerprint": "wrong", "valuation": {}})
    assert view.read_first_research_update(root=tmp_path, symbol="000568", now=NOW)["status"] == "UNASSESSABLE"

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



def test_e1_projection_rejects_unrelated_displayed_predecessor_before_replay(tmp_path, monkeypatch):
    _registered(tmp_path)

    def unexpected_replay(**_):
        raise AssertionError("Mismatched predecessor reached cold replay")

    monkeypatch.setattr(view, "replay_first_research_input", unexpected_replay)
    result = view.read_first_research_update(
        root=tmp_path, symbol="000568", now=NOW,
        predecessor_binding={"path": "runtime/TEST_ONLY-other.json", "sha256": "c"},
    )
    assert result["status"] == "UNASSESSABLE"
    assert "currently displayed first input" in result["reason"]
    assert result["condition_price"] is None and result["action"] == "no_order"


def test_direct_cash_update_checks_public_paths_before_replay(tmp_path, monkeypatch):
    """A valid update hash cannot make a private dependency publicly readable."""
    path = _registered(tmp_path)
    update = json.loads(path.read_text(encoding="utf-8"))
    update["schema_version"] = "direct-owner-cash-update-v1"
    update["change_binding"] = {"path": "runtime/private/reason.json", "sha256": "b" * 64}
    update["predecessor_binding"] = {"path": "runtime/private/account.json", "sha256": "a" * 64}
    path.write_text(json.dumps(update), encoding="utf-8")
    registry_path = tmp_path / view.REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["cases"]["000568"]["sha256"] = sha256_file(path)
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    from value_investment_agent.application.research import direct_owner_cash_update_v1 as direct
    def forbidden(**_):
        raise AssertionError("Private dependency reached direct cash replay")
    monkeypatch.setattr(direct, "replay_direct_owner_cash_update", forbidden)
    result = view.read_first_research_update(root=tmp_path, symbol="000568", now=NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["condition_price"] is None


def test_direct_cash_successor_is_consumed_after_real_kernel_replay(tmp_path, monkeypatch):
    from datetime import timedelta
    from test_direct_owner_cash_update_v1 import pair, build, NOW as DIRECT_NOW
    old, new, rationale, _ = pair(tmp_path, monkeypatch)
    built = build(tmp_path, old, new, rationale)
    registry_path = tmp_path / view.REGISTRY
    registry_path.parent.mkdir()
    registry_path.write_text(json.dumps({"schema_version": view.SCHEMA, "action": "no_order",
        "cases": {"600519": built["update_binding"]}}), encoding="utf-8")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
              for p in (tmp_path / "runtime").rglob("*") if p.is_file()}
    result = view.read_first_research_update(root=tmp_path, symbol="600519",
        now=DIRECT_NOW + timedelta(days=2), predecessor_binding=old["receipt_binding"])
    assert result["status"] == "SOURCE_BOUND_CONDITIONAL_SUCCESSOR", result
    assert result["predecessor_valuation"] == old["result"]["valuation"]
    assert result["successor_valuation"] == new["result"]["valuation"]
    assert result["condition_price"] is None and result["price_admitted"] is False
    assert result["change_rationale"] == "TEST_ONLY lower bear cash conversion"
    as_current = view.read_first_research_update(root=tmp_path, symbol="600519",
        now=DIRECT_NOW + timedelta(days=2), displayed_binding=new["receipt_binding"])
    assert as_current["status"] == "SOURCE_BOUND_CONDITIONAL_SUCCESSOR", as_current
    assert as_current["displayed_version_role"] == "SUCCESSOR"
    unrelated = view.read_first_research_update(root=tmp_path, symbol="600519",
        now=DIRECT_NOW + timedelta(days=2), displayed_binding={"path": "runtime/unrelated.json", "sha256": "f" * 64})
    assert unrelated["status"] == "UNASSESSABLE"
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in (tmp_path / "runtime").rglob("*") if p.is_file()}

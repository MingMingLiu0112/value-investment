"""Bound current observations propagate through immutable daily identities."""
import hashlib
import json
import pytest

from value_investment_agent.application.hotspot.current_registry import (
    REGISTRY, load_price_conditions, registry_identity,
)
from test_hotspot_current_price_case import capture, NOW


def register(root):
    case = capture(root)
    source = root / "runtime/watch.json"
    source.write_text(json.dumps({"dated_quote_observations": [{"symbol": "600519"}]}), encoding="utf-8")
    pointer = root / REGISTRY
    pointer.parent.mkdir(exist_ok=True)
    pointer.write_text(json.dumps({"schema_version": "current-price-conditions-v1", "action": "no_order",
        "watch_source_binding": {"path": "runtime/watch.json", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "watch_source_scope": "DATED_SECURITIES_OBSERVATION_NOT_INDUSTRY_ADMISSION",
        "items": [{"symbol": "600519", "company_name": "Moutai", "case_path": case["case_path"],
                   "case_sha256": case["case_sha256"]}]}), encoding="utf-8")
    return case


def test_registered_case_versions_and_raw_change_fail_closed(tmp_path):
    case = register(tmp_path)
    first = registry_identity(tmp_path)
    result = load_price_conditions(tmp_path, now=NOW, research_version="research-1")
    assert len(result["items"]) == 1
    plan = result["items"][0]["price_action_plan"]
    assert plan["decision_id"] == "hotspot-600519"
    assert plan["research_version"] == "research-1"
    assert plan["action_eligibility"] is False
    source = tmp_path / case["source_bindings"]["15m"]["path"]
    source.write_bytes(source.read_bytes() + b" ")
    assert registry_identity(tmp_path) != first
    blocked = load_price_conditions(tmp_path, now=NOW, research_version="research-1")
    assert not blocked["items"]
    assert blocked["blockers"] == ["CURRENT_PRICE_CASE_UNAVAILABLE:600519"]


def test_retained_candidate_preserves_original_plan_until_exact_deadline(tmp_path, monkeypatch):
    from datetime import datetime
    from value_investment_agent.application.hotspot.intraday_plan_observation import bind_quote_plan, evaluate_quote_plan
    register(tmp_path)
    pointer = tmp_path / REGISTRY
    registry = json.loads(pointer.read_bytes())
    original = load_price_conditions(tmp_path, now=NOW, research_version="TEST_ONLY")["items"][0]["price_action_plan"]
    retained = {**registry["items"][0], "watch_source_binding": registry["watch_source_binding"],
                "watch_source_scope": registry["watch_source_scope"]}
    registry["previous_items"] = [retained]
    registry["items"] = []
    # Isolate shortlist membership; the retained price case uses the real loader.
    monkeypatch.setattr("value_investment_agent.application.hotspot.current_registry.verify_daily_selection",
                        lambda root, report: None)
    registry["watch_source_binding"] = dict(path="runtime/empty-watch.json", sha256="")
    source = tmp_path / "runtime/empty-watch.json"
    source.write_text(json.dumps(dict(schema_version="hotspot-daily-selection-v1", rows=[{}],
        failures=[], ranking=dict(candidates=[]), candidate_pool=[], observation_list=[])), encoding="utf-8")
    registry["watch_source_binding"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    pointer.write_text(json.dumps(registry), encoding="utf-8")
    before = datetime.fromisoformat("2026-09-28T14:59:59+08:00")
    result = load_price_conditions(tmp_path, now=before, research_version="TEST_ONLY")
    assert len(result["items"]) == 1, result
    plan = result["items"][0]["price_action_plan"]
    assert plan["candidate_lifecycle"] == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
    assert plan["retained_observation_valid"] is True
    for key in ("signal_state", "opportunity_quality", "data_available_at", "expires_after_session"):
        assert plan[key] == original[key]
    binding = bind_quote_plan(plan, symbol="600519", now=before)
    deadline = datetime.fromisoformat(binding["valid_until"])
    assert evaluate_quote_plan(binding, None, previous=None, now=deadline)["plan_status"] == "STALE_OR_UNAVAILABLE"
    expired = load_price_conditions(tmp_path, now=deadline, research_version="TEST_ONLY")["items"][0]["price_action_plan"]
    assert expired["retained_observation_valid"] is False
    assert expired["signal_state"] == "STALE"
    with pytest.raises(ValueError):
        bind_quote_plan(expired, symbol="600519", now=deadline)


def test_changed_watch_source_and_escape_refused(tmp_path):
    register(tmp_path)
    (tmp_path / "runtime/watch.json").write_text("{}", encoding="utf-8")
    assert load_price_conditions(tmp_path, now=NOW, research_version="v")["status"] == "BLOCKED"
    pointer = tmp_path / REGISTRY
    content = json.loads(pointer.read_text())
    content["watch_source_binding"]["path"] = "../outside.json"
    pointer.write_text(json.dumps(content), encoding="utf-8")
    assert load_price_conditions(tmp_path, now=NOW, research_version="v")["status"] == "BLOCKED"


@pytest.mark.parametrize("fault", ["missing_watch", "invalid_watch", "missing_case", "unreadable_source"])
def test_retired_failure_keeps_current_evidence_identity(tmp_path, monkeypatch, fault):
    case = register(tmp_path)
    before = registry_identity(tmp_path)
    pointer = tmp_path / REGISTRY
    registry = json.loads(pointer.read_bytes())
    old_watch = tmp_path / "runtime/retired-watch.json"
    old_leaf = tmp_path / "runtime/retired-source.txt"
    old_leaf.write_bytes(b"retired original")
    old_watch.write_text(json.dumps({"source_bindings": [{"path": "runtime/retired-source.txt"}]}), encoding="utf-8")
    registry["previous_items"] = [dict(case_path="runtime/retired-case.json",
        watch_source_binding={"path": "runtime/retired-watch.json"})]
    (tmp_path / "runtime/retired-case.json").write_text(json.dumps({
        "source_bindings": {}, "current_reference_close": {"bundle_path": "runtime/retired-source.txt"}}), encoding="utf-8")
    pointer.write_text(json.dumps(registry), encoding="utf-8")
    if fault == "missing_watch":
        old_watch.unlink()
    elif fault == "invalid_watch":
        old_watch.write_bytes(b"invalid json")
    elif fault == "missing_case":
        (tmp_path / "runtime/retired-case.json").unlink()
    else:
        read_bytes = type(old_leaf).read_bytes

        def denied(path):
            if path == old_leaf:
                raise PermissionError("TEST_ONLY")
            return read_bytes(path)

        monkeypatch.setattr(type(old_leaf), "read_bytes", denied)
    first = registry_identity(tmp_path)
    indexed = {row["path"]: row for row in first["evidence"]}
    for row in before["evidence"]:
        assert indexed[row["path"]] == row
    assert first["error"] == "CURRENT_PRICE_REGISTRY_UNAVAILABLE"
    failed = next(row for row in first["evidence"] if "error" in row)
    if fault == "invalid_watch":
        assert indexed["runtime/retired-watch.json"]["observed_sha256"] == hashlib.sha256(b"invalid json").hexdigest()
    else:
        assert failed["observed_sha256"] is None
    source = tmp_path / case["source_bindings"]["15m"]["path"]
    source.write_bytes(source.read_bytes() + b" ")
    second = registry_identity(tmp_path)
    assert second != first
    assert second["observed_sha256"] == first["observed_sha256"]


def test_identity_refuses_escape_without_losing_other_evidence(tmp_path, monkeypatch):
    case = register(tmp_path)
    pointer = tmp_path / REGISTRY
    registry = json.loads(pointer.read_bytes())
    registry["previous_items"] = [dict(case_path="../outside.json",
        watch_source_binding={"path": "../outside-watch.json"})]
    pointer.write_text(json.dumps(registry), encoding="utf-8")
    read_bytes = type(pointer).read_bytes

    def confined(path):
        assert path.resolve().is_relative_to(tmp_path.resolve())
        return read_bytes(path)

    monkeypatch.setattr(type(pointer), "read_bytes", confined)
    identity = registry_identity(tmp_path)
    indexed = {row["path"]: row for row in identity["evidence"]}
    assert indexed["../outside.json"] == {"path": "../outside.json", "observed_sha256": None, "error": "ValueError"}
    assert indexed["../outside-watch.json"]["error"] == "ValueError"
    assert indexed[case["source_bindings"]["15m"]["path"]]["observed_sha256"]


@pytest.mark.parametrize("malformed", [[], None, 3, "bad", {"items": None}])
def test_malformed_registry_returns_blocked(tmp_path, malformed):
    (tmp_path / "config").mkdir()
    (tmp_path / REGISTRY).write_text(json.dumps(malformed), encoding="utf-8")
    assert load_price_conditions(tmp_path, now=NOW, research_version="v")["status"] == "BLOCKED"
    assert registry_identity(tmp_path)["error"] == "CURRENT_PRICE_REGISTRY_UNAVAILABLE"


@pytest.mark.parametrize("fault", ["case", "source"])
def test_retired_unavailable_candidate_does_not_block_verified_current_rows(tmp_path, fault):
    register(tmp_path)
    pointer = tmp_path / REGISTRY
    registry = json.loads(pointer.read_bytes())
    old_watch = tmp_path / "runtime/retired-watch.json"
    old_watch.write_text(json.dumps({"dated_quote_observations": [{"symbol": "000333"}]}), encoding="utf-8")
    old_source = dict(path="runtime/retired-watch.json", sha256=hashlib.sha256(old_watch.read_bytes()).hexdigest())
    registry["previous_items"] = [dict(symbol="000333", company_name="TEST_ONLY",
        case_path="runtime/retired-unavailable.json", case_sha256="0" * 64,
        watch_source_binding=old_source, watch_source_scope="HISTORICAL_ONLY")]
    pointer.write_text(json.dumps(registry), encoding="utf-8")
    if fault == "source":
        old_watch.write_bytes(b"changed")
    result = load_price_conditions(tmp_path, now=NOW, research_version="research-1")
    assert result["blockers"] == []
    assert [row["symbol"] for row in result["items"]] == ["600519"]
    assert len(result["retired_warnings"]) == 1
    assert "000333" in result["retired_warnings"][0]
    assert result["items"][0]["price_action_plan"]["formal_eligibility"] is False

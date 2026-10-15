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


def test_changed_watch_source_and_escape_refused(tmp_path):
    register(tmp_path)
    (tmp_path / "runtime/watch.json").write_text("{}", encoding="utf-8")
    assert load_price_conditions(tmp_path, now=NOW, research_version="v")["status"] == "BLOCKED"
    pointer = tmp_path / REGISTRY
    content = json.loads(pointer.read_text())
    content["watch_source_binding"]["path"] = "../outside.json"
    pointer.write_text(json.dumps(content), encoding="utf-8")
    assert load_price_conditions(tmp_path, now=NOW, research_version="v")["status"] == "BLOCKED"


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

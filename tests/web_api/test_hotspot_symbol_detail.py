from test_read_api import _fixture
from value_investment_agent.application.discovery import dual_strategy_selection
from value_investment_agent.application.hotspot import replay_read_model


def test_hotspot_sample_failure_preserves_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(dual_strategy_selection, "build_dual_strategy_selection",
        lambda **kw: {"hotspot": {"items": [{"symbol": "300059", "name": "东方财富",
            "blockers": ["OBSERVATION_ONLY"]}]}})
    client = _fixture(tmp_path)
    response = client.get("/api/v1/decisions/300059?strategy=hotspot")
    assert response.status_code == 200
    data = response.json()
    assert data["decision"]["symbol"] == "300059"
    assert data["selection_candidate"]["name"] == "东方财富"
    assert data["hotspot_sample_review"]["status"] == "UNAVAILABLE"
    assert data["action"] == "no_order"
    assert data["hotspot_sample_review"]["reason_code"] == "MISSING_SOURCE"
    assert data["selection_candidate"] == {
        "symbol": "300059", "name": "东方财富", "blockers": ["OBSERVATION_ONLY"],
        "quote_date": None, "trade_date": None,
    }
    assert "hotspot_sample_review" not in data["decision"]["selection_candidate"]


def test_hotspot_detail_passes_exact_symbol_to_projection(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(dual_strategy_selection, "build_dual_strategy_selection",
        lambda **kw: {"hotspot": {"items": [{"symbol": "600150"}]}})
    def project(**kw):
        seen.append(kw["symbol"])
        return {"status": "NOT_COVERED", "symbol": kw["symbol"], "action": "no_order"}
    monkeypatch.setattr(replay_read_model, "load_symbol_retained_replay", project)
    data = _fixture(tmp_path).get("/api/v1/decisions/600150?strategy=hotspot").json()
    assert seen == ["600150"]
    assert data["hotspot_sample_review"]["status"] == "NOT_COVERED"
    assert data["decision"]["symbol"] == "600150"


def test_actual_symbol_endpoint_bypasses_candidate_pool_and_batch_replay(monkeypatch):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.application.hotspot import retained_source_replay
    from value_investment_agent.domain.hotspot import event_replay
    import pytest
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(replay_read_model, "load_replay_summary",
        lambda **kw: pytest.fail("must not load old five-case batch"))
    monkeypatch.setattr(retained_source_replay, "build_retained_descriptive_validation",
        lambda **kw: pytest.fail("must not replay all five cases"))
    monkeypatch.setattr(dual_strategy_selection, "build_dual_strategy_selection",
        lambda **kw: pytest.fail("sample access must not fabricate or require candidates"))
    calls = []
    original = event_replay.replay_v1
    def one(bars, spec):
        calls.append(1)
        return original(bars, spec)
    monkeypatch.setattr(event_replay, "replay_v1", one)
    client = TestClient(create_app(root))
    response = client.get("/api/v1/hotspot-replay-review?symbol=300059")
    data = response.json()
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert data["status"] == "COVERED" and data["namespace"] == "ACTUAL"
    assert len(data["events"]) == 34 and len(calls) == 1
    assert "1.2倍" in data["rule_definition"]["entry"]
    assert "严格高于" in data["rule_definition"]["entry"]
    assert "严格低于" in data["rule_definition"]["invalidation"]
    assert "实际EXIT及净收益不可评" in data["rule_definition"]["exit"]
    assert data["trade_count"] is None
    not_covered = client.get("/api/v1/hotspot-replay-review?symbol=300364").json()
    assert not_covered["status"] == "NOT_COVERED" and not_covered["events"] == []
    assert len(calls) == 1
    assert client.get("/api/v1/hotspot-replay-review?symbol=bad").status_code == 422

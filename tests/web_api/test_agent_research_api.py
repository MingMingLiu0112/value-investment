"""Registered research is read-only and never grants investment authority."""
from datetime import timedelta

import pytest

from test_held_continuity_api import client_for, unlock
from test_web_agent_research import build, sha, state, write
from value_investment_agent.application.research.agent_review.web_research import REGISTRY_PATH
from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider, OpenAICompatibleChatProvider
from value_investment_agent.presentation.web_api import app as web_app


ROUTE = "/api/v1/agent-research/600519"


def registered_client(root, journal, monkeypatch, now):
    # Inject only the existing route clock; all registry/source/packet replay is real.
    register = web_app.register_agent_research_routes
    monkeypatch.setattr(web_app, "register_agent_research_routes",
        lambda api, **kwargs: register(api, clock=lambda: now, **kwargs))
    def forbidden_provider(*args, **kwargs):
        pytest.fail("Read-only research API must never call a provider")
    monkeypatch.setattr(MockLLMProvider, "complete", forbidden_provider)
    monkeypatch.setattr(OpenAICompatibleChatProvider, "complete", forbidden_provider)
    return client_for(root, journal, monkeypatch)


def assert_no_admission(result):
    assert result["action"] == "no_order"
    assert result["eligibility"] is result["admitted"] is result["decision_changed"] is False
    assert result["formal_fact_count"] == result["approval_count"] == 0


def test_agent_research_session_origin_and_missing_registry(tmp_path, monkeypatch):
    journal = tmp_path / "TEST_ONLY.jsonl"
    client, secret = client_for(tmp_path, journal, monkeypatch)
    route = "/api/v1/agent-research/600519"
    assert client.get(route).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.get(route).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    response = client.get(route)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["status"] == "NOT_CONNECTED"
    assert result["action"] == "no_order"
    assert result["eligibility"] is False
    assert result["decision_changed"] is False
    assert client.get("/api/v1/agent-research/not-a-symbol").status_code == 422
    assert not journal.exists()
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "config/current-agent-research.json").exists()


@pytest.mark.parametrize("context,offline", [(False, False), (True, False), (False, True), (True, True)])
def test_authenticated_api_replays_registered_contract_without_provider_or_writes(tmp_path, monkeypatch, context, offline):
    packet, _, workbench, original, registry, now = build(tmp_path, context=context, offline=offline)
    journal = tmp_path / "TEST_ONLY.jsonl"
    client, secret = registered_client(tmp_path, journal, monkeypatch, now)
    before = state(tmp_path)
    assert client.get(ROUTE).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.get(ROUTE).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    response = client.get(ROUTE)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["status"] == "VERIFIED", result
    assert_no_admission(result)
    assert result["scope"] == packet["scope"]
    assert result["mode"] == ("OFFLINE_REPLAY" if offline else "MOCK")
    assert result["research_as_of"] == "2026-10-08"
    assert result["generated_at"] == packet["generated_at"]
    assert result["bindings"]["packet"] == registry["cases"]["600519"]["packet"]
    assert result["bindings"]["workbench"]["sha256"] == sha(workbench)
    assert result["sources"][0]["sha256"] == sha(original)
    assert {item["role"] for item in result["findings"]} == {"FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"}
    assert all(item["status"] == "PENDING_HUMAN_REVIEW" for item in result["findings"])
    assert all("semantic_review" in item for item in result["findings"])
    if context:
        assert result["findings"][0]["source_context"]["context_assurance"] == "EXACT_SOURCE_EXCERPTS_VERIFIED"
    assert client.get(ROUTE).json() == result
    assert state(tmp_path) == before
    assert not journal.exists()


@pytest.mark.parametrize("mutation", ["packet_bytes", "source_bytes", "missing_packet", "missing_source",
    "rehashed_claim", "rehashed_context", "rehashed_approval", "rehashed_future", "workbench_substitution"])
def test_authenticated_api_tamper_fails_closed_without_provider_or_writes(tmp_path, monkeypatch, mutation):
    packet, path, workbench, original, registry, now = build(tmp_path, context=True)
    client, secret = registered_client(tmp_path, tmp_path / "TEST_ONLY.jsonl", monkeypatch, now)
    unlock(client, secret)
    assert client.get(ROUTE).json()["status"] == "VERIFIED"
    if mutation == "packet_bytes":
        path.write_text("changed packet bytes", encoding="utf-8")
    elif mutation == "source_bytes":
        original.write_text("TEST_ONLY changed original", encoding="utf-8")
    elif mutation == "missing_packet":
        path.unlink()
    elif mutation == "missing_source":
        original.unlink()
    elif mutation == "workbench_substitution":
        other = workbench.with_name("different-workbench.json")
        other.write_bytes(workbench.read_bytes())
        registry["cases"]["600519"]["workbench"]["path"] = other.relative_to(tmp_path).as_posix()
        write(tmp_path / REGISTRY_PATH, registry)
    else:
        if mutation == "rehashed_claim":
            packet["findings"][0]["claim"] = "TEST_ONLY forged economic claim"
        elif mutation == "rehashed_context":
            packet["source_context"]["excerpts"][0]["excerpt"] = "TEST_ONLY forged original excerpt"
        elif mutation == "rehashed_approval":
            packet["approval_count"] = 1
        else:
            packet["generated_at"] = (now + timedelta(seconds=1)).isoformat()
        write(path, packet)
        registry["cases"]["600519"]["packet"]["sha256"] = sha(path)
        write(tmp_path / REGISTRY_PATH, registry)
    before = state(tmp_path)
    response = client.get(ROUTE)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "REGISTERED_RESEARCH_VERIFICATION_FAILED"
    assert result["findings"] == result["sources"] == []
    assert_no_admission(result)
    assert state(tmp_path) == before
    assert not (tmp_path / "TEST_ONLY.jsonl").exists()

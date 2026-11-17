import json

from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.presentation.web_api import runtime_identity as identity


HEAD = "a" * 40


def test_publication_registry_checks_snapshot_not_git_cleanliness(tmp_path):
    import hashlib
    paths = dict(quote_bridge_pointer="config/current-quote-bridge.json",
        research_registry="config/current-company-research-registry.json",
        current_price_conditions="config/current-price-conditions.json",
        hotspot_structure_rule="config/hotspot-confirmed-structure-v1.json")
    packet = dict(packet_status="CURRENT", source_bindings_verified=True, identity_inputs={})
    (tmp_path / "config").mkdir()
    for role, relative in paths.items():
        content = b'{"action":"no_order"}'
        (tmp_path / relative).write_bytes(content)
        packet["identity_inputs"][role] = dict(path=relative,
            observed_sha256=hashlib.sha256(content).hexdigest())
    assert identity.publication_registry_status(tmp_path, packet)["status"] == "MATCHED"
    (tmp_path / paths["current_price_conditions"]).write_bytes(b'{}')
    result = identity.publication_registry_status(tmp_path, packet)
    assert result["status"] == "MISMATCH"
    assert result["mismatched_roles"] == ["current_price_conditions"]
    assert result["checked_count"] == 4


def test_publication_registry_rejects_missing_and_arbitrary_paths(tmp_path):
    assert identity.publication_registry_status(tmp_path, None)["status"] == "UNAVAILABLE"
    packet = dict(packet_status="CURRENT", source_bindings_verified=True,
        identity_inputs={"quote_bridge_pointer": dict(path="../private.json", observed_sha256="a"*64)})
    result = identity.publication_registry_status(tmp_path, packet)
    assert result["status"] == "MISMATCH"
    assert "quote_bridge_pointer" in result["mismatched_roles"]


def test_runtime_identity_reports_matching_build_and_backend(tmp_path, monkeypatch):
    module = tmp_path / "backend.py"
    module.write_text("loaded", encoding="utf-8")
    dist = tmp_path / "web/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "build-info.json").write_text(json.dumps({
        "schema_version": "web-build-identity-v1", "commit": HEAD,
        "built_at": "2026-10-16T09:05:49Z", "source_dirty": False,
    }), encoding="utf-8")
    monkeypatch.setattr(identity, "git_head", lambda root: HEAD)
    monkeypatch.setattr(identity, "source_worktree_dirty", lambda root: False)
    digest = identity.sha256(module)
    result = identity.runtime_identity(tmp_path, backend_head=HEAD,
                                       backend_module=module, backend_module_sha=digest)
    assert result["status"] == "MATCHED"
    assert result["reasons"] == []
    module.write_text("changed", encoding="utf-8")
    result = identity.runtime_identity(tmp_path, backend_head=HEAD,
                                       backend_module=module, backend_module_sha=digest)
    assert result["status"] == "MISMATCH"
    assert "BACKEND_SOURCE_CHANGED_ON_DISK" in result["reasons"]


def test_runtime_identity_rejects_stale_or_dirty_web_build(tmp_path, monkeypatch):
    module = tmp_path / "backend.py"
    module.write_text("loaded", encoding="utf-8")
    dist = tmp_path / "web/dist"
    dist.mkdir(parents=True)
    (dist / "build-info.json").write_text(json.dumps({
        "schema_version": "web-build-identity-v1", "commit": "b" * 40,
        "built_at": "2026-10-16T09:05:49Z", "source_dirty": True,
    }), encoding="utf-8")
    monkeypatch.setattr(identity, "git_head", lambda root: HEAD)
    monkeypatch.setattr(identity, "source_worktree_dirty", lambda root: False)
    result = identity.runtime_identity(tmp_path, backend_head=HEAD,
                                       backend_module=module,
                                       backend_module_sha=identity.sha256(module))
    assert result["status"] == "MISMATCH"
    assert "WEB_REBUILD_REQUIRED" in result["reasons"]


def test_runtime_identity_rejects_uncommitted_source(tmp_path, monkeypatch):
    module = tmp_path / "backend.py"
    module.write_text("loaded", encoding="utf-8")
    monkeypatch.setattr(identity, "git_head", lambda root: HEAD)
    monkeypatch.setattr(identity, "source_worktree_dirty", lambda root: True)
    result = identity.runtime_identity(tmp_path, backend_head=HEAD,
                                       backend_module=module,
                                       backend_module_sha=identity.sha256(module))
    assert "SOURCE_WORKTREE_DIRTY_OR_UNVERIFIED" in result["reasons"]


def test_runtime_identity_endpoint_is_public_but_never_a_trade_gate(tmp_path):
    response = TestClient(create_app(root=tmp_path)).get("/api/v1/runtime-identity")
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "no_order"
    assert payload["publication"]["status"] == "UNAVAILABLE"
    assert payload["status"] == "MISMATCH"

def test_data_pointer_change_keeps_code_identity_matched(tmp_path, monkeypatch):
    module = tmp_path / "backend.py"
    module.write_text("loaded", encoding="utf-8")
    dist = tmp_path / "web/dist"
    dist.mkdir(parents=True)
    (dist / "build-info.json").write_text(json.dumps({
        "schema_version": "web-build-identity-v1", "commit": HEAD,
        "built_at": "2026-10-16T09:05:49Z", "source_dirty": False,
    }), encoding="utf-8")
    monkeypatch.setattr(identity, "git_head", lambda root: HEAD)
    monkeypatch.setattr(identity, "source_worktree_dirty", lambda root: False)
    monkeypatch.setattr(identity, "config_worktree_changes", lambda root: {
        "behavior": [], "data": ["config/current-daily-public-snapshot.json"]})
    result = identity.runtime_identity(tmp_path, backend_head=HEAD,
                                       backend_module=module,
                                       backend_module_sha=identity.sha256(module))
    assert result["status"] == "MATCHED"
    assert result["config_status"] == "MATCHED"
    assert result["config_changes"]["data"] == ["config/current-daily-public-snapshot.json"]


def test_behavior_config_change_is_a_real_mismatch(tmp_path, monkeypatch):
    module = tmp_path / "backend.py"
    module.write_text("loaded", encoding="utf-8")
    dist = tmp_path / "web/dist"
    dist.mkdir(parents=True)
    (dist / "build-info.json").write_text(json.dumps({
        "schema_version": "web-build-identity-v1", "commit": HEAD,
        "built_at": "2026-10-16T09:05:49Z", "source_dirty": False,
    }), encoding="utf-8")
    monkeypatch.setattr(identity, "git_head", lambda root: HEAD)
    monkeypatch.setattr(identity, "source_worktree_dirty", lambda root: False)
    monkeypatch.setattr(identity, "config_worktree_changes", lambda root: {
        "behavior": ["config/thresholds.json"], "data": []})
    result = identity.runtime_identity(tmp_path, backend_head=HEAD,
                                       backend_module=module,
                                       backend_module_sha=identity.sha256(module))
    assert result["status"] == "MISMATCH"
    assert result["config_status"] == "DIRTY"
    assert "BEHAVIOR_CONFIG_DIRTY" in result["reasons"]


def test_data_freshness_uses_weekday_age_not_code_status():
    from datetime import date
    friday_on_saturday = identity.data_freshness(
        {"quote_trade_date": "2026-10-16"}, today=date(2026, 10, 17))
    assert friday_on_saturday["status"] == "FRESH"
    stale = identity.data_freshness(
        {"quote_trade_date": "2026-10-16"}, today=date(2026, 10, 20))
    assert stale["status"] == "STALE"
    assert stale["weekday_age"] == 2

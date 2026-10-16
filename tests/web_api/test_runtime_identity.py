import json

from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.presentation.web_api import runtime_identity as identity


HEAD = "a" * 40


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

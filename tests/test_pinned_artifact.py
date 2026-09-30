from pathlib import Path
from types import SimpleNamespace
import hashlib

import pytest

from value_investment_agent.infrastructure.evidence import pinned_artifact


def test_existing_artifact_does_not_consult_git(tmp_path, monkeypatch):
    path = tmp_path / "existing.json"
    path.write_bytes(b"retained")
    monkeypatch.setattr(pinned_artifact.subprocess, "run", lambda *a, **k: pytest.fail("git"))
    assert pinned_artifact.read_pinned_artifact_bytes(path, root=tmp_path, pins={}) == b"retained"


def test_missing_unpinned_artifact_is_not_recovered(tmp_path, monkeypatch):
    monkeypatch.setattr(pinned_artifact.subprocess, "run", lambda *a, **k: pytest.fail("git"))
    with pytest.raises(FileNotFoundError):
        pinned_artifact.read_pinned_artifact_bytes(tmp_path / "missing", root=tmp_path, pins={})


@pytest.mark.parametrize("matches", [True, False])
def test_git_recovery_requires_exact_pin(tmp_path, monkeypatch, matches):
    path = tmp_path / "retained.json"
    content = b"retained"
    def run(command, **kwargs):
        assert command == ["git", "show", "HEAD:retained.json"]
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(stdout=content)
    monkeypatch.setattr(pinned_artifact.subprocess, "run", run)
    pins = {path: hashlib.sha256(content if matches else b"changed").hexdigest()}
    if matches:
        assert pinned_artifact.read_pinned_artifact_bytes(path, root=tmp_path, pins=pins) == content
    else:
        with pytest.raises(ValueError, match="hash mismatch"):
            pinned_artifact.read_pinned_artifact_bytes(path, root=tmp_path, pins=pins)


@pytest.mark.parametrize("content,expected_type,error", [
    (b'{"action":"no_order"}', dict, None),
    (b'[]', list, None),
    (b'[]', dict, "Expected JSON object"),
    (b'{}', list, "Expected JSON array"),
    (b'{"action":"order"}', dict, "not no_order"),
])
def test_pinned_json_contract(tmp_path, content, expected_type, error):
    path = tmp_path / "packet.json"
    path.write_bytes(content)
    pins = {path: hashlib.sha256(content).hexdigest()}
    if error:
        with pytest.raises(ValueError, match=error):
            pinned_artifact.load_pinned_json(path, root=tmp_path, pins=pins, expected_type=expected_type)
    else:
        assert isinstance(pinned_artifact.load_pinned_json(
            path, root=tmp_path, pins=pins, expected_type=expected_type,
        ), expected_type)


def test_pinned_json_rejects_changed_local_bytes(tmp_path):
    path = tmp_path / "packet.json"
    path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="changed"):
        pinned_artifact.load_pinned_json(path, root=tmp_path, pins={path: "0" * 64}, expected_type=dict)

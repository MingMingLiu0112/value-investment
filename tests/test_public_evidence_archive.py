import hashlib
import json

import pytest

from value_investment_agent.infrastructure.public_evidence_archive import restore_public_archive


def package(root):
    source = root / "artifacts/current/raw.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"captured\r\nbytes\r\n")
    manifest = root / "manifest.json"
    body = dict(schema_version="tl11-p4-public-evidence-archive-v1", action="no_order", private_data=False,
                items=[dict(original_path="runtime/case/raw.txt", archive_path="artifacts/current/raw.txt",
                            sha256=hashlib.sha256(source.read_bytes()).hexdigest())])
    manifest.write_text(json.dumps(body), encoding="utf-8")
    return source, manifest, body


def test_byte_identical_isolated_restore_and_idempotent_repeat(tmp_path):
    source, manifest, _ = package(tmp_path)
    target = tmp_path / "isolated"
    result = restore_public_archive(tmp_path, manifest, target)
    assert (target / "runtime/case/raw.txt").read_bytes() == source.read_bytes()
    assert restore_public_archive(tmp_path, manifest, target) == result


def test_refuses_changed_original_and_path_escape_before_any_copy(tmp_path):
    _, manifest, body = package(tmp_path)
    target = tmp_path / "isolated"
    body["items"].append(dict(body["items"][0], original_path="../outside.txt"))
    manifest.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError):
        restore_public_archive(tmp_path, manifest, target)
    assert not target.exists()


def test_never_overwrites_different_existing_original(tmp_path):
    _, manifest, _ = package(tmp_path)
    target = tmp_path / "isolated"
    existing = target / "runtime/case/raw.txt"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"other captured history")
    with pytest.raises(ValueError):
        restore_public_archive(tmp_path, manifest, target)
    assert existing.read_bytes() == b"other captured history"

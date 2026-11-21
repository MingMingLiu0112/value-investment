import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.screening.verified_research_queue_cache_v1 import (
    VerifiedResearchQueueCache,
)


def put(root, name, raw):
    path = root / "runtime" / name
    path.write_bytes(raw)
    return {"path": f"runtime/{name}", "sha256": hashlib.sha256(raw).hexdigest()}


def test_duplicate_bindings_resolve_once_and_keep_sibling_receipts(tmp_path, monkeypatch):
    (tmp_path / "runtime").mkdir()
    original = put(tmp_path, "source.pdf", b"source")
    receipt = put(tmp_path, "receipt.json", b"{}")
    manifest = put(tmp_path, "manifest.json", json.dumps(
        [original] * 1000 + [dict(original, receipt=receipt)]).encode())
    resolve, read = Path.resolve, Path.read_bytes
    calls = {"resolve": 0, "read": 0}

    def count_resolve(path, *args, **kwargs):
        if path.name == "source.pdf":
            calls["resolve"] += 1
        return resolve(path, *args, **kwargs)

    def count_read(path):
        if path.name == "source.pdf":
            calls["read"] += 1
        return read(path)

    monkeypatch.setattr(Path, "resolve", count_resolve)
    monkeypatch.setattr(Path, "read_bytes", count_read)
    cache = VerifiedResearchQueueCache()
    cache.put(tmp_path, manifest, {"verified": True})
    assert calls == {"resolve": 1, "read": 1}
    assert cache.get(tmp_path, manifest) == {"verified": True}
    assert calls == {"resolve": 2, "read": 2}
    (tmp_path / receipt["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="CACHE.*HASH_CHANGED"):
        cache.get(tmp_path, manifest)
    assert cache.get(tmp_path, manifest) is None


@pytest.mark.parametrize("issue", ["conflicting_hash", "outside_runtime", "missing_file"])
def test_incomplete_closure_is_not_cached(tmp_path, issue):
    (tmp_path / "runtime").mkdir()
    original = put(tmp_path, "original.pdf", b"source")
    invalid = {
        "conflicting_hash": dict(original, sha256="0" * 64),
        "outside_runtime": dict(original, path="runtime/../original.pdf"),
        "missing_file": dict(original, path="runtime/missing.pdf"),
    }[issue]
    manifest = put(tmp_path, "manifest.json", json.dumps([original, invalid]).encode())
    cache = VerifiedResearchQueueCache()
    with pytest.raises((OSError, ValueError)):
        cache.put(tmp_path, manifest, {})
    assert cache.get(tmp_path, manifest) is None

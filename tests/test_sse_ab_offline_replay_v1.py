from hashlib import sha256
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.diagnostics.replay_sse_ab_offline_v1 import bound_bytes, stage_tree


def test_stages_only_hash_bound_public_sse_inputs(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    path = source / "runtime/sse-main-screening/run/public.json"
    path.parent.mkdir(parents=True)
    raw = b'{"status":"public"}'
    path.write_bytes(raw)
    binding = {"path": "runtime/sse-main-screening/run/public.json", "sha256": sha256(raw).hexdigest()}
    staged = {}
    stage_tree(source, target, {"inputs": [binding]}, staged)
    assert (target / binding["path"]).read_bytes() == raw
    assert staged == {binding["path"]: binding["sha256"]}
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SOURCE_HASH_MISMATCH"):
        bound_bytes(source, binding)


def test_rejects_escape_and_conflicting_existing_stage(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    with pytest.raises(ValueError, match="PUBLIC_SSE_RUNTIME_PATH_REQUIRED"):
        bound_bytes(source, {"path": "../private.json", "sha256": "a" * 64})
    path = source / "runtime/sse-main-screening/run/public.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{}")
    binding = {"path": "runtime/sse-main-screening/run/public.json", "sha256": sha256(b"{}").hexdigest()}
    staged = target / binding["path"]
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"old")
    with pytest.raises(ValueError, match="STAGED_SOURCE_CONFLICT"):
        stage_tree(source, target, binding, {})

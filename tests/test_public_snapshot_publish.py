"""TL10-RC: the published daily snapshot is immutable, idempotent, fail-closed.

The daily CLI writes one versioned packet artifact and atomically repoints the
current snapshot; these tests drive that contract against a tmp project tree,
covering exit codes 0/2/3/4 and the named failure reasons the Web read surface
depends on.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_daily_public_packet_identity import build_verified_tree, _write_json

from value_investment_agent.application.product.daily_public_packet import (
    build_daily_public_packet,
)
from value_investment_agent.application.product.public_snapshot import (
    SNAPSHOT_RECEIPT_DIR,
    load_current_packet,
    pointer_path,
    publish_snapshot,
    snapshot_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
CLI_SOURCE = ROOT / "scripts/current/build_daily_public_packet.py"
SNAPSHOT_RUNTIME_DIR = "runtime/daily-public-packet"
NOW = datetime(2026, 10, 13, 4, 0, tzinfo=timezone.utc)
STAMP = "2026-10-13T04:00:00+00:00"


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the shipped CLI against ``root`` from a byte-identical copy.

    The script derives its project root from its own location, so the copy
    lives inside the tmp tree while the package still resolves from this
    checkout through PYTHONPATH.
    """
    script = root / "scripts/current/build_daily_public_packet.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(CLI_SOURCE.read_bytes())
    env = dict(os.environ)
    parts = [str(ROOT / "src"), str(ROOT)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-B", str(script), *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        timeout=300, env=env)


def _report(completed: subprocess.CompletedProcess) -> dict:
    assert completed.stdout.strip(), completed.stderr
    return json.loads(completed.stdout)


def _publish_fixture(root: Path) -> tuple[dict, Path]:
    packet = build_daily_public_packet(root, generated_at=NOW)
    assert packet["packet_status"] == "CURRENT", packet.get("chain_error")
    artifact = root / SNAPSHOT_RUNTIME_DIR / f"daily-public-packet-{packet['publication_id']}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes((json.dumps(packet, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    publish_snapshot(root, packet, artifact)
    return packet, artifact


def test_registry_change_writes_a_new_artifact_on_the_next_cli_run(tmp_path):
    root = build_verified_tree(tmp_path)
    first = _run_cli(root, "--generated-at", STAMP)
    assert first.returncode == 0, first.stderr
    report1 = _report(first)
    assert report1["status"] == "WRITTEN"
    evidence = _write_json(root, "docs/current/tl10-registry-evidence.json", {"receipt": "v1"})
    _write_json(root, "config/current-company-research-registry.json", {
        "schema_version": "current-company-research-registry-v1", "action": "no_order",
        "companies": {"600741": {
            "name": "华域汽车", "status": "PENDING_RESEARCH", "valuation_route": "fcff",
            "summary": "已登记待研究", "missing_inputs": ["估值输入未注册"],
            "required_actor": "ENGINEERING", "next_step": "补齐输入后再评估",
            "evidence": [evidence]}}})
    second = _run_cli(root, "--generated-at", STAMP)
    assert second.returncode == 0, second.stderr
    report2 = _report(second)
    assert report2["status"] == "WRITTEN"
    assert report2["publication_id"] != report1["publication_id"]
    output = root / "runtime/daily-public-packet"
    assert (output / f"daily-public-packet-{report1['publication_id']}.json").is_file()
    assert (output / f"daily-public-packet-{report2['publication_id']}.json").is_file()
    assert report2["snapshot"]["status"] == "VERIFIED"
    pointer = json.loads(pointer_path(root).read_text(encoding="utf-8"))
    assert pointer["publication_id"] == report2["publication_id"]


def test_identical_inputs_report_unchanged_and_rewrite_nothing(tmp_path):
    root = build_verified_tree(tmp_path)
    first = _run_cli(root, "--generated-at", STAMP)
    assert first.returncode == 0, first.stderr
    report1 = _report(first)
    artifact = root / report1["path"]
    before = artifact.read_bytes()
    second = _run_cli(root, "--generated-at", STAMP)
    assert second.returncode == 0, second.stderr
    report2 = _report(second)
    assert report2["status"] == "UNCHANGED"
    assert report2["publication_id"] == report1["publication_id"]
    assert report2["sha256"] == report1["sha256"]
    assert artifact.read_bytes() == before
    loaded, error = load_current_packet(root)
    assert error is None
    assert loaded["publication_id"] == report1["publication_id"]


def test_corrupted_existing_artifact_exits_three_without_overwrite(tmp_path):
    root = build_verified_tree(tmp_path)
    first = _run_cli(root, "--generated-at", STAMP)
    assert first.returncode == 0, first.stderr
    report1 = _report(first)
    artifact = root / report1["path"]
    pointer_before = pointer_path(root).read_bytes()
    artifact.write_bytes(b"\x00broken")
    poisoned = artifact.read_bytes()
    second = _run_cli(root, "--generated-at", STAMP)
    assert second.returncode == 3, (second.returncode, second.stdout, second.stderr)
    report2 = _report(second)
    assert report2["status"] == "REFUSED_EXISTING_UNREADABLE"
    assert artifact.read_bytes() == poisoned
    assert pointer_path(root).read_bytes() == pointer_before


def test_same_identity_with_different_content_exits_four_and_keeps_pointer(tmp_path):
    root = build_verified_tree(tmp_path)
    first = _run_cli(root, "--generated-at", STAMP)
    assert first.returncode == 0, first.stderr
    report1 = _report(first)
    artifact = root / report1["path"]
    pointer_before = pointer_path(root).read_bytes()
    # A stored record whose identity matches but whose content does not (an
    # edited artifact, or an engine regression) must never be reused: the
    # guard refuses it, records the conflict and leaves the pointer alone.
    # Input drift is handled earlier now that identity v4 covers the bound
    # explanation files (see test_bound_explanation_content_mints_a_new_identity).
    stored = json.loads(artifact.read_text(encoding="utf-8"))
    stored["blockers"] = [*stored["blockers"], "TAMPERED_FOR_TL10_TEST"]
    stored["content_sha256"] = "0" * 64
    artifact.write_text(json.dumps(stored, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    tampered = artifact.read_bytes()
    second = _run_cli(root, "--generated-at", STAMP)
    assert second.returncode == 4, (second.returncode, second.stdout, second.stderr)
    report2 = _report(second)
    assert report2["status"] == "REFUSED_IDENTITY_CONFLICT"
    assert report2["publication_id"] == report1["publication_id"]
    conflict = root / report2["conflict_receipt"]
    assert conflict.is_file()
    conflict_doc = json.loads(conflict.read_text(encoding="utf-8"))
    assert conflict_doc["status"] == "IDENTITY_CONFLICT"
    assert conflict_doc["stored_content_sha256"] == "0" * 64
    assert conflict_doc["recomputed_content_sha256"] == report1["content_sha256"]
    assert pointer_path(root).read_bytes() == pointer_before
    assert artifact.read_bytes() == tampered


def test_chain_unavailable_exits_two_and_preserves_the_pointer(tmp_path):
    root = build_verified_tree(tmp_path)
    first = _run_cli(root, "--generated-at", STAMP)
    assert first.returncode == 0, first.stderr
    pointer_before = pointer_path(root).read_bytes()
    (root / "runtime/publication.json").write_text("{broken", encoding="utf-8")
    second = _run_cli(root, "--generated-at", STAMP)
    assert second.returncode == 2, (second.returncode, second.stdout, second.stderr)
    report2 = _report(second)
    assert report2["status"] == "BLOCKED_CHAIN_UNAVAILABLE"
    assert report2["publication_id"] is None
    assert report2.get("chain_error")
    assert report2.get("snapshot") is None
    assert pointer_path(root).read_bytes() == pointer_before


def test_load_current_packet_fails_closed_with_named_reasons(tmp_path):
    root = build_verified_tree(tmp_path)
    packet, artifact = _publish_fixture(root)
    pointer = pointer_path(root)
    pointer_bytes = pointer.read_bytes()
    artifact_bytes = artifact.read_bytes()
    pointer_doc = json.loads(pointer_bytes)

    loaded, error = load_current_packet(root)
    assert error is None
    assert loaded["publication_id"] == packet["publication_id"]

    def reset() -> None:
        pointer.write_bytes(pointer_bytes)
        artifact.write_bytes(artifact_bytes)

    pointer.unlink()
    assert load_current_packet(root) == (None, "SNAPSHOT_POINTER_MISSING")

    reset()
    pointer.write_text(json.dumps({**pointer_doc, "schema_version": "other"}), encoding="utf-8")
    assert load_current_packet(root) == (None, "SNAPSHOT_POINTER_INVALID")

    reset()
    artifact.unlink()
    assert load_current_packet(root) == (None, "SNAPSHOT_ARTIFACT_MISSING")

    reset()
    artifact.write_bytes(artifact_bytes + b" ")
    assert load_current_packet(root) == (None, "SNAPSHOT_ARTIFACT_HASH_MISMATCH")

    reset()
    garbage = b"{not json"
    artifact.write_bytes(garbage)
    pointer.write_text(json.dumps({**pointer_doc,
                                   "packet_sha256": hashlib.sha256(garbage).hexdigest()}),
                       encoding="utf-8")
    assert load_current_packet(root) == (None, "SNAPSHOT_ARTIFACT_UNREADABLE")

    reset()
    tampered = json.loads(artifact_bytes.decode("utf-8"))
    tampered["blockers"] = [*tampered["blockers"], "TL10_TAMPERED"]
    tampered_bytes = json.dumps(tampered, ensure_ascii=False).encode("utf-8")
    artifact.write_bytes(tampered_bytes)
    pointer.write_text(json.dumps({**pointer_doc,
                                   "packet_sha256": hashlib.sha256(tampered_bytes).hexdigest()}),
                       encoding="utf-8")
    # The artifact hash was refreshed but the stored decision digest no longer
    # matches the decision content: the snapshot must refuse to serve it.
    assert load_current_packet(root) == (None, "SNAPSHOT_CONTENT_TAMPERED")

    reset()
    pointer.write_text(json.dumps({**pointer_doc, "publication_id": "pub-other"}),
                       encoding="utf-8")
    assert load_current_packet(root) == (None, "SNAPSHOT_IDENTITY_MISMATCH")

    reset()
    metadata = snapshot_metadata(root)
    assert metadata["status"] == "VERIFIED"
    assert metadata["publication_id"] == packet["publication_id"]


def test_publish_snapshot_is_idempotent_and_rejects_digest_mismatch(tmp_path):
    root = build_verified_tree(tmp_path)
    packet, artifact = _publish_fixture(root)
    pointer = json.loads(pointer_path(root).read_text(encoding="utf-8"))
    receipt_path = root / pointer["receipt_path"]
    receipt_bytes = receipt_path.read_bytes()
    second = publish_snapshot(root, packet, artifact)
    assert second["publication_id"] == packet["publication_id"]
    assert receipt_path.read_bytes() == receipt_bytes
    receipts = sorted((root / SNAPSHOT_RECEIPT_DIR).glob("*.json"))
    assert len(receipts) == 1
    loaded, error = load_current_packet(root)
    assert error is None
    assert loaded["publication_id"] == packet["publication_id"]
    tampered = dict(packet, blockers=[*packet["blockers"], "TL10_TAMPER"])
    with pytest.raises(ValueError):
        publish_snapshot(root, tampered, artifact)

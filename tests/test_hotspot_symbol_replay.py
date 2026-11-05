"""Actual retained bytes, isolated corruption checks; no synthetic success samples."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import pytest
from value_investment_agent.application.hotspot import replay_read_model as model
from value_investment_agent.domain.hotspot import event_replay

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


@pytest.fixture
def archive(tmp_path):
    # Preserve the archive's exact nested paths on Windows as well as Linux.
    if os.name == "nt":
        tmp_path = Path("\\\\?\\" + str(tmp_path))
    pins = json.loads((ROOT / model.REVIEW_POINTER).read_bytes())
    ref = pins["retained_manifest_binding"]
    folder = Path(ref["path"]).parent
    shutil.copytree(ROOT / folder, tmp_path / folder)
    pointer = tmp_path / model.REVIEW_POINTER
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps(pins), encoding="utf-8")
    return tmp_path, pins, json.loads((tmp_path / ref["path"]).read_bytes())


def test_real_symbol_only_replays_one_case_and_returns_full_events(archive, monkeypatch):
    root, _, _ = archive
    calls = []
    real = event_replay.replay_v1
    def counted(bars, spec):
        calls.append(bars)
        return real(bars, spec)
    monkeypatch.setattr(event_replay, "replay_v1", counted)
    result = model.load_symbol_retained_replay(root=root, symbol="300059", now=NOW)
    assert result["status"] == "COVERED"
    assert result["namespace"] == "ACTUAL"
    assert len(calls) == 1
    assert len(result["events"]) == 34
    assert sum(e["outcome"]["right_censored"] for e in result["events"]) == 2
    assert result["partitions"]["end_date"] == "2026-10-15"
    assert result["rule_version"] == "hotspot-prior-five-completed-bars-v1"
    assert all(e["outcome"]["execution"]["net_trade_return_pct"] is None for e in result["events"])
    assert result["trade_count"] is None and result["formal_eligibility"] is False
    assert result["source_bindings"]["60m"]["source_url"].startswith("https://quotes.sina.cn/")
    assert result["case_binding"]["sha256"] == "f5a1c3a6021896c073c014b064114713e5dbd397df185c4a86b874fc6b00437e"
    assert result["execution_unassessable_reasons"]


def test_not_covered_does_not_replay_or_borrow_old_five(archive, monkeypatch):
    monkeypatch.setattr(event_replay, "replay_v1", lambda *a: pytest.fail("must not replay"))
    result = model.load_symbol_retained_replay(root=archive[0], symbol="300364", now=NOW)
    assert result["status"] == "NOT_COVERED"
    assert result["events"] == []


def test_other_symbol_corruption_does_not_block_selected_case(archive):
    root, _, manifest = archive
    ref = next(r["retained_binding"] for r in manifest["files"]
               if "601318-" in r["original_binding"]["path"])
    (root / ref["path"]).write_bytes(b"broken")
    assert model.load_symbol_retained_replay(root=root, symbol="300059", now=NOW)["status"] == "COVERED"
    assert model.load_symbol_retained_replay(root=root, symbol="601318", now=NOW)["status"] == "UNAVAILABLE"


def test_tamper_after_success_is_not_served_from_stale_cache(archive):
    root, _, manifest = archive
    assert model.load_symbol_retained_replay(root=root, symbol="300059", now=NOW)["status"] == "COVERED"
    ref = next(r["retained_binding"] for r in manifest["files"]
               if "300059-" in r["original_binding"]["path"] and r["original_binding"]["path"].endswith("case.json"))
    (root / ref["path"]).write_bytes(b"broken")
    result = model.load_symbol_retained_replay(root=root, symbol="300059", now=NOW)
    assert result["status"] == "UNAVAILABLE" and result["events"] == []
    assert result["reason_code"] == "HASH_MISMATCH"
    assert str(root) not in json.dumps(result)
    assert "case.json" not in result["reason"]


def test_test_only_manifest_rejected_even_with_updated_pin(archive):
    root, pins, manifest = archive
    manifest["namespace"] = "TEST_ONLY"
    raw = json.dumps(manifest).encode()
    ref = pins["retained_manifest_binding"]
    (root / ref["path"]).write_bytes(raw)
    ref["sha256"] = sha256(raw).hexdigest()
    (root / model.REVIEW_POINTER).write_text(json.dumps(pins), encoding="utf-8")
    assert model.load_symbol_retained_replay(root=root, symbol="300059", now=NOW)["status"] == "UNAVAILABLE"


def test_missing_source_and_future_clock_fail_closed(archive):
    assert model.load_symbol_retained_replay(root=archive[0], symbol="300059",
        now=datetime(2026, 10, 1, tzinfo=timezone.utc))["status"] == "UNAVAILABLE"
    (archive[0] / model.REVIEW_POINTER).unlink()
    assert model.load_symbol_retained_replay(root=archive[0], symbol="300059", now=NOW)["status"] == "UNAVAILABLE"


@pytest.mark.parametrize(("error", "code"), [
    (FileNotFoundError("D:/private/user/source.json"), "MISSING_SOURCE"),
    (PermissionError("D:/private/user/source.json"), "SOURCE_READ_FAILED"),
    (ValueError("Replay source hash mismatch: D:/private/user/source.json"), "HASH_MISMATCH"),
    (ValueError("Running rule differs from historical protocol"), "RULE_MISMATCH"),
    (ValueError("Replay pointer changed"), "BINDING_CHANGED"),
    (ValueError("Retained evidence is not yet available"), "CLOCK_INVALID"),
    (ValueError("TEST_ONLY evidence cannot enter ACTUAL retained replay"), "NON_ACTUAL_EVIDENCE"),
    (ValueError("invalid protocol: D:/private/user/source.json"), "PROTOCOL_INVALID"),
])
def test_structured_failure_never_publishes_exception_paths(error, code):
    actual, text = model._symbol_replay_failure(error)
    assert actual == code
    assert "D:" not in text and "private" not in text and "source.json" not in text


@pytest.mark.parametrize(("damage", "code"), [
    ("missing", "MISSING_SOURCE"), ("protocol", "PROTOCOL_INVALID"), ("clock", "CLOCK_INVALID"),
])
def test_unavailable_retains_reason_code_without_another_symbol(archive, damage, code):
    root, pins, manifest = archive
    if damage == "missing":
        ref = next(r["retained_binding"] for r in manifest["files"]
                   if "300059-" in r["original_binding"]["path"])
        (root / ref["path"]).unlink()
    else:
        if damage == "protocol":
            manifest["scope"] = "INVALID"
        else:
            manifest["retained_at"] = "2099-01-01T00:00:00+00:00"
        raw = json.dumps(manifest).encode()
        ref = pins["retained_manifest_binding"]
        (root / ref["path"]).write_bytes(raw)
        ref["sha256"] = sha256(raw).hexdigest()
        (root / model.REVIEW_POINTER).write_text(json.dumps(pins), encoding="utf-8")
    result = model.load_symbol_retained_replay(root=root, symbol="300059", now=NOW)
    assert result["status"] == "UNAVAILABLE"
    assert result["reason_code"] == code
    assert result["symbol"] == "300059" and result["events"] == []
    assert "601318" not in json.dumps(result)
    assert str(root) not in json.dumps(result)

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.current.publish_product_workbench_to_canonical import (
    _load_m5_event_projection,
    _load_prospective_observation_ledger,
    _observation_ledger_binding_status,
    _require_monotonic_quote_session,
)


def test_projection_loader_requires_runtime_path_and_exact_hash(tmp_path):
    root = tmp_path / "repo"
    path = root / "runtime" / "projection.json"
    path.parent.mkdir(parents=True)
    payload = {"action": "no_order", "report": {}, "projection": {"action": "no_order", "events": []}}
    encoded = json.dumps(payload).encode("utf-8")
    path.write_bytes(encoded)

    result, digest = _load_m5_event_projection(root, path, hashlib.sha256(encoded).hexdigest())

    assert result == payload["projection"]
    assert digest == hashlib.sha256(encoded).hexdigest()


def test_registered_projection_loader_binds_announcement_date_as_cutoff(tmp_path):
    root = tmp_path / "repo"
    path = root / "runtime" / "projection.json"
    path.parent.mkdir(parents=True)
    payload = {
        "action": "no_order",
        "report": {
            "schema_version": "registered-public-event-projection-v3",
            "appended_observation": {"announcement_date": "2026-09-28"},
        },
        "projection": {"action": "no_order", "events": [], "audit_evidence": [], "audit_decisions": []},
    }
    encoded = json.dumps(payload).encode("utf-8")
    path.write_bytes(encoded)

    result, _ = _load_m5_event_projection(root, path, hashlib.sha256(encoded).hexdigest())

    assert result["evaluation_cutoff_date"] == "2026-09-28"


def test_asof_successor_loader_binds_explicit_product_cutoff(tmp_path):
    root = tmp_path / "repo"
    path = root / "runtime" / "projection.json"
    path.parent.mkdir(parents=True)
    payload = {
        "action": "no_order",
        "report": {
            "schema_version": "registered-public-event-projection-v4",
            "public_event_observation_as_of": "2026-09-28",
        },
        "projection": {"action": "no_order", "events": [], "audit_evidence": [], "audit_decisions": []},
    }
    encoded = json.dumps(payload).encode("utf-8")
    path.write_bytes(encoded)

    result, _ = _load_m5_event_projection(root, path, hashlib.sha256(encoded).hexdigest())

    assert result["evaluation_cutoff_date"] == "2026-09-28"


def test_projection_loader_rejects_hash_mismatch_and_outside_runtime(tmp_path):
    root = tmp_path / "repo"
    path = root / "runtime" / "projection.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"action":"no_order"}', encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _load_m5_event_projection(root, path, "0" * 64)
    with pytest.raises(ValueError, match="under runtime"):
        _load_m5_event_projection(root, path.parent / ".." / ".." / "projection.json", "0" * 64)


def test_projection_loader_rejects_missing_hash_or_non_no_order(tmp_path):
    root = tmp_path / "repo"
    path = root / "runtime" / "projection.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"action":"submit_order"}', encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="supplied together"):
        _load_m5_event_projection(root, path, None)
    with pytest.raises(ValueError, match="no_order"):
        _load_m5_event_projection(root, path, digest)


def test_observation_ledger_loader_binds_all_three_inputs(tmp_path):
    root = tmp_path / "repo"
    path = root / "config" / "ledger.json"
    path.parent.mkdir(parents=True)
    encoded = json.dumps({
        "schema_version": "prospective-observation-ledger-v1",
        "action": "no_order",
        "records": [],
    }).encode("utf-8")
    path.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()

    rows, returned_digest, cutoff = _load_prospective_observation_ledger(
        root, Path("config/ledger.json"), digest, "2026-09-28T00:00:00+08:00"
    )

    assert rows == ()
    assert returned_digest == digest
    assert cutoff == "2026-09-28T00:00:00+08:00"


def test_observation_ledger_loader_requires_complete_binding(tmp_path):
    root = tmp_path / "repo"
    with pytest.raises(ValueError, match="supplied together"):
        _load_prospective_observation_ledger(
            root, Path("config/ledger.json"), None, "2026-09-28T00:00:00+08:00"
        )


def test_observation_binding_status_distinguishes_unbound_from_empty_bound_ledger():
    assert _observation_ledger_binding_status(None) == "NOT_BOUND"
    assert _observation_ledger_binding_status("a" * 64) == "BOUND"


def _write_current_quote_state(tmp_path, *, pointer_as_of="2026-09-24", receipt_as_of="2026-09-24"):
    config = tmp_path / "config"
    receipts = tmp_path / "runtime" / "publication-receipts"
    config.mkdir()
    receipts.mkdir(parents=True)
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"canonical-workbook")
    canonical_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    receipt_path = receipts / "canonical-m7-product-publication-current.json"
    receipt = {
        "schema_version": "canonical-product-publication-v1",
        "status": "PUBLISHED_PENDING_WPS_VISUAL_REVIEW",
        "canonical_file_after_sha256": canonical_sha256,
    }
    if receipt_as_of is not None:
        receipt["daily_quote_binding"] = {"as_of": receipt_as_of}
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    pointer = {
        "quote_as_of": pointer_as_of,
        "canonical_workbook_sha256": canonical_sha256,
        "publication_receipt": "runtime/publication-receipts/canonical-m7-product-publication-current.json",
    }
    (config / "current-trial-workbook.json").write_text(json.dumps(pointer), encoding="utf-8")
    return canonical_sha256


def test_publisher_rejects_quote_session_regression(tmp_path):
    canonical_sha256 = _write_current_quote_state(tmp_path)

    with pytest.raises(ValueError, match="DAILY_QUOTE_SESSION_REGRESSION"):
        _require_monotonic_quote_session(tmp_path, "2026-09-23", canonical_sha256)

    _require_monotonic_quote_session(tmp_path, "2026-09-24", canonical_sha256)


def test_publisher_uses_latest_successful_receipt_when_config_pointer_lags(tmp_path):
    canonical_sha256 = _write_current_quote_state(tmp_path)
    receipts = tmp_path / "runtime" / "publication-receipts"
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"newer-canonical-workbook")
    canonical_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    (receipts / "canonical-m7-product-publication-20260928T010000Z.json").write_text(
        json.dumps({
            "schema_version": "canonical-product-publication-v1",
            "status": "PUBLISHED_PENDING_WPS_VISUAL_REVIEW",
            "canonical_file_after_sha256": canonical_sha256,
            "daily_quote_binding": {"as_of": "2026-09-25"},
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="DAILY_QUOTE_SESSION_REGRESSION"):
        _require_monotonic_quote_session(tmp_path, "2026-09-24", canonical_sha256)

    _require_monotonic_quote_session(tmp_path, "2026-09-25", canonical_sha256)
    _require_monotonic_quote_session(tmp_path, "2026-09-26", canonical_sha256)


def test_publisher_keeps_referenced_receipt_date_as_floor_when_pointer_hash_is_stale(tmp_path):
    _write_current_quote_state(tmp_path, pointer_as_of="2026-09-24", receipt_as_of="2026-09-25")
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"different-canonical-workbook")
    canonical_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    current_receipt = {
        "schema_version": "canonical-product-publication-v1",
        "status": "PUBLISHED_PENDING_WPS_VISUAL_REVIEW",
        "canonical_file_after_sha256": canonical_sha256,
        "daily_quote_binding": {"as_of": "2026-09-24"},
    }
    receipt_path = (
        tmp_path / "runtime" / "publication-receipts"
        / "canonical-m7-product-publication-current-canonical.json"
    )
    receipt_path.write_text(json.dumps(current_receipt), encoding="utf-8")

    with pytest.raises(ValueError, match="DAILY_QUOTE_SESSION_REGRESSION"):
        _require_monotonic_quote_session(tmp_path, "2026-09-24", canonical_sha256)

    _require_monotonic_quote_session(tmp_path, "2026-09-25", canonical_sha256)


def test_publisher_ignores_legacy_receipt_without_quote_binding(tmp_path):
    canonical_sha256 = _write_current_quote_state(tmp_path, receipt_as_of=None)

    _require_monotonic_quote_session(tmp_path, "2026-09-24", canonical_sha256)


def test_publisher_fails_closed_on_invalid_bound_publication_receipt(tmp_path):
    canonical_sha256 = _write_current_quote_state(tmp_path)
    receipt_path = tmp_path / "runtime" / "publication-receipts" / "canonical-m7-product-publication-current.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["daily_quote_binding"]["as_of"] = "not-a-date"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(ValueError, match="CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID"):
        _require_monotonic_quote_session(tmp_path, "2026-09-25", canonical_sha256)


def test_publisher_fails_closed_when_pointer_receipt_is_missing_or_mismatched(tmp_path):
    canonical_sha256 = _write_current_quote_state(tmp_path)
    pointer_path = tmp_path / "config" / "current-trial-workbook.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["publication_receipt"] = "runtime/publication-receipts/missing.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(ValueError, match="CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID"):
        _require_monotonic_quote_session(tmp_path, "2026-09-25", canonical_sha256)

    pointer["publication_receipt"] = "runtime/publication-receipts/canonical-m7-product-publication-current.json"
    pointer["canonical_workbook_sha256"] = "f" * 64
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(ValueError, match="CANONICAL_QUOTE_PUBLICATION_RECEIPT_INVALID"):
        _require_monotonic_quote_session(tmp_path, "2026-09-25", canonical_sha256)


def test_publisher_uses_hash_bound_recovery_receipt_as_quote_floor(tmp_path):
    _write_current_quote_state(tmp_path)
    canonical = tmp_path / "canonical.xlsx"
    canonical.write_bytes(b"recovered-canonical-workbook")
    canonical_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    recovery = {
        "schema_version": "canonical-product-publication-recovery-v1",
        "status": "PUBLISHED_RESULT_RECOVERED_FROM_CAPTURED_OUTPUT",
        "canonical_file_after_sha256": canonical_sha256,
        "quote_as_of": "2026-09-25",
    }
    recovery_path = (
        tmp_path / "runtime" / "publication-receipts"
        / "canonical-m7-product-publication-recovery.json"
    )
    recovery_path.write_text(json.dumps(recovery), encoding="utf-8")

    with pytest.raises(ValueError, match="DAILY_QUOTE_SESSION_REGRESSION"):
        _require_monotonic_quote_session(tmp_path, "2026-09-24", canonical_sha256)

    _require_monotonic_quote_session(tmp_path, "2026-09-25", canonical_sha256)

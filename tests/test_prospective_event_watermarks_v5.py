from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "config/prospective-public-event-watermarks-v4.json"
CURRENT = ROOT / "config/prospective-public-event-watermarks-v5.json"
MIDEA_SCAN = ROOT / "runtime/prospective-public-event-20260927/gapfill-000333-20260927T172744007289Z"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, str) and "T" in value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).isoformat()
    return value


def test_v5_is_append_only_and_does_not_advance_incomplete_midea_watermark():
    parent = _read(PARENT)
    current = _read(CURRENT)
    assert current["schema_version"] == "m5-event-infrastructure-v5"
    assert current["supersedes"] == "config/prospective-public-event-watermarks-v4.json"

    old_watermarks = parent["watermarks"]
    new_watermarks = current["watermarks"]
    assert len(new_watermarks) == len(old_watermarks)
    for old, new in zip(old_watermarks, new_watermarks, strict=True):
        if old["scope"] != "prospective:000333":
            assert _canonical(new) == _canonical(old)
            continue
        expected = dict(old)
        expected["local_later_window_evidence"] = list(old["local_later_window_evidence"]) + [{
            "path": "runtime/prospective-public-event-20260927/gapfill-000333-20260927T172744007289Z/index.json",
            "sha256": "12e156fda8bca0f1aa676c39478b96f8ceccd686778a557c853120c866cda083",
            "window": "2026-09-28",
            "status": "COMPLETE_WINDOW_ONLY_NOT_CONTINUOUS_WATERMARK",
        }]
        expected["latest_bounded_observation"] = {
            "retrieved_at": "2026-09-27T17:27:44.524640+00:00",
            "document_id": "1225582141",
            "source_sha256": "94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686",
            "scan_receipt_path": "runtime/prospective-public-event-20260927/gapfill-000333-20260927T172744007289Z/scan-receipt.json",
            "scan_receipt_sha256": "664bf165ba847a8da902cd8d8efa32b92a1588d5447c93ff678940cf03673021",
            "status": "SINGLE_DAY_SNAPSHOT_ONLY",
        }
        assert _canonical(new) == _canonical(expected)
        assert new["coverage_status"] == "INCOMPLETE"
        assert _canonical(new["coverage_through"]) == _canonical(old["coverage_through"])


def test_v5_bounded_window_hashes_match_retained_scan_and_review():
    scan = _read(MIDEA_SCAN / "scan-receipt.json")
    review = _read(MIDEA_SCAN / "document-review-1225582141.json")
    index_bytes = (ROOT / scan["index_path"]).read_bytes()
    assert hashlib.sha256(index_bytes).hexdigest() == scan["index_sha256"]
    assert hashlib.sha256((MIDEA_SCAN / "scan-receipt.json").read_bytes()).hexdigest() == review["source"]["scan_receipt_sha256"]
    assert hashlib.sha256((ROOT / review["source"]["pdf_path"]).read_bytes()).hexdigest() == review["source"]["pdf_sha256"]

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "config/prospective-public-event-watermarks-v5.json"
CURRENT = ROOT / "config/prospective-public-event-watermarks-v6.json"
RAW_SHA256 = "c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114"
SNAPSHOTS = {
    "600887": {
        "watermark_id": "prospective-600887-cninfo-20260927-rerun",
        "index": "runtime/prospective-public-event-20260927/gapfill-600887-20260927T172744553862Z/index.json",
        "index_sha256": "86ee4f66ee4785842dc616b9da77e4b5d7b0d02df64ba5a03bcc0bbb918973d0",
        "receipt": "runtime/prospective-public-event-20260927/gapfill-600887-20260927T172744553862Z/scan-receipt.json",
        "receipt_sha256": "3682057b9e97a915352390ba3968c660ce92c33c835b21da891a4fdc11a9b2c0",
        "raw": "runtime/prospective-public-event-20260927/gapfill-600887-20260927T172744553862Z/600887-page-1.raw.json",
        "organization_id": "gssh0600887",
    },
    "601088": {
        "watermark_id": "prospective-601088-cninfo-contiguous-20260927-v1",
        "index": "runtime/prospective-public-event-20260927/gapfill-601088-20260927T172744786163Z/index.json",
        "index_sha256": "4bdb05966c6ea74dc53e5cf9c627dd0b75f652f463080d6eb6d97d77b549d3e8",
        "receipt": "runtime/prospective-public-event-20260927/gapfill-601088-20260927T172744786163Z/scan-receipt.json",
        "receipt_sha256": "935114d2544c410d62938cc9c8e6aa0586aab3546a9b439eeaa19c3c78fa8e2e",
        "raw": "runtime/prospective-public-event-20260927/gapfill-601088-20260927T172744786163Z/601088-page-1.raw.json",
        "organization_id": "9900003701",
    },
}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v6_only_appends_yili_and_shenhua_single_day_snapshots():
    parent = _read(PARENT)
    current = _read(CURRENT)
    assert current["schema_version"] == "m5-event-infrastructure-v6"
    assert current["supersedes"] == "config/prospective-public-event-watermarks-v5.json"
    assert current["action"] == "no_order"
    assert len(current["watermarks"]) == len(parent["watermarks"])

    by_id = {item["watermark_id"]: item for item in current["watermarks"]}
    for old in parent["watermarks"]:
        new = by_id[old["watermark_id"]]
        symbol = next(
            (code for code, spec in SNAPSHOTS.items() if spec["watermark_id"] == old["watermark_id"]),
            None,
        )
        if symbol is None:
            assert new == old
            continue

        spec = SNAPSHOTS[symbol]
        expected = dict(old)
        expected["local_later_window_evidence"] = list(
            old.get("local_later_window_evidence", [])
        ) + [
            {
                "path": spec["index"],
                "sha256": spec["index_sha256"],
                "window": "2026-09-28 as of 01:27:44 +08:00",
                "status": "SINGLE_DAY_SNAPSHOT_ONLY",
            }
        ]
        expected["latest_bounded_observation"] = {
            "retrieved_at": (
                "2026-09-27T17:27:44.770278+00:00"
                if symbol == "600887"
                else "2026-09-27T17:27:44.974127+00:00"
            ),
            "index_path": spec["index"],
            "index_sha256": spec["index_sha256"],
            "scan_receipt_path": spec["receipt"],
            "scan_receipt_sha256": spec["receipt_sha256"],
            "returned_announcements": 0,
            "status": "SINGLE_DAY_SNAPSHOT_ONLY",
        }
        assert new == expected
        assert new["coverage_through"] == old["coverage_through"]
        assert new["coverage_status"] == old["coverage_status"]


def test_v6_snapshot_sources_are_hash_bound_and_explicitly_bounded():
    for symbol, spec in SNAPSHOTS.items():
        index_path = ROOT / spec["index"]
        receipt_path = ROOT / spec["receipt"]
        raw_path = ROOT / spec["raw"]
        index = _read(index_path)
        receipt = _read(receipt_path)

        assert _sha256(index_path) == spec["index_sha256"]
        assert _sha256(receipt_path) == spec["receipt_sha256"]
        assert _sha256(raw_path) == RAW_SHA256
        assert index["symbol"] == symbol
        assert index["scan_from"] == index["scan_to"] == "2026-09-28"
        assert index["organization_id"] == spec["organization_id"]
        assert index["announcements"] == []
        assert index["pages"] == [
            {
                "page": 1,
                "path": spec["raw"],
                "sha256": RAW_SHA256,
                "returned_count": 0,
                "has_more": False,
                "http_status": 200,
            }
        ]

        assert receipt["capture_status"] == "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS"
        assert receipt["scan_date"] == "2026-09-28"
        assert receipt["exact_query_date_filter"] == "2026-09-28~2026-09-28"
        assert receipt["index_path"] == spec["index"]
        assert receipt["index_sha256"] == spec["index_sha256"]
        assert receipt["pagination"]["page_count"] == 1
        assert receipt["pagination"]["returned_announcements"] == 0
        assert receipt["pagination"]["terminal_has_more"] is False
        assert any("later same-day postings" in item for item in receipt["limitations"])
        assert any("does not prove strict contemporaneous PIT" in item for item in receipt["limitations"])

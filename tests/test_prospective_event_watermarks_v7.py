from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "config/prospective-public-event-watermarks-v6.json"
CURRENT = ROOT / "config/prospective-public-event-watermarks-v7.json"
SNAPSHOTS = {
    "000333": {
        "watermark_id": "prospective-000333-initial-20260927",
        "run": "runtime/prospective-public-event-2026-09-28/gapfill-000333-20260927T211403213554Z",
        "raw": "000333-page-1.raw.json",
        "index_sha256": "1e01dd2d4e0e4bdd598361e0690ed2ae9d7a25b1b88a410afda1fc881bede9ee",
        "receipt_sha256": "0e251210a1380b832914f46de5758443a82641a4926916b28472c12971cc52be",
        "raw_sha256": "ad8cb13b94623e0cffa83621c91d1c98a4af7723335f0699ac64aa8c0ab068eb",
        "organization_id": "9900005965",
        "retrieved_at": "2026-09-27T21:14:03.471920+00:00",
        "returned": 1,
    },
    "600887": {
        "watermark_id": "prospective-600887-cninfo-20260927-rerun",
        "run": "runtime/prospective-public-event-2026-09-28/gapfill-600887-20260927T211524092707Z",
        "raw": "600887-page-1.raw.json",
        "index_sha256": "6efd8438d8ae98cf9037cff87d5f1a57c307289837d6d2495b3b4e10ecb24b1c",
        "receipt_sha256": "806e38d5a06fdc3da491a4d185957b433b8ad807a6738e4f3b821e903dbb9a90",
        "raw_sha256": "c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114",
        "organization_id": "gssh0600887",
        "retrieved_at": "2026-09-27T21:15:24.514642+00:00",
        "returned": 0,
    },
    "601088": {
        "watermark_id": "prospective-601088-cninfo-contiguous-20260927-v1",
        "run": "runtime/prospective-public-event-2026-09-28/gapfill-601088-20260927T211539346696Z",
        "raw": "601088-page-1.raw.json",
        "index_sha256": "3e73216f317fa0e96a50b575f4e079bc1c7d35af8dd3a872e926daea5be41d40",
        "receipt_sha256": "cae43c78b07e00cd25608e796cdd6c18b67c767aa5386c867c34f0f2658e43b9",
        "raw_sha256": "c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114",
        "organization_id": "9900003701",
        "retrieved_at": "2026-09-27T21:15:39.563269+00:00",
        "returned": 0,
    },
}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v7_is_append_only_and_does_not_advance_formal_watermarks():
    parent = _read(PARENT)
    current = _read(CURRENT)
    assert current["schema_version"] == "m5-event-infrastructure-v7"
    assert current["supersedes"] == "config/prospective-public-event-watermarks-v6.json"
    assert current["action"] == "no_order"
    assert len(current["watermarks"]) == len(parent["watermarks"])

    prior_by_id = {item["watermark_id"]: item for item in parent["watermarks"]}
    current_by_id = {item["watermark_id"]: item for item in current["watermarks"]}
    for watermark_id, prior in prior_by_id.items():
        current_item = copy.deepcopy(current_by_id[watermark_id])
        assert current_item["coverage_through"] == prior["coverage_through"]
        assert current_item["coverage_status"] == prior["coverage_status"]
        symbol = next(
            (code for code, spec in SNAPSHOTS.items() if spec["watermark_id"] == watermark_id),
            None,
        )
        if symbol is None:
            assert current_item == prior
            continue

        current_item["latest_bounded_observation"] = current_item.pop(
            "prior_latest_bounded_observation"
        )
        current_item["local_later_window_evidence"].pop()
        assert current_item == prior


def test_v7_single_day_snapshots_bind_index_receipt_raw_and_query_scope():
    current = _read(CURRENT)
    parent_by_id = {item["watermark_id"]: item for item in _read(PARENT)["watermarks"]}
    by_id = {item["watermark_id"]: item for item in current["watermarks"]}
    for symbol, spec in SNAPSHOTS.items():
        run = ROOT / spec["run"]
        index_path = run / "index.json"
        receipt_path = run / "scan-receipt.json"
        raw_path = run / spec["raw"]
        index = _read(index_path)
        receipt = _read(receipt_path)
        watermark = by_id[spec["watermark_id"]]
        snapshot = watermark["latest_bounded_observation"]
        predecessor = watermark["prior_latest_bounded_observation"]

        assert _sha256(index_path) == spec["index_sha256"]
        assert _sha256(receipt_path) == spec["receipt_sha256"]
        assert _sha256(raw_path) == spec["raw_sha256"]
        assert index["symbol"] == symbol
        assert index["organization_id"] == spec["organization_id"]
        assert index["scan_from"] == index["scan_to"] == "2026-09-28"
        assert index["retrieved_at"] == spec["retrieved_at"]
        assert len(index["announcements"]) == spec["returned"]
        assert len(index["pages"]) == 1
        page = index["pages"][0]
        assert page["path"] == f'{spec["run"]}/{spec["raw"]}'
        assert page["sha256"] == spec["raw_sha256"]
        assert page["returned_count"] == spec["returned"]
        assert page["has_more"] is False
        assert page["http_status"] == 200
        if symbol == "000333":
            assert index["announcements"][0]["announcementId"] == "1225582141"
        assert receipt["capture_status"] == "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS"
        assert receipt["exact_query_date_filter"] == "2026-09-28~2026-09-28"
        assert receipt["index_sha256"] == spec["index_sha256"]
        assert receipt["pagination"]["returned_announcements"] == spec["returned"]
        assert any("later postings" in item for item in receipt["limitations"])
        assert any("strict contemporaneous PIT" in item for item in receipt["limitations"])

        assert snapshot["retrieved_at"] == spec["retrieved_at"]
        assert snapshot["index_path"] == f'{spec["run"]}/index.json'
        assert snapshot["index_sha256"] == spec["index_sha256"]
        assert snapshot["scan_receipt_path"] == f'{spec["run"]}/scan-receipt.json'
        assert snapshot["scan_receipt_sha256"] == spec["receipt_sha256"]
        assert snapshot["raw_page_path"] == f'{spec["run"]}/{spec["raw"]}'
        assert snapshot["raw_page_sha256"] == spec["raw_sha256"]
        assert snapshot["returned_announcements"] == spec["returned"]
        assert snapshot["status"] == "SINGLE_DAY_SNAPSHOT_ONLY"
        assert predecessor == parent_by_id[spec["watermark_id"]]["latest_bounded_observation"]

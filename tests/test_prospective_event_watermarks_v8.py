from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from value_investment_agent.disclosures import validate_cninfo_announcement_window


ROOT = Path(__file__).resolve().parents[1]
V7 = ROOT / "config/prospective-public-event-watermarks-v7.json"
V8 = ROOT / "config/prospective-public-event-watermarks-v8.json"
MIDEA_WINDOWS = [
    {
        "start": "2026-03-31",
        "end": "2026-08-28",
        "index": "runtime/prospective-public-event-20260927/gapfill-000333-20260927T135108559217Z/index.json",
        "sha256": "31d99109b568f0753d194165c86c98a2b157e7715e2fb5b505f976c502e51652",
        "records": 98,
        "pages": 4,
        "retrieved_at": "2026-09-27T13:51:09.123752+00:00",
    },
    {
        "start": "2026-08-29",
        "end": "2026-09-27",
        "index": "runtime/prospective-public-event-20260927/gapfill-000333-20260927T114140840633Z/index.json",
        "sha256": "6c04cd73eeb3e3d79e9589b80398b96eafa34d36f7f49d317300a630e5ea1dab",
        "records": 8,
        "pages": 1,
        "retrieved_at": "2026-09-27T11:41:41.050337+00:00",
    },
]
CURRENT_SNAPSHOTS = {
    "000333": {
        "watermark_id": "prospective-000333-cninfo-datechain-20260927-v1",
        "run": "runtime/prospective-public-event-2026-09-28/gapfill-000333-20260928T020040966184Z",
        "raw": "000333-page-1.raw.json",
        "index_sha256": "7fddbe9ea30ddfa2d7113debad410ae8d4f2618fc105d18f011431a29f874890",
        "receipt_sha256": "6e305597c2604c32a980b72178584ac13b3d3acabd33eccbed68172b71ba484f",
        "raw_sha256": "ad8cb13b94623e0cffa83621c91d1c98a4af7723335f0699ac64aa8c0ab068eb",
        "organization_id": "9900005965",
        "retrieved_at": "2026-09-28T02:00:41.172152+00:00",
        "count": 1,
    },
    "600887": {
        "watermark_id": "prospective-600887-cninfo-20260927-rerun",
        "run": "runtime/prospective-public-event-2026-09-28/gapfill-600887-20260928T020132411066Z",
        "raw": "600887-page-1.raw.json",
        "index_sha256": "39db16b37b92e136b425c7aa49ced860385e19013533fc6fea384ea77dc08e7b",
        "receipt_sha256": "1964967233fd4f8c3dbf5168902874f0b35539049e9d2caaa1d009548412d0d7",
        "raw_sha256": "c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114",
        "organization_id": "gssh0600887",
        "retrieved_at": "2026-09-28T02:01:33.651715+00:00",
        "count": 0,
    },
    "601088": {
        "watermark_id": "prospective-601088-cninfo-contiguous-20260927-v1",
        "run": "runtime/prospective-public-event-2026-09-28/gapfill-601088-20260928T020200717747Z",
        "raw": "601088-page-1.raw.json",
        "index_sha256": "32a4a0f6f6e5da59443ca729f21e6eba5e8fd027fa3729ac7617733dca0225dc",
        "receipt_sha256": "53de05fdbe327ed9d98334f42817517be3074dc286c70b1a35f54ef3b9f05d53",
        "raw_sha256": "c2a890bbf3a6a53ab02ddc6c1794bf1c72ba45799fe9f59dcc5ba2cc18467114",
        "organization_id": "9900003701",
        "retrieved_at": "2026-09-28T02:02:00.942875+00:00",
        "count": 0,
    },
}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v8_preserves_v7_and_adds_only_a_bounded_midea_successor():
    parent = _read(V7)
    current = _read(V8)
    assert current["schema_version"] == "m5-event-infrastructure-v8"
    assert current["supersedes"] == "config/prospective-public-event-watermarks-v7.json"
    assert current["action"] == "no_order"
    assert current["watermarks"][:-1] == parent["watermarks"]

    watermark = current["watermarks"][-1]
    assert watermark["watermark_id"] == "prospective-000333-cninfo-datechain-20260927-v1"
    assert watermark["supersedes_watermark_id"] == "prospective-000333-initial-20260927"
    assert watermark["coverage_from"] == "2026-03-31"
    assert watermark["coverage_through"] == MIDEA_WINDOWS[-1]["retrieved_at"]
    assert datetime.fromisoformat(watermark["coverage_through"]).tzinfo is not None
    assert watermark["coverage_status"] == "INCOMPLETE"
    assert watermark["coverage_window"]["status"] == "COMPLETE"
    assert datetime.fromisoformat(watermark["retrieved_at"]) == max(
        datetime.fromisoformat(spec["retrieved_at"]) for spec in MIDEA_WINDOWS
    )
    assert datetime.fromisoformat(watermark["coverage_through"]) <= datetime.fromisoformat(
        watermark["retrieved_at"]
    )
    assert watermark["watermark_advance"].startswith("NOT_APPLIED:")
    assert watermark["source_health"] == "HEALTHY"
    assert watermark["retrieval_clock_attestation"] == "PROCESS_CLOCK_ONLY_UNATTESTED"
    assert watermark["strict_pit_admissible"] is False
    assert [item["sha256"] for item in watermark["evidence_refs"]] == [
        item["sha256"] for item in MIDEA_WINDOWS
    ]


def test_midea_date_chain_indexes_raw_pages_and_has_no_date_gap():
    ids: list[str] = []
    previous_end: date | None = None
    for spec in MIDEA_WINDOWS:
        index_path = ROOT / spec["index"]
        index = _read(index_path)
        start = date.fromisoformat(spec["start"])
        end = date.fromisoformat(spec["end"])

        assert _sha256(index_path) == spec["sha256"]
        assert index["schema_version"] == "prospective-cninfo-window-index-v1"
        assert index["provider"] == "cninfo"
        assert index["symbol"] == "000333"
        assert index["organization_id"] == "9900005965"
        assert index["scan_from"] == spec["start"]
        assert index["scan_to"] == spec["end"]
        assert index["retrieved_at"] == spec["retrieved_at"]
        assert index["query"]["stock"] == "000333,9900005965"
        assert index["query"]["seDate"] == f"{spec['start']}~{spec['end']}"
        assert index["coverage_status"] == "COMPLETE"
        assert index["returned_announcements"] == spec["records"]
        assert len(index["pages"]) == spec["pages"]
        validate_cninfo_announcement_window(index["announcements"], spec["start"], spec["end"])

        if previous_end is not None:
            assert start == previous_end + timedelta(days=1)
        previous_end = end

        page_records = []
        for expected_page, page_ref in enumerate(index["pages"], start=1):
            raw_path = ROOT / page_ref["path"]
            raw = _read(raw_path)
            assert page_ref["page"] == expected_page
            assert _sha256(raw_path) == page_ref["sha256"]
            assert raw["totalAnnouncement"] == spec["records"]
            assert len(raw["announcements"]) == page_ref["returned_count"]
            assert raw["hasMore"] is page_ref["has_more"]
            assert all(item["secCode"] == "000333" for item in raw["announcements"])
            page_records.extend(raw["announcements"])

        assert index["pages"][-1]["has_more"] is False
        assert page_records == index["announcements"]
        ids.extend(item["announcementId"] for item in page_records)

    assert previous_end == date(2026, 9, 27)
    assert len(ids) == 106
    assert len(set(ids)) == len(ids)


def test_v8_current_day_queries_are_snapshots_not_watermark_advances():
    current = _read(V8)
    snapshots = {item["symbol"]: item for item in current["current_bounded_observations"]}
    assert set(snapshots) == set(CURRENT_SNAPSHOTS)

    for symbol, expected in CURRENT_SNAPSHOTS.items():
        snapshot = snapshots[symbol]
        index_path = ROOT / snapshot["index_path"]
        receipt_path = ROOT / snapshot["scan_receipt_path"]
        raw_path = ROOT / snapshot["raw_page_path"]
        index = _read(index_path)
        receipt = _read(receipt_path)

        assert snapshot["watermark_id"] == expected["watermark_id"]
        assert index["symbol"] == symbol
        assert index["organization_id"] == expected["organization_id"]
        assert index["retrieved_at"] == expected["retrieved_at"]
        assert index["query"]["stock"] == f"{symbol},{expected['organization_id']}"
        assert index["query"]["seDate"] == "2026-09-28~2026-09-28"
        assert _sha256(index_path) == expected["index_sha256"] == snapshot["index_sha256"]
        assert _sha256(receipt_path) == expected["receipt_sha256"] == snapshot["scan_receipt_sha256"]
        assert _sha256(raw_path) == expected["raw_sha256"] == snapshot["raw_page_sha256"]
        assert snapshot["index_path"] == f"{expected['run']}/index.json"
        assert snapshot["scan_receipt_path"] == f"{expected['run']}/scan-receipt.json"
        assert snapshot["raw_page_path"] == f"{expected['run']}/{expected['raw']}"
        assert index["scan_from"] == index["scan_to"] == "2026-09-28"
        assert len(index["announcements"]) == expected["count"]
        assert len(index["pages"]) == 1
        page = index["pages"][0]
        assert page["path"] == f"{expected['run']}/{expected['raw']}"
        assert page["sha256"] == expected["raw_sha256"]
        assert page["returned_count"] == expected["count"]
        assert page["has_more"] is False
        assert page["http_status"] == 200
        assert all(item["secCode"] == symbol for item in index["announcements"])
        if symbol == "000333":
            assert [item["announcementId"] for item in index["announcements"]] == [
                "1225582141"
            ]
        assert snapshot["coverage_status"] == "SINGLE_DAY_SNAPSHOT_ONLY"
        assert datetime.fromisoformat(snapshot["retrieved_at"]) == datetime.fromisoformat(
            expected["retrieved_at"]
        )
        assert snapshot["retrieval_clock_attestation"] == "PROCESS_CLOCK_ONLY_UNATTESTED"
        assert snapshot["strict_pit_admissible"] is False
        assert receipt["capture_status"] == "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS"
        assert receipt["exact_query_date_filter"] == "2026-09-28~2026-09-28"
        assert receipt["index_sha256"] == expected["index_sha256"]
        assert receipt["pagination"]["returned_announcements"] == expected["count"]
        assert any("later postings" in item for item in receipt["limitations"])
        assert any("strict contemporaneous PIT" in item for item in receipt["limitations"])

    midea = next(item for item in current["watermarks"] if item["watermark_id"].endswith("datechain-20260927-v1"))
    assert midea["coverage_through"] == MIDEA_WINDOWS[-1]["retrieved_at"]
    assert midea["coverage_status"] == "INCOMPLETE"
    assert snapshots["000333"]["returned_announcements"] == 1
    assert snapshots["000333"]["announcement_ids"] == ["1225582141"]
    assert snapshots["600887"]["returned_announcements"] == 0
    assert snapshots["601088"]["returned_announcements"] == 0

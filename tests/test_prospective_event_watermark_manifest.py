from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _index_and_raw_page_refs(value):
    if isinstance(value, dict):
        path = value.get("path")
        digest = value.get("sha256")
        if isinstance(path, str) and path.endswith(("index.json", ".raw.json")):
            yield {"path": path, "sha256": digest}
        for nested in value.values():
            yield from _index_and_raw_page_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _index_and_raw_page_refs(nested)


def test_successor_manifest_does_not_promote_bounded_windows_to_watermarks():
    previous = _load("config/prospective-public-event-watermarks-v1.json")
    current = _load("config/prospective-public-event-watermarks-v2.json")
    old_by_id = {item["watermark_id"]: item for item in previous["watermarks"]}

    assert current["action"] == "no_order"
    assert current["supersedes"] == "config/prospective-public-event-watermarks-v1.json"
    assert len(current["watermarks"]) == len(old_by_id) == 3
    for item in current["watermarks"]:
        old = old_by_id[item["watermark_id"]]
        assert item["scope"] == old["scope"]
        assert item["coverage_through"] == old["coverage_through"]
        assert item["coverage_status"] == old["coverage_status"]
        assert item["action"] == "no_order"

    assert current["watermarks"][0]["coverage_status"] == "INCOMPLETE"
    assert current["watermarks"][1]["coverage_status"] == "COMPLETE"
    assert current["watermarks"][1]["watermark_advance"].startswith("NOT_APPLIED")
    assert current["watermarks"][2]["coverage_status"] == "INCOMPLETE"


def test_later_bounded_event_evidence_is_hash_bound_but_not_mislabelled():
    current = _load("config/prospective-public-event-watermarks-v2.json")
    references: list[dict] = []
    for watermark in current["watermarks"]:
        local = watermark.get("local_later_window_evidence", [])
        if isinstance(local, list):
            references.extend(local)
    yili = current["watermarks"][1]["local_later_window_evidence"]
    references.extend(
        {"path": yili[key], "sha256": yili[digest_key]}
        for key, digest_key in (
            ("path", "sha256"),
            ("interpretation_path", "interpretation_sha256"),
            ("receipt_path", "receipt_sha256"),
        )
    )

    assert len(references) == 7
    for reference in references:
        assert _sha256(reference["path"]) == reference["sha256"]

    assert yili["announcement_ids"] == ["1225578520"]
    assert yili["status"] == "BOUNDED_WINDOW_EVIDENCE_NOT_ADVANCED_TO_FORMAL_WATERMARK"
    assert current["watermarks"][1]["watermark_advance"].startswith("NOT_APPLIED")


def test_v3_advances_only_yili_on_a_validated_contiguous_window():
    previous = _load("config/prospective-public-event-watermarks-v2.json")
    current = _load("config/prospective-public-event-watermarks-v3.json")
    old_by_scope = {item["scope"]: item for item in previous["watermarks"]}
    new_by_scope = {item["scope"]: item for item in current["watermarks"]}

    assert current["supersedes"] == "config/prospective-public-event-watermarks-v2.json"
    assert current["action"] == "no_order"
    assert new_by_scope["prospective:000333"] == old_by_scope["prospective:000333"]
    assert new_by_scope["prospective:601088"] == old_by_scope["prospective:601088"]

    yili = new_by_scope["prospective:600887"]
    old_yili = old_by_scope["prospective:600887"]
    assert yili["supersedes_watermark_id"] == old_yili["watermark_id"]
    assert yili["coverage_status"] == "COMPLETE"
    assert yili["coverage_window"] == {
        "start": "2026-09-23", "end": "2026-09-27",
        "coverage_scope": "CNINFO exact issuer and bounded date window only",
        "status": "COMPLETE",
    }
    assert yili["announcement_ids"] == ["1225578520"]
    assert yili["event_materiality"] == "UNDETERMINED_INSUFFICIENT_EVIDENCE"
    assert yili["watermark_advance"].startswith("APPLIED:")
    assert yili["prior_bounded_scan"]["status"] == "SUMMARY_PARSE_FAILED_NOT_USED_FOR_ADVANCE"
    for reference in yili["evidence_refs"]:
        assert _sha256(reference["path"]) == reference["sha256"]

    scan = _load(yili["evidence_refs"][2]["path"])
    assert scan["coverage_status"] == "COMPLETE"
    assert scan["announcements"][0]["announcement_id"] == "1225578520"
    assert scan["announcements"][0]["source_url"].endswith("1225578520.PDF")


def test_v4_preserves_v3_history_and_marks_shenhua_successor_no_order():
    previous = _load("config/prospective-public-event-watermarks-v3.json")
    current = _load("config/prospective-public-event-watermarks-v4.json")
    new_by_id = {item["watermark_id"]: item for item in current["watermarks"]}

    assert current["schema_version"] == "m5-event-infrastructure-v4"
    assert current["supersedes"] == "config/prospective-public-event-watermarks-v3.json"
    assert current["action"] == "no_order"
    for old in previous["watermarks"]:
        assert new_by_id[old["watermark_id"]] == old

    shenhua = next(
        item
        for item in current["watermarks"]
        if item["watermark_id"] == "prospective-601088-cninfo-contiguous-20260927-v1"
    )
    assert shenhua["supersedes_watermark_id"] == "prospective-601088-initial-20260927"
    assert shenhua["scope"] == "prospective:601088"
    assert shenhua["action"] == "no_order"


def test_v4_shenhua_has_seven_contiguous_hash_bound_windows_and_terminal_pages():
    current = _load("config/prospective-public-event-watermarks-v4.json")
    index_and_raw_refs = list(_index_and_raw_page_refs(current))
    assert index_and_raw_refs
    for reference in index_and_raw_refs:
        assert reference["sha256"]
        assert _sha256(reference["path"]) == reference["sha256"]

    shenhua = next(
        item
        for item in current["watermarks"]
        if item["watermark_id"] == "prospective-601088-cninfo-contiguous-20260927-v1"
    )
    windows = shenhua["coverage_chain"]
    assert [item["window"] for item in windows] == [
        "2026-03-31..2026-03-31",
        "2026-04-01..2026-06-25",
        "2026-06-26..2026-08-27",
        "2026-08-25..2026-08-31",
        "2026-09-01..2026-09-22",
        "2026-09-23..2026-09-26",
        "2026-09-27..2026-09-27",
    ]
    assert len(windows) == 7

    for previous, following in zip(windows, windows[1:]):
        previous_end = previous["window"].split("..", maxsplit=1)[1]
        following_start = following["window"].split("..", maxsplit=1)[0]
        assert date.fromisoformat(following_start) <= date.fromisoformat(previous_end) + timedelta(days=1)

    assert shenhua["coverage_window"]["start"] == "2026-03-31"
    assert shenhua["coverage_window"]["end"] == "2026-09-27"
    assert shenhua["coverage_through"] == "2026-09-27T11:22:35.313956+00:00"
    assert shenhua["retrieved_at"] == shenhua["coverage_through"]

    for window in windows:
        index_ref = window["index"]
        assert _sha256(index_ref["path"]) == index_ref["sha256"]
        index = _load(index_ref["path"])
        assert index["coverage_status"] == "COMPLETE"
        assert len(index["pages"]) == len(window["raw_pages"])
        assert sum(page["returned_count"] for page in index["pages"]) == index["total_announcements"]

        for page, raw_ref in zip(index["pages"], window["raw_pages"]):
            assert page["path"] == raw_ref["path"]
            assert page["sha256"] == raw_ref["sha256"]
            assert _sha256(raw_ref["path"]) == raw_ref["sha256"]
            raw = _load(raw_ref["path"])
            assert len(raw.get("announcements") or []) == raw_ref["returned_count"]
            assert raw["totalAnnouncement"] == index["total_announcements"]
            assert raw["hasMore"] is raw_ref["has_more"] is page["has_more"]

        assert window["raw_pages"][-1]["has_more"] is False

    empty_terminal = windows[-1]
    assert empty_terminal["total_announcements"] == 0
    assert empty_terminal["raw_pages"][-1]["returned_count"] == 0
    assert empty_terminal["raw_pages"][-1]["has_more"] is False


def test_v4_shenhua_announcement_ids_bind_to_raw_pages_and_original_retrieval_evidence():
    current = _load("config/prospective-public-event-watermarks-v4.json")
    shenhua = next(
        item
        for item in current["watermarks"]
        if item["watermark_id"] == "prospective-601088-cninfo-contiguous-20260927-v1"
    )
    ids = {"1225546775", "1225546779", "1225565223", "1225567741"}
    sep_window = next(
        item for item in shenhua["coverage_chain"] if item["window"] == "2026-09-01..2026-09-22"
    )
    assert _sha256(sep_window["index"]["path"]) == sep_window["index"]["sha256"]
    index = _load(sep_window["index"]["path"])
    index_ids = {str(item["announcementId"]) for item in index["announcements"]}
    raw_ref = sep_window["raw_pages"][0]
    assert _sha256(raw_ref["path"]) == raw_ref["sha256"]
    raw = _load(raw_ref["path"])
    raw_ids = {str(item["announcementId"]) for item in raw["announcements"]}
    assert ids <= index_ids
    assert ids <= raw_ids

    retrieval_root = "runtime/prospective-public-event-20260927/shenhua-indexed-originals-20260927T154222Z"
    receipt_path = f"{retrieval_root}/receipt.json"
    receipt = _load(receipt_path)
    assert receipt["action"] == "no_order"
    assert receipt["index_path"] == sep_window["index"]["path"]
    assert receipt["index_sha256"] == sep_window["index"]["sha256"]
    assert _sha256(receipt["index_path"]) == receipt["index_sha256"]
    pdf_records = {str(item["announcement_id"]): item for item in receipt["pdfs"]}
    assert ids <= pdf_records.keys()

    for announcement_id in ids:
        record = pdf_records[announcement_id]
        assert record["symbol"] == "601088"
        assert _sha256(record["path"]) == record["sha256"]

        scan_path = f"{retrieval_root}/scan-evidence-{announcement_id}.json"
        scan = _load(scan_path)
        assert scan["coverage_status"] == "COMPLETE"
        assert scan["returned_announcements"] == scan["total_announcements"] == 4
        assert scan["has_more"] is False
        matched = [item for item in scan["announcements"] if item["announcement_id"] == announcement_id]
        assert len(matched) == 1
        assert matched[0]["source_url"] == record["source_url"]
        for reference in scan["evidence_refs"]:
            assert _sha256(reference["path"]) == reference["sha256"]
        assert {reference["path"] for reference in scan["evidence_refs"]} >= {
            sep_window["index"]["path"], raw_ref["path"]
        }

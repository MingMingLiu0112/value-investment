from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from scripts.build_m7_actual_event_candidate import verified_followup_scan
from value_investment_agent.m5_disclosure_queue import DisclosureReviewQueue, build_cninfo_event_scan


def _scan(tmp_path):
    start, end = date(2026, 9, 10), date(2026, 9, 25)
    payload = {
        "url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        "parameters": {"seDate": f"{start}~{end}", "stock": "600519,gssh0600519"},
        "total_announcements": 0, "announcements": [],
    }
    scan = build_cninfo_event_scan(
        payload, symbol="600519", scan_from=start, scan_to=end,
        retrieved_at=datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc),
        evidence_dir=tmp_path / "600519", root=tmp_path,
    )
    queue = DisclosureReviewQueue(
        queue_id="followup-1", schema_version="m5-cninfo-disclosure-queue-v1",
        provider="cninfo", parser_version="m5-cninfo-announcement-title-v1",
        scan_from=start, scan_to=end,
        retrieved_at=datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc),
        scans=(scan,),
    )
    path = tmp_path / "queue.json"
    path.write_text(queue.to_json() + "\n", encoding="utf-8")
    return path, tmp_path / "600519/cninfo-index.json"


def test_verified_followup_scan_binds_contiguous_zero_announcement_index(tmp_path):
    queue, index = _scan(tmp_path)
    result = verified_followup_scan(
        queue, root=tmp_path, symbol="600519",
        previous_scan_to="2026-09-09", as_of="2026-09-25",
    )
    assert result["coverage_status"] == "COMPLETE"
    assert result["announcement_count"] == 0
    assert result["index_sha256"] == hashlib.sha256(index.read_bytes()).hexdigest()
    assert result["action"] == "no_order"


def test_verified_followup_scan_rejects_gap_future_and_changed_index(tmp_path):
    queue, index = _scan(tmp_path)
    with pytest.raises(ValueError, match="coverage window"):
        verified_followup_scan(queue, root=tmp_path, symbol="600519",
                               previous_scan_to="2026-09-08", as_of="2026-09-25")
    with pytest.raises(ValueError, match="coverage window"):
        verified_followup_scan(queue, root=tmp_path, symbol="600519",
                               previous_scan_to="2026-09-09", as_of="2026-09-24")
    index.write_text(index.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="missing or changed"):
        verified_followup_scan(queue, root=tmp_path, symbol="600519",
                               previous_scan_to="2026-09-09", as_of="2026-09-25")


def test_verified_followup_scan_rejects_rehashed_nonzero_index(tmp_path):
    queue, index = _scan(tmp_path)
    raw = json.loads(index.read_text(encoding="utf-8"))
    raw["total_announcements"] = 1
    index.write_text(json.dumps(raw), encoding="utf-8")
    payload = json.loads(queue.read_text(encoding="utf-8"))
    payload["scans"][0]["evidence_refs"][0]["sha256"] = hashlib.sha256(index.read_bytes()).hexdigest()
    queue.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        verified_followup_scan(queue, root=tmp_path, symbol="600519",
                               previous_scan_to="2026-09-09", as_of="2026-09-25")

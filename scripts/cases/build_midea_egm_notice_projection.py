"""Build a strictly bounded M5 projection for Midea's 2026 EGM notice."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = Path(
    "runtime/prospective-public-event-20260927/"
    "gapfill-000333-20260927T172744007289Z"
)
INPUT_SHA256 = {
    "scan-receipt.json": "664bf165ba847a8da902cd8d8efa32b92a1588d5447c93ff678940cf03673021",
    "index.json": "12e156fda8bca0f1aa676c39478b96f8ceccd686778a557c853120c866cda083",
    "000333-page-1.raw.json": "ad8cb13b94623e0cffa83621c91d1c98a4af7723335f0699ac64aa8c0ab068eb",
    "1225582141.PDF": "94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686",
    "document-review-1225582141.json": "39e3efcc41a6612b579a891c638a699fe41802288a2f26fad28d312ddb263b75",
}
ISSUER = "000333"
ANNOUNCEMENT_ID = "1225582141"
ANNOUNCEMENT_DATE = "2026-09-28"
PIT_AVAILABLE_AT = "2026-09-29T00:00:00+08:00"
CNINFO_URL = "https://static.cninfo.com.cn/finalpage/2026-09-28/1225582141.PDF"
ADJUNCT_URL = "finalpage/2026-09-28/1225582141.PDF"
REVIEW_CLASSIFICATION = "PROCEDURAL_MEETING_NOTICE_WITH_RESEARCH_RELEVANT_AGENDA"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verified_input(root: Path, name: str) -> Path:
    path = (root / EVIDENCE_DIR / name).resolve()
    evidence_root = (root / EVIDENCE_DIR).resolve()
    if evidence_root not in path.parents:
        raise ValueError(f"Input path escapes evidence directory: {name}")
    if not path.is_file():
        raise ValueError(f"Missing input: {path}")
    actual = _sha256(path)
    expected = INPUT_SHA256[name]
    if actual != expected:
        raise ValueError(f"{name} SHA-256 mismatch: expected {expected}, got {actual}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def _validate_inputs(files: dict[str, Path]) -> None:
    receipt = _read_json(files["scan-receipt.json"])
    index = _read_json(files["index.json"])
    raw = _read_json(files["000333-page-1.raw.json"])
    review = _read_json(files["document-review-1225582141.json"])

    if (
        receipt.get("symbol") != ISSUER
        or receipt.get("scan_date") != ANNOUNCEMENT_DATE
        or receipt.get("exact_query_date_filter") != "2026-09-28~2026-09-28"
        or receipt.get("schema_version") != "cninfo-exact-issuer-single-day-receipt-v1"
        or receipt.get("capture_status") != "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS"
        or receipt.get("action") != "no_order"
    ):
        raise ValueError("CNINFO receipt scope or identity is unexpected")
    page_refs = receipt.get("pagination", {}).get("page_refs", [])
    if len(page_refs) != 1 or page_refs[0].get("sha256") != INPUT_SHA256["000333-page-1.raw.json"]:
        raise ValueError("CNINFO receipt does not bind the pinned raw response")
    if receipt.get("index_sha256") != INPUT_SHA256["index.json"]:
        raise ValueError("CNINFO receipt does not bind the pinned index")

    query = index.get("query", {})
    if (
        index.get("symbol") != ISSUER
        or index.get("provider") != "cninfo"
        or index.get("scan_from") != ANNOUNCEMENT_DATE
        or index.get("scan_to") != ANNOUNCEMENT_DATE
        or query.get("stock") != "000333,9900005965"
        or query.get("seDate") != "2026-09-28~2026-09-28"
    ):
        raise ValueError("CNINFO index issuer or date scope is unexpected")
    announcements = index.get("announcements", [])
    if len(announcements) != 1:
        raise ValueError("CNINFO index must contain exactly the bounded announcement")
    indexed = announcements[0]
    raw_announcements = raw.get("announcements", [])
    if len(raw_announcements) != 1:
        raise ValueError("CNINFO raw response must contain exactly one announcement")
    raw_item = raw_announcements[0]
    for item in (indexed, raw_item):
        if (
            item.get("secCode") != ISSUER
            or item.get("announcementId") != ANNOUNCEMENT_ID
            or item.get("adjunctUrl") != ADJUNCT_URL
        ):
            raise ValueError("CNINFO announcement issuer, id, or adjunct URL mismatch")
    if indexed.get("announcementTime") != raw_item.get("announcementTime"):
        raise ValueError("CNINFO announcement date fields disagree")

    source = review.get("source", {})
    assessment = review.get("assessment", {})
    if (
        source.get("symbol") != ISSUER
        or source.get("announcement_id") != ANNOUNCEMENT_ID
        or source.get("announcement_date") != ANNOUNCEMENT_DATE
        or source.get("url") != CNINFO_URL
        or source.get("pdf_sha256") != INPUT_SHA256["1225582141.PDF"]
        or source.get("scan_index_sha256") != INPUT_SHA256["index.json"]
        or source.get("raw_scan_response_sha256") != INPUT_SHA256["000333-page-1.raw.json"]
        or source.get("scan_receipt_sha256") != INPUT_SHA256["scan-receipt.json"]
        or source.get("title") != "关于召开2026年第一次临时股东会的通知"
        or assessment.get("classification") != REVIEW_CLASSIFICATION
        or assessment.get("new_economic_fact_in_this_notice") is not False
        or assessment.get("vote_or_implementation_outcome_established") is not False
        or review.get("state_changes", {}).get("action") != "no_order"
    ):
        raise ValueError("CNINFO document review does not match the pinned notice and classification")


def build_projection_payload(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Verify pinned source artifacts and build one non-decision M5 event."""
    root = Path(repository_root).resolve()
    files = {name: _verified_input(root, name) for name in INPUT_SHA256}
    _validate_inputs(files)

    from value_investment_agent.presentation.read_models.m5_event_state_projection import (
        EventStateInput,
        project_m5_event_states,
    )
    from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord

    relative_pdf_path = (EVIDENCE_DIR / "1225582141.PDF").as_posix()
    evidence = EvidenceRecord(
        evidence_id=f"cninfo-{ANNOUNCEMENT_ID}",
        title="关于召开2026年第一次临时股东会的通知（公告日2026-09-28）",
        artifact_type="cninfo_original_pdf",
        path=relative_pdf_path,
        sha256=INPUT_SHA256["1225582141.PDF"],
        available_at=date(2026, 9, 29),
        source_url=CNINFO_URL,
    )
    event = EventStateInput(
        state="material_risk_monitor",
        event_id="midea-2026-egm-notice-1225582141",
        company_name="美的集团",
        what_happened=(
            "公司通知将于2026-10-13召开临时股东会，审议2022及2023年限制性股票激励计划"
            "部分股份回购注销议题和2026年中期利润分配议题；以上均为待审议事项。"
            "会议通知不证明议案通过或实施，也未证明新增分红金额或注销股数。"
        ),
        impact_area="治理、股本与资本分配监测",
        evidence=(evidence,),
        reopen_condition=(
            "取得后续股东会决议及表决结果，并分别取得股份注销完成及更新股本证据、"
            "以及中期分红方案批准与实施证据。"
        ),
    )
    projection = project_m5_event_states((event,))
    if projection.action != "no_order":
        raise ValueError("M5 projection action must remain no_order")

    return {
        "action": "no_order",
        "report": {
            "schema_version": "midea-egm-notice-projection-v2",
            "successor_of": "midea-egm-notice-projection-v1",
            "company": "美的集团",
            "symbol": ISSUER,
            "announcement_id": ANNOUNCEMENT_ID,
            "announcement_date": ANNOUNCEMENT_DATE,
            "source_available_at": PIT_AVAILABLE_AT,
            "source_time_precision": "DATE_ONLY_CONSERVATIVE_NEXT_DAY",
            "classification": REVIEW_CLASSIFICATION,
            "strict_pit_admissible": False,
            "watermark_status": "UNCHANGED",
            "coverage_status": "SINGLE_DAY_SNAPSHOT_ONLY",
            "valuation_or_trade_conclusion_changed": False,
            "action": "no_order",
            "input_sha256": INPUT_SHA256.copy(),
        },
        "projection": projection.as_payload(),
    }


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    """Create output exclusively; never replace an existing file."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"Refusing to overwrite existing output: {target}") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New JSON output path")
    args = parser.parse_args(argv)
    try:
        payload = build_projection_payload()
        write_new_json(args.output, payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

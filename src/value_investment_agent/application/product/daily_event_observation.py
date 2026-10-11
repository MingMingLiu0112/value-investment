"""Archive a manual official query using the existing M5 scan contract."""
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from .common import require_inside, write_new_json, sha256_file
from ...disclosures import search_announcement_window, validate_cninfo_announcement_window, PDF_BASE_URL
from ...infrastructure.filings.official_pdf import download_official_pdf as download_disclosure_pdf, validate_pdf_original
from ...event_scan import (AnnouncementReview, EventScanResult, EVENT_SCAN_SCHEMA,
    COVERAGE_COMPLETE, PRE_MODEL_NONE, SCAN_PENDING_HUMAN_REVIEW, REVIEW_PENDING_HUMAN_REVIEW)


def collect_daily_event_observation(*, root: Path, symbol: str, issuer_name: str,
                                    start: date, end: date, output_dir: Path) -> dict:
    output_dir = require_inside(root / "runtime", output_dir, "daily event archive")
    if output_dir.exists():
        raise FileExistsError("daily event archive already exists")
    now = datetime.now(timezone.utc)
    if not start <= end <= now.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("daily event query has invalid/future boundaries")
    output_dir.mkdir(parents=True)
    index = search_announcement_window(symbol, start.isoformat(), end.isoformat(), issuer_name=issuer_name)
    validate_cninfo_announcement_window(index["announcements"], start.isoformat(), end.isoformat())
    if (index["parameters"]["stock"].split(",")[0] != symbol
            or index["parameters"]["seDate"] != f"{start}~{end}"
            or index["total_announcements"] != len(index["announcements"])):
        raise ValueError("official daily event index identity/window/count mismatch")
    index_path = output_dir / "cninfo-index.json"
    write_new_json(index_path, index)
    refs = [{"id": f"daily-index-{symbol}", "path": index_path.relative_to(root).as_posix(),
             "sha256": sha256_file(index_path), "source_url": index["url"]}]
    reviews = []
    for item in index["announcements"]:
        if str(item["secCode"]) != symbol:
            raise ValueError("daily event announcement issuer mismatch")
        url = urljoin(PDF_BASE_URL, item["adjunctUrl"])
        if urlparse(url).hostname != "static.cninfo.com.cn" or urlparse(url).scheme != "https":
            raise ValueError("daily event original is outside official disclosure host")
        identity = str(item["announcementId"])
        if not identity.isdigit():
            raise ValueError("daily event announcement ID must be numeric")
        original = output_dir / f"{symbol}-{identity}.pdf"
        digest = download_disclosure_pdf(url, original)
        validate_pdf_original(original)
        if sha256_file(original) != digest:
            raise ValueError("Official PDF changed after download")
        ref = dict(id=f"cninfo:{identity}", path=original.relative_to(root).as_posix(),
                   sha256=digest, source_url=url)
        refs.append(ref)
        reviews.append(AnnouncementReview(announcement_id=identity,
            published_at=datetime.fromtimestamp(item["announcementTime"]/1000, ZoneInfo("Asia/Shanghai")),
            title=item["announcementTitle"], source_url=url, rule_kind="unknown",
            review_status=REVIEW_PENDING_HUMAN_REVIEW, materiality_candidate=True,
            pre_model=False, evidence_refs=(ref,),
            notes="原件已归档；是否影响原论点、预测或估值尚待版本绑定材料性复核。"))
    acquired = datetime.now(timezone.utc)
    scan = EventScanResult(schema_version=EVENT_SCAN_SCHEMA, symbol=symbol, provider="cninfo",
        scan_from=start, scan_to=end, validity_from=start, validity_to=end,
        status=SCAN_PENDING_HUMAN_REVIEW, coverage_status=COVERAGE_COMPLETE,
        pre_model_review_status=PRE_MODEL_NONE, announcements=tuple(reviews),
        blockers=("This acquired query window does not replace earlier event/model/G3 reviews.",),
        evidence_refs=tuple(refs), retrieved_at=acquired, parser_version="cninfo-announcement-window-v1")
    scan_path = output_dir / "event-scan.json"
    write_new_json(scan_path, scan.as_policy())
    result = dict(schema_version="daily-event-observation-v1", symbol=symbol, action="no_order",
        scan_from=start.isoformat(), scan_to=end.isoformat(), acquired_at=acquired.isoformat(),
        announcement_count=len(reviews), collection_status="OFFICIAL_QUERY_ARCHIVED",
        index_representation="PARSED_OFFICIAL_QUERY_NOT_RAW_HTTP_BYTES",
        timestamp_assurance="PROVIDER_DATE_METADATA_NOT_INTRADAY_AVAILABILITY",
        pagination_complete=True, materiality_approved=False, model_revalidated=False,
        research_date_advanced=False, earlier_reviews_preserved=True,
        scan_binding=dict(path=scan_path.relative_to(root).as_posix(), sha256=sha256_file(scan_path)),
        source_bindings=refs,
        next_step="Bind the full earlier and incremental event windows to exact model/assumptions, then review; do not advance research date automatically.")
    write_new_json(output_dir / "observation.json", result)
    return result

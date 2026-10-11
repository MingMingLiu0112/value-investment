"""Archive a manual official query using the existing M5 scan contract."""
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import json
import shutil

from .common import require_inside, write_new_json, sha256_file
from ...disclosures import (search_announcement_window, validate_cninfo_announcement_window,
    PDF_BASE_URL, SEARCH_URL, MAX_CNINFO_RAW_RESPONSE_BYTES, MAX_CNINFO_RAW_TOTAL_BYTES,
    MAX_CNINFO_RAW_REQUESTS)
from ...infrastructure.filings.official_pdf import download_official_pdf as download_disclosure_pdf, validate_pdf_original
from ...event_scan import (AnnouncementReview, EventScanResult, EVENT_SCAN_SCHEMA,
    COVERAGE_COMPLETE, PRE_MODEL_NONE, SCAN_PENDING_HUMAN_REVIEW, REVIEW_PENDING_HUMAN_REVIEW)


def collect_daily_event_observation(*, root: Path, symbol: str, issuer_name: str,
                                    start: date, end: date, output_dir: Path,
                                    retain_raw_index: bool = False) -> dict:
    root = root.resolve()
    runtime_root = require_inside(root, root / "runtime", "daily runtime root")
    output_dir = require_inside(runtime_root, output_dir, "daily event archive")
    if output_dir.exists():
        raise FileExistsError("daily event archive already exists")
    now = datetime.now(timezone.utc)
    if not start <= end <= now.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("daily event query has invalid/future boundaries")
    output_dir.mkdir(parents=True)
    raw_records = []
    raw_bytes = 0

    def check_json_space(payload):
        size = len((json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        if size > MAX_CNINFO_RAW_TOTAL_BYTES:
            raise ValueError("CNINFO raw archive JSON exceeds byte limit")
        if shutil.disk_usage(output_dir).free - size < 2 * 1024**3:
            raise OSError("Low disk: preserve 2 GiB reserve for CNINFO archive JSON")

    def retain(body, metadata):
        nonlocal raw_bytes
        if (not isinstance(body, bytes) or not body or len(body) > MAX_CNINFO_RAW_RESPONSE_BYTES
                or len(raw_records) >= MAX_CNINFO_RAW_REQUESTS
                or raw_bytes + len(body) > MAX_CNINFO_RAW_TOTAL_BYTES):
            raise ValueError("CNINFO raw archive exceeds response/request/total bounds")
        acquired_at = datetime.fromisoformat(metadata["acquired_at"])
        if (acquired_at.tzinfo is None or not now <= acquired_at <= datetime.now(timezone.utc)
                or metadata.get("url") != SEARCH_URL or metadata.get("method") != "POST"
                or metadata.get("page") != int(metadata["request"]["pageNum"])):
            raise ValueError("CNINFO raw acquisition metadata mismatch")
        if len(json.dumps(metadata, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 32 * 1024:
            raise ValueError("CNINFO raw acquisition metadata exceeds byte limit")
        raw_dir = require_inside(output_dir, output_dir / "raw-index", "raw index archive")
        raw_dir.mkdir(exist_ok=True)
        if shutil.disk_usage(raw_dir).free - len(body) - 64 * 1024 < 2 * 1024**3:
            raise OSError("Low disk: preserve 2 GiB reserve for raw CNINFO archive")
        path = require_inside(raw_dir, raw_dir / f"response-{len(raw_records) + 1:04d}.bin", "raw body")
        with path.open("xb") as handle:
            handle.write(body)
        if (sha256_file(path) != metadata.get("sha256")
                or metadata.get("size_bytes") != len(body)):
            raise ValueError("CNINFO raw archive hash/size mismatch")
        record = {**metadata, "path": path.relative_to(root).as_posix(),
                  "request_kind": "window" if metadata["request"].get("seDate") else "issuer_discovery"}
        metadata_path = path.with_suffix(".json")
        write_new_json(metadata_path, record)
        raw_records.append({**record, "metadata_path": metadata_path.relative_to(root).as_posix(),
                            "metadata_sha256": sha256_file(metadata_path)})
        raw_bytes += len(body)

    options = {"raw_response_sink": retain} if retain_raw_index else {}
    index = search_announcement_window(symbol, start.isoformat(), end.isoformat(),
                                      issuer_name=issuer_name, **options)
    validate_cninfo_announcement_window(index["announcements"], start.isoformat(), end.isoformat())
    if (index["parameters"]["stock"].split(",")[0] != symbol
            or index["parameters"]["seDate"] != f"{start}~{end}"
            or index["total_announcements"] != len(index["announcements"])):
        raise ValueError("official daily event index identity/window/count mismatch")
    if retain_raw_index:
        rows = []
        window_pages = 0
        for record in raw_records:
            path = require_inside(output_dir, root / record["path"], "raw body binding")
            metadata_path = require_inside(output_dir, root / record["metadata_path"], "raw metadata binding")
            if (sha256_file(path) != record["sha256"] or path.stat().st_size != record["size_bytes"]
                    or sha256_file(metadata_path) != record["metadata_sha256"]):
                raise ValueError("CNINFO raw archive changed before scan")
            payload = json.loads(path.read_bytes())
            if record["request_kind"] == "window":
                window_pages += 1
                request = dict(record["request"])
                page = request.pop("pageNum")
                if (page != str(window_pages) or request != index["parameters"]
                        or payload.get("totalAnnouncement") != index["total_announcements"]):
                    raise ValueError("CNINFO raw pagination/request/total mismatch")
                rows.extend(payload.get("announcements") or [])
        if not window_pages or rows != index["announcements"]:
            raise ValueError("CNINFO raw pages missing or inconsistent with parsed index")
    index_path = output_dir / "cninfo-index.json"
    if retain_raw_index:
        check_json_space(index)
    write_new_json(index_path, index)
    refs = [{"id": f"daily-index-{symbol}", "path": index_path.relative_to(root).as_posix(),
             "sha256": sha256_file(index_path), "source_url": index["url"]}]
    if retain_raw_index:
        manifest_path = output_dir / "raw-index-manifest.json"
        manifest = {"schema_version": "cninfo-raw-index-v1", "symbol": symbol,
            "scan_from": start.isoformat(), "scan_to": end.isoformat(), "action": "no_order",
            "pagination_complete": True, "responses": raw_records, "total_bytes": raw_bytes}
        check_json_space(manifest)
        write_new_json(manifest_path, manifest)
        manifest_sha256 = sha256_file(manifest_path)
        refs.append({"id": f"daily-raw-index-manifest-{symbol}",
            "path": manifest_path.relative_to(root).as_posix(), "sha256": manifest_sha256,
            "source_url": SEARCH_URL})
        for number, record in enumerate(raw_records, 1):
            refs.extend([{"id": f"daily-raw-{symbol}-{number}", "path": record["path"],
                "sha256": record["sha256"], "source_url": record["url"]},
                {"id": f"daily-raw-metadata-{symbol}-{number}", "path": record["metadata_path"],
                 "sha256": record["metadata_sha256"], "source_url": record["url"]}])
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
    if retain_raw_index:
        # PDF acquisition may be slow: recheck raw bindings at scan publication.
        if sha256_file(manifest_path) != manifest_sha256:
            raise ValueError("CNINFO raw manifest changed before scan")
        for record in raw_records:
            body_path = require_inside(output_dir, root / record["path"], "raw body binding")
            metadata_path = require_inside(output_dir, root / record["metadata_path"], "raw metadata binding")
            if (sha256_file(body_path) != record["sha256"]
                    or sha256_file(metadata_path) != record["metadata_sha256"]):
                raise ValueError("CNINFO raw archive changed before scan")
    acquired = datetime.now(timezone.utc)
    scan = EventScanResult(schema_version=EVENT_SCAN_SCHEMA, symbol=symbol, provider="cninfo",
        scan_from=start, scan_to=end, validity_from=start, validity_to=end,
        status=SCAN_PENDING_HUMAN_REVIEW, coverage_status=COVERAGE_COMPLETE,
        pre_model_review_status=PRE_MODEL_NONE, announcements=tuple(reviews),
        blockers=("This acquired query window does not replace earlier event/model/G3 reviews.",),
        evidence_refs=tuple(refs), retrieved_at=acquired, parser_version="cninfo-announcement-window-v1")
    scan_path = output_dir / "event-scan.json"
    if retain_raw_index:
        check_json_space(scan.as_policy())
    write_new_json(scan_path, scan.as_policy())
    result = dict(schema_version="daily-event-observation-v1", symbol=symbol, action="no_order",
        scan_from=start.isoformat(), scan_to=end.isoformat(), acquired_at=acquired.isoformat(),
        announcement_count=len(reviews), collection_status="OFFICIAL_QUERY_ARCHIVED",
        index_representation=("PARSED_OFFICIAL_QUERY_WITH_RECEIVED_RESPONSE_CONTENT"
                              if retain_raw_index else "PARSED_OFFICIAL_QUERY_NOT_RAW_HTTP_BYTES"),
        timestamp_assurance="PROVIDER_DATE_METADATA_NOT_INTRADAY_AVAILABILITY",
        pagination_complete=True, materiality_approved=False, model_revalidated=False,
        research_date_advanced=False, earlier_reviews_preserved=True,
        scan_binding=dict(path=scan_path.relative_to(root).as_posix(), sha256=sha256_file(scan_path)),
        source_bindings=refs,
        next_step="Bind the full earlier and incremental event windows to exact model/assumptions, then review; do not advance research date automatically.")
    if retain_raw_index:
        check_json_space(result)
    write_new_json(output_dir / "observation.json", result)
    return result

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
    COVERAGE_COMPLETE, PRE_MODEL_NONE, SCAN_PENDING_HUMAN_REVIEW, REVIEW_PENDING_HUMAN_REVIEW,
    event_scan_from_payload)


def _replay_raw_index(root: Path, archive: Path, records: list[dict], index: dict) -> list[dict]:
    """Replay the collector's retained body/metadata and ordered window pages."""
    if records == []:
        raise ValueError("CNINFO raw pages missing or inconsistent with parsed index")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_CNINFO_RAW_REQUESTS:
        raise ValueError("CNINFO raw response count exceeds bounds")
    total = 0
    for record in records:
        path = require_inside(archive, root / record["path"], "raw body binding")
        metadata_path = require_inside(archive, root / record["metadata_path"], "raw metadata binding")
        size = path.stat().st_size
        total += size
        if (not 0 < size <= MAX_CNINFO_RAW_RESPONSE_BYTES
                or total > MAX_CNINFO_RAW_TOTAL_BYTES or metadata_path.stat().st_size > 32 * 1024):
            raise ValueError("CNINFO raw archive exceeds byte bounds")
        if size != record["size_bytes"]:
            raise ValueError("CNINFO raw archive changed before scan")
    rows = []
    window_pages = 0
    for record in records:
        path = require_inside(archive, root / record["path"], "raw body binding")
        metadata_path = require_inside(archive, root / record["metadata_path"], "raw metadata binding")
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
    return rows


def verify_retained_event_coverage(root: Path, observation: dict, *, symbol: str,
                                   required_from: date, required_to: date, now: datetime) -> dict:
    """Read-only replay of retained CNINFO coverage, never materiality approval.

    Hashes bind local artifacts, not an external signature or timestamp authority.
    Legacy observations without received raw responses cannot prove coverage here.
    """
    try:
        return _verify_retained_event_coverage(root.resolve(), observation, symbol=symbol,
            required_from=required_from, required_to=required_to, now=now)
    except (OSError, KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError("Retained event coverage is unavailable or malformed") from error


def _verify_retained_event_coverage(root, observation, *, symbol, required_from, required_to, now):
    china = ZoneInfo("Asia/Shanghai")

    def stamp(value):
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None or result > now:
            raise ValueError("Retained event acquisition must be aware and available")
        return result

    def bound(ref, limit=MAX_CNINFO_RAW_TOTAL_BYTES):
        path = require_inside(root, root / ref["path"], "retained event source")
        if not 0 < path.stat().st_size <= limit:
            raise ValueError("Retained event source exceeds byte bounds")
        if sha256_file(path) != ref["sha256"]:
            raise ValueError("Retained event source hash mismatch")
        return path

    def document(ref, limit=MAX_CNINFO_RAW_TOTAL_BYTES):
        payload = json.loads(bound(ref, limit).read_bytes())
        if not isinstance(payload, dict):
            raise ValueError("Retained event document must be an object")
        return payload

    if (now.utcoffset() is None or type(required_from) is not date or type(required_to) is not date
            or not required_from <= required_to < now.astimezone(china).date()
            or not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit()):
        raise ValueError("Retained coverage requires an elapsed exact symbol/date window")
    start, end = required_from.isoformat(), required_to.isoformat()
    acquired = stamp(observation["acquired_at"])
    if (observation.get("schema_version") != "daily-event-observation-v1"
            or observation.get("symbol") != symbol or observation.get("action") != "no_order"
            or observation.get("scan_from") != start or observation.get("scan_to") != end
            or observation.get("pagination_complete") is not True
            or observation.get("full_calendar_window_elapsed") is not True
            or observation.get("collection_status") != "OFFICIAL_QUERY_ARCHIVED"
            or observation.get("index_representation") != "PARSED_OFFICIAL_QUERY_WITH_RECEIVED_RESPONSE_CONTENT"
            or required_to >= acquired.astimezone(china).date()):
        raise ValueError("Retained observation window/coverage mismatch")
    scan_ref = observation["scan_binding"]
    scan = event_scan_from_payload(document(scan_ref))
    if (scan.symbol != symbol or scan.provider != "cninfo" or scan.scan_from != required_from
            or scan.scan_to != required_to or scan.validity_from != required_from
            or scan.validity_to != required_to or scan.retrieved_at != acquired
            or scan.coverage_status != COVERAGE_COMPLETE
            or observation["source_bindings"] != list(scan.evidence_refs)
            or type(observation["announcement_count"]) is not int
            or observation["announcement_count"] != len(scan.announcements)):
        raise ValueError("Retained scan identity/window/coverage mismatch")
    refs = {ref["id"]: ref for ref in scan.evidence_refs}
    if len(refs) != len(scan.evidence_refs):
        raise ValueError("Duplicate retained source identity")
    index = document(refs[f"daily-index-{symbol}"])
    manifest = document(refs[f"daily-raw-index-manifest-{symbol}"])
    parameters = index["parameters"]
    stock = parameters["stock"].split(",")
    expected_column = "sse" if symbol.startswith("6") else "szse" if symbol.startswith(("0", "3")) else ""
    expected_parameters = {"pageSize", "tabName", "column", "stock", "searchkey", "secid",
                           "plate", "category", "trade", "seDate", "sortName", "sortType", "isHLtitle"}
    if (index.get("url") != SEARCH_URL or parameters["stock"].split(",")[0] != symbol
            or len(stock) != 2 or not stock[1]
            or parameters.get("seDate") != f"{start}~{end}"
            or parameters.get("column") != expected_column
            or set(parameters) != expected_parameters or parameters.get("tabName") != "fulltext"
            or parameters.get("isHLtitle") != "true"
            or any(parameters.get(key, "") for key in ("searchkey", "category", "trade", "secid", "plate"))
            or manifest.get("schema_version") != "cninfo-raw-index-v1"
            or manifest.get("symbol") != symbol or manifest.get("action") != "no_order"
            or manifest.get("scan_from") != start or manifest.get("scan_to") != end
            or manifest.get("pagination_complete") is not True):
        raise ValueError("Retained index/manifest identity or filtering mismatch")
    page_size = int(parameters["pageSize"])
    if parameters["pageSize"] != str(page_size) or not 1 <= page_size <= 30:
        raise ValueError("Retained page size must be 1..30")
    records = manifest["responses"]
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_CNINFO_RAW_REQUESTS:
        raise ValueError("Retained raw response count is invalid")
    archive = bound(scan_ref).parent
    rows = _replay_raw_index(root, archive, records, index)
    for ref in scan.evidence_refs:
        limit = (32 * 1024 if ref["id"].startswith("daily-raw-metadata-") else
                 MAX_CNINFO_RAW_RESPONSE_BYTES if ref["id"].startswith("daily-raw-")
                 and not ref["id"].startswith("daily-raw-index-manifest-") else
                 32 * 1024 * 1024 if ref["id"].startswith("cninfo:") else MAX_CNINFO_RAW_TOTAL_BYTES)
        bound(ref, limit)
    total_bytes, paths, org_ids, window_pages = 0, set(), set(), 0
    for number, record in enumerate(records, 1):
        metadata_ref = refs[f"daily-raw-metadata-{symbol}-{number}"]
        body_ref = refs[f"daily-raw-{symbol}-{number}"]
        metadata = document(metadata_ref, 32 * 1024)
        if (metadata != {key: value for key, value in record.items()
                         if key not in {"metadata_path", "metadata_sha256"}}
                or metadata_ref["path"] != record["metadata_path"]
                or metadata_ref["sha256"] != record["metadata_sha256"]
                or body_ref["path"] != record["path"] or body_ref["sha256"] != record["sha256"]
                or record["path"] in paths or record["metadata_path"] in paths
                or record["url"] != SEARCH_URL or record["method"] != "POST"
                or type(record["page"]) is not int or record["page"] != int(record["request"]["pageNum"])
                or record["request_kind"] not in {"window", "issuer_discovery"}
                or bool(record["request"].get("seDate")) != (record["request_kind"] == "window")
                or type(record["size_bytes"]) is not int
                or not 0 < record["size_bytes"] <= MAX_CNINFO_RAW_RESPONSE_BYTES):
            raise ValueError("Retained raw metadata identity mismatch")
        paths.update((record["path"], record["metadata_path"]))
        received = stamp(record["acquired_at"])
        if received > acquired or (record["request_kind"] == "window"
                and required_to >= received.astimezone(china).date()):
            raise ValueError("Retained raw response predates full window or follows observation")
        payload = document(body_ref, MAX_CNINFO_RAW_RESPONSE_BYTES)
        records_on_page = payload.get("announcements") or []
        if not isinstance(records_on_page, list):
            raise ValueError("Retained raw announcements must be a list")
        for row in records_on_page:
            if str(row.get("secCode")) == symbol and row.get("orgId"):
                org_ids.add(str(row["orgId"]))
        if record["request_kind"] == "window":
            window_pages += 1
            total = index["total_announcements"]
            if (type(total) is not int or total < 0
                    or type(payload.get("totalAnnouncement")) is not int):
                raise ValueError("Retained total must be a nonnegative integer")
            expected_pages = max(1, (total + page_size - 1) // page_size)
            expected_count = min(page_size, max(0, total - (window_pages - 1) * page_size))
            if (window_pages > expected_pages or len(records_on_page) != expected_count
                    or ("hasMore" in payload and (type(payload["hasMore"]) is not bool
                        or payload["hasMore"] != (window_pages < expected_pages)))):
                raise ValueError("Retained page count/hasMore mismatch")
        total_bytes += record["size_bytes"]
    if org_ids != {stock[1]}:
        raise ValueError("Retained issuer orgId lacks unambiguous exact-code evidence")
    if window_pages != max(1, (index["total_announcements"] + page_size - 1) // page_size):
        raise ValueError("Retained window page count mismatch")
    if (type(manifest["total_bytes"]) is not int or total_bytes != manifest["total_bytes"]
            or total_bytes > MAX_CNINFO_RAW_TOTAL_BYTES
            or type(index["total_announcements"]) is not int or index["total_announcements"] != len(rows)):
        raise ValueError("Retained raw totals mismatch")
    validate_cninfo_announcement_window(rows, start, end)
    indexed = {str(row["announcementId"]): row for row in rows}
    if (len(indexed) != len(rows) or any(not key.isdigit() for key in indexed)
            or any(str(row["secCode"]) != symbol for row in rows)
            or set(indexed) != {item.announcement_id for item in scan.announcements}):
        raise ValueError("Retained announcement set/issuer mismatch")
    for item in scan.announcements:
        row = indexed[item.announcement_id]
        url = urljoin(PDF_BASE_URL, row["adjunctUrl"])
        if (urlparse(url).scheme != "https" or urlparse(url).hostname != "static.cninfo.com.cn"
                or item.source_url != url or item.title != row["announcementTitle"]
                or item.published_at != datetime.fromtimestamp(row["announcementTime"] / 1000, china)
                or not item.evidence_refs):
            raise ValueError("Retained announcement content mismatch")
        for ref in item.evidence_refs:
            if ref.get("source_url") != url or refs.get(ref["id"]) != ref:
                raise ValueError("Retained announcement original binding mismatch")
            validate_pdf_original(bound(ref, 32 * 1024 * 1024))
    return {"symbol": symbol, "scan_from": start, "scan_to": end,
            "coverage_status": COVERAGE_COMPLETE, "scan_binding": dict(scan_ref),
            "action": "no_order", "materiality_approved": False, "model_revalidated": False}


def collect_daily_event_observation(*, root: Path, symbol: str, issuer_name: str,
                                    start: date, end: date, output_dir: Path,
                                    retain_raw_index: bool = False,
                                    retained_originals: list[dict] | None = None) -> dict:
    root = root.resolve()
    runtime_root = require_inside(root, root / "runtime", "daily runtime root")
    output_dir = require_inside(runtime_root, output_dir, "daily event archive")
    if output_dir.exists():
        raise FileExistsError("daily event archive already exists")
    now = datetime.now(timezone.utc)
    retained = {}
    for binding in retained_originals or []:
        url = binding.get('source_url')
        path = require_inside(runtime_root, root / binding['path'], 'retained official original')
        if (not isinstance(url, str) or urlparse(url).scheme != 'https'
                or urlparse(url).hostname != 'static.cninfo.com.cn'
                or not path.is_file() or sha256_file(path) != binding.get('sha256')):
            raise ValueError('retained official original URL/hash mismatch')
        if url in retained and retained[url] != binding:
            raise ValueError('conflicting retained official originals')
        retained[url] = binding
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
        _replay_raw_index(root, output_dir, raw_records, index)
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
        cached = retained.get(url)
        original = (root / cached['path'] if cached else output_dir / f"{symbol}-{identity}.pdf")
        digest = cached['sha256'] if cached else download_disclosure_pdf(url, original)
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
        full_calendar_window_elapsed=end < now.astimezone(ZoneInfo('Asia/Shanghai')).date(),
        reused_original_count=sum(ref.get('source_url') in retained for ref in refs
                                  if ref['id'].startswith('cninfo:')),
        pagination_complete=True, materiality_approved=False, model_revalidated=False,
        research_date_advanced=False, earlier_reviews_preserved=True,
        scan_binding=dict(path=scan_path.relative_to(root).as_posix(), sha256=sha256_file(scan_path)),
        source_bindings=refs,
        next_step="Bind the full earlier and incremental event windows to exact model/assumptions, then review; do not advance research date automatically.")
    if retain_raw_index:
        check_json_space(result)
    write_new_json(output_dir / "observation.json", result)
    return result

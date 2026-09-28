"""Append-only, source-bound public observations for prospective case checkpoints."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .common import require_inside
from .prospective_registration import verify_prospective_registration_receipt


def _read_pinned(root: Path, path: str, digest: str, label: str) -> tuple[Path, bytes]:
    if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"{label} needs path and SHA-256")
    file = require_inside(root, root / path, label)
    data = file.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest.lower():
        raise ValueError(f"{label} byte hash mismatch")
    return file, data


def _time(value: str, label: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _supersession_sha256(
    *, target: Path, case_id: str, observation_id: str, source_document_id: str,
    source_sha256: str, now: datetime,
) -> str | None:
    """Validate one predecessor without allowing a mutable observation chain."""
    if observation_id is None:
        return None
    prior_path = require_inside(target.parent.parent.parent, target / f"{observation_id}.json", "superseded observation")
    prior_bytes = prior_path.read_bytes()
    prior = json.loads(prior_bytes)
    if (
        prior.get("case_id") != case_id
        or prior.get("observation_id") != observation_id
        or prior.get("source_document_id") != source_document_id
        or prior.get("source_sha256") != source_sha256
    ):
        raise ValueError("superseded observation must be an earlier record for the same source")
    prior_created_value = prior.get("receipt_created_at", prior.get("record_created_at"))
    if prior_created_value is not None and _time(prior_created_value, "prior observation creation time") >= now:
        raise ValueError("successor record creation time must be later than its predecessor")
    return hashlib.sha256(prior_bytes).hexdigest()


def _observation_classification(source_available_at: datetime, observation_start_at: datetime) -> str:
    return (
        "PREEXISTING_PUBLIC_DOCUMENT_REOBSERVED_AFTER_START"
        if source_available_at <= observation_start_at
        else "POST_REGISTRATION_DISCLOSURE"
    )


def append_cninfo_observation(
    *, root: Path, registration_path: str, registration_sha256: str,
    scan_receipt_path: str, scan_receipt_sha256: str,
    interpretation_path: str, interpretation_sha256: str,
    symbol: str, document_id: str, output_dir: Path,
    supersedes_observation_id: str | None = None,
) -> dict[str, Any]:
    """Bind a CNINFO raw response and original PDF; never infer materiality."""
    target = require_inside(root, output_dir, "observation output")
    if not target.is_relative_to((root / "runtime" / "prospective-observations").resolve()):
        raise ValueError("observations must remain under runtime/prospective-observations")
    registration, policy = verify_prospective_registration_receipt(
        root=root, receipt_path=registration_path, receipt_sha256=registration_sha256,
        plan_path="config/prospective-research-observation-plan-v2.json",
    )
    cases = [case for case in policy.cases if case.symbol == symbol]
    if len(cases) != 1:
        raise ValueError("issuer is not in the prospective registration")
    case_policy = cases[0]
    case = {
        "case_id": case_policy.case_id, "symbol": case_policy.symbol,
        "observation_start_at": case_policy.observation_start_at.isoformat(),
    }
    start = case_policy.observation_start_at
    _, receipt_bytes = _read_pinned(root, scan_receipt_path, scan_receipt_sha256, "scan receipt")
    receipt = json.loads(receipt_bytes)
    if receipt.get("schema") != "track-c-cninfo-post-start-readonly-v1" or receipt.get("action") != "no_order":
        raise ValueError("post-start read-only scan receipt required")
    receipt_created = _time(receipt.get("created_utc", ""), "scan receipt created time")
    receipt_start = _time(receipt.get("observation_start", ""), "scan observation start")
    if receipt_start != start:
        raise ValueError("scan receipt observation start differs from registration")
    index_times = []
    for item in receipt.get("indexes", []):
        sent = _time(item.get("sent_utc", ""), "index request sent time")
        received = _time(item.get("received_utc", ""), "index response received time")
        if item.get("http_status") != 200 or sent < start or received < sent:
            raise ValueError("index request/response time order is invalid")
        index_times.append((sent, received))
    _, interpretation_bytes = _read_pinned(root, interpretation_path, interpretation_sha256, "scan interpretation")
    interpretation = json.loads(interpretation_bytes)
    if interpretation.get("schema") != "track-c-cninfo-raw-interpretation-v1":
        raise ValueError("unsupported scan interpretation")
    scanned = [item for item in receipt["indexes"] if item["symbol"] == symbol]
    interpreted = [item for item in interpretation["rows"] if item["symbol"] == symbol]
    if len(scanned) != 1 or len(interpreted) != 1:
        raise ValueError("scan issuer identity is ambiguous")
    scan, parsed = scanned[0], interpreted[0]
    if scan["raw_sha256"] != parsed["raw_sha256"] or parsed["has_more"] or not parsed["exact_symbol"]:
        raise ValueError("scan interpretation differs from raw response scope")
    _, raw_bytes = _read_pinned(root, scan["raw_path"], scan["raw_sha256"], "raw CNINFO response")
    raw = json.loads(raw_bytes)
    matches = [item for item in raw.get("announcements") or [] if item.get("announcementId") == document_id]
    if len(matches) != 1 or matches[0].get("secCode") != symbol or document_id not in parsed["ids"]:
        raise ValueError("document identity is not bound to the raw response")
    if raw.get("hasMore") or raw.get("totalRecordNum") != parsed["total"]:
        raise ValueError("raw response pagination or total differs from interpretation")
    pdf = receipt.get("pdf")
    if not isinstance(pdf, dict) or pdf.get("document_id") != f"cninfo:{document_id}" or pdf.get("http_status") != 200:
        raise ValueError("scan receipt does not bind the requested PDF")
    expected_url = "https://static.cninfo.com.cn/" + matches[0]["adjunctUrl"]
    if pdf.get("url") != expected_url:
        raise ValueError("PDF URL differs from official index")
    _, pdf_bytes = _read_pinned(root, pdf["path"], pdf["sha256"], "original PDF")
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) != pdf.get("bytes"):
        raise ValueError("original PDF signature or size mismatch")
    pdf_sent = _time(pdf.get("sent_utc", ""), "PDF request sent time")
    observed = _time(pdf.get("received_utc", ""), "PDF received time")
    now = datetime.now(timezone.utc)
    if (
        pdf.get("http_status") != 200
        or pdf_sent < start
        or observed < pdf_sent
        or any(received > pdf_sent for _, received in index_times)
        or receipt_created < observed
        or receipt_created > now
        or observed > now
    ):
        raise ValueError("PDF was not observed within the prospective period")
    indexed_at = datetime.fromtimestamp(matches[0]["announcementTime"] / 1000, timezone.utc)
    local_date = indexed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    safe_available = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=ZoneInfo("Asia/Shanghai"))
    if safe_available > observed:
        raise ValueError("source was not conservatively available at observation time")
    observation_id = "prospective-" + hashlib.sha256(
        f"v2:{case['case_id']}:{document_id}:{pdf['sha256']}:{observed.isoformat()}:{supersedes_observation_id or ''}".encode("utf-8")
    ).hexdigest()[:32]
    supersedes_sha256 = _supersession_sha256(
        target=target, case_id=case["case_id"], observation_id=supersedes_observation_id,
        source_document_id=f"cninfo:{document_id}", source_sha256=pdf["sha256"], now=now,
    )
    record_created_at = datetime.now(timezone.utc)
    record = {
        "schema_version": "prospective-public-observation-v2", "case_id": case["case_id"],
        "symbol": symbol, "observation_id": observation_id, "observed_at": observed.isoformat(),
        "record_created_at": record_created_at.isoformat(),
        "receipt_created_at": record_created_at.isoformat(),
        "source_available_at": safe_available.isoformat(),
        "source_time_precision": "DATE_ONLY_CONSERVATIVE_NEXT_DAY",
        "source_document_id": f"cninfo:{document_id}", "source_sha256": pdf["sha256"],
        "source_url": expected_url, "source_path": pdf["path"],
        "scan_receipt_sha256": scan_receipt_sha256,
        "raw_response_sha256": scan["raw_sha256"],
        "raw_response_path": scan["raw_path"],
        "registration_receipt_sha256": registration_sha256,
        "fact_type": "public_capital_allocation_notice", "dependency_nodes": ["capital_allocation", "share_denominator"],
        "dependency_status": "UNASSESSED", "materiality": "UNDETERMINED",
        "classification": _observation_classification(safe_available, start),
        "supersedes_observation_id": supersedes_observation_id, "action": "no_order",
    }
    if supersedes_sha256 is not None:
        record["supersedes_observation_sha256"] = supersedes_sha256
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{observation_id}.json"
    if path.exists():
        existing_bytes = path.read_bytes()
        existing = json.loads(existing_bytes)
        replay = record | {"record_created_at": existing.get("record_created_at")}
        if "receipt_created_at" in existing:
            replay["receipt_created_at"] = existing["receipt_created_at"]
        else:
            replay.pop("receipt_created_at", None)
        replay_bytes = (json.dumps(replay, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if existing_bytes == replay_bytes:
            return existing | {"path": str(path), "sha256": hashlib.sha256(existing_bytes).hexdigest()}
        raise ValueError("observation id conflicts with existing immutable bytes")
    encoded = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if supersedes_observation_id is not None:
        for existing_path in target.glob("prospective-*.json"):
            existing = json.loads(existing_path.read_bytes())
            if existing.get("case_id") != case["case_id"] or existing.get("supersedes_observation_id") != supersedes_observation_id:
                continue
            if existing_path == path and existing_path.read_bytes() == encoded:
                return record | {"path": str(path), "sha256": hashlib.sha256(encoded).hexdigest()}
            raise ValueError("observation supersession would create a fork or duplicate successor")
    try:
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise ValueError("observation id conflicts with existing immutable bytes") from None
    return record | {"path": str(path), "sha256": hashlib.sha256(encoded).hexdigest()}


def append_reviewed_cninfo_notice_observation(
    *, root: Path, registration_path: str, registration_sha256: str,
    scan_receipt_path: str, scan_receipt_sha256: str,
    document_review_path: str, document_review_sha256: str,
    symbol: str, document_id: str, output_dir: Path,
    supersedes_observation_id: str | None = None,
) -> dict[str, Any]:
    """Append a reviewed notice from the bounded exact-issuer scan contract."""
    target = require_inside(root, output_dir, "observation output")
    if not target.is_relative_to((root / "runtime" / "prospective-observations").resolve()):
        raise ValueError("observations must remain under runtime/prospective-observations")
    _, registration = verify_prospective_registration_receipt(
        root=root, receipt_path=registration_path, receipt_sha256=registration_sha256,
        plan_path="config/prospective-research-observation-plan-v2.json",
    )
    cases = [case for case in registration.cases if case.symbol == symbol]
    if len(cases) != 1:
        raise ValueError("issuer is not in the prospective registration")
    case = cases[0]
    _, receipt_bytes = _read_pinned(root, scan_receipt_path, scan_receipt_sha256, "scan receipt")
    receipt = json.loads(receipt_bytes)
    if receipt.get("schema_version") != "cninfo-exact-issuer-single-day-receipt-v1" or receipt.get("action") != "no_order":
        raise ValueError("bounded exact-issuer scan receipt required")
    scan_date = receipt.get("scan_date")
    if (
        receipt.get("symbol") != symbol
        or receipt.get("exact_query_date_filter") != f"{scan_date}~{scan_date}"
        or receipt.get("pagination", {}).get("terminal_has_more") is not False
        or receipt.get("pagination", {}).get("returned_announcements") != 1
        or receipt.get("pagination", {}).get("total_announcements") != 1
        or receipt.get("pagination", {}).get("page_count") != 1
    ):
        raise ValueError("scan scope or pagination is not a single exact issuer result")
    request_rows = receipt.get("requests", [])
    page_refs = receipt.get("pagination", {}).get("page_refs", [])
    if len(request_rows) != 1 or len(page_refs) != 1:
        raise ValueError("scan request/page evidence is ambiguous")
    request = request_rows[0]
    page = page_refs[0]
    sent = _time(request.get("request_started_at", ""), "scan request start")
    received = _time(request.get("response_received_at", ""), "scan response receipt")
    if (
        request.get("http_status") != 200
        or request.get("request_parameters", {}).get("stock", "").split(",")[0] != symbol
        or request.get("request_parameters", {}).get("seDate") != f"{scan_date}~{scan_date}"
        or received < sent
        or _time(receipt.get("china_local_scan_started_at", ""), "China-local scan start") > sent
        or page.get("http_status") != 200
        or page.get("has_more") is not False
        or page.get("returned_count") != 1
    ):
        raise ValueError("scan request time, identity, or terminal-page evidence is invalid")
    _, index_bytes = _read_pinned(root, receipt["index_path"], receipt["index_sha256"], "scan index")
    index = json.loads(index_bytes)
    if index.get("symbol") != symbol or index.get("scan_from") != scan_date or index.get("scan_to") != scan_date:
        raise ValueError("single-day index scope differs from its receipt")
    _, raw_bytes = _read_pinned(root, page["path"], page["sha256"], "raw CNINFO response")
    raw = json.loads(raw_bytes)
    rows = raw.get("announcements") or []
    matches = [row for row in rows if row.get("announcementId") == document_id]
    if len(rows) != 1 or len(matches) != 1 or matches[0].get("secCode") != symbol:
        raise ValueError("requested document is not uniquely bound to the exact-issuer response")
    if raw.get("totalRecordNum") != 1 or raw.get("hasMore") is True:
        raise ValueError("raw CNINFO response is incomplete")
    _, review_bytes = _read_pinned(root, document_review_path, document_review_sha256, "document review")
    review = json.loads(review_bytes)
    source = review.get("source", {})
    reviewed_at = _time(review.get("reviewed_at_china", ""), "document review time")
    if (
        review.get("schema_version") != "cninfo-document-review-v1"
        or source.get("symbol") != symbol
        or source.get("announcement_id") != document_id
        or source.get("announcement_date") != scan_date
        or source.get("scan_receipt_sha256") != scan_receipt_sha256
        or source.get("scan_index_sha256") != receipt["index_sha256"]
        or source.get("raw_scan_response_sha256") != page["sha256"]
        or review.get("review_clock") != "local process clock; not independently timestamp-attested"
        or source.get("pdf_sha256") is None
        or reviewed_at.astimezone(timezone.utc) < received.astimezone(timezone.utc)
    ):
        raise ValueError("review does not bind the scan and source document")
    expected_url = "https://static.cninfo.com.cn/" + matches[0]["adjunctUrl"]
    if source.get("url") != expected_url:
        raise ValueError("reviewed PDF URL differs from the official index")
    _, pdf_bytes = _read_pinned(root, source["pdf_path"], source["pdf_sha256"], "original PDF")
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) != source.get("pdf_bytes"):
        raise ValueError("reviewed original PDF signature or size mismatch")
    now = datetime.now(timezone.utc)
    if reviewed_at > now or received > now:
        raise ValueError("scan or review time cannot be in the future")
    indexed_at = datetime.fromtimestamp(matches[0]["announcementTime"] / 1000, timezone.utc)
    source_date = indexed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    safe_available = datetime.combine(source_date + timedelta(days=1), time.min, tzinfo=ZoneInfo("Asia/Shanghai"))
    if safe_available > received or safe_available > reviewed_at:
        raise ValueError("source was not conservatively available before observation")
    if reviewed_at < case.observation_start_at:
        raise ValueError("document review predates the prospective observation start")
    supersedes_sha256 = _supersession_sha256(
        target=target, case_id=case.case_id, observation_id=supersedes_observation_id,
        source_document_id=f"cninfo:{document_id}", source_sha256=source["pdf_sha256"], now=now,
    )
    observation_id = "prospective-" + hashlib.sha256(
        f"v2:{case.case_id}:{document_id}:{source['pdf_sha256']}:{reviewed_at.isoformat()}:{supersedes_observation_id or ''}".encode("utf-8")
    ).hexdigest()[:32]
    record = {
        "schema_version": "prospective-public-observation-v2",
        "case_id": case.case_id, "symbol": symbol, "observation_id": observation_id,
        "observed_at": reviewed_at.isoformat(),
        "record_created_at": now.isoformat(),
        "receipt_created_at": now.isoformat(),
        "record_time_assurance": "PROCESS_CLOCK_ONLY_UNATTESTED",
        "source_available_at": safe_available.isoformat(),
        "source_time_precision": "DATE_ONLY_CONSERVATIVE_NEXT_DAY",
        "source_document_id": f"cninfo:{document_id}",
        "source_sha256": source["pdf_sha256"], "source_url": expected_url,
        "source_path": source["pdf_path"],
        "scan_receipt_sha256": scan_receipt_sha256,
        "scan_index_sha256": receipt["index_sha256"],
        "raw_response_sha256": page["sha256"], "raw_response_path": page["path"],
        "document_review_sha256": document_review_sha256,
        "registration_receipt_sha256": registration_sha256,
        "fact_type": "public_governance_notice",
        "dependency_nodes": ["capital_allocation", "share_denominator"],
        "dependency_status": "UNASSESSED", "materiality": "UNDETERMINED",
        "classification": _observation_classification(safe_available, case.observation_start_at),
        "supersedes_observation_id": supersedes_observation_id, "action": "no_order",
    }
    if supersedes_sha256 is not None:
        record["supersedes_observation_sha256"] = supersedes_sha256
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{observation_id}.json"
    encoded = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if path.exists():
        existing_bytes = path.read_bytes()
        existing = json.loads(existing_bytes)
        replay = record | {"record_created_at": existing.get("record_created_at")}
        if "receipt_created_at" in existing:
            replay["receipt_created_at"] = existing["receipt_created_at"]
        else:
            replay.pop("receipt_created_at", None)
        replay_bytes = (json.dumps(replay, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if existing_bytes == replay_bytes:
            return existing | {"path": str(path), "sha256": hashlib.sha256(existing_bytes).hexdigest()}
        raise ValueError("observation id conflicts with existing immutable bytes")
    if supersedes_observation_id is not None:
        for existing_path in target.glob("prospective-*.json"):
            existing = json.loads(existing_path.read_bytes())
            if existing.get("case_id") != case.case_id or existing.get("supersedes_observation_id") != supersedes_observation_id:
                continue
            if existing_path == path and existing_path.read_bytes() == encoded:
                return record | {"path": str(path), "sha256": hashlib.sha256(encoded).hexdigest()}
            raise ValueError("observation supersession would create a fork or duplicate successor")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
    return record | {"path": str(path), "sha256": hashlib.sha256(encoded).hexdigest()}


def observations_at(
    *, root: Path, directory: Path, case_id: str, evaluation_cutoff: datetime,
    trusted_hashes: Mapping[str, str],
    observation_paths: tuple[Path, ...] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Exclude future disclosures and post-cutoff observations.

    When ``observation_paths`` is supplied, it is the complete input set. This
    keeps product publication driven by an explicit manifest instead of an
    implicit directory scan. The legacy omitted-argument behavior remains for
    callers that already provide a trusted hash map for a whole directory.
    """
    if evaluation_cutoff.tzinfo is None:
        raise ValueError("evaluation cutoff must be timezone-aware")
    if evaluation_cutoff.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("evaluation cutoff cannot be in the future")
    folder = require_inside(root, directory, "observation ledger")
    if not folder.is_relative_to((root / "runtime" / "prospective-observations").resolve()):
        raise ValueError("observation ledger must remain under runtime")
    selected = []
    paths = (
        tuple(sorted(observation_paths))
        if observation_paths is not None
        else tuple(sorted(folder.glob("prospective-*.json")))
    )
    for path in paths:
        path = require_inside(root, path, "observation ledger record")
        if path.parent != folder or path.suffix != ".json" or not path.name.startswith("prospective-"):
            raise ValueError("observation path must be a prospective JSON record in the ledger directory")
        expected = trusted_hashes.get(path.stem)
        if expected is None or len(expected) != 64:
            raise ValueError("observation lacks an externally pinned SHA-256")
        raw_record = path.read_bytes()
        if hashlib.sha256(raw_record).hexdigest() != expected.lower():
            raise ValueError("observation bytes differ from the pinned SHA-256")
        row = json.loads(raw_record)
        if row.get("case_id") != case_id:
            continue
        if row.get("action") != "no_order" or row.get("observation_id") != path.stem:
            raise ValueError("observation ledger identity or action mismatch")
        _read_pinned(root, row["source_path"], row["source_sha256"], "observation source")
        schema_version = row.get("schema_version")
        if schema_version not in {"prospective-public-observation-v1", "prospective-public-observation-v2"}:
            raise ValueError("unsupported prospective observation schema")
        observed_at = _time(row["observed_at"], "observed_at")
        created_at = None
        if schema_version == "prospective-public-observation-v2":
            created_value = row.get("receipt_created_at", row.get("record_created_at"))
            created_at = _time(created_value, "observation creation time")
        if (created_at is not None and created_at > datetime.now(timezone.utc)) or observed_at > datetime.now(timezone.utc):
            raise ValueError("observation contains a future process or observation time")
        predecessor_id = row.get("supersedes_observation_id")
        if predecessor_id is not None:
            predecessor_path, predecessor_bytes = _read_pinned(
                root,
                str(folder / f"{predecessor_id}.json"),
                row.get("supersedes_observation_sha256", ""),
                "superseded observation",
            )
            predecessor = json.loads(predecessor_bytes)
            successor_created_at = None
            if row.get("schema_version") == "prospective-public-observation-v2":
                successor_created_at = _time(row.get("receipt_created_at", row.get("record_created_at", "")), "observation creation time")
            predecessor_created_at = (
                _time(predecessor.get("receipt_created_at", predecessor["record_created_at"]), "prior observation creation time")
                if predecessor.get("schema_version") == "prospective-public-observation-v2"
                else None
            )
            legacy_v1_lineage = (
                row.get("schema_version") == "prospective-public-observation-v1"
                and predecessor.get("schema_version") == "prospective-public-observation-v1"
            )
            if (
                predecessor_path.stem != predecessor_id
                or predecessor.get("case_id") != row.get("case_id")
                or predecessor.get("source_document_id") != row.get("source_document_id")
                or predecessor.get("source_sha256") != row.get("source_sha256")
                or predecessor.get("schema_version") not in {"prospective-public-observation-v1", "prospective-public-observation-v2"}
                or (
                    not legacy_v1_lineage
                    and successor_created_at is None
                )
                or (predecessor_created_at is not None and predecessor_created_at >= successor_created_at)
                or _time(predecessor["observed_at"], "prior observed_at") > _time(row["observed_at"], "observed_at")
            ):
                raise ValueError("superseding observation lineage mismatch")
        _, raw_response = _read_pinned(root, row["raw_response_path"], row["raw_response_sha256"], "observation index")
        indexed = [item for item in json.loads(raw_response).get("announcements") or [] if f"cninfo:{item.get('announcementId')}" == row["source_document_id"]]
        if len(indexed) != 1 or indexed[0].get("secCode") != row["symbol"]:
            raise ValueError("observation no longer matches its official index")
        indexed_at = datetime.fromtimestamp(indexed[0]["announcementTime"] / 1000, timezone.utc)
        local_date = indexed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
        safe_available = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=ZoneInfo("Asia/Shanghai"))
        source_available_at = _time(row["source_available_at"], "source_available_at")
        if source_available_at != safe_available:
            raise ValueError("observation availability differs from its source date")
        chronology_is_valid = (
            source_available_at <= observed_at
            and (created_at is None or observed_at <= created_at)
        )
        if (
            schema_version in {"prospective-public-observation-v1", "prospective-public-observation-v2"}
            and chronology_is_valid
            and (created_at is None or created_at <= evaluation_cutoff)
            and observed_at <= evaluation_cutoff
            and source_available_at <= evaluation_cutoff
        ):
            selected.append(row)
    all_paths = paths if observation_paths is not None else tuple(sorted(folder.glob("prospective-*.json")))
    all_rows = [json.loads(path.read_bytes()) for path in all_paths]
    case_rows = [row for row in all_rows if row.get("case_id") == case_id]
    predecessors = [row.get("supersedes_observation_id") for row in case_rows if row.get("supersedes_observation_id")]
    if len(predecessors) != len(set(predecessors)):
        raise ValueError("observation lineage contains a supersession fork")
    superseded = {row.get("supersedes_observation_id") for row in selected}
    selected = [row for row in selected if row["observation_id"] not in superseded]
    return tuple(selected)


def load_verified_observation_ledger(
    *,
    root: Path,
    manifest_path: Path,
    manifest_sha256: str,
    evaluation_cutoff: datetime,
) -> tuple[dict[str, Any], ...]:
    """Load only the observation records explicitly named by a pinned manifest.

    The manifest is a publication input, not a discovery mechanism. It must
    live under ``config/`` and enumerate every record intended for this
    evaluation. Records are grouped by issuer ledger so the normal PIT and
    supersession checks remain authoritative.
    """
    if not isinstance(root, Path) or not isinstance(manifest_path, Path):
        raise ValueError("observation ledger requires pathlib.Path inputs")
    if evaluation_cutoff.tzinfo is None:
        raise ValueError("evaluation cutoff must be timezone-aware")
    if evaluation_cutoff.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("evaluation cutoff cannot be in the future")
    if not isinstance(manifest_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", manifest_sha256):
        raise ValueError("observation ledger manifest needs a SHA-256")
    manifest = require_inside(
        root,
        manifest_path if manifest_path.is_absolute() else root / manifest_path,
        "observation ledger manifest",
    )
    config_root = (root / "config").resolve()
    if not manifest.is_relative_to(config_root):
        raise ValueError("observation ledger manifest must remain under config")
    raw_manifest = manifest.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != manifest_sha256.lower():
        raise ValueError("observation ledger manifest SHA-256 mismatch")
    payload = json.loads(raw_manifest)
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version") != "prospective-observation-ledger-v1"
        or payload.get("action") != "no_order"
    ):
        raise ValueError("unsupported observation ledger manifest or action")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("observation ledger manifest records must be a list")

    grouped: dict[tuple[str, Path], list[Path]] = {}
    trusted_by_group: dict[tuple[str, Path], dict[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise ValueError("observation ledger record must be an object")
        case_id = raw_record.get("case_id")
        observation_id = raw_record.get("observation_id")
        path_value = raw_record.get("path")
        digest = raw_record.get("sha256")
        if not all(isinstance(value, str) and value.strip() for value in (case_id, observation_id, path_value, digest)):
            raise ValueError("observation ledger record requires case_id, observation_id, path and sha256")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("observation ledger record SHA-256 is invalid")
        if (case_id, observation_id) in seen:
            raise ValueError("observation ledger contains a duplicate record")
        seen.add((case_id, observation_id))
        record_path = require_inside(root, root / path_value, "observation ledger record")
        observation_root = (root / "runtime" / "prospective-observations").resolve()
        if (
            not record_path.is_relative_to(observation_root)
            or record_path.suffix != ".json"
            or record_path.stem != observation_id
            or record_path.name != f"{observation_id}.json"
        ):
            raise ValueError("observation ledger record path or identity is invalid")
        actual = hashlib.sha256(record_path.read_bytes()).hexdigest()
        if actual != digest.lower():
            raise ValueError("observation ledger record SHA-256 mismatch")
        key = (case_id, record_path.parent)
        grouped.setdefault(key, []).append(record_path)
        trusted_by_group.setdefault(key, {})[observation_id] = digest.lower()

    selected: list[dict[str, Any]] = []
    for (case_id, directory), paths in grouped.items():
        rows = observations_at(
                root=root,
                directory=directory,
                case_id=case_id,
                evaluation_cutoff=evaluation_cutoff,
                trusted_hashes=trusted_by_group[(case_id, directory)],
                observation_paths=tuple(paths),
            )
        path_by_id = {path.stem: path for path in paths}
        selected.extend(row | {"_ledger_path": path_by_id[row["observation_id"]].as_posix()} for row in rows)
    return tuple(sorted(selected, key=lambda row: (row["case_id"], row["observation_id"])))

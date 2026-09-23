"""Build a fail-closed real CNINFO disclosure queue for M5.

The queue is the missing link between the existing real CNINFO collector and the
human materiality contract. Title rules only produce review candidates; this
module never decides materiality and never creates M5 change events.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .disclosures import PDF_BASE_URL, download_disclosure_pdf
from .event_scan import (
    COVERAGE_COMPLETE,
    COVERAGE_INCOMPLETE,
    EVENT_SCAN_SCHEMA,
    PRE_MODEL_NONE,
    REVIEW_PENDING_HUMAN_REVIEW,
    REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    SCAN_PENDING_HUMAN_REVIEW,
    SCAN_UNKNOWN,
    AnnouncementReview,
    EventScanResult,
    event_scan_from_payload,
)
from .investment_decision import ACTION_NO_ORDER


DISCLOSURE_QUEUE_SCHEMA = "m5-cninfo-disclosure-queue-v1"
PARSER_VERSION = "m5-cninfo-announcement-title-v1"
PROVIDER_CNINFO = "cninfo"
SOURCE_NAME_CNINFO = "CNINFO statutory disclosure"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
SOURCE_ARCHIVED = "SOURCE_ARCHIVED"

CN_TZ = timezone(timedelta(hours=8))
_SYMBOL = re.compile(r"^[0-9]{6}$")
_ANNOUNCEMENT_ID = re.compile(r"^[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

NON_CANDIDATE_KINDS = frozenset(
    {
        "governance",
        "investor_relations",
        "routine",
    }
)


def classify_disclosure_title(title: str) -> str:
    """Classify one announcement title into a bounded rule kind.

    Unknown titles deliberately remain review candidates. A title rule is only
    a queue priority signal, never a materiality conclusion.
    """

    normalized = title.replace(" ", "")
    if any(word in normalized for word in ("半年度报告", "年度报告", "季度报告")):
        return "financial_statement"
    if any(word in normalized for word in ("利润分配", "权益分派", "分红")):
        return "dividend"
    if "回购" in normalized:
        return "buyback"
    if any(word in normalized for word in ("减资", "注册资本", "股本变动")):
        return "capital_structure"
    if "资产减值" in normalized:
        return "asset_impairment"
    if "会计政策" in normalized:
        return "accounting_policy"
    if any(word in normalized for word in ("提供担保", "对外担保")):
        return "guarantee"
    if "经营数据" in normalized:
        return "operating_data"
    if any(word in normalized for word in ("股东会", "董事会", "监事会")):
        return "governance"
    if any(word in normalized for word in ("业绩说明会", "投资者关系", "接待日")):
        return "investor_relations"
    if any(word in normalized for word in ("管理制度", "登记管理", "法律意见书", "报告制度")):
        return "governance"
    return "unknown"


def _iso(value: date | datetime) -> str:
    return value.isoformat()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path, root: Path) -> str:
    path = path.resolve()
    root = root.resolve()
    if not path.is_relative_to(root):
        raise ValueError("Disclosure evidence path escapes the project root")
    return str(path.relative_to(root)).replace("\\", "/")


def _require_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("CNINFO announcement payload must be an object")
    return dict(value)


def _published_at(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=CN_TZ)
    except (TypeError, ValueError, OSError) as error:
        raise ValueError("CNINFO announcementTime must be Unix milliseconds") from error


def _announcement_id(value: object) -> str:
    text = str(value or "")
    if not _ANNOUNCEMENT_ID.fullmatch(text):
        raise ValueError("CNINFO announcementId must contain digits only")
    return text


def _source_url(item: Mapping[str, Any], *, index_url: str) -> str:
    adjunct = str(item.get("adjunctUrl") or "")
    if not adjunct:
        return index_url
    return PDF_BASE_URL + adjunct.lstrip("/")


def _is_complete_pdf(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 4 and path.read_bytes()[:4] == b"%PDF"


def _archive_pdf(
    url: str,
    target: Path,
    downloader: Callable[[str, Path], str],
) -> str:
    if not url:
        raise ValueError("CNINFO announcement has no PDF URL")
    if _is_complete_pdf(target):
        return _digest(target)
    return downloader(url, target)


def _index_evidence(
    symbol: str,
    payload: dict[str, Any],
    *,
    evidence_dir: Path,
    root: Path,
) -> dict[str, Any]:
    announcements = list(payload.get("announcements") or [])
    total = int(payload.get("total_announcements") or 0)
    rows = [
        _require_mapping(item)
        for item in announcements
        if str(_require_mapping(item).get("secCode") or "") == symbol
    ]
    if total != len(rows):
        raise ValueError(
            f"CNINFO announcement count mismatch for {symbol}: {total}/{len(rows)}"
        )
    ids = [_announcement_id(item.get("announcementId")) for item in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"CNINFO announcement window contains duplicate ids for {symbol}")
    index_path = evidence_dir / "cninfo-index.json"
    if index_path.exists():
        raise ValueError(f"CNINFO index evidence already exists: {index_path}")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "id": f"{symbol}-cninfo-index",
        "path": _relative(index_path, root),
        "sha256": _digest(index_path),
        "source_url": str(payload.get("url") or ""),
        "announcement_count": len(rows),
    }


def build_cninfo_event_scan(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    scan_from: date,
    scan_to: date,
    retrieved_at: datetime,
    evidence_dir: Path,
    root: Path,
    pdf_downloader: Callable[[str, Path], str] = download_disclosure_pdf,
) -> EventScanResult:
    """Turn one raw CNINFO index into a bounded, pending-human-review scan."""

    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("CNINFO disclosure queue symbol must contain six digits")
    if retrieved_at.tzinfo is None:
        raise ValueError("CNINFO disclosure retrieved_at must include a timezone")
    if scan_from > scan_to:
        raise ValueError("CNINFO disclosure window cannot start after it ends")
    payload = _require_mapping(payload)
    index_ref = _index_evidence(
        symbol,
        payload,
        evidence_dir=evidence_dir,
        root=root,
    )
    rows = [
        _require_mapping(item)
        for item in payload.get("announcements") or []
        if str(_require_mapping(item).get("secCode") or "") == symbol
    ]
    announcements: list[AnnouncementReview] = []
    blockers: list[str] = []
    source_complete = True

    for item in rows:
        announcement_id = _announcement_id(item.get("announcementId"))
        published_at = _published_at(item.get("announcementTime"))
        if published_at > retrieved_at:
            raise ValueError(
                f"CNINFO announcement is in the future: {symbol} {announcement_id}"
            )
        published_date = published_at.astimezone(CN_TZ).date()
        if published_date < scan_from or published_date > scan_to:
            raise ValueError(
                f"CNINFO announcement is outside the requested window: "
                f"{symbol} {announcement_id}"
            )
        title = str(item.get("announcementTitle") or "")
        if not title.strip():
            raise ValueError("CNINFO announcement title is required")
        source_url = _source_url(item, index_url=str(payload.get("url") or ""))
        rule_kind = classify_disclosure_title(title)
        candidate = rule_kind not in NON_CANDIDATE_KINDS
        has_adjunct = bool(str(item.get("adjunctUrl") or ""))
        pdf_ref: dict[str, Any] | None = None
        notes: list[str] = []
        if candidate:
            pdf_path = (
                evidence_dir
                / "announcements"
                / published_date.isoformat()
                / f"{announcement_id}.pdf"
            )
            if not has_adjunct:
                source_complete = False
                pdf_ref = {
                    "id": f"{symbol}-pdf-attempt-{announcement_id}",
                    "source_url": source_url,
                    "source_status": SOURCE_UNAVAILABLE,
                }
                notes.append(
                    "candidate PDF URL missing; "
                    "human review must use the retained index row"
                )
                blockers.append(
                    f"{symbol} announcement {announcement_id} PDF unavailable; "
                    "materiality cannot be closed from a title alone"
                )
            else:
                try:
                    source_sha256 = _archive_pdf(source_url, pdf_path, pdf_downloader)
                    pdf_ref = {
                        "id": f"{symbol}-pdf-{announcement_id}",
                        "path": _relative(pdf_path, root),
                        "sha256": source_sha256,
                        "source_url": source_url,
                        "source_status": SOURCE_ARCHIVED,
                    }
                    notes.append("title-rule candidate; PDF archived")
                except Exception as error:
                    source_complete = False
                    pdf_ref = {
                        "id": f"{symbol}-pdf-attempt-{announcement_id}",
                        "source_url": source_url,
                        "source_status": SOURCE_UNAVAILABLE,
                    }
                    notes.append(
                        f"candidate PDF unavailable: {type(error).__name__}; "
                        "human review must use the retained index row"
                    )
                    blockers.append(
                        f"{symbol} announcement {announcement_id} PDF unavailable; "
                        "materiality cannot be closed from a title alone"
                    )
        else:
            notes.append("title-rule non-candidate; raw index retained")

        announcements.append(
            AnnouncementReview(
                announcement_id=announcement_id,
                published_at=published_at,
                title=title,
                source_url=source_url,
                rule_kind=rule_kind,
                review_status=(
                    REVIEW_PENDING_HUMAN_REVIEW
                    if candidate
                    else REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE
                ),
                materiality_candidate=candidate,
                pre_model=False,
                evidence_refs=tuple(
                    ref
                    for ref in (index_ref, pdf_ref)
                    if ref is not None
                ),
                notes="；".join(notes),
            )
        )

    pending = [item for item in announcements if item.materiality_candidate]
    return EventScanResult(
        schema_version=EVENT_SCAN_SCHEMA,
        symbol=symbol,
        provider=PROVIDER_CNINFO,
        scan_from=scan_from,
        scan_to=scan_to,
        validity_from=scan_from,
        validity_to=scan_to,
        status=(
            SCAN_PENDING_HUMAN_REVIEW
            if pending or blockers
            else SCAN_COMPLETE_NO_MATERIAL_EVENT
        ),
        coverage_status=(
            COVERAGE_COMPLETE if source_complete else COVERAGE_INCOMPLETE
        ),
        pre_model_review_status=PRE_MODEL_NONE,
        announcements=tuple(announcements),
        blockers=tuple(blockers),
        evidence_refs=(index_ref,),
        retrieved_at=retrieved_at,
        parser_version=PARSER_VERSION,
    )


def source_failure_event_scan(
    *,
    symbol: str,
    scan_from: date,
    scan_to: date,
    retrieved_at: datetime,
    error: Exception,
) -> EventScanResult:
    """Represent a source failure as an explicit health event, not silence."""

    return EventScanResult(
        schema_version=EVENT_SCAN_SCHEMA,
        symbol=symbol,
        provider=PROVIDER_CNINFO,
        scan_from=scan_from,
        scan_to=scan_to,
        validity_from=scan_from,
        validity_to=scan_to,
        status=SCAN_UNKNOWN,
        coverage_status=COVERAGE_INCOMPLETE,
        pre_model_review_status=PRE_MODEL_NONE,
        announcements=(),
        blockers=(
            f"CNINFO index retrieval failed for {symbol}: "
            f"{type(error).__name__}: {str(error)[:240]}",
        ),
        evidence_refs=(),
        retrieved_at=retrieved_at,
        parser_version=PARSER_VERSION,
    )


@dataclass(frozen=True)
class DisclosureReviewQueue:
    """One deterministic, no-order queue across a small selected security set."""

    queue_id: str
    schema_version: str
    provider: str
    parser_version: str
    scan_from: date
    scan_to: date
    retrieved_at: datetime
    scans: tuple[EventScanResult, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != DISCLOSURE_QUEUE_SCHEMA:
            raise ValueError("Unknown disclosure queue schema")
        if not self.queue_id.strip():
            raise ValueError("Disclosure review queue requires an id")
        if self.provider != PROVIDER_CNINFO:
            raise ValueError("Disclosure review queue must be CNINFO")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Disclosure review queue must remain no_order")
        if self.scan_from > self.scan_to:
            raise ValueError("Disclosure review queue window cannot end before it starts")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("Disclosure review queue retrieved_at must include timezone")
        if not self.scans:
            raise ValueError("Disclosure review queue requires at least one scan")
        symbols = [item.symbol for item in self.scans]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Disclosure review queue contains a duplicate symbol")
        if any(
            item.scan_from != self.scan_from
            or item.scan_to != self.scan_to
            for item in self.scans
        ):
            raise ValueError("Every disclosure scan must match the queue window")

    @property
    def pending_candidates(self) -> tuple[AnnouncementReview, ...]:
        return tuple(
            item
            for scan in self.scans
            for item in scan.announcements
            if item.materiality_candidate
        )

    @property
    def unavailable_source_count(self) -> int:
        row_missing = sum(
            any(
                ref.get("source_status") == SOURCE_UNAVAILABLE
                for ref in item.evidence_refs
            )
            for scan in self.scans
            for item in scan.announcements
        )
        failed_scans = sum(
            scan.coverage_status == COVERAGE_INCOMPLETE and not scan.announcements
            for scan in self.scans
        )
        return row_missing + failed_scans

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "queue_id": self.queue_id,
            "provider": self.provider,
            "parser_version": self.parser_version,
            "scan_from": _iso(self.scan_from),
            "scan_to": _iso(self.scan_to),
            "retrieved_at": _iso(self.retrieved_at),
            "scans": [item.as_policy() for item in self.scans],
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def disclosure_review_queue_from_payload(
    payload: Mapping[str, Any],
) -> DisclosureReviewQueue:
    if not isinstance(payload, Mapping):
        raise ValueError("Disclosure review queue must be an object")
    data = dict(payload)
    return DisclosureReviewQueue(
        queue_id=str(data["queue_id"]),
        schema_version=str(data["schema_version"]),
        provider=str(data["provider"]),
        parser_version=str(data["parser_version"]),
        scan_from=date.fromisoformat(str(data["scan_from"])),
        scan_to=date.fromisoformat(str(data["scan_to"])),
        retrieved_at=datetime.fromisoformat(str(data["retrieved_at"])),
        scans=tuple(
            event_scan_from_payload(item)
            for item in data.get("scans") or ()
        ),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )

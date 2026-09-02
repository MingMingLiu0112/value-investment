from __future__ import annotations

import json
from urllib.parse import urlparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .models import SourceRecord


OFFICIAL_EXCHANGE_HOSTS = {
    "www.sse.com.cn",
    "static.sse.com.cn",
    "www.szse.cn",
    "disc.static.szse.cn",
    "www.cninfo.com.cn",
    "static.cninfo.com.cn",
}


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _validate_verified_source(payload: dict) -> tuple[str, str]:
    source_type = payload.get("source_type")
    if source_type not in {"exchange", "company_ir"}:
        raise ValueError("Verified evidence requires source_type: exchange or company_ir")
    parsed = urlparse(payload["source_url"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Verified evidence requires an HTTPS source_url")
    hostname = parsed.hostname.lower()
    if source_type == "exchange" and hostname not in OFFICIAL_EXCHANGE_HOSTS:
        raise ValueError("Verified exchange evidence must use an approved exchange disclosure host")
    if source_type == "company_ir":
        approved_domain = str(payload.get("company_ir_domain", "")).lower().strip()
        if not approved_domain or hostname != approved_domain.lstrip("."):
            raise ValueError("Verified company IR evidence requires a matching company_ir_domain")
    reviewer = str(payload.get("reviewed_by", "")).strip()
    if not reviewer:
        raise ValueError("Verified evidence requires reviewed_by")
    reviewed_at = _parse_datetime(payload.get("reviewed_at"))
    if reviewed_at is None:
        raise ValueError("Verified evidence requires reviewed_at")
    return source_type, reviewer


def _point_metadata(point: dict, payload: dict, source_type: str | None, reviewer: str | None) -> dict:
    metadata = {
        "source_type": source_type,
        "reviewed_by": reviewer,
        "reviewed_at": payload.get("reviewed_at"),
    }
    if point["field_name"] == "fair_value":
        required = ("calculation_method", "calculation_formula", "assumptions", "valuation_as_of")
        missing = [field for field in required if not point.get(field)]
        if missing:
            raise ValueError(f"fair_value requires: {', '.join(missing)}")
        metadata["valuation"] = {field: point[field] for field in required}
    return {key: value for key, value in metadata.items() if value is not None}


def load_evidence_manifest(manifest_path: Path) -> tuple[list[SourceRecord], str, bool]:
    """Load one official filing and its reviewed metric/valuation points."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    document_path = (manifest_path.parent / payload["evidence_file"]).resolve()
    if not document_path.is_file():
        raise FileNotFoundError(f"Evidence file not found: {document_path}")
    validation_status = payload.get("validation_status", "verified")
    if validation_status not in {"pending", "verified", "conflict", "failed"}:
        raise ValueError("validation_status must be pending, verified, conflict, or failed")
    human_reviewed = bool(payload.get("human_reviewed", False))
    source_type: str | None = None
    reviewer: str | None = None
    if validation_status == "verified" and not human_reviewed:
        raise ValueError("Verified evidence requires human_reviewed: true")
    if validation_status == "verified":
        source_type, reviewer = _validate_verified_source(payload)
    raw_payload = document_path.read_bytes()
    fetched_at = datetime.now(timezone.utc)
    published_at = _parse_datetime(payload.get("published_at"))
    records: list[SourceRecord] = []
    for point in payload["points"]:
        records.append(
            SourceRecord(
                symbol=str(point["symbol"]).zfill(6),
                field_name=point["field_name"],
                period_label=point["period_label"],
                value=Decimal(str(point["value"])),
                unit=point["unit"],
                source_name=payload["source_name"],
                source_url=payload["source_url"],
                published_at=published_at,
                fetched_at=fetched_at,
                parser_version=payload.get("parser_version", "manual-evidence-v1"),
                raw_payload=raw_payload,
                local_path=str(document_path),
                point_metadata=_point_metadata(point, payload, source_type, reviewer),
            )
        )
    if not records:
        raise ValueError("Evidence manifest must include at least one point")
    return records, validation_status, human_reviewed

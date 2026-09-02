from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .models import SourceRecord


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
    if validation_status == "verified" and not human_reviewed:
        raise ValueError("Verified evidence requires human_reviewed: true")
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
            )
        )
    if not records:
        raise ValueError("Evidence manifest must include at least one point")
    return records, validation_status, human_reviewed

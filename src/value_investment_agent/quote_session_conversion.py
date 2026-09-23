"""Convert an archived quote-session bundle into a typed quote observation.

The bundle is raw provider evidence only. This converter replays the retained
Tencent and Sina responses against the venue calendar and never promotes a
provider price to verified_close unless the existing session gate passes.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

from .quote_session_collection import resolve_session_reference
from .quote_sessions import evaluate_quote_session, parse_quote
from .quote_snapshot import (
    QUOTE_STATUS_PENDING_EXTERNAL_DATA,
    QUOTE_STATUS_UNVERIFIED,
    QUOTE_STATUS_VERIFIED_CLOSE,
    QuoteSnapshot,
)


def quote_snapshot_from_bundle_file(
    bundle_path: Path,
    root: Path,
    *,
    symbol: str,
    ref_id: str,
    expected_sha256: str | None = None,
    now: datetime | str | None = None,
) -> QuoteSnapshot:
    """Replay one symbol from an immutable quote-session bundle file."""
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Quote session bundle missing: {bundle_path}")
    raw = bundle_path.read_bytes()
    bundle_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if bundle_sha256 != expected_sha256.lower():
            raise ValueError("Quote session bundle hash does not match its reference")
    try:
        payload: dict[str, Any] = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Quote session bundle is not valid JSON") from exc
    if payload.get("version") != "quote-session-collection-v1":
        raise ValueError("Unsupported quote-session bundle version")
    references = payload.get("references")
    documents = payload.get("documents")
    if not isinstance(references, dict) or not isinstance(documents, dict):
        raise ValueError("Quote session bundle references or documents are missing")
    if symbol not in references:
        raise ValueError(f"Quote session bundle has no reference for {symbol}")
    reference = references[symbol]
    resolved = resolve_session_reference(reference, documents)
    now_value = now or payload.get("finished_at")
    if isinstance(now_value, str):
        now_value = datetime.fromisoformat(now_value.replace("Z", "+00:00"))
    if not isinstance(now_value, datetime) or now_value.tzinfo is None:
        raise ValueError("Timezone-aware quote session replay time is required")

    provider_documents = {
        "tencent": resolved["tencent"],
        "sina": resolved["sina"],
    }
    tencent = parse_quote(
        provider_documents["tencent"], "tencent", symbol, now_value
    )
    result = evaluate_quote_session(
        symbol,
        tencent["price"],
        reference,
        now_value,
        documents=documents,
    )

    relative_path = bundle_path.resolve().relative_to(root.resolve()).as_posix()
    evidence_refs: list[dict[str, Any]] = [
        {
            "id": ref_id,
            "kind": "quote_session",
            "path": relative_path,
            "sha256": bundle_sha256,
            "status": str(payload.get("status")),
            "expected_session": result.get("expected_session"),
            "session_result": result.get("status"),
            "reason": result.get("reason"),
        }
    ]
    for provider in ("tencent", "sina"):
        document = provider_documents[provider]
        evidence_refs.append(
            {
                "id": f"{ref_id}-{provider}",
                "kind": "quote_provider_document",
                "provider": provider,
                "source_url": document["source_url"],
                "fetched_at": document["fetched_at"],
                "sha256": document["sha256"],
                "observed_trade_at": result.get("provider_times", {}).get(provider),
            }
        )

    quote_date: date | None = None
    if result.get("expected_session"):
        quote_date = date.fromisoformat(result["expected_session"])
    if result.get("passed") is True and result.get("status") == "matched_close":
        return QuoteSnapshot(
            symbol=symbol,
            quote_date=quote_date,
            current_price=tencent["price"],
            status=QUOTE_STATUS_VERIFIED_CLOSE,
            evidence_refs=evidence_refs,
            blockers=[],
        )

    blockers = [
        str(result.get("reason") or "quote session did not pass verification")
    ]
    if quote_date is None and tencent["price"] is None:
        return QuoteSnapshot(
            symbol=symbol,
            quote_date=None,
            current_price=None,
            status=QUOTE_STATUS_PENDING_EXTERNAL_DATA,
            evidence_refs=evidence_refs,
            blockers=blockers,
        )
    return QuoteSnapshot(
        symbol=symbol,
        quote_date=quote_date,
        current_price=tencent["price"],
        status=QUOTE_STATUS_UNVERIFIED,
        evidence_refs=evidence_refs,
        blockers=blockers,
    )

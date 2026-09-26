"""Fail-closed binding of a retained quote bundle to a read-only daily packet."""
from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to((root / "runtime").resolve()):
        raise ValueError("DAILY_QUOTE_BUNDLE_MUST_REMAIN_UNDER_RUNTIME")
    return resolved


def _positive_price(value: object, symbol: str) -> str:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"DAILY_QUOTE_INVALID_PRICE:{symbol}") from error
    if not price.is_finite() or price <= 0:
        raise ValueError(f"DAILY_QUOTE_INVALID_PRICE:{symbol}")
    return format(price, "f")


def load_daily_quote_binding(*, root: Path, bundle_path: Path) -> dict[str, Any]:
    """Return presentation-safe quote context only after raw evidence checks."""
    root = root.resolve()
    bundle_path = _inside(root, bundle_path)
    report_path = bundle_path.with_name("report.json")
    if not bundle_path.is_file() or not report_path.is_file():
        raise ValueError("DAILY_QUOTE_BUNDLE_OR_REPORT_MISSING")
    raw = bundle_path.read_bytes()
    bundle = json.loads(raw)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    bundle_sha = hashlib.sha256(raw).hexdigest()
    if (
        bundle.get("version") != "quote-session-collection-v1"
        or bundle.get("status") != "collected_not_verified"
        or bundle.get("request_failures")
        or report.get("bundle_sha256") != bundle_sha
        or report.get("bundle_bytes") != len(raw)
        or report.get("status") != bundle["status"]
        or report.get("production_database_changed") is not False
        or report.get("financial_or_strategy_approval") is not False
    ):
        raise ValueError("DAILY_QUOTE_BUNDLE_NOT_BOUND_OR_SAFE")
    try:
        finished_at = datetime.fromisoformat(str(bundle["finished_at"]))
    except (KeyError, ValueError) as error:
        raise ValueError("DAILY_QUOTE_FINISHED_AT_INVALID") from error
    if finished_at.tzinfo is None:
        raise ValueError("DAILY_QUOTE_FINISHED_AT_INVALID")
    documents = bundle.get("documents")
    references = bundle.get("references")
    observations = report.get("observations")
    if not isinstance(documents, dict) or not isinstance(references, dict) or not isinstance(observations, list):
        raise ValueError("DAILY_QUOTE_BUNDLE_SHAPE_INVALID")
    by_symbol = {str(item.get("symbol")): item for item in observations if isinstance(item, dict)}
    if len(by_symbol) != len(observations) or set(by_symbol) != set(references) or not by_symbol:
        raise ValueError("DAILY_QUOTE_OBSERVATION_COVERAGE_INVALID")
    sessions: set[str] = set()
    quotes: list[dict[str, str]] = []
    for symbol in sorted(references):
        reference, observation = references[symbol], by_symbol[symbol]
        result = observation.get("result") if isinstance(observation, dict) else None
        if not isinstance(reference, dict) or reference.get("symbol") != symbol:
            raise ValueError("DAILY_QUOTE_REFERENCE_INVALID")
        if not isinstance(result, dict) or result.get("status") != "matched_close" or result.get("passed") is not True:
            raise ValueError(f"DAILY_QUOTE_NOT_MATCHED_CLOSE:{symbol}")
        session = result.get("expected_session")
        if not isinstance(session, str) or len(session) != 10:
            raise ValueError(f"DAILY_QUOTE_SESSION_INVALID:{symbol}")
        refs = reference.get("document_refs")
        if not isinstance(refs, dict):
            raise ValueError("DAILY_QUOTE_DOCUMENT_REFS_INVALID")
        for key in ("tencent", "sina"):
            document = documents.get(refs.get(key))
            if not isinstance(document, dict) or not isinstance(document.get("raw_base64"), str):
                raise ValueError("DAILY_QUOTE_DOCUMENT_MISSING")
            try:
                source_raw = base64.b64decode(document["raw_base64"], validate=True)
            except ValueError as error:
                raise ValueError("DAILY_QUOTE_DOCUMENT_INVALID") from error
            if hashlib.sha256(source_raw).hexdigest() != document.get("sha256"):
                raise ValueError("DAILY_QUOTE_DOCUMENT_HASH_MISMATCH")
        sessions.add(session)
        quotes.append({"symbol": symbol, "price": _positive_price(observation.get("observed_price"), symbol)})
    if len(sessions) != 1:
        raise ValueError("DAILY_QUOTE_SESSIONS_DO_NOT_ALIGN")
    return {
        "schema_version": "daily-quote-binding-v1", "as_of": sessions.pop(),
        "finished_at": finished_at.isoformat(), "bundle_path": str(bundle_path.relative_to(root)),
        "bundle_sha256": bundle_sha, "report_path": str(report_path.relative_to(root)),
        "report_sha256": _sha256(report_path), "quotes": quotes, "action": "no_order",
    }

"""Fail-closed binding of a retained quote bundle to a read-only daily packet."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Sequence

from value_investment_agent.quote_sessions import evaluate_quote_session


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


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"DAILY_QUOTE_{label}_HASH_INVALID")
    return value


def load_daily_quote_binding(
    *, root: Path, bundle_path: Path, registered_symbols: Sequence[str],
    registration_receipt_sha256: str, registration_sha256: str,
    plan_sha256: str, excluded_symbols: Sequence[str] = (),
) -> dict[str, Any]:
    """Return presentation-safe quote context only after raw evidence checks."""
    root = root.resolve()
    registration_receipt_sha256 = _require_sha256(registration_receipt_sha256, "REGISTRATION_RECEIPT")
    registration_sha256 = _require_sha256(registration_sha256, "REGISTRATION")
    plan_sha256 = _require_sha256(plan_sha256, "PLAN")
    registered = tuple(sorted(set(registered_symbols)))
    excluded = tuple(sorted(set(excluded_symbols)))
    if (
        not registered or len(registered) != len(registered_symbols)
        or any(not re.fullmatch(r"\d{6}", symbol) for symbol in registered)
        or set(registered) & set(excluded)
        or any(not re.fullmatch(r"\d{6}", symbol) for symbol in excluded)
    ):
        raise ValueError("DAILY_QUOTE_REGISTERED_SYMBOLS_INVALID")
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
    finished_at = finished_at.astimezone(timezone.utc)
    if finished_at > datetime.now(timezone.utc):
        raise ValueError("DAILY_QUOTE_CUTOFF_IN_FUTURE")
    documents = bundle.get("documents")
    references = bundle.get("references")
    observations = report.get("observations")
    if not isinstance(documents, dict) or not isinstance(references, dict) or not isinstance(observations, list):
        raise ValueError("DAILY_QUOTE_BUNDLE_SHAPE_INVALID")
    by_symbol = {str(item.get("symbol")): item for item in observations if isinstance(item, dict)}
    if len(by_symbol) != len(observations) or set(by_symbol) != set(references) or not by_symbol:
        raise ValueError("DAILY_QUOTE_OBSERVATION_COVERAGE_INVALID")
    actual_symbols = set(by_symbol)
    unregistered = actual_symbols - set(registered)
    if unregistered - set(excluded):
        raise ValueError("DAILY_QUOTE_UNREGISTERED_SYMBOLS:" + ",".join(sorted(unregistered - set(excluded))))
    sessions: set[str] = set()
    quotes: list[dict[str, str]] = []
    source_evidence: dict[str, dict[str, Any]] = {}
    for symbol in sorted(references):
        reference, observation = references[symbol], by_symbol[symbol]
        result = observation.get("result") if isinstance(observation, dict) else None
        if not isinstance(reference, dict) or reference.get("symbol") != symbol:
            raise ValueError("DAILY_QUOTE_REFERENCE_INVALID")
        expected_exchange = "SZSE" if symbol.startswith(("0", "3")) else "SSE" if symbol.startswith("6") else "BSE"
        if reference.get("calendar_exchange") != expected_exchange:
            raise ValueError("DAILY_QUOTE_CALENDAR_EXCHANGE_MISMATCH")
        if not isinstance(result, dict):
            raise ValueError(f"DAILY_QUOTE_NOT_MATCHED_CLOSE:{symbol}")
        refs = reference.get("document_refs")
        if not isinstance(refs, dict) or not isinstance(refs.get("calendar_documents"), list):
            raise ValueError("DAILY_QUOTE_DOCUMENT_REFS_INVALID")
        resolved_documents: dict[str, dict[str, Any]] = {}
        for key in ("tencent", "sina"):
            document_id = refs.get(key)
            document = documents.get(document_id)
            if not isinstance(document, dict) or not isinstance(document.get("raw_base64"), str):
                raise ValueError("DAILY_QUOTE_DOCUMENT_MISSING")
            try:
                source_raw = base64.b64decode(document["raw_base64"], validate=True)
            except ValueError as error:
                raise ValueError("DAILY_QUOTE_DOCUMENT_INVALID") from error
            if hashlib.sha256(source_raw).hexdigest() != document.get("sha256"):
                raise ValueError("DAILY_QUOTE_DOCUMENT_HASH_MISMATCH")
            identity = hashlib.sha256((
                str(document.get("source_url")) + "\n" + str(document.get("fetched_at"))
                + "\n" + str(document.get("sha256"))
            ).encode("utf-8")).hexdigest()
            if identity != document_id or document.get("http_status") != 200:
                raise ValueError("DAILY_QUOTE_DOCUMENT_IDENTITY_INVALID")
            fetched_at = datetime.fromisoformat(str(document.get("fetched_at", "")))
            if fetched_at.tzinfo is None or fetched_at.astimezone(timezone.utc) > finished_at:
                raise ValueError("DAILY_QUOTE_EVIDENCE_AFTER_CUTOFF")
            resolved_documents[key] = document
        calendar_documents = []
        for document_id in refs["calendar_documents"]:
            document = documents.get(document_id)
            if not isinstance(document, dict):
                raise ValueError("DAILY_QUOTE_CALENDAR_DOCUMENT_MISSING")
            fetched_at = datetime.fromisoformat(str(document.get("fetched_at", "")))
            if fetched_at.tzinfo is None or fetched_at.astimezone(timezone.utc) > finished_at:
                raise ValueError("DAILY_QUOTE_EVIDENCE_AFTER_CUTOFF")
            calendar_documents.append(document)
        checked = evaluate_quote_session(
            symbol, observation.get("observed_price"),
            {"symbol": symbol, "calendar_exchange": expected_exchange,
             "tencent": resolved_documents["tencent"], "sina": resolved_documents["sina"],
             "calendar_documents": calendar_documents},
            finished_at.astimezone(timezone.utc),
        )
        if (
            checked.get("status") != "matched_close" or checked.get("passed") is not True
        ):
            raise ValueError(f"DAILY_QUOTE_RAW_REVALIDATION_FAILED:{symbol}:{checked.get('status')}:{checked.get('detail', '')}")
        if (
            result.get("status") != checked.get("status")
            or result.get("passed") is not checked.get("passed")
            or result.get("expected_session") != checked.get("expected_session")
        ):
            raise ValueError(f"DAILY_QUOTE_RAW_REVALIDATION_FAILED:{symbol}:{checked.get('status')}")
        session = checked["expected_session"]
        quote = _positive_price(observation.get("observed_price"), symbol)
        if not isinstance(session, str) or len(session) != 10:
            raise ValueError(f"DAILY_QUOTE_SESSION_INVALID:{symbol}")
        sessions.add(session)
        source_evidence[symbol] = {
            provider: {
                "source_url": resolved_documents[provider]["source_url"],
                "fetched_at": resolved_documents[provider]["fetched_at"],
                "sha256": resolved_documents[provider]["sha256"],
            }
            for provider in ("tencent", "sina")
        } | {
            "calendar": [
                {"source_url": item["source_url"], "fetched_at": item["fetched_at"],
                 "sha256": item["sha256"]}
                for item in calendar_documents
            ]
        }
        if symbol in registered:
            quotes.append({"symbol": symbol, "price": quote})
    if len(sessions) != 1:
        raise ValueError("DAILY_QUOTE_SESSIONS_DO_NOT_ALIGN")
    return {
        "schema_version": "daily-quote-binding-v1", "as_of": sessions.pop(),
        "finished_at": finished_at.isoformat(), "pit_cutoff": finished_at.isoformat(),
        "bundle_path": str(bundle_path.relative_to(root)),
        "bundle_sha256": bundle_sha, "report_path": str(report_path.relative_to(root)),
        "report_sha256": _sha256(report_path), "registered_symbols": list(registered),
        "registration_receipt_sha256": registration_receipt_sha256,
        "registration_sha256": registration_sha256, "plan_sha256": plan_sha256,
        "source_evidence": source_evidence,
        "coverage_status": "COMPLETE" if not (set(registered) - actual_symbols) else "PARTIAL",
        "missing_symbols": sorted(set(registered) - actual_symbols),
        "excluded_symbols": sorted(unregistered), "quotes": quotes, "action": "no_order",
}

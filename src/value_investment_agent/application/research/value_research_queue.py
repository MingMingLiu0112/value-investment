"""Replayable, non-admitted research queue from a bound M2 discovery run."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from value_investment_agent.m2_opportunity_discovery import (
    CHANNELS,
    discovery_receipt_from_payload,
)


SCHEMA_VERSION = "value-research-queue-v1"
STATES = frozenset({"DISCOVERED", "DATA_CHECK"})


def _load_bound(path: Path, expected_sha256: str) -> dict[str, Any]:
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("expected SHA-256 must be lowercase hex")
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"hash mismatch: {path.name}")
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bound input must be a JSON object")
    return value


def _canonical_hash(value: dict[str, Any]) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return sha256(data.encode("utf-8")).hexdigest()


def build_value_research_queue(
    *,
    root: Path,
    report_path: Path,
    report_sha256: str,
    receipt_path: Path,
    receipt_sha256: str,
    budget: int,
    previous_path: Path | None = None,
    previous_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic queue; caller persists the returned versioned payload."""
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("budget must be a nonnegative integer")
    runtime = (root / "runtime").resolve()

    def inside(path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(runtime):
            raise ValueError("queue inputs must remain inside runtime")
        return resolved

    report_file, receipt_file = inside(report_path), inside(receipt_path)
    report = _load_bound(report_file, report_sha256)
    receipt = discovery_receipt_from_payload(_load_bound(receipt_file, receipt_sha256))
    if receipt.action != "no_order" or report.get("action") != "no_order":
        raise ValueError("research queue requires no_order inputs")
    if report.get("schema_version") != "value-discovery-product-v1" or report.get("status") != "RESEARCH_LEADS_ONLY":
        raise ValueError("unsupported discovery report")
    binding = report.get("receipt_binding")
    if binding != {"path": receipt_file.relative_to(root.resolve()).as_posix(), "sha256": receipt_sha256}:
        raise ValueError("report/receipt binding mismatch")
    if report.get("run_id") != receipt.run_id or report.get("as_of") != receipt.as_of.isoformat():
        raise ValueError("report/receipt identity mismatch")
    if report.get("data_health") != receipt.data_health.as_policy():
        raise ValueError("report data health mismatch")
    if report.get("channel_counts") != {channel: len(receipt.channel_results[channel].candidates) for channel in CHANNELS}:
        raise ValueError("report channel counts mismatch")
    if report.get("quote_date_verification") != "UNVERIFIED_PROVIDER_TRADE_DATE":
        raise ValueError("unknown quote-date contract")
    for reference in receipt.evidence_refs:
        evidence = inside(root / reference.path)
        _check_raw_hash(evidence, reference.sha256)

    pool = receipt.candidate_pool()
    leads = report.get("leads")
    if not isinstance(leads, list) or report.get("deduplicated_lead_count") != len(pool):
        raise ValueError("report lead count mismatch")
    by_symbol = {}
    for lead in leads:
        if not isinstance(lead, dict) or lead.get("symbol") in by_symbol:
            raise ValueError("duplicate or invalid report lead")
        symbol = lead.get("symbol")
        if symbol not in pool:
            raise ValueError("report lead not in receipt")
        reasons = pool[symbol]
        expected_ids = sorted({ref.id for item in reasons for ref in item.evidence_refs})
        expected_channels = sorted({item.channel for item in reasons})
        if (lead.get("candidate_class") != "LEAD" or lead.get("research_state") != "DISCOVERED"
                or lead.get("evidence_ids") != expected_ids or lead.get("channels") != expected_channels
                or lead.get("company_name") != reasons[0].name
                or lead.get("screening_reasons") != list(dict.fromkeys(r for item in reasons for r in item.reasons))
                or lead.get("data_status") != ("PARTIAL" if receipt.data_health.status != "COMPLETE" else reasons[0].data_status)
                or lead.get("quote_date") != receipt.quote_date
                or lead.get("quote_date_verification") != "UNVERIFIED_PROVIDER_TRADE_DATE"):
            raise ValueError("report lead differs from receipt")
        by_symbol[symbol] = lead
    if set(by_symbol) != set(pool):
        raise ValueError("report omitted receipt candidates")

    previous = None
    if previous_path is not None or previous_sha256 is not None:
        if previous_path is None or previous_sha256 is None:
            raise ValueError("previous queue requires path and hash")
        previous = _load_bound(inside(previous_path), previous_sha256)
        _validate_previous(previous, receipt.as_of.isoformat())

    entries = []
    for symbol, lead in by_symbol.items():
        reasons = pool[symbol]
        gaps = []
        if receipt.data_health.status != "COMPLETE":
            gaps.append("RUN_DATA_HEALTH_INCOMPLETE")
        if any(item.data_status != "COMPLETE" for item in reasons):
            gaps.append("CANDIDATE_DATA_INCOMPLETE")
        if not lead["evidence_ids"]:
            gaps.append("SOURCE_EVIDENCE_MISSING")
        if any(item.profile_status != "SUPPORTED" for item in reasons):
            gaps.append("MODEL_PROFILE_UNSUPPORTED_OR_UNKNOWN")
        gaps.extend(("OFFICIAL_FINANCIAL_EVIDENCE_NOT_ADMITTED", "VALUATION_MODEL_NOT_VALIDATED", "QUOTE_DATE_UNVERIFIED"))
        old = next((item for item in previous["entries"] if item["symbol"] == symbol), None) if previous else None
        entries.append({
            "symbol": symbol,
            "company_name": lead["company_name"],
            "channels": lead["channels"],
            "screening_reasons": lead["screening_reasons"],
            "evidence_ids": lead["evidence_ids"],
            "research_state": "DATA_CHECK" if gaps else "DISCOVERED",
            "gaps": gaps,
            "queue_status": "PENDING_BUDGET",
            "transition": "NEW" if old is None else "CARRIED",
            "first_seen_as_of": old["first_seen_as_of"] if old else receipt.as_of.isoformat(),
        })
    entries.sort(key=lambda item: (-len(item["channels"]), item["symbol"]))
    for index, item in enumerate(entries):
        item["queue_status"] = "SELECTED_FOR_DATA_CHECK" if index < budget else "BUDGET_DEFERRED"
    previous_symbols = {item["symbol"] for item in previous["entries"]} if previous else set()
    removed = sorted(previous_symbols - set(by_symbol))
    result = {
        "schema_version": SCHEMA_VERSION,
        "action": "no_order",
        "admission": "RESEARCH_QUEUE_ONLY",
        "as_of": receipt.as_of.isoformat(),
        "run_id": receipt.run_id,
        "budget": budget,
        "selected_count": min(budget, len(entries)),
        "entries": entries,
        "removed_symbols": removed,
        "inputs": {"report_path": report_file.relative_to(root.resolve()).as_posix(),
                   "receipt_path": receipt_file.relative_to(root.resolve()).as_posix(),
                   "report_sha256": report_sha256, "receipt_sha256": receipt_sha256,
                   "previous_queue_path": inside(previous_path).relative_to(root.resolve()).as_posix() if previous_path else None,
                   "previous_queue_sha256": previous_sha256},
    }
    result["content_sha256"] = _canonical_hash(result)
    return result


def _check_raw_hash(path: Path, expected: str) -> None:
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"evidence hash mismatch: {path.name}")


def _validate_previous(previous: dict[str, Any], current_as_of: str) -> None:
    digest = previous.get("content_sha256")
    if not isinstance(digest, str) or digest != _canonical_hash({k: v for k, v in previous.items() if k != "content_sha256"}):
        raise ValueError("previous queue content changed")
    if previous.get("schema_version") != SCHEMA_VERSION or previous.get("action") != "no_order" or previous.get("admission") != "RESEARCH_QUEUE_ONLY":
        raise ValueError("unsupported previous queue")
    if not isinstance(previous.get("as_of"), str) or previous["as_of"] >= current_as_of:
        raise ValueError("previous queue must be from an earlier day")
    entries = previous.get("entries")
    if not isinstance(entries, list) or len({item["symbol"] for item in entries}) != len(entries):
        raise ValueError("invalid previous queue entries")
    if any(item.get("research_state") not in STATES for item in entries):
        raise ValueError("previous queue contains admitted state")

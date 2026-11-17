"""Deterministic, read-only audit of a hash-pinned M2 research funnel."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from value_investment_agent.application.research.value_research_queue import (
    STATES as VALUE_RESEARCH_QUEUE_STATES,
)
from value_investment_agent.financial_quality import GENERAL_FIELDS, _accepted
from value_investment_agent.m2_opportunity_discovery import (
    CHANNELS,
    discovery_receipt_from_payload,
)


TASK_ID = "W6-FUNNEL-AUDIT-V1"
SCHEMA_VERSION = "research-funnel-audit-v1"
OUTPUT_MANIFEST_SCHEMA = "research-funnel-audit-manifest-v1"
HUMAN_REVIEW_PACKET_SCHEMA = "research-funnel-human-review-packet-v1"
M2_RECEIPT_SCHEMA = "m2-opportunity-discovery-v2"
M2_PRODUCT_REPORT_SCHEMA = "value-discovery-product-v1"
VALUE_RESEARCH_QUEUE_SCHEMA = "value-research-queue-v1"
ACTION_NO_ORDER = "no_order"

STATUSES = (
    "DATA_GAP",
    "REJECTED",
    "UNSUPPORTED",
    "PASS",
    "CONFLICT",
    "NOT_EVALUATED",
    "BUDGET_EXCLUDED",
)
QUEUE_SELECTED = "SELECTED_FOR_DATA_CHECK"
QUEUE_DEFERRED = "BUDGET_DEFERRED"
QUOTE_UNVERIFIED = "UNVERIFIED_PROVIDER_TRADE_DATE"
CAPITAL_RETURN_FIELDS = frozenset(
    {
        "roic",
        "roiic",
        "incremental_roic",
        "return_on_invested_capital",
        "capital_return",
    }
)
OUTPUT_FILENAMES = (
    "result.json",
    "report.md",
    "human-review-packet.json",
    "manifest.json",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[0-9]{6}$")
_PREFIXED_SYMBOL = re.compile(r"^(?:sh|sz|bj)([0-9]{6})$", re.IGNORECASE)


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _digest(path: Path) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"cannot read {path}: {error}") from error


def _decode_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _read_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    """Read and hash one file exactly once, then parse those same bytes."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    return _decode_object(raw, label), sha256(raw).hexdigest()


def _resolve_path(root: Path, path: Path | str, label: str) -> Path:
    root = root.resolve()
    raw = Path(str(path).replace("\\", "/"))
    target = (raw if raw.is_absolute() else root / raw).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"{label} must remain under the repository root")
    return target


def _allowed_roots(root: Path) -> tuple[Path, Path]:
    root = root.resolve()
    return (root / "runtime", root / "artifacts")


def _resolve_data_path(root: Path, path: Path | str, label: str) -> Path:
    target = _resolve_path(root, path, label)
    if not any(target.is_relative_to(allowed) for allowed in _allowed_roots(root)):
        raise ValueError(f"{label} must remain under runtime or artifacts")
    return target


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _require_hash(value: object, label: str) -> str:
    digest = str(value or "").lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return digest


def _manifest_files(
    *,
    root: Path,
    product_dir: Path,
    manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files must be a non-empty object")
    result: dict[str, dict[str, Any]] = {}
    for key, item in files.items():
        if key in {"manifest", "queue"}:
            raise ValueError(f"manifest file key is reserved: {key}")
        if not isinstance(item, dict):
            raise ValueError(f"manifest file entry is invalid: {key}")
        path = _resolve_data_path(root, str(item.get("path") or ""), f"manifest file {key}")
        if not path.is_relative_to(product_dir):
            raise ValueError(f"manifest file is outside the M2 product directory: {key}")
        digest = _require_hash(item.get("sha256"), f"manifest file {key} sha256")
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ValueError(f"cannot read {path}: {error}") from error
        actual = sha256(raw).hexdigest()
        if actual != digest:
            raise ValueError(f"manifest hash mismatch: {key}")
        result[str(key)] = {
            "path": _relative(root, path),
            "sha256": actual,
            "resolved_path": path,
            "raw": raw,
        }
    return result


def _find_file(
    files: Mapping[str, Mapping[str, Any]],
    label: str,
    aliases: Sequence[str] = (),
) -> Mapping[str, Any]:
    for key in (label, *aliases):
        if key in files:
            return files[key]
    raise ValueError(f"manifest is missing required file: {label}")


def _normalize_symbol(value: object) -> str | None:
    text = str(value or "").strip()
    match = _PREFIXED_SYMBOL.fullmatch(text)
    if match:
        text = match.group(1)
    if text.isdigit() and len(text) < 6:
        text = text.zfill(6)
    return text if _SYMBOL.fullmatch(text) else None


def _row_symbol(row: object) -> str | None:
    if isinstance(row, Mapping):
        return _normalize_symbol(
            row.get("symbol") or row.get("code") or row.get("证券代码")
        )
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and row:
        return _normalize_symbol(row[0])
    return None


def _finite_number(value: object) -> bool:
    if value is None or value == "":
        return False
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return number.is_finite()


def _dividend_symbols(rows: Iterable[object]) -> set[str]:
    symbols: set[str] = set()
    for row in rows:
        symbol = _row_symbol(row)
        if symbol is None:
            continue
        if isinstance(row, Mapping):
            cash_dps = row.get("cash_dps")
            declared_yield = row.get("declared_yield")
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)) and len(row) > 6:
            cash_dps, declared_yield = row[5], row[6]
        else:
            continue
        if _finite_number(cash_dps) and _finite_number(declared_yield):
            symbols.add(symbol)
    return symbols


def _industry_map(
    official_records: Sequence[Mapping[str, Any]],
    sina_rows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in official_records:
        symbol = _normalize_symbol(record.get("symbol"))
        industry = str(record.get("official_industry") or "").strip()
        if symbol and industry:
            result[symbol] = industry
    for row in sina_rows:
        symbol = _row_symbol(row)
        industry = str(row.get("class") or row.get("industry") or "").strip()
        if symbol and industry:
            result[symbol] = industry
    return result


def _status_counts(rows: Iterable[Any]) -> dict[str, int]:
    counts = Counter(row.status for row in rows)
    unknown = set(counts) - set(STATUSES)
    if unknown:
        raise ValueError(f"unknown evaluation statuses: {sorted(unknown)}")
    return {status: counts[status] for status in STATUSES}


def _validate_receipt_counts(
    receipt_payload: Mapping[str, Any],
    receipt: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, int]]]:
    universe_symbols = [record.symbol for record in receipt.universe.records]
    universe_set = set(universe_symbols)
    if len(universe_set) != len(universe_symbols):
        raise ValueError("universe/evaluation count mismatch: duplicate universe symbols")
    if receipt.data_health.universe_count != len(universe_symbols):
        raise ValueError("universe/evaluation count mismatch: data-health universe")

    channels: dict[str, dict[str, Any]] = {}
    status_counts: dict[str, dict[str, int]] = {}
    payload_channels = receipt_payload.get("channel_results") or {}
    for channel in CHANNELS:
        result = receipt.channel_results[channel]
        evaluations = result.evaluations
        evaluation_symbols = [item.symbol for item in evaluations]
        if len(evaluation_symbols) != len(universe_symbols):
            raise ValueError(
                f"universe/evaluation count mismatch: {channel} evaluation count"
            )
        if len(set(evaluation_symbols)) != len(evaluation_symbols):
            raise ValueError(f"universe/evaluation count mismatch: duplicate {channel} symbols")
        if set(evaluation_symbols) != universe_set:
            raise ValueError(f"universe/evaluation count mismatch: {channel} symbol set")
        if any(item.channel != channel for item in evaluations):
            raise ValueError(f"evaluation channel mismatch: {channel}")

        counted = _status_counts(evaluations)
        supplied = (payload_channels.get(channel) or {}).get("coverage")
        if not isinstance(supplied, dict):
            raise ValueError(f"receipt coverage is missing: {channel}")
        if int(supplied.get("coverage_count", -1)) != len(evaluations):
            raise ValueError(f"receipt coverage count mismatch: {channel}")
        for status in STATUSES:
            key = f"{status.lower()}_count"
            if int(supplied.get(key, 0)) != counted[status]:
                raise ValueError(f"receipt coverage status mismatch: {channel} {status}")
        status_counts[channel] = counted
        channels[channel] = {
            "candidate_count": len(result.candidates),
            "evaluation_count": len(evaluations),
        }
    return channels, status_counts


def _channel_audit(
    receipt: Any,
    status_counts: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for channel in CHANNELS:
        rows = receipt.channel_results[channel].evaluations
        reason_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            reason_counts[row.reason][row.status] += 1
        grouped = sorted(
            reason_counts.items(),
            key=lambda item: (-sum(item[1].values()), item[0]),
        )
        top_reasons = [
            {
                "reason": reason,
                "count": sum(counts.values()),
                "raw_status_counts": dict(sorted(counts.items())),
            }
            for reason, counts in grouped[:5]
        ]

        effective = Counter(row.status for row in rows)
        if channel == "quality":
            insufficient = sum(
                1
                for row in rows
                if row.status == "REJECTED" and not row.evidence_refs
            )
            if insufficient:
                effective["REJECTED"] -= insufficient
                effective["INSUFFICIENT_EVIDENCE"] += insufficient
        with_evidence = sum(1 for row in rows if row.evidence_refs)
        output[channel] = {
            "status_counts": dict(status_counts[channel]),
            "effective_status_counts": {
                **dict(status_counts[channel]),
                **(
                    {"INSUFFICIENT_EVIDENCE": effective["INSUFFICIENT_EVIDENCE"]}
                    if effective["INSUFFICIENT_EVIDENCE"]
                    else {}
                ),
                **(
                    {"REJECTED": effective["REJECTED"]}
                    if effective["REJECTED"] != status_counts[channel]["REJECTED"]
                    else {}
                ),
            },
            "evidence_ref_coverage": {
                "with_evidence_refs": with_evidence,
                "without_evidence_refs": len(rows) - with_evidence,
            },
            "top_reasons": top_reasons,
        }
    return output


def _validate_report(
    *,
    root: Path,
    receipt_path: Path,
    receipt_sha256: str,
    receipt: Any,
    report: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Mapping[str, Any]]]:
    if report.get("schema_version") != M2_PRODUCT_REPORT_SCHEMA:
        raise ValueError("unsupported M2 product report schema")
    if report.get("action") != ACTION_NO_ORDER:
        raise ValueError("M2 product report action must be no_order")
    if report.get("status") != "RESEARCH_LEADS_ONLY":
        raise ValueError("M2 product report must remain RESEARCH_LEADS_ONLY")
    if report.get("run_id") != receipt.run_id or report.get("as_of") != receipt.as_of.isoformat():
        raise ValueError("report/receipt identity mismatch")
    if report.get("data_health") != receipt.data_health.as_policy():
        raise ValueError("report data-health counts mismatch")

    binding = report.get("receipt_binding") or {}
    bound_receipt = _resolve_data_path(root, str(binding.get("path") or ""), "report receipt binding")
    if bound_receipt != receipt_path or _require_hash(binding.get("sha256"), "report receipt binding") != receipt_sha256:
        raise ValueError("queue binding mismatch: report receipt binding")

    expected_channel_counts = {
        channel: len(receipt.channel_results[channel].candidates) for channel in CHANNELS
    }
    if report.get("channel_counts") != expected_channel_counts:
        raise ValueError("report channel counts mismatch")
    leads = report.get("leads")
    if not isinstance(leads, list) or report.get("deduplicated_lead_count") != len(leads):
        raise ValueError("report lead count mismatch")
    pool = receipt.candidate_pool()
    if len(leads) != len(pool):
        raise ValueError("report lead count mismatch: receipt candidate pool")

    by_symbol: dict[str, Mapping[str, Any]] = {}
    for lead in leads:
        if not isinstance(lead, dict):
            raise ValueError("report lead is invalid")
        symbol = lead.get("symbol")
        if symbol in by_symbol or symbol not in pool:
            raise ValueError("report lead is duplicate or absent from receipt")
        reasons = pool[symbol]
        expected_ids = sorted({ref.id for item in reasons for ref in item.evidence_refs})
        expected_channels = sorted({item.channel for item in reasons})
        if (
            lead.get("candidate_class") != "LEAD"
            or lead.get("research_state") != "DISCOVERED"
            or lead.get("channels") != expected_channels
            or lead.get("evidence_ids") != expected_ids
            or lead.get("company_name") != reasons[0].name
        ):
            raise ValueError("report lead differs from receipt")
        if lead.get("quote_date") != receipt.quote_date:
            raise ValueError("report lead quote date mismatch")
        if lead.get("quote_date_verification") != report.get("quote_date_verification"):
            raise ValueError("report lead quote verification mismatch")
        by_symbol[symbol] = lead
    if set(by_symbol) != set(pool):
        raise ValueError("report omitted receipt candidates")
    return report, sorted(by_symbol), by_symbol


def _validate_queue(
    *,
    root: Path,
    queue_path: Path,
    queue_sha256: str,
    queue_payload: Mapping[str, Any],
    receipt_path: Path,
    receipt_sha256: str,
    receipt: Any,
    report_path: Path,
    report_sha256: str,
    report: Mapping[str, Any],
    report_leads: Mapping[str, Mapping[str, Any]],
    industries: Mapping[str, str],
) -> dict[str, Any]:
    queue = queue_payload
    if queue.get("schema_version") != VALUE_RESEARCH_QUEUE_SCHEMA:
        raise ValueError("unsupported value research queue schema")
    if queue.get("action") != ACTION_NO_ORDER:
        raise ValueError("value research queue action must be no_order")
    if queue.get("admission") != "RESEARCH_QUEUE_ONLY":
        raise ValueError("value research queue admission must remain research-only")
    claimed_queue_hash = _require_hash(queue.get("content_sha256"), "queue content_sha256")
    calculated_queue_hash = _canonical_hash(
        {key: value for key, value in queue.items() if key != "content_sha256"}
    )
    if claimed_queue_hash != calculated_queue_hash:
        raise ValueError("queue content hash mismatch")

    inputs = queue.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("queue binding mismatch: inputs missing")
    bound_receipt = _resolve_data_path(root, str(inputs.get("receipt_path") or ""), "queue receipt binding")
    bound_report = _resolve_data_path(root, str(inputs.get("report_path") or ""), "queue report binding")
    if (
        bound_receipt != receipt_path
        or _require_hash(inputs.get("receipt_sha256"), "queue receipt sha256") != receipt_sha256
        or bound_report != report_path
        or _require_hash(inputs.get("report_sha256"), "queue report sha256") != report_sha256
    ):
        raise ValueError("queue binding mismatch: product files")
    if queue.get("run_id") != receipt.run_id or queue.get("as_of") != receipt.as_of.isoformat():
        raise ValueError("queue binding mismatch: run identity")

    entries = queue.get("entries")
    if not isinstance(entries, list):
        raise ValueError("queue count mismatch: entries missing")
    if len(entries) != len(report_leads):
        raise ValueError("queue count mismatch: report lead count")
    symbols = [entry.get("symbol") for entry in entries if isinstance(entry, dict)]
    if len(symbols) != len(entries) or len(set(symbols)) != len(symbols):
        raise ValueError("queue count mismatch: duplicate or invalid entries")
    if set(symbols) != set(report_leads):
        raise ValueError("queue count mismatch: symbol set differs from report")

    selected_entries: list[dict[str, Any]] = []
    for entry in entries:
        symbol = entry["symbol"]
        lead = report_leads[symbol]
        if entry.get("company_name") != lead.get("company_name"):
            raise ValueError("queue entry differs from report lead")
        if entry.get("channels") != lead.get("channels"):
            raise ValueError("queue entry channels differ from report lead")
        research_state = entry.get("research_state")
        if research_state not in VALUE_RESEARCH_QUEUE_STATES:
            raise ValueError("queue entry research_state is invalid")
        gaps = entry.get("gaps")
        if not isinstance(gaps, list) or any(
            not isinstance(gap, str) or not gap.strip() for gap in gaps
        ):
            raise ValueError("queue entry gaps must be a list of non-empty strings")
        if research_state == "DISCOVERED" and gaps:
            raise ValueError("queue DISCOVERED entry must have empty gaps")
        if research_state == "DATA_CHECK" and not gaps:
            raise ValueError("queue DATA_CHECK entry must have non-empty gaps")
        status = entry.get("queue_status")
        if status not in {QUEUE_SELECTED, QUEUE_DEFERRED}:
            raise ValueError("queue entry status is invalid")
        if status == QUEUE_SELECTED:
            selected_entries.append(entry)

    budget = queue.get("budget")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError("queue budget must be a nonnegative integer")
    selected_count = queue.get("selected_count")
    if selected_count != len(selected_entries) or selected_count != min(budget, len(entries)):
        raise ValueError("queue count mismatch: selected count")
    deferred_count = len(entries) - len(selected_entries)

    all_distribution = Counter(
        industries.get(symbol, "UNKNOWN") for symbol in sorted(symbols)
    )
    selected_distribution = Counter(
        industries.get(entry["symbol"], "UNKNOWN")
        for entry in sorted(selected_entries, key=lambda item: item["symbol"])
    )
    deferred_distribution = Counter(
        industries.get(entry["symbol"], "UNKNOWN")
        for entry in entries
        if entry.get("queue_status") == QUEUE_DEFERRED
    )

    def distribution(counts: Counter[str]) -> dict[str, int]:
        return dict(sorted(counts.items()))

    review_candidates = []
    for entry in sorted(selected_entries, key=lambda item: item["symbol"]):
        lead = report_leads[entry["symbol"]]
        review_candidates.append(
            {
                "symbol": entry["symbol"],
                "company_name": entry["company_name"],
                "industry": industries.get(entry["symbol"], "UNKNOWN"),
                "channels": list(entry.get("channels") or []),
                "queue_status": entry["queue_status"],
                "research_state": entry.get("research_state"),
                "gaps": list(entry.get("gaps") or []),
                "evidence_ids": list(lead.get("evidence_ids") or []),
                "quote_date": lead.get("quote_date"),
                "quote_date_verification": lead.get("quote_date_verification"),
                "review_status": "HUMAN_REVIEW_PENDING",
                "materiality_status": "UNREVIEWED",
                "model_validity": "NOT_PROVEN",
                "price_assessment": "NOT_ASSESSED",
                "signature": None,
                "approval": None,
            }
        )

    return {
        "path": _relative(root, queue_path),
        "sha256": queue_sha256,
        "entry_count": len(entries),
        "selected_count": len(selected_entries),
        "deferred_count": deferred_count,
        "selected_symbols": sorted(entry["symbol"] for entry in selected_entries),
        "deferred_symbols": sorted(
            entry["symbol"] for entry in entries if entry.get("queue_status") == QUEUE_DEFERRED
        ),
        "industry_distribution": {
            "all": distribution(all_distribution),
            "selected": distribution(selected_distribution),
            "deferred": distribution(deferred_distribution),
        },
        "selected_entries": review_candidates,
    }


def _safe_accepted(point: Mapping[str, Any]) -> bool:
    try:
        return bool(_accepted(dict(point)))
    except (TypeError, ValueError):
        return False


def _validate_point_available_at(
    point: Mapping[str, Any], *, generated_at: datetime, index: int
) -> datetime:
    raw: object = None
    for field in ("available_at", "fetched_at", "created_at"):
        candidate = point.get(field)
        if candidate is not None and candidate != "":
            raw = candidate
            break
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"retained financial point is missing an availability timestamp at index {index}"
        )
    try:
        available_at = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(
            f"retained financial point has an invalid availability timestamp at index {index}"
        ) from error
    if available_at.tzinfo is None or available_at.utcoffset() is None:
        raise ValueError(
            f"retained financial point timestamp must include a timezone at index {index}"
        )
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("receipt generated_at must include a timezone")
    if available_at > generated_at:
        raise ValueError(
            f"retained financial point is later than receipt.generated_at at index {index}"
        )
    return available_at


def _source_category(point: Mapping[str, Any]) -> str:
    source = str(point.get("source_name") or "").strip().lower()
    parser = str(point.get("parser_version") or "").strip().lower()
    metadata = point.get("metadata") if isinstance(point.get("metadata"), dict) else {}
    if "derivation" in source or "derived" in source or parser.startswith("verified-financial-derivation"):
        return "derived_facts"
    if metadata.get("derivation_formula"):
        return "derived_facts"
    if "cninfo official institution report" in source:
        return "cninfo_official_institution_report"
    if "cninfo" in source:
        return "cninfo_statutory_points"
    if "tencent" in source:
        return "tencent_market"
    if "akshare" in source or "sina" in source or "eastmoney" in source:
        return "independent_structured"
    return "other"


def _financial_coverage(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    categories = (
        "cninfo_statutory_points",
        "cninfo_official_institution_report",
        "independent_structured",
        "tencent_market",
        "derived_facts",
        "other",
    )
    grouped: dict[str, list[Mapping[str, Any]]] = {category: [] for category in categories}
    for point in points:
        grouped[_source_category(point)].append(point)
    coverage: dict[str, Any] = {}
    for category in categories:
        rows = grouped[category]
        symbols = {str(point.get("symbol")) for point in rows}
        coverage[category] = {
            "point_count": len(rows),
            "symbol_count": len(symbols),
            "verified_count": sum(
                1 for point in rows if point.get("validation_status") == "verified"
            ),
            "accepted_count": sum(1 for point in rows if _safe_accepted(point)),
        }
    return coverage


def _general_fields_audit(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matrix = []
    for field in GENERAL_FIELDS:
        rows = [point for point in points if point.get("field_name") == field]
        matrix.append(
            {
                "field": field,
                "point_count": len(rows),
                "symbol_count": len({str(point.get("symbol")) for point in rows}),
                "verified_count": sum(
                    1 for point in rows if point.get("validation_status") == "verified"
                ),
                "accepted_count": sum(1 for point in rows if _safe_accepted(point)),
            }
        )

    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for point in points:
        if point.get("field_name") in GENERAL_FIELDS:
            by_symbol[str(point.get("symbol"))].append(point)

    point_complete = verified_complete = accepted_complete = 0
    for symbol_points in by_symbol.values():
        annual = [
            point
            for point in symbol_points
            if str(point.get("period_label") or "").endswith("-12-31")
        ]
        pool = annual or symbol_points
        latest: dict[str, Mapping[str, Any]] = {}
        for point in sorted(
            pool,
            key=lambda item: (
                str(item.get("period_label") or ""),
                str(item.get("created_at") or ""),
            ),
        ):
            latest[str(point["field_name"])] = point
        if set(latest) != set(GENERAL_FIELDS):
            continue
        periods = {str(point.get("period_label") or "") for point in latest.values()}
        if len(periods) != 1:
            continue
        point_complete += 1
        if all(point.get("validation_status") == "verified" for point in latest.values()):
            verified_complete += 1
        if all(_safe_accepted(point) for point in latest.values()):
            accepted_complete += 1

    return {
        "required_fields": list(GENERAL_FIELDS),
        "acceptance_semantics": "financial_quality._accepted",
        "matrix": matrix,
        "totals": {
            field: sum(item[field] for item in matrix)
            for field in ("point_count", "symbol_count", "verified_count", "accepted_count")
        },
        "same_period_point_complete_symbol_count": point_complete,
        "same_period_verified_complete_symbol_count": verified_complete,
        "same_period_complete_symbol_count": accepted_complete,
    }


def _capital_return_audit(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [point for point in points if point.get("field_name") in CAPITAL_RETURN_FIELDS]
    accepted_symbols = {
        str(point.get("symbol")) for point in rows if _safe_accepted(point)
    }
    if accepted_symbols:
        status = "AVAILABLE"
        reason = "Accepted ROIC/capital-return points are present; model validity is not assessed."
    elif rows:
        status = "UNAVAILABLE"
        reason = "ROIC/capital-return points are present but none pass financial_quality._accepted."
    else:
        status = "UNAVAILABLE"
        reason = "No retained ROIC/capital-return points are present."
    return {
        "status": status,
        "available": bool(accepted_symbols),
        "proven": bool(accepted_symbols),
        "point_count": len(rows),
        "verified_count": sum(
            1 for point in rows if point.get("validation_status") == "verified"
        ),
        "accepted_count": sum(1 for point in rows if _safe_accepted(point)),
        "accepted_symbol_count": len(accepted_symbols),
        "reason": reason,
        "model_validity": "NOT_ASSESSED",
    }


def _validate_manifest_summary(
    manifest: Mapping[str, Any],
    receipt: Any,
    report: Mapping[str, Any],
    receipt_path: Path,
    report_path: Path,
    root: Path,
) -> None:
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("manifest summary is missing")
    if summary.get("action") != ACTION_NO_ORDER:
        raise ValueError("manifest action must be no_order")
    if summary.get("run_id") != receipt.run_id:
        raise ValueError("manifest run identity mismatch")
    if summary.get("as_of") != receipt.as_of.isoformat():
        raise ValueError("manifest as-of mismatch")
    if summary.get("coverage_signature") != receipt.coverage_signature:
        raise ValueError("manifest coverage signature mismatch")
    if summary.get("candidate_signature") != receipt.candidate_signature:
        raise ValueError("manifest candidate signature mismatch")
    expected_channels = {
        channel: len(receipt.channel_results[channel].candidates) for channel in CHANNELS
    }
    if summary.get("channel_counts") != expected_channels:
        raise ValueError("manifest channel count mismatch")
    expected_coverage = {
        channel: receipt.channel_results[channel].as_policy()["coverage"]
        for channel in CHANNELS
    }
    if summary.get("coverage_counts") != expected_coverage:
        raise ValueError("manifest coverage count mismatch")
    if summary.get("data_health") != receipt.data_health.as_policy():
        raise ValueError("manifest data-health count mismatch")
    if summary.get("quote_date") != receipt.quote_date:
        raise ValueError("manifest quote date mismatch")
    if summary.get("quote_date_verification") != report.get("quote_date_verification"):
        raise ValueError("manifest quote verification mismatch")
    if "lead_report_path" in summary:
        bound = _resolve_data_path(root, str(summary["lead_report_path"]), "manifest report path")
        if bound != report_path:
            raise ValueError("manifest report path mismatch")
    if "receipt_path" in summary:
        bound = _resolve_data_path(root, str(summary["receipt_path"]), "manifest receipt path")
        if bound != receipt_path:
            raise ValueError("manifest receipt path mismatch")
    replay = summary.get("replay")
    if isinstance(replay, dict) and (
        replay.get("raw_inputs_match") is not True
        or replay.get("receipt_bytes_match") is not True
    ):
        raise ValueError("manifest replay binding is not byte-consistent")


def audit_research_funnel(
    *,
    root: Path,
    receipt_path: Path,
    manifest_path: Path,
    queue_path: Path,
    sample_size: int = 10,
) -> dict[str, Any]:
    """Return a deterministic audit of pinned M2 evidence; never writes or trades."""
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 0:
        raise ValueError("sample_size must be a nonnegative integer")
    root = root.resolve()
    receipt_file = _resolve_data_path(root, receipt_path, "M2 receipt")
    manifest_file = _resolve_data_path(root, manifest_path, "M2 manifest")
    queue_file = _resolve_data_path(root, queue_path, "value research queue")
    if receipt_file.parent != manifest_file.parent:
        raise ValueError("receipt and manifest must share the M2 product directory")
    product_dir = receipt_file.parent

    manifest, manifest_sha256 = _read_object(manifest_file, "M2 manifest")
    if manifest.get("schema_version") != "m2-run-manifest-v1":
        raise ValueError("unsupported M2 manifest schema")
    files = _manifest_files(root=root, product_dir=product_dir, manifest=manifest)
    receipt_entry = _find_file(files, "receipt")
    report_entry = _find_file(files, "lead_report", ("report",))
    official_entry = _find_file(files, "official", ("official_universe",))
    tencent_entry = _find_file(files, "tencent", ("market",))
    sina_entry = _find_file(files, "sina", ("industry",))
    financial_entry = _find_file(files, "financial")
    dividend_entry = _find_file(files, "dividend")
    if receipt_entry["resolved_path"] != receipt_file:
        raise ValueError("manifest receipt path does not match --receipt")
    receipt_sha256 = receipt_entry["sha256"]
    report_path = report_entry["resolved_path"]
    report_sha256 = report_entry["sha256"]
    queue_payload, queue_sha256 = _read_object(queue_file, "value research queue")

    receipt_payload = _decode_object(receipt_entry["raw"], "M2 receipt")
    try:
        receipt = discovery_receipt_from_payload(receipt_payload)
    except ValueError as error:
        raise ValueError(f"invalid M2 receipt: {error}") from error
    if receipt.schema_version != M2_RECEIPT_SCHEMA:
        raise ValueError("M2 receipt schema mismatch")
    if receipt.action != ACTION_NO_ORDER:
        raise ValueError("M2 receipt action must be no_order")

    channel_counts, raw_status_counts = _validate_receipt_counts(receipt_payload, receipt)

    official = _decode_object(official_entry["raw"], "official universe snapshot")
    official_records = official.get("records")
    if not isinstance(official_records, list):
        raise ValueError("official universe records must be a list")
    official_symbols = {_normalize_symbol(item.get("symbol")) for item in official_records if isinstance(item, dict)}
    if None in official_symbols:
        raise ValueError("official universe contains an invalid symbol")
    receipt_symbols = {record.symbol for record in receipt.universe.records}
    if official_symbols != receipt_symbols or len(official_records) != len(receipt.universe.records):
        raise ValueError("universe/evaluation count mismatch: official universe")

    tencent = _decode_object(tencent_entry["raw"], "Tencent market snapshot")
    sina = _decode_object(sina_entry["raw"], "Sina industry snapshot")
    tencent_rows = tencent.get("rows")
    sina_rows = sina.get("rows")
    if not isinstance(tencent_rows, list) or not isinstance(sina_rows, list):
        raise ValueError("market and industry snapshots must contain row lists")
    tencent_symbols = {serial for row in tencent_rows if (serial := _row_symbol(row)) is not None}
    sina_symbols = {serial for row in sina_rows if (serial := _row_symbol(row)) is not None}
    if any(_row_symbol(row) is None for row in tencent_rows):
        raise ValueError("Tencent market snapshot contains an invalid symbol")
    if any(_row_symbol(row) is None for row in sina_rows):
        raise ValueError("Sina industry snapshot contains an invalid symbol")
    market_symbols = tencent_symbols | sina_symbols
    matched_symbols = market_symbols & receipt_symbols
    missing_symbols = receipt_symbols - market_symbols
    extra_symbols = market_symbols - receipt_symbols
    if receipt.data_health.quote_count != len(market_symbols):
        raise ValueError("market snapshot count mismatch: quote count")
    if receipt.data_health.matched_quote_count != len(matched_symbols):
        raise ValueError("market snapshot count mismatch: matched quotes")
    if receipt.data_health.missing_quote_count != len(missing_symbols):
        raise ValueError("market snapshot count mismatch: missing quotes")
    if receipt.data_health.extra_quote_count != len(extra_symbols):
        raise ValueError("market snapshot count mismatch: extra quotes")

    industries = _industry_map(official_records, [row for row in sina_rows if isinstance(row, dict)])
    industry_count = sum(
        1 for symbol in receipt_symbols if symbol in industries
    )
    if receipt.data_health.industry_mapping_count != industry_count:
        raise ValueError("industry snapshot count mismatch: mapped symbols")

    financial_payload = _decode_object(financial_entry["raw"], "retained financial points")
    points = financial_payload.get("points")
    if not isinstance(points, list) or not all(isinstance(point, dict) for point in points):
        raise ValueError("retained financial points must be a list of objects")
    point_ids: set[str] = set()
    for index, point in enumerate(points):
        symbol = _normalize_symbol(point.get("symbol"))
        if symbol is None or symbol not in receipt_symbols:
            raise ValueError(f"retained financial point has invalid symbol at index {index}")
        point["symbol"] = symbol
        field = str(point.get("field_name") or "").strip()
        if not field:
            raise ValueError(f"retained financial point is missing field_name at index {index}")
        _validate_point_available_at(
            point, generated_at=receipt.generated_at, index=index
        )
        point_id = str(point.get("data_point_id") or "").strip()
        if point_id:
            if point_id in point_ids:
                raise ValueError("retained financial points contain duplicate data_point_id")
            point_ids.add(point_id)
    financial_symbols = {str(point["symbol"]) for point in points}
    if receipt.data_health.financial_evidence_count != len(financial_symbols):
        raise ValueError("financial evidence count mismatch: retained points")

    dividend = _decode_object(dividend_entry["raw"], "dividend snapshot")
    dividend_rows = dividend.get("rows")
    if not isinstance(dividend_rows, list):
        raise ValueError("dividend snapshot must contain a row list")
    dividend_symbols = _dividend_symbols(dividend_rows)
    if receipt.data_health.dividend_evidence_count != len(dividend_symbols):
        raise ValueError("dividend evidence count mismatch: retained rows")

    report, lead_symbols, report_leads = _validate_report(
        root=root,
        receipt_path=receipt_file,
        receipt_sha256=receipt_sha256,
        receipt=receipt,
        report=_decode_object(report_entry["raw"], "M2 product report"),
    )
    _validate_manifest_summary(
        manifest, receipt, report, receipt_file, report_path, root
    )
    queue = _validate_queue(
        root=root,
        queue_path=queue_file,
        queue_sha256=queue_sha256,
        queue_payload=queue_payload,
        receipt_path=receipt_file,
        receipt_sha256=receipt_sha256,
        receipt=receipt,
        report_path=report_path,
        report_sha256=report_sha256,
        report=report,
        report_leads=report_leads,
        industries=industries,
    )

    verification = str(report.get("quote_date_verification") or "")
    if verification != QUOTE_UNVERIFIED:
        raise ValueError("unsupported quote-date verification status")
    trade_date_verified = False
    quote_count = receipt.data_health.quote_count
    verified_quote_count = quote_count if trade_date_verified else 0
    lead_verified_count = len(lead_symbols) if trade_date_verified else 0

    channels = _channel_audit(receipt, raw_status_counts)
    quality_rows = receipt.channel_results["quality"].evaluations
    quality_zero_evidence = sum(
        1 for row in quality_rows if row.status == "REJECTED" and not row.evidence_refs
    )
    quality_effective = dict(channels["quality"]["effective_status_counts"])
    financial_sources = _financial_coverage(points)
    general_fields = _general_fields_audit(points)
    capital_return = _capital_return_audit(points)

    source_hashes = {
        "manifest": manifest_sha256,
        "receipt": receipt_sha256,
        "queue": queue_sha256,
    }
    source_files: dict[str, dict[str, str]] = {}
    for key, entry in sorted(files.items()):
        source_hashes[key] = entry["sha256"]
        source_files[key] = {"path": entry["path"], "sha256": entry["sha256"]}
    source_files["manifest"] = {
        "path": _relative(root, manifest_file),
        "sha256": manifest_sha256,
    }
    source_files["queue"] = {
        "path": _relative(root, queue_file),
        "sha256": queue_sha256,
    }
    if set(source_hashes) != set(source_files):
        raise ValueError("source file bindings do not match source hashes")
    if any(
        source_hashes[key] != binding["sha256"]
        for key, binding in source_files.items()
    ):
        raise ValueError("source file hash binding mismatch")

    if quality_zero_evidence:
        quality_statement = (
            f"{quality_zero_evidence} Quality rows have raw status REJECTED but zero "
            "evidence refs; the product-level classification is INSUFFICIENT_EVIDENCE. "
            "The raw receipt status remains REJECTED rather than being rewritten."
        )
    else:
        quality_statement = (
            "No Quality REJECTED rows with zero evidence refs were observed; raw receipt "
            "statuses remain authoritative."
        )

    counts = {
        "universe": len(receipt.universe.records),
        "market_snapshot": len(market_symbols),
        "industry_snapshot": len(sina_symbols),
        "industry_mapped": industry_count,
        "financial_points": len(points),
        "financial_evidence": len(financial_symbols),
        "dividend_records": len(dividend_rows),
        "dividend_evidence": len(dividend_symbols),
        "leads": len(lead_symbols),
        "queue_entries": queue["entry_count"],
        "queue_selected": queue["selected_count"],
        "queue_deferred": queue["deferred_count"],
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "action": ACTION_NO_ORDER,
        "admission": "READ_ONLY_AUDIT",
        "trade_intent": "NO_TRADE",
        "run_id": receipt.run_id,
        "as_of": receipt.as_of.isoformat(),
        "source_hashes": dict(sorted(source_hashes.items())),
        "source_files": dict(sorted(source_files.items())),
        "counts": counts,
        "universe_count": counts["universe"],
        "market_snapshot_count": counts["market_snapshot"],
        "industry_count": counts["industry_mapped"],
        "financial_evidence_count": counts["financial_evidence"],
        "dividend_evidence_count": counts["dividend_evidence"],
        "lead_count": counts["leads"],
        "queue_count": counts["queue_entries"],
        "receipt_data_health": receipt.data_health.as_policy(),
        "quote": {
            "quote_date": receipt.quote_date,
            "quote_date_verification": verification,
            "trade_date_verified": trade_date_verified,
            "quoted_symbol_count": quote_count,
            "verified_quote_count": verified_quote_count,
            "unverified_quote_count": quote_count - verified_quote_count,
            "verified_lead_count": lead_verified_count,
            "unverified_lead_count": len(lead_symbols) - lead_verified_count,
            "interpretation": (
                "Provider trade dates are unverified; quote dates are not claimed as verified trading dates."
                if not trade_date_verified
                else "The report declares verified provider trade dates."
            ),
        },
        "channels": channels,
        "channel_status_counts": {
            channel: dict(raw_status_counts[channel]) for channel in CHANNELS
        },
        "quality_rejected_zero_evidence_count": quality_zero_evidence,
        "quality_effective_status_counts": quality_effective,
        "interpretation": {
            "product_level": quality_statement,
            "quality_rejected_without_evidence": {
                "raw_status": "REJECTED",
                "effective_status": "INSUFFICIENT_EVIDENCE",
                "count": quality_zero_evidence,
            },
            "decision": "NO_TRADE",
            "research_status": "HUMAN_REVIEW_PENDING",
        },
        "financial": {
            "point_count": len(points),
            "symbol_count": len(financial_symbols),
            "source_coverage": financial_sources,
        },
        "general_fields": general_fields,
        "same_period_complete_symbol_count": general_fields[
            "same_period_complete_symbol_count"
        ],
        "capital_return_roic": capital_return,
        "queue": queue,
        "human_review": {
            "status": "HUMAN_REVIEW_PENDING",
            "signature": None,
            "approval": None,
        },
        "sample_size": sample_size,
    }
    result["audit_sha256"] = _canonical_hash(result)
    return result


def build_human_review_packet(result: Mapping[str, Any], *, sample_size: int = 10) -> dict[str, Any]:
    """Build a deterministic, unsigned human-review sample from selected queue entries."""
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 0:
        raise ValueError("sample_size must be a nonnegative integer")
    if result.get("action") != ACTION_NO_ORDER:
        raise ValueError("human review packet requires a no_order audit")
    queue = result.get("queue")
    if not isinstance(queue, Mapping):
        raise ValueError("human review packet requires queue audit data")
    candidates = queue.get("selected_entries")
    if not isinstance(candidates, list):
        raise ValueError("human review packet requires selected queue entries")
    ordered = sorted(candidates, key=lambda item: (str(item.get("symbol")), str(item.get("company_name"))))
    sample = [json.loads(json.dumps(item, ensure_ascii=False)) for item in ordered[:sample_size]]
    packet: dict[str, Any] = {
        "schema_version": HUMAN_REVIEW_PACKET_SCHEMA,
        "task_id": TASK_ID,
        "action": ACTION_NO_ORDER,
        "review_status": "HUMAN_REVIEW_PENDING",
        "source_audit_sha256": result.get("audit_sha256"),
        "queue_sha256": queue.get("sha256"),
        "selection": {
            "method": "selected queue entries sorted by symbol, then company name",
            "population_count": len(candidates),
            "sample_size": len(sample),
            "requested_sample_size": sample_size,
        },
        "sample": sample,
        "signature": None,
        "approval": None,
        "signed": False,
        "approved": False,
    }
    packet["packet_sha256"] = _canonical_hash(packet)
    return packet


def _md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_markdown_report(
    result: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> str:
    lines = [
        "# W6 Research Funnel Audit",
        "",
        f"- Task: `{TASK_ID}`",
        f"- Action: `{result['action']}`",
        f"- Trade intent: `{result['trade_intent']}`",
        f"- Run ID: `{result['run_id']}`",
        f"- As of: `{result['as_of']}`",
        "",
        "## Funnel counts",
        "",
        "| Layer | Count |",
        "| --- | ---: |",
    ]
    for key, value in result["counts"].items():
        lines.append(f"| {_md_cell(key)} | {value} |")

    quote = result["quote"]
    lines.extend(
        [
            "",
            "## Quote date",
            "",
            f"- Quote date: `{quote['quote_date']}`",
            f"- Verification: `{quote['quote_date_verification']}`",
            f"- Verified quote count: {quote['verified_quote_count']}",
            f"- Unverified quote count: {quote['unverified_quote_count']}",
            f"- Trade date verified: `{str(quote['trade_date_verified']).lower()}`",
            f"- Interpretation: {_md_cell(quote['interpretation'])}",
            "",
            "## Channels",
            "",
            "| Channel | Raw statuses | Effective statuses | Top reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    for channel in CHANNELS:
        data = result["channels"][channel]
        top = data["top_reasons"][0] if data["top_reasons"] else {"reason": "", "count": 0}
        lines.append(
            "| "
            + " | ".join(
                (
                    _md_cell(channel),
                    _md_cell(_compact(data["status_counts"])),
                    _md_cell(_compact(data["effective_status_counts"])),
                    _md_cell(f"{top['reason']} ({top['count']})"),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            result["interpretation"]["product_level"],
            "",
            "## Financial source coverage",
            "",
            "| Source category | Points | Symbols | Verified points | Accepted points |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for category, data in result["financial"]["source_coverage"].items():
        lines.append(
            f"| {_md_cell(category)} | {data['point_count']} | {data['symbol_count']} | "
            f"{data['verified_count']} | {data['accepted_count']} |"
        )

    lines.extend(
        [
            "",
            "## GENERAL_FIELDS matrix",
            "",
            "| Field | Points | Symbols | Verified | Accepted |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in result["general_fields"]["matrix"]:
        lines.append(
            f"| {_md_cell(item['field'])} | {item['point_count']} | {item['symbol_count']} | "
            f"{item['verified_count']} | {item['accepted_count']} |"
        )
    general = result["general_fields"]
    capital = result["capital_return_roic"]
    lines.extend(
        [
            "",
            f"- Same-period complete symbols: {general['same_period_complete_symbol_count']} "
            f"(point-complete {general['same_period_point_complete_symbol_count']}, "
            f"verified-complete {general['same_period_verified_complete_symbol_count']})",
            f"- Capital return / ROIC: `{capital['status']}`; {_md_cell(capital['reason'])}",
            "",
            "## Research queue",
            "",
            f"- Entries: {result['queue']['entry_count']}",
            f"- Selected: {result['queue']['selected_count']}",
            f"- Deferred: {result['queue']['deferred_count']}",
            f"- Industry distribution: `{_compact(result['queue']['industry_distribution'])}`",
            "",
            "## Human review",
            "",
            f"- Status: `{packet['review_status']}`",
            f"- Sample size: {packet['selection']['sample_size']}",
            f"- Signature: `{packet['signature']}`",
            f"- Approval: `{packet['approval']}`",
            "",
            "| Symbol | Company | Industry | Queue status |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in packet["sample"]:
        lines.append(
            f"| {_md_cell(row['symbol'])} | {_md_cell(row['company_name'])} | "
            f"{_md_cell(row['industry'])} | {_md_cell(row['queue_status'])} |"
        )
    lines.extend(
        [
            "",
            "This audit is read-only. It does not approve research, establish model validity, create a price decision, or authorize an order.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_new_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as error:
        raise FileExistsError(f"refusing to overwrite: {path}") from error


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _json_object_copy(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        copied = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be JSON serializable") from error
    if not isinstance(copied, dict):
        raise ValueError(f"{label} must be a JSON object")
    return copied


def _recomputed_digest(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return _canonical_hash(payload)


def write_research_funnel_audit(
    result: Mapping[str, Any],
    packet: Mapping[str, Any] | None = None,
    *,
    root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write the four fixed audit files once, refusing any overwrite."""
    result_payload = _json_object_copy(result, "audit result")
    if (
        result_payload.get("schema_version") != SCHEMA_VERSION
        or result_payload.get("action") != ACTION_NO_ORDER
    ):
        raise ValueError("audit result is not a W6 no_order result")
    audit_sha256 = _recomputed_digest(result_payload, "audit_sha256")
    if result_payload.get("audit_sha256") != audit_sha256:
        raise ValueError("audit result digest is stale or missing")
    if packet is None:
        packet_payload = build_human_review_packet(result_payload)
    else:
        packet_payload = _json_object_copy(packet, "human review packet")
    if packet_payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("human review packet must remain no_order")
    packet_sha256 = _recomputed_digest(packet_payload, "packet_sha256")
    if packet_payload.get("packet_sha256") != packet_sha256:
        raise ValueError("human review packet digest is stale or missing")
    if packet_payload.get("source_audit_sha256") != audit_sha256:
        raise ValueError("human review packet is not bound to the audit result")

    root = root.resolve()
    target_dir = _resolve_data_path(root, output_dir, "audit output directory")
    targets = {name: target_dir / name for name in OUTPUT_FILENAMES}
    existing = [path for path in targets.values() if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite: {existing[0]}")

    result_text = _json_text(result_payload)
    packet_text = _json_text(packet_payload)
    report_text = render_markdown_report(result_payload, packet_payload)
    _write_new_text(targets["result.json"], result_text)
    _write_new_text(targets["report.md"], report_text)
    _write_new_text(targets["human-review-packet.json"], packet_text)

    outputs = {
        name: {
            "path": _relative(root, targets[name]),
            "sha256": _digest(targets[name]),
        }
        for name in ("result.json", "report.md", "human-review-packet.json")
    }
    manifest = {
        "schema_version": OUTPUT_MANIFEST_SCHEMA,
        "task_id": TASK_ID,
        "action": ACTION_NO_ORDER,
        "trade_intent": "NO_TRADE",
        "review_status": "HUMAN_REVIEW_PENDING",
        "source_hashes": dict(result_payload["source_hashes"]),
        "audit_sha256": audit_sha256,
        "packet_sha256": packet_sha256,
        "outputs": outputs,
    }
    _write_new_text(targets["manifest.json"], _json_text(manifest))
    return manifest


write_audit_outputs = write_research_funnel_audit


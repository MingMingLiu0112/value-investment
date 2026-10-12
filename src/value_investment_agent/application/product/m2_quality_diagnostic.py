"""Bounded, read-only diagnosis of an existing M2 Quality receipt."""

from collections import Counter
import hashlib
import json
from pathlib import Path


STATUSES = ("DATA_GAP", "REJECTED", "UNSUPPORTED", "PASS", "CONFLICT", "NOT_EVALUATED", "BUDGET_EXCLUDED")


def diagnose_quality(receipt_path: Path, repository_root: Path) -> dict:
    """Return aggregate evidence only; never infer missing financial scores."""
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("action") != "no_order":
        raise ValueError("receipt action must be no_order")
    quality = receipt["channel_results"]["quality"]
    rows = quality["evaluations"]
    counts = Counter(row["status"] for row in rows)
    unknown = set(counts) - set(STATUSES)
    if unknown:
        raise ValueError(f"unknown quality statuses: {sorted(unknown)}")
    if len({row["symbol"] for row in rows}) != len(rows):
        raise ValueError("duplicate quality symbols")
    coverage = quality["coverage"]
    for status in STATUSES:
        if counts[status] != coverage.get(f"{status.lower()}_count", 0):
            raise ValueError(f"quality coverage mismatch: {status}")
    if len(rows) != coverage["coverage_count"] or len(rows) != len(receipt["universe"]["records"]):
        raise ValueError("quality evaluation/universe mismatch")

    financial_ref = next(ref for ref in receipt["evidence_refs"] if ref["id"] == "financial")
    source_path = repository_root / Path(financial_ref["path"].replace("\\", "/"))
    source_bytes = source_path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != financial_ref["sha256"]:
        raise ValueError("financial source hash mismatch")
    points = json.loads(source_bytes)["points"]
    source_symbols = {point["symbol"] for point in points}
    by_status = {status: {row["symbol"] for row in rows if row["status"] == status} for status in STATUSES}
    reasons = {
        status: dict(sorted(Counter(row["reason"] for row in rows if row["status"] == status).items()))
        for status in STATUSES if counts[status]
    }
    return {
        "action": "no_order",
        "run_id": receipt["run_id"],
        "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        "quality_coverage_count": len(rows),
        "status_counts": {status: counts[status] for status in STATUSES},
        "status_reasons": reasons,
        "financial_source_sha256": financial_ref["sha256"],
        "financial_point_count": len(points),
        "financial_symbol_count": len(source_symbols),
        "financial_symbol_overlap_by_status": {
            status: len(symbols & source_symbols) for status, symbols in by_status.items()
        },
        "interpretation": "Receipt classifications and source presence only; no inferred quality score or investment eligibility.",
    }

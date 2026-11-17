"""Blank-safe observations from an otherwise authenticated parent cash statement.

Only rows with two printed, period-bound amounts are admitted. A blank
comparative column remains unknown; it is never interpreted as zero.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import parent_cash_research as legacy
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import require_inside


VERSION = "parent-cash-observations-blank-safe-v3"


def replay_blank_safe_parent_cash_observations(*, root: Path, symbol: str,
        issuer_name: str, receipt_bindings: list[dict], now: datetime) -> dict:
    """Replay pinned originals; reject ambiguous rows and retain exact gaps."""
    if now.utcoffset() is None or not receipt_bindings:
        raise ValueError("PARENT_CASH_V3_AWARE_CLOCK_AND_RECEIPTS_REQUIRED")
    root = root.resolve()
    seen = set()
    statements = []
    refs = []
    gaps = []
    for entry in receipt_bindings:
        if not isinstance(entry, dict) or set(entry) != {"period", "receipt_binding"}:
            raise ValueError("PARENT_CASH_V3_RECEIPT_SCHEMA_INVALID")
        period, pin = entry["period"], entry["receipt_binding"]
        if period in seen:
            raise ValueError("PARENT_CASH_V3_DUPLICATE_PERIOD")
        periods = legacy._period_pair(period)
        issuer_query = legacy._receipt_issuer_query(root=root, receipt_binding=pin)
        receipt = load_retained_official_report(root=root, receipt_binding=pin,
            symbol=symbol, issuer_name=issuer_query, period=period)
        available = datetime.combine(date.fromisoformat(receipt["published_date"]) +
            timedelta(days=1), time(), timezone(timedelta(hours=8)))
        if available > now:
            raise ValueError("PARENT_CASH_V3_SOURCE_NOT_YET_AVAILABLE")
        source = receipt["source"]
        original = require_inside(root, root / source["path"], "blank-safe parent cash original")
        if legacy.sha256_file(original) != source["sha256"]:
            raise ValueError("PARENT_CASH_V3_ORIGINAL_HASH_MISMATCH")
        pages = extract_pages(original)
        spec = dict(symbol=symbol, issuer=issuer_name, periods=list(periods),
                    column_labels=legacy._column_labels(periods))
        rows = {}
        unknown = []
        for field in sorted(legacy._partial_fields(periods)):
            try:
                row = legacy.extract_parent_cash_statement(
                    pages=pages, spec=spec, observation_fields={field})["rows"][field]
            except ValueError as error:
                # An unprinted comparative amount is a known source gap. All
                # other identity, unit, section or locator failures stay fatal.
                if str(error) != "PARENT_CASH_TWO_PRINTED_VALUES_REQUIRED:" + field:
                    raise
                unknown.append(field)
                continue
            rows[field] = row
        if not rows or not {"cfo_cny", "closing_cash_and_equivalents_cny"} <= rows.keys():
            raise ValueError("PARENT_CASH_V3_ESSENTIAL_ROWS_MISSING")
        source_binding = dict(receipt_path=pin["path"], receipt_sha256=pin["sha256"],
            source_id=receipt["source_id"], source_url=source["source_url"],
            published_date=receipt["published_date"], source_path=source["path"],
            source_sha256=source["sha256"], acquisition_issuer_query=issuer_query,
            date_only_available_at_conservative=available.isoformat())
        for row in rows.values():
            row.update(source_id=receipt["source_id"], source_binding=dict(source_binding))
        statement = dict(symbol=symbol, issuer=issuer_name, periods=list(periods),
            statement_scope="listed_parent_only", rows=rows,
            balances=[dict(period=p, **{k: row["columns"][i]["value"]
                for k, row in rows.items()}) for i, p in enumerate(periods)],
            whole_statement_reconciled=False, unknown_fields=unknown,
            source_binding=source_binding)
        statements.append(statement)
        refs.append(source_binding)
        gaps.extend(dict(reason="PRINTED_COMPARATIVE_AMOUNT_MISSING:" + field,
                         report_period=period) for field in unknown)
        seen.add(period)
    if seen == {"2025-12-31", "2026-06-30"}:
        annual = next(s for s in statements if s["periods"][0] == "FY2025")
        interim = next(s for s in statements if s["periods"][0] == "H12026")
        if (annual["issuer"] != interim["issuer"] or
                annual["balances"][0]["closing_cash_and_equivalents_cny"] !=
                interim["balances"][0]["opening_cash_and_equivalents_cny"]):
            raise ValueError("PARENT_CASH_V3_PERIOD_CONTINUITY_FAILED")
    return dict(schema_version=VERSION, status="SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS",
        symbol=symbol, issuer_name=issuer_name, action="no_order", formal_eligibility=False,
        evaluated_at=now.isoformat(), historical_statements=statements,
        source_bindings=refs, gaps=gaps, whole_statement_reconciled=False,
        limitation="Printed two-column parent cash rows only; blank columns are unknown, not zero or future policy.")

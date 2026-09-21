"""Promotion of official filing candidates after automatic cross-source verification."""

from __future__ import annotations

import csv
import hashlib
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

from .models import SourceRecord
from .growth_evidence import official_growth_period_matches, validate_retained_growth
from .payables_evidence import validate_payables_components


REQUIRED_COLUMNS = {
    "candidate_id", "confirmed_value", "confirmed_unit", "report_period",
    "official_url", "file_sha256", "reviewed_by", "reviewed_at", "approve",
}

# Only fields with an unambiguous unit and a comparable independently sourced
# counterpart are eligible for unattended promotion.  Amount fields remain
# pending until their report unit can also be extracted deterministically.
AUTOMATIC_FIELD_MAP = {
    'revenue_yoy': 'revenue_yoy', 'net_income_yoy': 'net_income_yoy',
    "roe": "roe_weighted",
    "bvps": "bvps",
    "eps_annual": "eps_reported",
    "cash": "cash", "short_term_borrowings": "short_term_borrowings",
    "current_portion_long_term_debt": "current_portion_long_term_debt",
    "long_term_borrowings": "long_term_borrowings", "bonds_payable": "bonds_payable",
    "lease_liabilities_noncurrent": "lease_liabilities_noncurrent",
    "long_term_payables_noncurrent": "long_term_payables_noncurrent",
    "operating_cash_flow": "operating_cash_flow",
    "revenue": "revenue", "net_income": "net_income", "operating_cost": "operating_cost",
    "total_assets": "total_assets", "total_liabilities": "total_liabilities",
}


def values_agree(official: Decimal, secondary: Decimal, unit: str) -> bool:
    """Use field-appropriate tolerance, never silently coerce units."""
    if unit == "percent":
        return abs(official - secondary) <= Decimal("0.05")
    if unit == "CNY/share":
        return abs(official - secondary) <= Decimal("0.02")
    if unit == "CNY":
        return abs(official - secondary) <= max(Decimal("1"), abs(official) * Decimal("0.001"))
    return False


def load_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Review CSV missing columns: {', '.join(sorted(missing))}")
        rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("Review CSV must contain at least one row")
    return rows


def _reviewed_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _candidate(connection: psycopg.Connection, candidate_id: str) -> dict:
    row = connection.execute(
        """SELECT c.candidate_id, c.field_name, c.value, c.unit, c.page_number, c.source_label, c.excerpt,
                  o.symbol, o.report_period, o.source_name, o.source_url, o.published_at,
                  o.sha256, o.local_path, o.archive_status, o.archive_uri
             FROM filing_candidates c
             JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
            WHERE c.candidate_id = %s""",
        (candidate_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown candidate_id: {candidate_id}")
    if row['archive_status'] != 'server_resident':
        raise ValueError(
            f"candidate {candidate_id} requires cold archive restore before review: {row['archive_uri']}"
        )
    return row


def reviewed_records(connection: psycopg.Connection, rows: list[dict[str, str]]) -> list[SourceRecord]:
    """Validate review attestations and turn them into verified source records."""
    records: list[SourceRecord] = []
    seen: set[str] = set()
    for row in rows:
        candidate_id = row["candidate_id"].strip()
        if not candidate_id or candidate_id in seen:
            raise ValueError(f"candidate_id must be nonempty and unique: {candidate_id or '<blank>'}")
        seen.add(candidate_id)
        if row["approve"].strip().lower() not in {"yes", "true", "1", "是"}:
            raise ValueError(f"candidate {candidate_id} is not explicitly approved")
        candidate = _candidate(connection, candidate_id)
        try:
            confirmed_value = Decimal(row["confirmed_value"].strip())
        except InvalidOperation as error:
            raise ValueError(f"candidate {candidate_id} has invalid confirmed_value") from error
        if confirmed_value != Decimal(candidate["value"]):
            raise ValueError(f"candidate {candidate_id} value differs from extracted candidate")
        if row["confirmed_unit"].strip() != candidate["unit"]:
            raise ValueError(f"candidate {candidate_id} unit differs from extracted candidate")
        if row["report_period"].strip() != candidate["report_period"]:
            raise ValueError(f"candidate {candidate_id} report_period differs from official disclosure")
        if row["official_url"].strip() != candidate["source_url"]:
            raise ValueError(f"candidate {candidate_id} official_url differs from archived disclosure")
        if row["file_sha256"].strip().lower() != candidate["sha256"].lower():
            raise ValueError(f"candidate {candidate_id} file_sha256 differs from archived disclosure")
        reviewer = row["reviewed_by"].strip()
        if not reviewer:
            raise ValueError(f"candidate {candidate_id} requires reviewed_by")
        reviewed_at = _reviewed_at(row["reviewed_at"].strip())
        local_path = Path(candidate["local_path"])
        if not local_path.is_file():
            raise FileNotFoundError(f"candidate {candidate_id} archived filing is missing: {local_path}")
        payload = local_path.read_bytes()
        if hashlib.sha256(payload).hexdigest().lower() != candidate["sha256"].lower():
            raise ValueError(f"candidate {candidate_id} archived filing hash no longer matches")
        exists = connection.execute(
            "SELECT 1 FROM data_points WHERE metadata ->> 'candidate_id' = %s LIMIT 1", (candidate_id,)
        ).fetchone()
        if exists:
            raise ValueError(f"candidate {candidate_id} has already been promoted")
        records.append(SourceRecord(
            symbol=candidate["symbol"], field_name=candidate["field_name"],
            period_label=candidate["report_period"], value=confirmed_value,
            unit=candidate["unit"], source_name=candidate["source_name"],
            source_url=candidate["source_url"], published_at=candidate["published_at"],
            fetched_at=datetime.now(timezone.utc), parser_version="candidate-review-v1",
            raw_payload=payload, local_path=str(local_path), point_metadata={
                "candidate_id": str(candidate["candidate_id"]), "page_number": candidate["page_number"],
                "candidate_excerpt": candidate.get("excerpt", ""),
                "source_label": candidate["source_label"], "reviewed_by": reviewer,
                "reviewed_at": reviewed_at.isoformat(), "review_method": "page-level official-filing review",
            },
        ))
    return records


def write_review_template(connection: psycopg.Connection, output: Path) -> int:
    """Export all unpromoted candidates in a CSV that can be reviewed in Excel."""
    rows = connection.execute(
        """SELECT c.candidate_id, o.symbol, i.name, o.report_period, c.field_name, c.value, c.unit,
                  c.page_number, c.source_label, c.excerpt, o.source_url, o.sha256
             FROM filing_candidates c JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
             JOIN instruments i ON i.symbol = o.symbol
            WHERE o.archive_status = 'server_resident'
              AND NOT EXISTS (SELECT 1 FROM data_points p WHERE p.metadata ->> 'candidate_id' = c.candidate_id::text)
            ORDER BY o.published_at DESC, o.symbol, c.page_number"""
    ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    headers = ["candidate_id", "symbol", "name", "report_period", "field_name", "candidate_value", "candidate_unit",
               "page_number", "source_label", "excerpt", "official_url", "file_sha256", "confirmed_value",
               "confirmed_unit", "reviewed_by", "reviewed_at", "approve"]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in headers})
    return len(rows)


def comparable_value_agrees(value: Decimal, unit: str, row: dict) -> bool:
    """Compare explicit RMB scales without rewriting the original observation."""
    scales = {'CNY': Decimal(1), 'CNY 10K': Decimal(10000), 'CNY 100M': Decimal(100000000)}
    try:
        secondary = Decimal(str(row['value']))
        if not value.is_finite() or not secondary.is_finite():
            return False
        if unit in scales and row['unit'] in scales:
            return values_agree(value * scales[unit], secondary * scales[row['unit']], 'CNY')
        return row['unit'] == unit and values_agree(value, secondary, unit)
    except (InvalidOperation, TypeError, ValueError, KeyError):
        return False


def latest_consistent_secondary(matches: list[dict], value: Decimal, unit: str) -> dict | None:
    """Rows arrive newest first; older provider snapshots cannot resolve a conflict."""
    latest = {}
    for row in matches:
        latest.setdefault(row['source_name'], row)
    if not latest or any(
        not comparable_value_agrees(value, unit, row)
        for row in latest.values()
    ):
        return None
    return next(iter(latest.values()))


def cashflow_secondary(matches: list[dict], value: Decimal, unit: str) -> dict | None:
    if latest_consistent_secondary(matches, value, unit) is None:
        return None
    for row in matches:
        if row['source_name'] == 'AkShare / Sina detailed financial statements':
            metadata = row.get('metadata') or {}
            return row if isinstance(metadata, dict) and metadata.get('statement_scope') == 'consolidated' else None
    return None


def automatically_verified_candidates(connection: psycopg.Connection, limit: int) -> Iterator[tuple[str, SourceRecord]]:
    """Promote only candidates corroborated by a second structured source.

    A statutory PDF remains the value ultimately stored as the fact.  The
    separate provider supplies a cross-check for symbol, period, unit and value.
    No candidate becomes verified when either side is missing or conflicts.
    """
    candidates = connection.execute(
        """SELECT c.candidate_id, c.field_name, c.value, c.unit, c.page_number, c.source_label, c.excerpt,
                  o.symbol, o.report_period, o.source_name, o.source_url, o.published_at,
                  o.sha256, o.local_path
            FROM filing_candidates c JOIN official_disclosures o ON o.disclosure_id = c.disclosure_id
            WHERE o.archive_status = 'server_resident'
              AND (c.status = 'candidate_pending_automated_verification'
                   OR (c.status = 'automatically_verified' AND EXISTS (
                       SELECT 1 FROM data_points old
                        WHERE old.metadata ->> 'candidate_id' = c.candidate_id::text
                          AND old.metadata -> 'evidence_quarantine' ->> 'reason'
                              = 'total_revenue_used_as_operating_revenue'
                   )))
              AND NOT EXISTS (
                  SELECT 1 FROM data_points existing
                   WHERE existing.metadata ->> 'candidate_id' = c.candidate_id::text
                     AND NOT (COALESCE(existing.metadata, '{}'::jsonb) ? 'evidence_quarantine')
              )
              AND c.field_name = ANY(%s)
              AND EXISTS (
                  SELECT 1
                    FROM data_points p JOIN raw_documents d ON d.document_id = p.source_id
                   WHERE p.symbol = o.symbol
                     AND p.field_name = CASE c.field_name
                         WHEN 'eps_annual' THEN 'eps_reported'
                         WHEN 'roe' THEN 'roe_weighted' ELSE c.field_name END
                     AND p.period_label = o.report_period
                     AND p.unit = c.unit
                     AND d.source_url <> o.source_url
                     AND (c.field_name NOT IN ('revenue_yoy','net_income_yoy')
                          OR d.source_name = 'Value Investment Agent same-scope secondary growth')
                     AND p.validation_status IN ('pending', 'verified')
                     AND NOT (COALESCE(p.metadata, '{}'::jsonb) ? 'evidence_quarantine')
                     AND NOT (p.field_name = 'revenue' AND d.source_name = 'AkShare / Sina financial abstract')
                     AND (
                         (c.unit = 'percent' AND abs(c.value - p.value) <= 0.05)
                         OR (c.unit = 'CNY/share' AND abs(c.value - p.value) <= 0.02)
                         OR (c.unit = 'CNY' AND abs(c.value - p.value) <= GREATEST(1, abs(c.value) * 0.001))
                     )
              )
            ORDER BY o.published_at DESC, c.created_at
            LIMIT %s""",
        (list(AUTOMATIC_FIELD_MAP), limit),
    ).fetchall()
    for candidate in candidates:
        if candidate['field_name'] in ('revenue_yoy', 'net_income_yoy') and not official_growth_period_matches(
                candidate.get('excerpt'), candidate['report_period']):
            continue
        previous = connection.execute(
            """SELECT data_point_id, validation_status, metadata FROM data_points
                 WHERE metadata ->> 'candidate_id' = %s""",
            (str(candidate['candidate_id']),),
        ).fetchall()
        if any(row['validation_status'] != 'failed' or
               (row.get('metadata') or {}).get('evidence_quarantine', {}).get('reason')
               != 'total_revenue_used_as_operating_revenue' for row in previous):
            continue
        secondary_field = AUTOMATIC_FIELD_MAP[candidate['field_name']]
        matches = connection.execute(
            """SELECT p.value, p.unit, p.metadata, p.data_point_id, d.document_id AS source_id, d.source_name, d.source_url
                 FROM data_points p JOIN raw_documents d ON d.document_id = p.source_id
                WHERE p.symbol = %s AND p.field_name = %s AND p.period_label = %s
                  AND d.source_url <> %s
                  AND (p.field_name NOT IN ('revenue_yoy','net_income_yoy')
                       OR d.source_name = 'Value Investment Agent same-scope secondary growth')
                  AND p.validation_status IN ('pending', 'verified')
                  AND NOT (COALESCE(p.metadata, '{}'::jsonb) ? 'evidence_quarantine')
                  AND NOT (p.field_name = 'revenue' AND d.source_name = 'AkShare / Sina financial abstract')
                ORDER BY p.created_at DESC, p.data_point_id DESC""",
            (candidate['symbol'], secondary_field, candidate['report_period'], candidate['source_url']),
        ).fetchall()
        match = latest_consistent_secondary(matches, Decimal(candidate['value']), candidate['unit'])
        if candidate['field_name'] == 'operating_cash_flow':
            match = cashflow_secondary(matches, Decimal(candidate['value']), candidate['unit'])
        if match is None:
            continue
        if candidate['field_name'] in ('revenue_yoy','net_income_yoy'):
            metadata = match.get('metadata') or {}
            try:
                ids = [uuid.UUID(str(value)) for value in metadata.get('input_data_point_ids', [])]
            except (ValueError,TypeError):
                continue
            inputs = connection.execute(
                """SELECT p.*,d.sha256,d.source_name,d.source_url FROM data_points p
                     JOIN raw_documents d ON d.document_id=p.source_id WHERE p.data_point_id=ANY(%s)""",
                (ids,)).fetchall()
            if not validate_retained_growth(metadata,inputs,candidate['symbol'],candidate['report_period'],
                                            candidate['field_name'],Decimal(match['value'])):
                continue
        payables_input_ids = []
        if candidate['field_name'] == 'long_term_payables_noncurrent':
            inputs = connection.execute("""SELECT * FROM data_points
                WHERE source_id=%s AND symbol=%s AND period_label=%s
                  AND field_name IN ('long_term_payables_excluding_special','special_payables_noncurrent')""",
                (match['source_id'], candidate['symbol'], candidate['report_period'])).fetchall()
            if not validate_payables_components(match, inputs, candidate['symbol'], candidate['report_period']):
                continue
            payables_input_ids = [str(row['data_point_id']) for row in inputs]
        local_path = Path(candidate['local_path'])
        if not local_path.is_file():
            continue
        payload = local_path.read_bytes()
        if hashlib.sha256(payload).hexdigest().lower() != candidate['sha256'].lower():
            raise ValueError(f"candidate {candidate['candidate_id']} archived filing hash no longer matches")
        # Yield one PDF at a time: store_record hashes the actual archived bytes.
        yield str(candidate['candidate_id']), SourceRecord(
            symbol=candidate['symbol'], field_name=candidate['field_name'],
            period_label=candidate['report_period'], value=Decimal(candidate['value']),
            unit=candidate['unit'], source_name=candidate['source_name'],
            source_url=candidate['source_url'], published_at=candidate['published_at'],
            fetched_at=datetime.now(timezone.utc), parser_version='automatic-cross-source-v2',
            raw_payload=payload, local_path=str(local_path), point_metadata={
                'official_file_sha256': candidate['sha256'].lower(),
                'official_file_hash_verified_at_promotion': True,
                'candidate_id': str(candidate['candidate_id']), 'page_number': candidate['page_number'],
                'candidate_excerpt': candidate.get('excerpt', ''),
                'source_label': candidate['source_label'], 'automatic_cross_source_verification': True,
                'verification_method': 'official_pdf_plus_independent_structured_source',
                'secondary_data_point_id': str(match['data_point_id']),
                'secondary_source_id': str(match['source_id']),
                **({'secondary_component_data_point_ids': payables_input_ids,
                    'payables_scope': 'total_including_special_not_financing_classified'}
                   if payables_input_ids else {}),
                'secondary_source_name': match['source_name'], 'secondary_source_url': match['source_url'],
                'official_file_hash_verified_during_extraction': True,
                **({'reverification': {
                    'reason': 'replacement_same_scope_secondary_evidence',
                    'previous_data_point_ids': [str(row['data_point_id']) for row in previous],
                    'previous_records_preserved': True,
                }} if previous else {}),
            },
        )

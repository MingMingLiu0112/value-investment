"""Verify archived statement candidates against PDF bytes and table context."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.extract_m5_financial_fact_candidates import FACT_PATTERNS, SECTION_BY_HEADING, SECTION_HEADINGS  # noqa: E402
from value_investment_agent.research_artifacts import (  # noqa: E402
    ARTIFACT_FINANCIAL_FACTS,
    SCOPE_SECURITY,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sections(reader: PdfReader):
    active = None
    header = None
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        boundaries = sorted(
            (match.start(), match.group(0))
            for heading in SECTION_HEADINGS
            for match in re.finditer(r"(?m)^" + re.escape(heading) + r"$", text)
        )
        parts = [(0, active, header), *[
            (offset, SECTION_BY_HEADING.get(heading), text[offset:offset + 260])
            for offset, heading in boundaries
        ]]
        for index, (start, section, context) in enumerate(parts):
            end = parts[index + 1][0] if index + 1 < len(parts) else len(text)
            if section:
                yield page_number, text, text[start:end], section, context
        if boundaries:
            active = SECTION_BY_HEADING.get(boundaries[-1][1])
            header = text[boundaries[-1][0]:boundaries[-1][0] + 260]


def verify(
    *, candidate: dict, pdf: Path, source_record: dict, period_start: date,
    period_end: date, available_at: datetime, verified_at: datetime, run_id: str,
) -> tuple[ResearchArtifactEnvelope | None, tuple[dict, ...]]:
    if candidate.get("schema_version") != "m5-financial-fact-candidate-extraction-v1":
        raise ValueError("Unsupported candidate schema")
    if candidate.get("action") != "no_order" or not re.fullmatch(r"\d{6}", str(candidate.get("symbol", ""))):
        raise ValueError("Invalid candidate identity or action")
    if not pdf.is_file():
        raise ValueError("Official PDF and HTTPS source URL are required")
    source_url = source_record.get("source_url", "")
    if not source_url.startswith("https://static.cninfo.com.cn/finalpage/"):
        raise ValueError("Candidate source is not a pinned official CNINFO PDF")
    if (source_record.get("announcement_id") != candidate["announcement_id"]
        or source_record.get("published_at") != candidate["published_at"]):
        raise ValueError("Candidate does not match the archived announcement index")
    pdf_refs = [ref for ref in source_record.get("evidence_refs", ())
                if ref.get("sha256") == candidate["pdf"].get("sha256")
                and ref.get("source_url") == source_url]
    if len(pdf_refs) != 1:
        raise ValueError("Archived PDF hash and source URL are not bound to the announcement")
    published_at = datetime.fromisoformat(candidate["published_at"])
    if any(value.tzinfo is None for value in (published_at, available_at, verified_at)):
        raise ValueError("All timestamps must include a timezone")
    if available_at < published_at + timedelta(days=1) or verified_at < available_at:
        raise ValueError("Date-only publication needs conservative availability; verification cannot precede it")
    if period_start != date(period_end.year, 1, 1) or period_end != date(period_end.year, 6, 30):
        raise ValueError("Only explicit first-half cumulative periods are supported")
    pdf_bytes = pdf.read_bytes()
    pdf_sha = _digest(pdf_bytes)
    if pdf_sha != candidate["pdf"]["sha256"]:
        raise ValueError("Archived PDF byte hash changed")
    reader = PdfReader(str(pdf))
    if len(reader.pages) != candidate["pdf"]["page_count"]:
        raise ValueError("Archived PDF page count changed")
    matching = {}
    for page_number, page_text, segment, section, context in _sections(reader):
        for field, pattern in FACT_PATTERNS[section].items():
            match = pattern.search(segment)
            if match:
                matching.setdefault(field, []).append((page_number, page_text, section, context, match))
    verified = []
    pending = []
    seen = set()
    for item in candidate.get("numeric_facts", ()):
        field = item.get("field")
        if field in seen or field not in {name for rules in FACT_PATTERNS.values() for name in rules}:
            raise ValueError("Duplicate or unsupported financial fact field")
        seen.add(field)
        hits = matching.get(field, ())
        reason = None
        if len(hits) != 1:
            reason = "ambiguous_or_missing_pdf_row"
        else:
            page_number, page_text, section, context, match = hits[0]
            current = match.group(1).replace(",", "")
            line = match.group(0).replace("\n", " ")[:500]
            if (item.get("page_number") != page_number
                or item.get("page_text_sha256") != _digest(page_text.encode("utf-8"))
                or item.get("value") != current or item.get("source_line") != line
                or item.get("statement_type") != section
                or item.get("statement_scope") != "consolidated"
                or item.get("unit") != "CNY" or item.get("unit_basis") != "yuan"
                or item.get("column_basis") != "current_period_first_column"):
                reason = "candidate_pdf_or_statement_context_mismatch"
            elif "单位：元 币种：人民币" not in context:
                reason = "unit_header_not_proven"
            elif not re.search(rf"(?<!\d){period_end.year}(?!\d)", context):
                reason = "report_year_not_proven"
            elif (section == "consolidated_balance_sheet" and
                  not re.search(rf"{period_end.year}\s*年\s*{period_end.month}\s*月\s*{period_end.day}\s*日", context)):
                reason = "balance_sheet_date_not_proven"
            elif (section != "consolidated_balance_sheet" and period_end.month == 6 and "半年度" not in context):
                reason = "cumulative_period_not_proven"
        if reason:
            pending.append({"field": field, "reason": reason})
            continue
        verified.append({
            "field": field, "value": current, "currency": "CNY", "unit_basis": "yuan",
            "statement_scope": "consolidated", "statement_type": section,
            "column_basis": "current_period_first_column",
            "report_period_start": period_start.isoformat() if section != "consolidated_balance_sheet" else None,
            "report_period_end": period_end.isoformat(), "page_number": page_number,
            "page_text_sha256": item["page_text_sha256"], "source_line": line,
            "verification_method": "deterministic_archived_pdf_table_context_v1",
        })
    if not verified:
        return None, tuple(pending)
    payload = {
        "schema_version": "m5-verified-financial-facts-v1",
        "symbol": candidate["symbol"], "announcement_id": candidate["announcement_id"],
        "source_url": source_url, "pdf_sha256": pdf_sha,
        "published_at": published_at.isoformat(), "available_at": available_at.isoformat(),
        "verified_at": verified_at.isoformat(), "facts": verified, "pending": pending,
        "action": "no_order",
    }
    evidence_refs = ({"id": f"pdf:{candidate['announcement_id']}", "source_url": source_url, "sha256": pdf_sha},)
    envelope = ResearchArtifactEnvelope.build(
        identity=ResearchArtifactIdentity(SCOPE_SECURITY, candidate["symbol"], ARTIFACT_FINANCIAL_FACTS,
                                          "m5-verified-financial-facts-v1", period_end, available_at),
        payload=payload, evidence_refs=evidence_refs, run_id=run_id,
    )
    return envelope, tuple(pending)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--period-start", required=True, type=date.fromisoformat)
    parser.add_argument("--period-end", required=True, type=date.fromisoformat)
    parser.add_argument("--available-at", required=True, type=datetime.fromisoformat)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Verified facts artifact is write-once")
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    records = [record for scan in queue.get("scans", ())
               for record in scan.get("announcements", ())
               if record.get("announcement_id") == candidate["announcement_id"]
               and scan.get("symbol") == candidate["symbol"]]
    if len(records) != 1:
        raise ValueError("Candidate announcement is missing or duplicated in the queue")
    envelope, pending = verify(candidate=candidate, pdf=args.pdf, source_record=records[0],
                               period_start=args.period_start, period_end=args.period_end,
                               available_at=args.available_at, verified_at=datetime.now(timezone.utc),
                               run_id=args.run_id)
    if envelope is None:
        raise ValueError(f"No financial facts verified: {pending}")
    output = {
        "identity": envelope.identity.as_dict(), "payload": envelope.payload_object(),
        "payload_sha256": envelope.payload_sha256, "evidence_refs": list(envelope.evidence_refs),
        "run_id": envelope.run_id,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "verified": len(envelope.payload_object()["facts"]),
                      "pending": len(pending), "payload_sha256": envelope.payload_sha256, "action": "no_order"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

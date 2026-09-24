"""Evidence-bound reading aids for an M5 human disclosure review.

This module narrows the reader's first pass through an already archived PDF.
It deliberately does not infer materiality, create a ChangeEvent, or prepare a
trading action.  A briefing is disposable reading assistance; the existing
human-review intake remains the only path to an EventMaterialityDecision.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

from .investment_decision import ACTION_NO_ORDER
from .m5_disclosure_queue import DisclosureReviewQueue
from .m5_disclosure_review import disclosure_queue_sha256, verify_archived_pdf


M5_DISCLOSURE_BRIEFING_SCHEMA = "m5-disclosure-briefing-v1"
MAX_HIT_PAGES_PER_TERM = 3
MAX_EXCERPT_CHARS = 280

# These are reading prompts keyed only to the title-rule category. They are not
# a classification of the contents or an investment/materiality recommendation.
REVIEW_TERMS: dict[str, tuple[str, ...]] = {
    "financial_statement": ("营业收入", "归属于上市公司股东的净利润", "经营活动产生的现金流量净额", "利润分配"),
    "dividend": ("每股", "现金红利", "除权除息", "股权登记日"),
    "buyback": ("回购", "资金来源", "回购价格", "股份用途"),
    "capital_structure": ("注册资本", "股本", "股份", "债务"),
    "asset_impairment": ("减值", "计提", "资产", "损失"),
    "accounting_policy": ("会计政策", "追溯", "财务报表", "影响"),
    "guarantee": ("担保", "被担保", "担保金额", "风险"),
    "operating_data": ("产量", "销量", "收入", "经营"),
}
DEFAULT_REVIEW_TERMS = ("事项", "影响", "风险", "财务")


def _pdf_pages(path: Path) -> tuple[str, ...]:
    reader = PdfReader(str(path), strict=False)
    return tuple(page.extract_text() or "" for page in reader.pages)


def _excerpt(page: str, term: str) -> str:
    normalized = re.sub(r"\s+", " ", page).strip()
    index = normalized.find(term)
    if index < 0:
        return ""
    start = max(0, index - 80)
    end = min(len(normalized), index + len(term) + 180)
    prefix = "..." if start else ""
    suffix = "..." if end < len(normalized) else ""
    return (prefix + normalized[start:end] + suffix)[:MAX_EXCERPT_CHARS]


def _term_hits(pages: tuple[str, ...], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for term in terms:
        hits: list[dict[str, Any]] = []
        for page_number, page in enumerate(pages, 1):
            if term not in page:
                continue
            hits.append({"page": page_number, "excerpt": _excerpt(page, term)})
            if len(hits) == MAX_HIT_PAGES_PER_TERM:
                break
        rows.append({"term": term, "hits": hits})
    return rows


def build_disclosure_review_briefing(
    queue: DisclosureReviewQueue,
    *,
    archive_root: Path,
    page_extractor: Callable[[Path], tuple[str, ...]] = _pdf_pages,
) -> dict[str, Any]:
    """Create a no-verdict briefing after re-verifying each candidate PDF.

    A corrupt, missing, or hash-mismatched document raises rather than emitting
    a partial briefing.  The returned structure intentionally has no decision
    or affected-domain field, preventing it from being mistaken for intake.
    """

    rows: list[dict[str, Any]] = []
    for scan in queue.scans:
        for candidate in scan.validity_material_candidates:
            ref, source_sha256 = verify_archived_pdf(
                candidate,
                archive_root=archive_root,
                symbol=scan.symbol,
            )
            relative_path = Path(str(ref["path"]))
            pages = page_extractor((archive_root.resolve() / relative_path).resolve())
            terms = REVIEW_TERMS.get(candidate.rule_kind, DEFAULT_REVIEW_TERMS)
            rows.append(
                {
                    "symbol": scan.symbol,
                    "announcement_id": candidate.announcement_id,
                    "published_at": candidate.published_at.isoformat(),
                    "title": candidate.title,
                    "title_rule_kind": candidate.rule_kind,
                    "source_url": candidate.source_url,
                    "archive_path": str(relative_path).replace("\\", "/"),
                    "source_sha256": source_sha256,
                    "page_count": len(pages),
                    "reading_prompts": list(terms),
                    "literal_term_hits": _term_hits(pages, terms),
                    "human_decision": None,
                    "action": ACTION_NO_ORDER,
                }
            )
    return {
        "schema_version": M5_DISCLOSURE_BRIEFING_SCHEMA,
        "queue_id": queue.queue_id,
        "queue_sha256": disclosure_queue_sha256(queue),
        "candidate_count": len(rows),
        "briefings": rows,
        "boundary": "reading_aid_only_no_materiality_decision",
        "action": ACTION_NO_ORDER,
    }

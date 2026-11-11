"""Bounded filing/body/attachment context, NOT a general issuer identity service."""
from datetime import datetime
import json

from ...infrastructure.hotspot.cash_implementation import _compact, _pdf
from ...infrastructure.hotspot.cash_implementation_v2 import parse_cash_implementation_pages_v2
from ...infrastructure.hotspot.related_disclosure_identity import (
    _attachment_titles, _classify, _direct_identity, _legal_name, _page_texts, _references,
)
from ...infrastructure.evidence.historical_price_correspondence import require_inside, sha256_file
from ..product.daily_event_observation import verify_retained_event_coverage
from ...quote_sessions import CHINA


def inspect_cash_related_disclosures(*, root, symbol, implementation_binding,
        observation_binding, start, end, now):
    """Reverify the full archive first; then keep every body failure as an item.

    A raw archive/hash failure invalidates the source set. Individual identity,
    text or relation gaps never suppress the remaining source-bound documents.
    """
    result = dict(status="NOT_ASSESSABLE", items=[], expected_document_count=None,
        reviewed_document_count=0, bound_subject_count=0, unresolved_subject_count=0,
        complete_action_coverage=False, comparison_allowed=False, revision_absence_proven=False,
        no_change=None, price_comparability="UNKNOWN", historical_availability_proven=False,
        action="no_order", gaps=["FULL_ACTION_HISTORY_AND_OPENING_STATE_NOT_PROVEN",
            "SEMANTIC_CHANGE_OR_NO_CHANGE_NOT_PROVEN"])
    try:
        root = root.resolve()
        path = require_inside(root, root / observation_binding["path"], "related official observation")
        if sha256_file(path) != observation_binding["sha256"]:
            raise ValueError("Official observation hash mismatch")
        observation = json.loads(path.read_bytes())
        archive = verify_retained_event_coverage(root, observation, symbol=symbol,
            required_from=start, required_to=end, now=now)
        scan_path = require_inside(root, root / archive["scan_binding"]["path"], "related official scan")
        if sha256_file(scan_path) != archive["scan_binding"]["sha256"]:
            raise ValueError("Official scan hash mismatch")
        scan = json.loads(scan_path.read_bytes())
        original_pages, _ = _pdf(root, implementation_binding, now)
        terms = parse_cash_implementation_pages_v2(original_pages, symbol=symbol)
        name = _legal_name(original_pages, symbol)
        originals = [row for row in scan["announcements"] if row["source_url"] == implementation_binding["url"]]
        if (len(originals) != 1 or len(originals[0]["evidence_refs"]) != 1
                or originals[0]["evidence_refs"][0]["sha256"] != implementation_binding["sha256"]
                or observation["scan_from"] > terms["published_date"]):
            raise ValueError("Implementation original not uniquely covered by official scan")
        rows = [row for row in scan["announcements"] if row is not originals[0]]
        if len(rows) > 16:
            raise ValueError("Related disclosure count exceeds bounded review")
        decoded = []
        for row in rows:
            item = dict(announcement_id=row["announcement_id"], title=row["title"], source_url=row["source_url"],
                published_date=datetime.fromisoformat(row["published_at"]).astimezone(CHINA).date().isoformat(),
                acquired_at=observation["acquired_at"], source_bindings=row["evidence_refs"], pages=[], texts=[],
                error=None)
            try:
                if len(row["evidence_refs"]) != 1:
                    raise ValueError("One original per related document required")
                ref = row["evidence_refs"][0]
                item["binding"] = dict(path=ref["path"], sha256=ref["sha256"], url=row["source_url"],
                    available_at=observation["acquired_at"])
                item["pages"], _ = _pdf(root, item["binding"], now)
                item["texts"] = _page_texts(item["pages"])
            except (OSError, ValueError, KeyError, TypeError, ArithmeticError, RuntimeError) as error:
                item["error"] = str(error)
            decoded.append(item)
        title_counts = {}
        for item in decoded:
            title = _compact(item["title"])
            title_counts[title] = title_counts.get(title, 0) + 1
        for item in decoded:
            item["official_title_count"] = title_counts[_compact(item["title"])]
        attachments = {}
        for item in decoded:
            if item["error"] or not item["texts"] or not all(item["texts"]):
                continue
            try:
                direct = _direct_identity(item["pages"], name=name, symbol=symbol, published_date=item["published_date"])
                if direct is not None and direct["body_signature_date"] is not None:
                    for title in _attachment_titles(item["texts"]):
                        attachments.setdefault(title, []).append(item["binding"])
            except (ValueError, TypeError):
                continue
        for item in decoded:
            try:
                identity = _classify(item, name=name, symbol=symbol, attachments=attachments) if not item["error"] else dict(
                    status="UNRESOLVED", reason=item["error"], document_role="UNRESOLVED")
            except (ValueError, TypeError, KeyError, ArithmeticError, RuntimeError) as error:
                identity = dict(status="UNRESOLVED", reason=str(error), document_role="UNRESOLVED")
            texts = item["texts"]
            relation = _references(texts, terms["title"], terms["announcement_number"])
            relation["implementation_references_this_document_pages"] = [i for i, page in enumerate(original_pages, 1)
                if f"《{_compact(item['title'])}》" in _compact(page)]
            result["items"].append(dict(announcement_id=item["announcement_id"], title=item["title"],
                published_date=item["published_date"], acquired_at=item["acquired_at"],
                evidence_bindings=item["source_bindings"], identity_review=identity,
                readable_pages=[i for i, text in enumerate(texts, 1) if text],
                unreadable_pages=[i for i, text in enumerate(texts, 1) if not text],
                text_coverage="COMPLETE" if texts and all(texts) else "PARTIAL" if any(texts) else "UNAVAILABLE",
                text_coverage_scope="EXTRACTED_TEXT_PRESENCE_PER_PAGE_NOT_VISUAL_OR_OCR_COMPLETENESS",
                visual_or_ocr_completeness_proven=False,
                implementation_relation=relation,
                no_change=None, comparison_allowed=False, action="no_order"))
        count = sum(row["identity_review"]["status"].startswith("BOUND_") for row in result["items"])
        result.update(status="BOUND_RELATED_IDENTITIES_ONLY" if count == len(rows) and all(
            row["text_coverage"] == "COMPLETE" for row in result["items"]) else "RELATED_REVIEW_PARTIAL",
            expected_document_count=len(rows), reviewed_document_count=len(result["items"]),
            bound_subject_count=count, unresolved_subject_count=len(rows) - count,
            implementation_issuer=dict(a_symbol=symbol, legal_name=name, evidence_binding=implementation_binding),
            official_archive_binding=observation_binding,
            official_archive_available_at=observation["acquired_at"],
            implementation_original_available_at=implementation_binding["available_at"],
            source_available_at=max(datetime.fromisoformat(observation["acquired_at"]),
                datetime.fromisoformat(implementation_binding["available_at"])).isoformat())
        for ref in (implementation_binding, observation_binding, archive["scan_binding"], *observation["source_bindings"]):
            if sha256_file(require_inside(root, root / ref["path"], "related source")) != ref["sha256"]:
                raise ValueError("Related source changed during review")
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, RuntimeError) as error:
        result.update(status="SOURCE_ARCHIVE_OR_IMPLEMENTATION_INVALID", diagnostic=str(error), items=[],
            reviewed_document_count=0, bound_subject_count=0, unresolved_subject_count=0)
    return result

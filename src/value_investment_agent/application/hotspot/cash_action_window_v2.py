"""Explicit v2 cash-basis consumer; never replace v1 or map a personal stop."""
from .corporate_action_coverage import inspect_official_action_coverage
from ...infrastructure.hotspot.cash_implementation_v2 import load_cash_implementation_v2
from ...infrastructure.evidence.historical_price_correspondence import require_inside, sha256_file


def inspect_cash_action_window_v2(*, root, symbol, record_date, registry_binding,
        start, end, now, observation_binding=None):
    coverage = inspect_official_action_coverage(root=root, symbol=symbol, start=start,
        end=end, now=now, observation_binding=observation_binding)
    result = dict(schema_version="hotspot-cash-action-window-v2", symbol=symbol,
        evaluated_at=now.isoformat(), status="NOT_ASSESSABLE", body_terms_status="NOT_ASSESSABLE",
        publication_coverage=coverage, implementation_proof=None, implementation_in_index=False,
        related_document_count=None, related_evidence_bindings=[], revision_status="NOT_EVALUATED", mapping=None,
        original_protection_adjusted=False, price_comparability="UNKNOWN", no_change=None,
        comparison_allowed=False, opening_state_verified=False, revision_absence_proven=False,
        formal_eligibility=False, position_guidance=None, strategy_validation="NOT_PROVEN",
        gaps=["OPENING_PENDING_ACTION_STATE_MISSING", "SEMANTIC_REVISION_ABSENCE_NOT_PROVEN"], action="no_order")
    try:
        proof = load_cash_implementation_v2(root=root, symbol=symbol, record_date=record_date,
            registry_binding=registry_binding, now=now)
        result.update(implementation_proof=proof, body_terms_status="READY",
            status="BODY_VERIFIED_WINDOW_PENDING", revision_status=proof["revision_status"])
        if coverage["official_publication_coverage"] != "COMPLETE":
            result["gaps"].append("COMPLETE_PRICE_FORMATION_PUBLICATION_WINDOW_REQUIRED")
            return result
        if coverage["publication_window"]["start"] > proof["terms"]["published_date"]:
            result.update(status="IMPLEMENTATION_PUBLICATION_NOT_COVERED")
            result["gaps"].append("SCAN_STARTS_AFTER_IMPLEMENTATION_PUBLICATION")
            return result
        original = proof["body_evidence_binding"]
        matches = [row for row in coverage["pending_announcements"] if row["source_url"] == original["url"]]
        if len(matches) != 1:
            result.update(status="IMPLEMENTATION_NOT_IN_INDEX")
            result["gaps"].append("IMPLEMENTATION_MISSING_OR_DUPLICATED_IN_OFFICIAL_INDEX")
            return result
        if any(ref["sha256"] != original["sha256"] for ref in matches[0]["evidence_bindings"]):
            raise ValueError("Implementation body conflicts with official index")
        result["implementation_in_index"] = True
        related = [dict(path=ref["path"], sha256=ref["sha256"], url=row["source_url"],
            available_at=coverage["source_available_at"]) for row in coverage["pending_announcements"]
            if row["announcement_id"] != matches[0]["announcement_id"] for ref in row["evidence_bindings"]]
        result["related_document_count"] = len(related)
        result["related_evidence_bindings"] = list(related)
        checked = load_cash_implementation_v2(root=root, symbol=symbol, record_date=record_date,
            registry_binding=registry_binding, now=now, related_disclosure_bindings=tuple(related))
        if any(sha256_file(require_inside(root, root / ref["path"], "cash v2 window source")) != ref["sha256"]
                for ref in coverage["evidence_bindings"]):
            raise ValueError("Official publication source changed during cash v2 review")
        result.update(implementation_proof=checked, revision_status=checked["revision_status"],
            status="REVISION_REVIEW_REQUIRED" if checked["revision_status"] == "PENDING_LINKAGE"
                else "IMPLEMENTATION_AND_PUBLICATION_WINDOW_BOUND")
        if checked["revision_status"] == "PENDING_LINKAGE":
            result["gaps"].append("CORRECTION_OR_CANCELLATION_LINKAGE_REQUIRED")
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        result.update(status="BODY_VERIFIED_RELATED_REVIEW_PENDING" if result["body_terms_status"] == "READY"
            else "NOT_ASSESSABLE", diagnostic=str(error))
        result["gaps"].append("RELATED_ORIGINAL_REVIEW_INCOMPLETE" if result["body_terms_status"] == "READY"
            else "EVENT_BODY_OR_REGISTRY_NOT_VERIFIED")
    return result

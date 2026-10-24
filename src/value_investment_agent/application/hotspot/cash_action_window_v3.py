"""Opt-in current re-evaluation; stored v2 artifacts and trading gates stay intact."""
from datetime import datetime

from .cash_action_window_v2 import inspect_cash_action_window_v2
from .cash_related_disclosures import inspect_cash_related_disclosures


def inspect_cash_action_window_v3(*, root, symbol, record_date, registry_binding,
        start, end, now, observation_binding=None):
    try:
        base = inspect_cash_action_window_v2(root=root, symbol=symbol, record_date=record_date,
            registry_binding=registry_binding, start=start, end=end, now=now, observation_binding=observation_binding)
    except RuntimeError as exc:
        return dict(schema_version="hotspot-cash-action-window-v3", symbol=symbol,
            evaluated_at=now.isoformat(), source_time=None, legacy_v2_review=None,
            related_disclosure_review=None, status="LEGACY_REVIEW_FAILED",
            failure_reason=str(exc), body_terms_status="UNKNOWN", mapping=None,
            original_protection_adjusted=False, price_comparability="UNKNOWN", no_change=None,
            revision_absence_proven=False, formal_eligibility=False, position_guidance=None,
            strategy_validation="NOT_PROVEN", action="no_order")
    review = None
    if (base["body_terms_status"] == "READY" and base["implementation_in_index"] is True
            and base["publication_coverage"]["official_publication_coverage"] == "COMPLETE"):
        binding = dict(base["implementation_proof"]["body_evidence_binding"])
        review = inspect_cash_related_disclosures(root=root, symbol=symbol,
            implementation_binding=binding, observation_binding=observation_binding,
            start=start, end=end, now=now)
    source_time = dict(base["implementation_proof"]["source_time"]) if base["implementation_proof"] else None
    if source_time and review and review.get("source_available_at"):
        source_time["official_archive_available_at"] = review["official_archive_available_at"]
        source_time["effective_source_available_at"] = max(
            datetime.fromisoformat(source_time["effective_source_available_at"]),
            datetime.fromisoformat(review["source_available_at"])).isoformat()
    return dict(schema_version="hotspot-cash-action-window-v3", symbol=symbol, evaluated_at=now.isoformat(),
        source_time=source_time,
        legacy_v2_review=base, related_disclosure_review=review,
        status=review["status"] if review else "RELATED_REVIEW_NOT_STARTED",
        body_terms_status=base["body_terms_status"], mapping=None, original_protection_adjusted=False,
        price_comparability="UNKNOWN", no_change=None, revision_absence_proven=False,
        formal_eligibility=False, position_guidance=None, strategy_validation="NOT_PROVEN", action="no_order")

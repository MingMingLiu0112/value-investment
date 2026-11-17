"""Official publication coverage is not complete effective-action coverage.

Reuse the full-window collector's raw-response verifier without trusting caller
coverage flags, title classifiers, or an empty search as a no-action certificate.
This read-only adapter never grants price comparability or historical PIT.
"""
from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path

from ..product.daily_event_observation import verify_retained_event_coverage
from ...infrastructure.evidence.historical_price_correspondence import require_inside, sha256_file
from ...quote_sessions import CHINA
from ...infrastructure.hotspot.cash_implementation import load_cash_implementation
from ...infrastructure.hotspot.action_lineage import inspect_action_lineage
from ...infrastructure.hotspot.capital_disclosure import inspect_capital_disclosures


VERSION = "hotspot-official-action-coverage-v1"
ACTION_FAMILIES = (
    "CASH_DISTRIBUTION", "BONUS_OR_CAPITALIZATION", "RIGHTS_ISSUE",
    "SPLIT_OR_CONSOLIDATION", "MERGER_OR_SHARE_CONVERSION", "AMENDMENT_OR_CANCELLATION",
)
MAX_OBSERVATION_BYTES = 4 * 1024 * 1024


def inspect_official_action_coverage(*, root: Path, symbol: str, start: date,
        end: date, now: datetime, observation_binding: dict | None = None) -> dict:
    """Reverify a retained, unfiltered official scan covering the price window.

    The scan can be wider than the requested window, but must be complete and
    elapsed in its entirety. An acquisition date is not the publication date or
    an independently attested historical availability date. Even full publication
    coverage lacks the opening pending-action state and reviewed effective terms.
    """
    if (now.utcoffset() is None or type(start) is not date or type(end) is not date
            or not start <= end <= now.astimezone(CHINA).date()
            or not isinstance(symbol, str) or len(symbol) != 6
            or not symbol.isascii() or not symbol.isdigit()):
        raise ValueError("Exact symbol and aware price-window cutoff required")
    result = dict(schema_version=VERSION, symbol=symbol, action="no_order",
        required_from=start.isoformat(), required_to=end.isoformat(),
        official_publication_coverage="MISSING", corporate_action_coverage="UNKNOWN",
        price_comparability="UNKNOWN", source_available_at=None,
        publication_window=None, announcement_count=None, pending_announcements=[],
        evidence_bindings=[], historical_availability_proven=False,
        pdf_semantics_reverified=False, effective_terms_verified=False,
        opening_pending_actions_verified=False, adjusted_protection_price=None,
        original_protection_preserved=True, formal_eligibility=False,
        strategy_validation="NOT_PROVEN",
        action_family_coverage={family: "UNKNOWN" for family in ACTION_FAMILIES},
        gaps=["OFFICIAL_PUBLICATION_WINDOW_MISSING", "OPENING_PENDING_ACTION_STATE_MISSING",
              "EFFECTIVE_TERMS_AND_AMENDMENT_CHAIN_UNREVIEWED",
              "SAME_BASIS_PRICE_MAPPING_NOT_VERIFIED"],
        verification_scope="RAW_OFFICIAL_PUBLICATION_WINDOW_NOT_EFFECTIVE_ACTION_COVERAGE")
    if observation_binding is None:
        return result
    try:
        root = root.resolve()
        if not isinstance(observation_binding, dict) or set(observation_binding) != {"path", "sha256"}:
            raise ValueError("Observation binding requires only path and sha256")
        relative = Path(observation_binding["path"])
        path = require_inside(root, root / relative, "official observation")
        if (relative.is_absolute() or not 0 < path.stat().st_size <= MAX_OBSERVATION_BYTES
                or sha256_file(path) != observation_binding["sha256"]):
            raise ValueError("Official observation binding mismatch")
        observation = json.loads(path.read_bytes())
        if not isinstance(observation, dict):
            raise ValueError("Official observation must be an object")
        scan_from = date.fromisoformat(observation["scan_from"])
        scan_to = date.fromisoformat(observation["scan_to"])
        proof = verify_retained_event_coverage(root, observation, symbol=symbol,
            required_from=scan_from, required_to=scan_to, now=now)
        scan_path = require_inside(root, root / proof["scan_binding"]["path"], "official scan")
        if sha256_file(scan_path) != proof["scan_binding"]["sha256"]:
            raise ValueError("Official scan changed after verification")
        scan = json.loads(scan_path.read_bytes())
        # Every announcement remains pending, including seemingly unrelated
        # titles. Absence of a keyword is not a reviewed absence of an action.
        pending = [dict(announcement_id=row["announcement_id"], title=row["title"],
            source_url=row["source_url"], published_at=row["published_at"],
            evidence_bindings=deepcopy(row["evidence_refs"]),
            review_status="PENDING_EFFECTIVE_ACTION_REVIEW",
            action_family="UNCLASSIFIED", effective_at=None)
            for row in scan["announcements"]]
        bindings = [dict(observation_binding), dict(proof["scan_binding"]),
            *[dict(path=ref["path"], sha256=ref["sha256"]) for ref in observation["source_bindings"]]]
        # Guard the exact bytes consumed across verification and projection.
        if any(sha256_file(require_inside(root, root / ref["path"], "official evidence"))
                != ref["sha256"] for ref in bindings):
            raise ValueError("Official evidence changed during projection")
        covers = scan_from <= start and scan_to >= end
        result.update(official_publication_coverage="COMPLETE" if covers else "PARTIAL",
            source_available_at=observation["acquired_at"],
            publication_window=dict(start=scan_from.isoformat(), end=scan_to.isoformat()),
            announcement_count=len(pending), pending_announcements=pending,
            evidence_bindings=bindings)
        result["gaps"][0:1] = [] if covers else ["PUBLICATION_SCAN_DOES_NOT_COVER_PRICE_FORMATION_WINDOW"]
        if pending:
            result["gaps"].append("ANNOUNCEMENT_SEMANTICS_UNREVIEWED")
        result["lineage_review"] = inspect_action_lineage(root=root, symbol=symbol, announcements=pending,
            acquired_at=observation["acquired_at"], now=now)
        result["capital_disclosure_review"] = inspect_capital_disclosures(root=root, symbol=symbol,
            announcements=pending, acquired_at=observation["acquired_at"], now=now)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result.update(official_publication_coverage="INVALID_OR_UNAVAILABLE", diagnostic=str(error))
        result["gaps"][0] = "OFFICIAL_PUBLICATION_WINDOW_INVALID_OR_UNAVAILABLE"
    return result


def inspect_cash_action_window(*, root: Path, symbol: str, record_date: date,
        registry_binding: dict, start: date, end: date, now: datetime,
        observation_binding: dict) -> dict:
    """Bind an implementation and EVERY other archived publication to its review.

    A complete publication range is required even for this event-local check.
    The opening action state and semantic absence of amendments remain separate;
    this result never certifies no-change or permits full-window comparison.
    """
    coverage = inspect_official_action_coverage(root=root, symbol=symbol, start=start,
        end=end, now=now, observation_binding=observation_binding)
    result = dict(schema_version="hotspot-cash-action-window-v1", symbol=symbol,
        action="no_order", status="WINDOW_UNAVAILABLE", publication_coverage=coverage,
        implementation_proof=None, implementation_in_index=False,
        related_document_count=None, revision_status="NOT_EVALUATED",
        price_comparability="UNKNOWN", no_change=None, comparison_allowed=False,
        opening_state_verified=False, revision_absence_proven=False,
        formal_eligibility=False, scope="EVENT_PUBLICATION_CHAIN_NOT_COMPLETE_PRICE_BASIS",
        evidence_bindings=list(coverage["evidence_bindings"]),
        gaps=["OPENING_PENDING_ACTION_STATE_MISSING", "SEMANTIC_REVISION_ABSENCE_NOT_PROVEN"])
    if coverage["official_publication_coverage"] != "COMPLETE":
        result["gaps"].append("COMPLETE_PRICE_FORMATION_PUBLICATION_WINDOW_REQUIRED")
        return result
    try:
        original = load_cash_implementation(root=root, symbol=symbol, record_date=record_date,
            registry_binding=registry_binding, now=now)
        result["implementation_proof"] = original
        binding = original["body_evidence_binding"]
        if coverage["publication_window"]["start"] > original["terms"]["published_date"]:
            result.update(status="IMPLEMENTATION_PUBLICATION_NOT_COVERED")
            result["gaps"].append("SCAN_STARTS_AFTER_IMPLEMENTATION_PUBLICATION")
            return result
        matches = [row for row in coverage["pending_announcements"] if row["source_url"] == binding["url"]]
        if len(matches) != 1:
            result.update(status="IMPLEMENTATION_NOT_IN_INDEX")
            result["gaps"].append("IMPLEMENTATION_MISSING_OR_DUPLICATED_IN_OFFICIAL_INDEX")
            return result
        if any(ref["sha256"] != binding["sha256"] for ref in matches[0]["evidence_bindings"]):
            raise ValueError("Implementation original conflicts with official window")
        result["implementation_in_index"] = True
        related = []
        for row in coverage["pending_announcements"]:
            if row["announcement_id"] == matches[0]["announcement_id"]:
                continue
            for ref in row["evidence_bindings"]:
                related.append(dict(path=ref["path"], sha256=ref["sha256"], url=row["source_url"],
                                    available_at=coverage["source_available_at"]))
        result["related_document_count"] = len(related)
        # No title/keyword filter: a neutral title must not hide a body correction.
        checked = load_cash_implementation(root=root, symbol=symbol, record_date=record_date,
            registry_binding=registry_binding, now=now, related_disclosure_bindings=tuple(related))
        if any(sha256_file(require_inside(root, root / ref["path"], "cash window source")) != ref["sha256"]
               for ref in coverage["evidence_bindings"]):
            raise ValueError("Official publication window changed during event review")
        result.update(implementation_proof=checked, revision_status=checked["revision_status"],
            status="REVISION_REVIEW_REQUIRED" if checked["revision_status"] == "PENDING_LINKAGE"
            else "IMPLEMENTATION_AND_PUBLICATION_WINDOW_BOUND")
        result["evidence_bindings"].extend(checked["evidence_bindings"])
        if checked["revision_status"] == "PENDING_LINKAGE":
            result["gaps"].append("CORRECTION_OR_CANCELLATION_LINKAGE_REQUIRED")
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        result.update(status="EVENT_CHAIN_UNAVAILABLE", implementation_in_index=False, diagnostic=str(error))
        result["gaps"].append("EVENT_BODY_OR_WINDOW_CORRESPONDENCE_FAILED")
    return result

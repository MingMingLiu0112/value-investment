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
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        result.update(official_publication_coverage="INVALID_OR_UNAVAILABLE", diagnostic=str(error))
        result["gaps"][0] = "OFFICIAL_PUBLICATION_WINDOW_INVALID_OR_UNAVAILABLE"
    return result

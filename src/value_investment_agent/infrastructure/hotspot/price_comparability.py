"""Reuse reviewed distribution correspondence; incomplete evidence stays unknown."""
from datetime import datetime, date
import json
from pathlib import Path

from ..evidence.historical_distribution_correspondence import verify_distribution_correspondence
from ..evidence.historical_price_correspondence import require_inside, sha256_file
from ...domain.hotspot.price_comparability import assess_price_comparability
from ...quote_sessions import CHINA


def inspect_price_comparability(*, root: Path, symbol: str, start: date, end: date,
        now: datetime, registry_binding: dict | None = None) -> dict:
    """The binding's acquisition stamp is not independent historical PIT proof.

    Only existing reviewed gross entitlements are consumed. Neither registry
    claims nor a zero-match query can grant full corporate-action coverage.
    """
    if now.utcoffset() is None or end > now.astimezone(CHINA).date():
        raise ValueError("Timezone-aware comparability cutoff required")
    result = assess_price_comparability(start=start, end=end, events=[])
    result.update(source_status="MISSING", evidence_bindings=[],
        source_available_at=None, historical_availability_proven=False,
        pdf_semantics_reverified=False,
        verification_scope="RETAINED_REVIEWED_DISTRIBUTIONS_NOT_COMPLETE_EVENT_COVERAGE")
    if registry_binding is None:
        return result
    try:
        available = datetime.fromisoformat(registry_binding["available_at"])
        if available.utcoffset() is None or available > now:
            raise ValueError("Distribution reference unavailable at cutoff")
        root = root.resolve()
        path = require_inside(root, root / registry_binding["path"], "distribution registry")
        if Path(registry_binding["path"]).is_absolute() or sha256_file(path) != registry_binding["sha256"]:
            raise ValueError("Invalid distribution registry binding")
        registry = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(registry["events"], list) or any(not isinstance(row, dict) for row in registry["events"]):
            raise ValueError("Distribution registry requires event objects")
        events = [row for row in registry["events"] if row.get("symbol") == symbol]
        # The correspondence verifier filters record dates. Include an earlier
        # record date even when its ex-date falls inside the price window.
        earliest = min([start.isoformat(), *[row["record_date"] for row in events]])
        selected = [row for row in events if row["record_date"] <= end.isoformat()]
        references = [dict(kind="reviewed_event_registry", path=registry_binding["path"],
                           sha256=registry_binding["sha256"])]
        cash = []
        for row in selected:
            references.extend(dict(kind="distribution", **original) for original in row["evidence"])
            cash.append(dict(event_id=symbol + ":" + row["record_date"],
                record_date=row["record_date"], ex_date=row["ex_date"],
                payment_date=row["cash_payment_date"], cash_per_share=row["cash_per_share"],
                bonus_shares_per_share=row.get("bonus_shares_per_share", "0"),
                bonus_listing_date=row.get("bonus_listing_date")))
        proof = verify_distribution_correspondence(root=root, symbol=symbol,
            sessions=[dict(date=earliest), dict(date=end.isoformat())],
            cash_events=cash, references=references)
        if proof["status"] != "MATCH":
            raise ValueError("Distribution correspondence unavailable")
        result.update(assess_price_comparability(start=start, end=end, events=proof["rows"],
            coverage_complete=proof["complete_historical_coverage_proven"]))
        result.update(source_status="VERIFIED_RETAINED_CORRESPONDENCE",
            source_available_at=available.isoformat(),
            evidence_bindings=[{key: ref[key] for key in ("path", "sha256")} for ref in references],
            reviewed_event_count=proof["matched_events"])
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        result.update(source_status="INVALID_OR_UNAVAILABLE", reason="CORPORATE_ACTION_EVIDENCE_UNAVAILABLE",
            diagnostic=str(error), evidence_bindings=[])
    return result

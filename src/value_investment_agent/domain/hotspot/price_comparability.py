"""Price-basis compatibility is not a return adjustment or trading permission."""
from datetime import date


VERSION = "hotspot-price-comparability-v1"


def assess_price_comparability(*, start: date, end: date, events: list[dict],
        coverage_complete: bool = False) -> dict:
    """Consume verified coverage, never infer absence from an empty event list.

    The retained-distribution adapter cannot establish complete coverage. The
    CONFIRMED branch is the domain contract for a future complete-coverage
    verifier; no current caller may turn registry metadata into that proof.
    """
    if start > end or type(coverage_complete) is not bool:
        raise ValueError("Invalid price comparability interval or coverage")
    crossings = [event for event in events if start < date.fromisoformat(event["ex_date"]) <= end]
    status = "INCOMPARABLE" if crossings else "CONFIRMED" if coverage_complete else "UNKNOWN"
    return dict(schema_version=VERSION, status=status,
        reason="IMPLEMENTED_DISTRIBUTION_CROSSES_PRICE_WINDOW" if crossings else
            "COMPLETE_SAME_BASIS_COVERAGE" if coverage_complete else "CORPORATE_ACTION_COVERAGE_INCOMPLETE",
        window_start=start.isoformat(), window_end=end.isoformat(),
        price_basis="UNADJUSTED", crossing_events=crossings,
        complete_corporate_action_coverage=coverage_complete,
        adjusted_protection_price=None, original_protection_preserved=True,
        scope="PRICE_BASIS_ONLY_NOT_TAX_TOTAL_RETURN_OR_PERSONAL_PERMISSION",
        formal_eligibility=False, action="no_order")

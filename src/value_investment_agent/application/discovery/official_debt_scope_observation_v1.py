"""Read-only debt-scope diagnostic for the initial screening queue.

This module deliberately does not admit a debt fact.  It makes the boundary
between an officially located financing bucket and a complete debt scope
visible before a company enters deeper evidence enrichment.
"""
from copy import deepcopy

from ...domain.discovery.financial_source_comparison_v1 import DEBT_LABELS

VERSION = "official-debt-scope-observation-v1"


def review(*, symbol: str, period: str | None, official_summary: dict) -> dict:
    """Describe coverage without treating omitted PDF rows as zero.

    ``official_summary`` is the already validated, non-overlapping source
    observation from the annual-report parser.  Complete classification still
    requires the separate ResearchCase evidence contract.
    """
    summary = deepcopy(official_summary or {})
    components = summary.get("components") or []
    fields = {item.get("field") for item in components}
    required = tuple(DEBT_LABELS)
    missing = [field for field in required if field not in fields]
    source_errors = list(summary.get("errors") or [])
    status = "NOT_AVAILABLE"
    if components:
        status = "PARTIAL_OFFICIAL_COMPONENTS"
    if source_errors:
        status = "SOURCE_CONFLICT_OR_AMBIGUITY"
    issues = ["OFFICIAL_COMPONENT_NOT_LOCATED:" + field for field in missing]
    issues.extend("OFFICIAL_SOURCE:" + item for item in source_errors)
    issues.append("INDEPENDENT_SOURCE_AND_SCOPE_CLASSIFICATION_REQUIRED")
    return dict(
        version=VERSION,
        symbol=symbol,
        period=period,
        status=status,
        identified_components=components,
        missing_components=missing,
        unresolved_classifications=[
            field for field in fields if field not in {
                "short_term_borrowings", "short_term_bonds",
                "long_term_borrowings_noncurrent", "long_term_borrowings_current",
                "lease_liabilities_noncurrent", "lease_liabilities_current",
                "bonds_payable_current", "long_term_payables_current",
            }
        ],
        issues=issues,
        complete_debt_verified=False,
        formal_admission=False,
        action="no_order",
    )

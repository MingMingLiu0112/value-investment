"""Read-only debt-scope diagnostic for the initial screening queue.

This module deliberately does not admit a debt fact.  It makes the boundary
between an officially located financing bucket and a complete debt scope
visible before a company enters deeper evidence enrichment.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from ...domain.discovery.financial_source_comparison_v1 import DEBT_LABELS

VERSION = "official-debt-scope-observation-v1"

# Annual-report buckets are intentionally more granular than the structured
# provider's balance-sheet headings.  Only unambiguous one-to-one pairs may be
# compared in the initial screen; current maturities must not be silently
# folded into non-current borrowings or leases.
PROVIDER_FIELD = {
    "short_term_borrowings": "short_term_borrowings",
    "long_term_borrowings_noncurrent": "long_term_borrowings",
    "lease_liabilities_noncurrent": "lease_liabilities_noncurrent",
}


def _amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def review(*, symbol: str, period: str | None, official_summary: dict,
           provider_components: list[dict] | None = None) -> dict:
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
    provider = {item.get("field"): item for item in provider_components or []}
    comparisons = []
    for official in components:
        source_field = official.get("field")
        provider_field = PROVIDER_FIELD.get(source_field)
        if provider_field is None:
            comparisons.append(dict(
                official_field=source_field, provider_field=None,
                status="NO_SAFE_PROVIDER_MAPPING", reason="当前到期或专用融资桶不能与宽口径余额表项目自动合并。",
            ))
            continue
        candidate = provider.get(provider_field) or {}
        official_value = _amount(official.get("value"))
        provider_value = _amount(candidate.get("value"))
        if candidate.get("status") == "CONFLICT":
            state, reason = "PROVIDER_CONFLICT", "独立结构化来源自身存在金额冲突。"
        elif official_value is None or provider_value is None:
            state, reason = "NOT_COMPARABLE", "一方未提供明确同口径金额；不按零处理。"
        elif official_value == provider_value:
            state, reason = "MATCHED", "官方附注与独立结构化余额表同口径金额一致；仍非完整债务范围。"
        else:
            state, reason = "AMOUNT_MISMATCH", "官方附注与独立结构化余额表金额不同，保留冲突等待复核。"
        comparisons.append(dict(
            official_field=source_field, provider_field=provider_field,
            official_value=str(official_value) if official_value is not None else None,
            provider_value=str(provider_value) if provider_value is not None else None,
            status=state, reason=reason,
        ))
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
        independent_comparisons=comparisons,
        matched_component_count=sum(item.get("status") == "MATCHED" for item in comparisons),
        conflicting_component_count=sum(item.get("status") in {"AMOUNT_MISMATCH", "PROVIDER_CONFLICT"}
                                        for item in comparisons),
        issues=issues,
        complete_debt_verified=False,
        formal_admission=False,
        action="no_order",
    )

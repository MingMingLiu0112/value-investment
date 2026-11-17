"""Evidence-bound separation of legacy operations and newly consolidated scope.

An operating forecast cannot treat an acquisition or a newly consolidated entity
as generic fixed-cost absorption.  This small domain contract keeps the two
economic mechanisms distinct before a D2 annual supplement can become an input
to shareholder-cash or valuation work.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


VERSION = "operating-scope-decomposition-v1"
SCOPE_KINDS = frozenset({"LEGACY_ORGANIC", "NEWLY_CONSOLIDATED", "UNKNOWN"})
CONTRACT_KINDS = frozenset({"BOT", "BOO", "MIXED", "UNKNOWN"})
MEASUREMENT_BASES = frozenset({"REPORTED_EXACT", "REPORTED_APPROXIMATE", "DERIVED_FROM_REPORTED", "UNSPECIFIED"})


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field}_INVALID")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}_INVALID") from None
    if not result.is_finite():
        raise ValueError(f"{field}_INVALID")
    return result


@dataclass(frozen=True)
class ScopeContribution:
    """One revenue/profit mechanism, with its own evidence and uncertainty."""

    scope_kind: str
    revenue_change_cny: Decimal
    profit_change_cny: Decimal | None
    evidence_ids: tuple[str, ...]
    contract_kind: str = "UNKNOWN"
    cash_handover_assumption: str | None = None
    measurement_basis: str = "UNSPECIFIED"
    calculation: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ScopeContribution":
        required = {"scope_kind", "revenue_change_cny", "profit_change_cny", "evidence_ids"}
        if set(value) - {"scope_kind", "revenue_change_cny", "profit_change_cny", "evidence_ids",
                         "contract_kind", "cash_handover_assumption", "measurement_basis",
                         "calculation"} or required - set(value):
            raise ValueError("SCOPE_CONTRIBUTION_FIELDS_INVALID")
        scope_kind = value["scope_kind"]
        contract_kind = value.get("contract_kind", "UNKNOWN")
        measurement_basis = value.get("measurement_basis", "UNSPECIFIED")
        if (scope_kind not in SCOPE_KINDS or contract_kind not in CONTRACT_KINDS
                or measurement_basis not in MEASUREMENT_BASES):
            raise ValueError("SCOPE_CONTRIBUTION_CLASSIFICATION_INVALID")
        evidence = value["evidence_ids"]
        if (not isinstance(evidence, Sequence) or isinstance(evidence, str)
                or not evidence or any(not isinstance(item, str) or not item for item in evidence)):
            raise ValueError("SCOPE_CONTRIBUTION_EVIDENCE_REQUIRED")
        handover = value.get("cash_handover_assumption")
        if handover is not None and handover not in {"FREE_BOT_ONLY", "NO_FREE_HANDOVER", "UNKNOWN"}:
            raise ValueError("SCOPE_HANDOVER_ASSUMPTION_INVALID")
        if contract_kind == "BOO" and handover == "FREE_BOT_ONLY":
            raise ValueError("BOO_CANNOT_USE_BOT_FREE_HANDOVER")
        calculation = value.get("calculation")
        if calculation is not None and (not isinstance(calculation, str) or not calculation.strip()
                                        or len(calculation) > 500):
            raise ValueError("SCOPE_CONTRIBUTION_CALCULATION_INVALID")
        if measurement_basis == "DERIVED_FROM_REPORTED" and calculation is None:
            raise ValueError("SCOPE_DERIVED_CONTRIBUTION_CALCULATION_REQUIRED")
        profit = value["profit_change_cny"]
        return cls(
            scope_kind=scope_kind,
            revenue_change_cny=_decimal(value["revenue_change_cny"], "SCOPE_REVENUE"),
            profit_change_cny=None if profit is None else _decimal(profit, "SCOPE_PROFIT"),
            evidence_ids=tuple(evidence), contract_kind=contract_kind,
            cash_handover_assumption=handover, measurement_basis=measurement_basis,
            calculation=calculation,
        )


def validate_scope_decomposition(
    contributions: Sequence[Mapping[str, object]], *, known_evidence_ids: set[str],
    scope_change_expected: bool | None = None,
) -> tuple[ScopeContribution, ...]:
    """Validate scope evidence without treating consolidation as universal.

    A stable operating scope needs a source-bound ``LEGACY_ORGANIC`` bridge.
    A known scope change additionally needs a separately evidenced
    ``NEWLY_CONSOLIDATED`` revenue and profit bridge.  The optional flag is
    supplied by a source/issuer applicability assessment; it is never inferred
    from a valuation result or from a missing contribution.
    """
    if not isinstance(contributions, Sequence) or isinstance(contributions, str) or not contributions:
        raise ValueError("SCOPE_DECOMPOSITION_REQUIRED")
    parsed = tuple(ScopeContribution.from_mapping(value) for value in contributions)
    kinds = {item.scope_kind for item in parsed}
    if "LEGACY_ORGANIC" not in kinds:
        raise ValueError("LEGACY_SCOPE_BRIDGE_REQUIRED")
    has_new_scope = "NEWLY_CONSOLIDATED" in kinds
    if scope_change_expected is True and not has_new_scope:
        raise ValueError("NEW_SCOPE_BRIDGE_REQUIRED")
    if scope_change_expected is False and has_new_scope:
        raise ValueError("UNEXPECTED_NEW_SCOPE_CONTRIBUTION")
    if "UNKNOWN" in kinds:
        raise ValueError("SCOPE_DECOMPOSITION_UNKNOWN")
    for item in parsed:
        if not set(item.evidence_ids) <= known_evidence_ids:
            raise ValueError("SCOPE_DECOMPOSITION_EVIDENCE_UNKNOWN")
        if item.scope_kind == "NEWLY_CONSOLIDATED" and item.profit_change_cny is None:
            raise ValueError("NEW_SCOPE_PROFIT_BRIDGE_REQUIRED")
    return parsed

import pytest

from value_investment_agent.domain.research.operating_scope_decomposition_v1 import (
    validate_scope_decomposition,
)


EVIDENCE = {"annual-p183", "annual-p24", "h1-p13"}


def rows(*, handover="NO_FREE_HANDOVER"):
    return [
        {"scope_kind": "LEGACY_ORGANIC", "revenue_change_cny": "10", "profit_change_cny": "2",
         "evidence_ids": ["annual-p24"], "contract_kind": "BOT", "cash_handover_assumption": "FREE_BOT_ONLY"},
        {"scope_kind": "NEWLY_CONSOLIDATED", "revenue_change_cny": "8", "profit_change_cny": "1",
         "evidence_ids": ["annual-p183"], "contract_kind": "BOO", "cash_handover_assumption": handover},
    ]


def test_accepts_evidence_bound_legacy_and_new_scope_profit_bridges_when_scope_changed():
    result = validate_scope_decomposition(rows(), known_evidence_ids=EVIDENCE)
    assert [item.scope_kind for item in result] == ["LEGACY_ORGANIC", "NEWLY_CONSOLIDATED"]


def test_accepts_stable_scope_without_inventing_newly_consolidated_business():
    result = validate_scope_decomposition([rows()[0]], known_evidence_ids=EVIDENCE,
                                          scope_change_expected=False)
    assert [item.scope_kind for item in result] == ["LEGACY_ORGANIC"]


@pytest.mark.parametrize("value, reason", [
    ([{**rows()[1]}], "LEGACY_SCOPE_BRIDGE_REQUIRED"),
    ([{**rows()[0], "evidence_ids": ["not-real"]}, {**rows()[1]}], "SCOPE_DECOMPOSITION_EVIDENCE_UNKNOWN"),
    ([{**rows()[0]}, {**rows()[1], "profit_change_cny": None}], "NEW_SCOPE_PROFIT_BRIDGE_REQUIRED"),
    (rows(handover="FREE_BOT_ONLY"), "BOO_CANNOT_USE_BOT_FREE_HANDOVER"),
])
def test_rejects_unproven_scope_or_contract_shortcuts(value, reason):
    with pytest.raises(ValueError, match=reason):
        validate_scope_decomposition(value, known_evidence_ids=EVIDENCE)


def test_declared_scope_applicability_cannot_be_silently_reversed():
    with pytest.raises(ValueError, match="NEW_SCOPE_BRIDGE_REQUIRED"):
        validate_scope_decomposition([rows()[0]], known_evidence_ids=EVIDENCE,
                                     scope_change_expected=True)
    with pytest.raises(ValueError, match="UNEXPECTED_NEW_SCOPE_CONTRIBUTION"):
        validate_scope_decomposition(rows(), known_evidence_ids=EVIDENCE,
                                     scope_change_expected=False)


def test_preserves_approximate_and_derived_scope_measurement_basis():
    result = validate_scope_decomposition([
        {"scope_kind":"LEGACY_ORGANIC", "revenue_change_cny":"-670000000",
         "profit_change_cny":"340000000", "evidence_ids":["annual-p24"],
         "measurement_basis":"DERIVED_FROM_REPORTED",
         "calculation":"reported total year-on-year change minus reported new-scope contribution"},
        {"scope_kind":"NEWLY_CONSOLIDATED", "revenue_change_cny":"2721000000",
         "profit_change_cny":"270000000", "evidence_ids":["annual-p24"],
         "measurement_basis":"REPORTED_APPROXIMATE"},
    ], known_evidence_ids=EVIDENCE, scope_change_expected=True)
    assert result[0].measurement_basis == "DERIVED_FROM_REPORTED"
    assert result[1].measurement_basis == "REPORTED_APPROXIMATE"


def test_derived_scope_amount_requires_its_calculation():
    with pytest.raises(ValueError, match="DERIVED_CONTRIBUTION_CALCULATION_REQUIRED"):
        validate_scope_decomposition([{
            "scope_kind":"LEGACY_ORGANIC", "revenue_change_cny":"1", "profit_change_cny":"1",
            "evidence_ids":["annual-p24"], "measurement_basis":"DERIVED_FROM_REPORTED",
        }], known_evidence_ids=EVIDENCE, scope_change_expected=False)

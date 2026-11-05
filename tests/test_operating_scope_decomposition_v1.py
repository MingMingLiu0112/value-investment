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


def test_requires_evidence_bound_legacy_and_new_scope_profit_bridges():
    result = validate_scope_decomposition(rows(), known_evidence_ids=EVIDENCE)
    assert [item.scope_kind for item in result] == ["LEGACY_ORGANIC", "NEWLY_CONSOLIDATED"]


@pytest.mark.parametrize("value, reason", [
    ([rows()[0]], "LEGACY_AND_NEW_SCOPE_SEPARATION_REQUIRED"),
    ([{**rows()[0], "evidence_ids": ["not-real"]}, {**rows()[1]}], "SCOPE_DECOMPOSITION_EVIDENCE_UNKNOWN"),
    ([{**rows()[0]}, {**rows()[1], "profit_change_cny": None}], "NEW_SCOPE_PROFIT_BRIDGE_REQUIRED"),
    (rows(handover="FREE_BOT_ONLY"), "BOO_CANNOT_USE_BOT_FREE_HANDOVER"),
])
def test_rejects_unproven_scope_or_contract_shortcuts(value, reason):
    with pytest.raises(ValueError, match=reason):
        validate_scope_decomposition(value, known_evidence_ids=EVIDENCE)

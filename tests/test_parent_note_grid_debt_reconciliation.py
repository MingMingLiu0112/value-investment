import json

import pytest

from value_investment_agent.application.research.parent_note_grid_debt_reconciliation import stress_reconciliation


class BoundPolicy:
    def _bound(self, pin):
        assert pin == {"test": True}
        return dict(scenario="bear.policy", source_fingerprint="fixture", response=dict(text=json.dumps({
            "years": [2026, 2027], "series": {"new_borrowing": {"values": ["0", "2"]},
                                            "debt_repayment": {"values": ["7", "3"]}}})))


def test_pressure_roll_forward_never_becomes_financing_fact():
    spec = dict(policy_capital_basis=dict(amount_cny="100", scope="ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"),
                terminal_response_wire="NOTE_GRID_FLAT_TERMINAL_V1", source_fingerprint="fixture")
    state = dict(error_code="BEAR_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID", responses={"bear.policy": {"test": True}})
    review = stress_reconciliation(BoundPolicy(), spec, state)
    assert review["stress_closing_cny"] == "92"
    assert review["verified_financing_balance_cny"] is None
    assert stress_reconciliation(BoundPolicy(), spec, dict(state, error_code=None)) is None
    with pytest.raises(ValueError, match="SOURCE_BINDING_MISMATCH"):
        stress_reconciliation(BoundPolicy(), dict(spec, source_fingerprint="changed"), state)

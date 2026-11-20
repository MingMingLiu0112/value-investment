"""TEST_ONLY exact arithmetic and fail-closed financing scope checks."""
from copy import deepcopy
import pytest

from value_investment_agent.application.research.parent_financing_bridge_v1 import (
    BALANCE_FIELDS, reconcile_parent_financing,
)


def _statement(period, values, flows=None):
    def fact(field, value):
        return dict(classification="FACT", scope="ISSUER_PARENT_STANDALONE",
                    currency="CNY", current=str(value),
                    source_refs=dict(current_period=period, field=field,
                                     path="runtime/TEST_ONLY.pdf", sha256="a" * 64))
    return dict(symbol="600887", issuer_name="TEST_ONLY_ISSUER",
                scope="ISSUER_PARENT_STANDALONE", period_end=period,
                opening_balance_as_of=("2024-12-31" if period == "2025-12-31"
                                       else "2025-12-31"),
                balance_sheet={key: fact(key, value) for key, value in zip(BALANCE_FIELDS, values)},
                cash_flow={key: fact(key, value) for key, value in (flows or {}).items()})


def test_reported_cash_flows_do_not_magically_reconcile_partial_balance_lines():
    fy = _statement("2025-12-31", (10, 4, 1, 1))
    h1 = _statement("2026-06-30", (8, 2, 1, 1),
                    {"borrowings_received_cny": 20, "debt_repaid_cny": 30})
    bridge = reconcile_parent_financing(fy, h1)
    assert bridge["opening_identified_balance_cny"] == "16"
    assert bridge["closing_identified_balance_cny"] == "12"
    assert bridge["reported_net_borrowing_cash_cny"] == "-10"
    assert bridge["unallocated_reconciliation_difference_cny"] == "6"
    assert bridge["complete_debt_scope_verified"] is False
    assert bridge["maturity_schedule_verified"] is False
    assert bridge["action"] == "no_order"


@pytest.mark.parametrize("change", ("period", "issuer", "scope", "source"))
def test_bridge_rejects_incomparable_sources(change):
    fy = _statement("2025-12-31", (10, 4, 1, 1))
    h1 = _statement("2026-06-30", (8, 2, 1, 1),
                    {"borrowings_received_cny": 20, "debt_repaid_cny": 30})
    h1 = deepcopy(h1)
    if change == "period":
        h1["opening_balance_as_of"] = "2024-12-31"
    elif change == "issuer":
        h1["issuer_name"] = "TEST_ONLY_OTHER"
    elif change == "scope":
        h1["balance_sheet"][BALANCE_FIELDS[0]]["scope"] = "CONSOLIDATED"
    else:
        h1["cash_flow"]["debt_repaid_cny"]["source_refs"]["current_period"] = "2025-12-31"
    with pytest.raises(ValueError, match="PARENT_FINANCING_"):
        reconcile_parent_financing(fy, h1)


def test_missing_parent_line_preserves_comparable_evidence_without_full_difference():
    fy = _statement("2025-12-31", (10, 4, 1, 1))
    h1 = _statement("2026-06-30", (8, 2, 1, 1),
                    {"borrowings_received_cny": 20, "debt_repaid_cny": 30})
    del fy["balance_sheet"][BALANCE_FIELDS[0]]
    bridge = reconcile_parent_financing(fy, h1)
    assert bridge["reconciliation_status"] == "PARTIAL_MISSING_COMPARABLE_BALANCE_LINES"
    assert bridge["missing_balance_fields_by_period"]["2025-12-31"] == [BALANCE_FIELDS[0]]
    assert bridge["opening_identified_balance_cny"] == "6"
    assert bridge["closing_identified_balance_cny"] == "4"
    assert bridge["reported_net_borrowing_cash_cny"] == "-10"
    assert bridge["unallocated_reconciliation_difference_cny"] is None
    assert bridge["complete_debt_scope_verified"] is False

    h1["balance_sheet"][BALANCE_FIELDS[0]]["scope"] = "CONSOLIDATED"
    with pytest.raises(ValueError, match="PARENT_FINANCING_FACT_SCOPE_OR_SOURCE_CHANGED"):
        reconcile_parent_financing(fy, h1)

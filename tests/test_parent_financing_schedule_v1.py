from copy import deepcopy

import pytest

from value_investment_agent.application.research.parent_financing_schedule_v1 import (
    project_parent_financing_schedule,
)


def test_parent_financing_schedule_excludes_repeat_issue_and_keeps_cash_unverified():
    issue = {
        "issue": {
            "code": "012345678",
            "interest_start": "2026-10-01",
            "maturity": "2026-12-29",
            "face_value_cny": "100",
            "issue_price_per_100_face_cny": "98",
        },
        "source_binding": {"path": "runtime/fixture.pdf", "sha256": "a" * 64},
    }
    inputs = {
        "period_end": "2026-09-30",
        "reported_ytd": {
            "borrowings_received_cny": {"current": "150.00"},
            "debt_repayments_paid_cny": {"current": "90.00"},
        },
    }
    result = project_parent_financing_schedule(**inputs, issuance_events=[issue, issue])
    assert result["reported_ytd_cny"]["borrowings_received_cny"] == "150.00"
    assert result["later_issuance_proceeds_at_issue_price_cny"] == "98"
    assert result["scheduled_face_principal_by_maturity_cny"] == {"2026-12-29": "100"}
    assert not result["actual_later_cash_verified"]
    assert not result["remaining_debt_verified"]
    assert result["action"] == "no_order"

    conflict = deepcopy(issue)
    conflict["issue"]["face_value_cny"] = "110"
    with pytest.raises(ValueError, match="CONFLICTING_ISSUE_TERMS"):
        project_parent_financing_schedule(**inputs, issuance_events=[issue, conflict])


def test_disclosed_policy_rejects_balancing_borrowing_and_missing_maturity():
    import pytest
    from value_investment_agent.application.research.parent_financing_schedule_v1 import (
        validate_disclosed_financing_policy,
    )

    schedule = {
        "period_end": "2026-09-30",
        "reported_ytd_cny": {
            "borrowings_received_cny": "182711547658.23",
            "debt_repayments_paid_cny": "202501881888.99",
        },
        "later_issuance_proceeds_at_issue_price_cny": "45000000000",
        "scheduled_face_principal_by_maturity_cny": {
            "2026-12-29": "22500000000",
            "2026-12-30": "19000000000",
            "2027-11-12": "3500000000",
        },
    }

    def policy(borrowing, next_year_repayment):
        return {"years": [2026, 2027], "series": {
            "new_borrowing": {"values": [borrowing, "0"]},
            "debt_repayment": {"values": ["244001881888.99", next_year_repayment]},
        }}

    validate_disclosed_financing_policy(schedule, policy("227711547658.23", "3500000000"))
    with pytest.raises(ValueError, match="PARENT_FINANCING_ABOVE_DISCLOSED_PROCEEDS:2026"):
        validate_disclosed_financing_policy(schedule, policy("251402617118.15", "3500000000"))
    with pytest.raises(ValueError, match="PARENT_FINANCING_BELOW_CONTRACTUAL_PRINCIPAL:2027"):
        validate_disclosed_financing_policy(schedule, policy("227711547658.23", "0"))

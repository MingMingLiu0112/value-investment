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

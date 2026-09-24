from datetime import datetime, timezone

import pytest

from value_investment_agent.m5_actual_offline_authorization import M5ActualOfflineAuthorization
from value_investment_agent.m5_event_core import NAMESPACE_ACTUAL
from value_investment_agent.m5_event_run_state import (
    M5EventRunState,
    m5_event_run_state_from_payload,
)


def _authorization(**changes):
    values = {
        "authorization_id": "m5-600519-user-confirmed-20260925",
        "review_provenance": "USER_CONFIRMED_DELEGATED_REVIEW",
        "review_sha256": "a" * 64,
        "queue_sha256": "b" * 64,
        "dependency_graph_sha256": "c" * 64,
        "authorized_at": datetime(2026, 9, 25, tzinfo=timezone.utc),
    }
    values.update(changes)
    return M5ActualOfflineAuthorization(**values)


def test_actual_offline_authorization_is_no_order_and_non_operational():
    authorization = _authorization()
    assert authorization.as_policy()["action"] == "no_order"
    assert authorization.as_policy()["scheduler_enabled"] is False


def test_actual_state_round_trips_only_with_embedded_authorization():
    authorization = _authorization()
    state = M5EventRunState.empty(
        state_key="actual-offline-600519",
        namespace=NAMESPACE_ACTUAL,
        actual_offline_authorization=authorization,
    )

    restored = m5_event_run_state_from_payload(state.as_policy())
    assert restored.actual_offline_authorization == authorization


@pytest.mark.parametrize("field", ["scheduler_enabled", "notification_enabled", "production_database_write"])
def test_actual_offline_authorization_refuses_production_operations(field):
    with pytest.raises(ValueError, match="cannot enable production operations"):
        _authorization(**{field: True})

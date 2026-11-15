import json

import pytest

from test_operating_horizon_task_v23_full_schema import native_row
from value_investment_agent.application.research.agent_review.operating_horizon_native_transport_v2 import normalize_scenario


def test_identical_native_duplicate_preserves_all_anchors_and_rationales():
    payload = native_row("base")
    duplicate = json.loads(json.dumps(payload["drivers"][0]))
    duplicate["baseline_anchor_ids"] = ["test:2024-12-31:revenue"]
    duplicate["rationale"] = "second disclosed anchor confirms the same range"
    payload["drivers"].append(duplicate)
    result = normalize_scenario(json.dumps(payload), "base", period_start="2027-01-01", period_end="2027-12-31")
    row = result["drivers"]["volume_change"]
    assert row["lower"] == str(payload["drivers"][0]["value"]["lower"])
    assert row["evidence_ids"] == [*payload["drivers"][0]["baseline_anchor_ids"], "test:2024-12-31:revenue"]
    assert "second disclosed anchor" in row["rationale"]


def test_conflicting_native_duplicate_is_rejected():
    payload = native_row("base")
    duplicate = json.loads(json.dumps(payload["drivers"][0]))
    duplicate["value"]["lower"] = 0.123
    payload["drivers"].append(duplicate)
    with pytest.raises(ValueError, match="DUPLICATE_VALUE_CONFLICT"):
        normalize_scenario(json.dumps(payload), "base", period_start="2027-01-01", period_end="2027-12-31")

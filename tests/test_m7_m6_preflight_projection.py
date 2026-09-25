import json

import pytest

from scripts.build_m7_actual_event_candidate import project_m6_preflight


def _receipt():
    return {
        "schema_version": "m6-operational-preflight-v1",
        "action": "no_order",
        "engineering_status": "DONE",
        "operational_acceptance_status": "NOT_STARTED",
        "criteria": {
            "m6c4_real_restore_rpo_rto": {"status": "PARTIAL"},
            "m6c5_real_sessions_and_events": {"status": "NOT_STARTED"},
            "m6c6_production_authorization": {"status": "REQUIRES_AUTHORIZATION"},
        },
        "summary": {"blockers": ["production authorization not granted"]},
    }


def test_m7_projects_only_bounded_m6_preflight(tmp_path):
    path = tmp_path / "m6.json"
    path.write_text(json.dumps(_receipt()), encoding="utf-8")
    view = project_m6_preflight(path)
    assert view["operational_status"] == "NOT_STARTED"
    assert view["criteria_status"] == {
        "restore": "PARTIAL", "shadow": "NOT_STARTED",
        "authorization": "REQUIRES_AUTHORIZATION", "calendar": "NOT_PROVEN",
    }
    assert len(view["receipt_sha256"]) == 64


@pytest.mark.parametrize("field,value", [
    ("operational_acceptance_status", "DONE"),
    ("action", "order"),
    ("authorization", "DONE"),
    ("shadow", "DONE"),
])
def test_m7_rejects_m6_state_promotion(tmp_path, field, value):
    receipt = _receipt()
    if field in {"authorization", "shadow"}:
        key = ("m6c6_production_authorization" if field == "authorization"
               else "m6c5_real_sessions_and_events")
        receipt["criteria"][key]["status"] = value
    else:
        receipt[field] = value
    path = tmp_path / "m6.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError):
        project_m6_preflight(path)

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from value_investment_agent.operations.start_criteria import (
    CLASSIFICATIONS,
    SHADOW_START_GATES,
    load_m6_start_criteria_matrix,
    m6_start_criteria_matrix_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "config" / "m6-start-criteria-matrix-v1.json"


def _payload() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _criteria_by_id():
    matrix = load_m6_start_criteria_matrix(MATRIX_PATH, root=ROOT)
    return {item.criterion_id: item for item in matrix.criteria}


def test_m6_matrix_uses_exact_enums_and_remains_not_started_without_authorization():
    payload = _payload()
    matrix = load_m6_start_criteria_matrix(MATRIX_PATH, root=ROOT)
    policy = matrix.as_policy()

    assert set(payload["classification_legend"]) == CLASSIFICATIONS
    assert set(payload["shadow_start_gate_legend"]) == SHADOW_START_GATES
    assert {item.classification for item in matrix.criteria} == CLASSIFICATIONS
    assert {item.shadow_start_gate for item in matrix.criteria} == SHADOW_START_GATES
    assert policy["M6_OPERATIONAL"] == "NOT_STARTED"
    assert policy["production_authorization_requested"] is False
    assert policy["production_authorization_granted"] is False
    assert policy["shadow_start_allowed"] is False
    assert policy["decision"] == "BLOCKED_PENDING_HARD_START_GATES"
    assert policy["action"] == "no_order"
    hard = [item for item in matrix.criteria if item.shadow_start_gate == "HARD_START_GATE"]
    assert hard
    assert all(item.current_satisfied is False for item in hard)


def test_m6_matrix_separates_hard_product_gates_from_research_and_natural_time():
    criteria = _criteria_by_id()

    assert criteria["m3_strict_contemporaneous_pit"].shadow_start_gate == "HARD_START_GATE"
    assert criteria["m4_confirmed_private_portfolio"].shadow_start_gate == "HARD_START_GATE"
    assert criteria["m5_product_event_loop"].shadow_start_gate == "HARD_START_GATE"
    assert criteria["m6c5_twenty_real_sessions"].shadow_start_gate == "NATURAL_TIME_GATE"
    assert criteria["m6c14_one_real_event"].shadow_start_gate == "NATURAL_TIME_GATE"
    assert criteria["m6c15_operational_acceptance"].shadow_start_gate == "NATURAL_TIME_GATE"
    assert criteria["m7_product_ux_candidate"].shadow_start_gate == "SOFT_PRODUCT_GAP"

    issuer_evidence = criteria["moutai_600519_scenario_evidence"]
    issuer_history = criteria["moutai_600519_historical_validation"]
    assert issuer_evidence.classification == "RESEARCH_EVIDENCE_REQUIRED"
    assert issuer_evidence.shadow_start_gate == "NOT_RELEVANT_TO_SHADOW_START"
    assert issuer_history.classification == "RESEARCH_EVIDENCE_REQUIRED"
    assert issuer_history.shadow_start_gate == "NOT_RELEVANT_TO_SHADOW_START"


def test_m6_matrix_rejects_authorization_request_or_unknown_classification():
    request = _payload()
    request["production_authorization_requested"] = True
    with pytest.raises(ValueError, match="must not request"):
        m6_start_criteria_matrix_from_payload(request)

    unknown = _payload()
    unknown["criteria"][0]["classification"] = "UNKNOWN"
    with pytest.raises(ValueError, match="Unknown M6 criterion classification"):
        m6_start_criteria_matrix_from_payload(unknown)


def test_m6_start_criteria_cli_is_read_only_and_prints_the_matrix():
    script = ROOT / "scripts" / "current" / "audit_m6_start_criteria.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["M6_OPERATIONAL"] == "NOT_STARTED"
    assert payload["production_authorization_requested"] is False
    assert payload["production_authorization_granted"] is False
    assert payload["shadow_start_allowed"] is False
    assert payload["action"] == "no_order"
    assert '"user_to_authorize":' not in completed.stdout


def _with_all_hard_gates_satisfied() -> dict[str, object]:
    payload = _payload()
    for item in payload["criteria"]:
        if item["shadow_start_gate"] == "HARD_START_GATE":
            item["current_satisfied"] = True
    return payload


def test_m6_matrix_can_represent_a_startable_shadow_decision():
    payload = _with_all_hard_gates_satisfied()
    payload["shadow_start_allowed"] = True
    payload["decision"] = "SHADOW_START_READY"

    policy = m6_start_criteria_matrix_from_payload(payload).as_policy()
    assert policy["shadow_start_allowed"] is True
    assert policy["decision"] == "SHADOW_START_READY"
    assert policy["M6_OPERATIONAL"] == "NOT_STARTED"
    assert policy["production_authorization_granted"] is False
    assert (
        policy["summary"]["hard_start_gates_satisfied"]
        == policy["summary"]["hard_start_gates"]
    )


def test_m6_matrix_rejects_a_contradictory_shadow_start_decision():
    startable = _with_all_hard_gates_satisfied()
    startable["shadow_start_allowed"] = True
    with pytest.raises(ValueError, match="SHADOW_START_READY"):
        m6_start_criteria_matrix_from_payload(startable)

    blocked = _payload()
    blocked["decision"] = "SHADOW_START_READY"
    with pytest.raises(ValueError, match="BLOCKED_PENDING_HARD_START_GATES"):
        m6_start_criteria_matrix_from_payload(blocked)

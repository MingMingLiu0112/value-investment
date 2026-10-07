import copy
from pathlib import Path
import json
import subprocess
import sys

import pytest

from value_investment_agent.operations.start_criteria import load_m6_start_criteria_matrix
from value_investment_agent.operations.personal_shadow_governance import assess_personal_observation_dependencies

ROOT = Path(__file__).resolve().parents[1]


def baseline():
    return load_m6_start_criteria_matrix(ROOT / 'config/m6-start-criteria-matrix-v1.json', root=ROOT).as_policy()


def test_actual_matrix_separates_observation_from_investment_and_private_admission():
    result = assess_personal_observation_dependencies(baseline())
    later = {row['criterion_id']: row['required_at'] for row in result['later_admission_requirements']}
    assert later['m3_strict_contemporaneous_pit'] == 'INVESTMENT_RESEARCH_ADMISSION'
    assert later['m4_confirmed_private_portfolio'] == 'PERSONALIZED_ADMISSION'
    assert not result['shadow_start_allowed']
    assert not result['investment_admission_granted']
    assert result['position_guidance'] is None
    assert result['verified_real_session_count'] == 0
    assert result['action'] == 'no_order'
    assert all(row['replacement_evidence_status'] == 'NOT_VERIFIED' for row in result['successor_evidence_requirements'])


@pytest.mark.parametrize('mutation', ('duplicate', 'unknown', 'missing', 'order', 'schema'))
def test_fail_closed_baseline(mutation):
    payload = baseline()
    if mutation == 'duplicate':
        payload['criteria'].append(copy.deepcopy(payload['criteria'][0]))
    elif mutation == 'unknown':
        row = copy.deepcopy(payload['criteria'][0])
        row['criterion_id'] = 'new_unclassified_safety_gate'
        payload['criteria'].append(row)
    elif mutation == 'missing':
        payload['criteria'].pop(0)
    elif mutation == 'order':
        payload['action'] = 'order'
    else:
        payload['schema_version'] = 'other'
    with pytest.raises(ValueError):
        assess_personal_observation_dependencies(payload)


def test_static_all_pass_flags_never_grant_start_or_migrate_credit():
    payload = baseline()
    for row in payload['criteria']:
        row['current_satisfied'] = True
    payload['shadow_start_allowed'] = True
    payload['production_authorization_granted'] = True
    result = assess_personal_observation_dependencies(payload)
    assert not result['shadow_start_allowed']
    assert not result['production_authorization_granted']
    assert not result['legacy_session_credit_migrated']


def test_existing_cli_profile_preserves_legacy_defaults():
    command = [sys.executable, str(ROOT / 'scripts/current/audit_m6_start_criteria.py')]
    legacy = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    personal = subprocess.run(command + ['--governance-profile', 'personal-observation-v1'],
                              cwd=ROOT, capture_output=True, text=True, check=True)
    legacy_payload = json.loads(legacy.stdout)
    personal_payload = json.loads(personal.stdout)
    assessment = personal_payload.pop('personal_observation_assessment')
    assert personal_payload == legacy_payload
    assert assessment['assessment_status'] == 'DEPENDENCY_PLAN_ONLY'
    assert not assessment['shadow_start_allowed']

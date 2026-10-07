"""Versioned personal observation dependency assessment, never admission."""
from collections.abc import Mapping

PROFILE = 'personal-observation-governance-v1'

# These obligations remain mandatory at their later admission boundary.
DEFERRED = {
    'm3_strict_contemporaneous_pit': 'INVESTMENT_RESEARCH_ADMISSION',
    'm4_confirmed_private_portfolio': 'PERSONALIZED_ADMISSION',
    'm5_product_event_loop': 'FINAL_EVENT_PRODUCT_ACCEPTANCE',
    'm6_authorize_real_restore_drill': 'FULL_RECOVERY_ACCEPTANCE',
    'm6c4_real_restore_rpo_rto': 'FULL_RECOVERY_ACCEPTANCE',
}
REPLACED = {
    'm6_authorize_private_backup_bucket': 'verified_independent_encrypted_offsite_backup',
    'm6c5_distinct_signer_keys': 'approved_personal_identity_and_external_checkpoint_contract',
    'm6c8_backup_readiness': 'complete_backup_and_isolated_recovery_baseline',
}
REQUIRED = frozenset({
    'm6_scoped_production_authorization', 'm6_authorize_existing_runtime',
    'm6_authorize_shadow_scheduler_scope', 'm6_authorize_sse_szse_start',
    'm6c2_repository_privacy_audit', 'm6c3_isolated_restore_mechanism',
    'm6c7_official_calendar_scope', 'm6c11_emergency_stop_restart',
    'm6c9_resource_readiness', 'm6c9_disk_reserve', 'm6c10_health_readiness',
    'm6c12_scheduler_readiness',
})


def assess_personal_observation_dependencies(matrix: Mapping) -> dict:
    """Classify a validated baseline; static flags cannot authorize production."""
    if matrix.get('schema_version') != 'm6-start-criteria-matrix-v1':
        raise ValueError('personal governance requires the validated legacy matrix')
    if matrix.get('action') != 'no_order':
        raise ValueError('personal governance requires no_order')
    criteria = matrix.get('criteria')
    if not isinstance(criteria, list):
        raise ValueError('criteria must be a list')
    ids = [item.get('criterion_id') for item in criteria]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate governance criterion')
    expected = REQUIRED | DEFERRED.keys() | REPLACED.keys()
    if not expected.issubset(ids):
        raise ValueError('missing personal governance baseline criteria')
    start, later, replacements, other = [], [], [], []
    for item in criteria:
        criterion_id = item['criterion_id']
        row = dict(item)
        if criterion_id in DEFERRED:
            row['required_at'] = DEFERRED[criterion_id]
            later.append(row)
        elif criterion_id in REPLACED:
            row['replacement_requirement'] = REPLACED[criterion_id]
            row['replacement_evidence_status'] = 'NOT_VERIFIED'
            replacements.append(row)
        elif criterion_id in REQUIRED:
            start.append(row)
        elif item.get('shadow_start_gate') == 'HARD_START_GATE':
            raise ValueError('unclassified hard start gate: ' + str(criterion_id))
        else:
            other.append(row)
    return {
        'schema_version': PROFILE,
        'assessment_status': 'DEPENDENCY_PLAN_ONLY',
        'state_semantics': 'STATIC_BASELINE_NOT_CURRENT_READINESS',
        'start_requirements': start,
        'successor_evidence_requirements': replacements,
        'later_admission_requirements': later,
        'other_requirements': other,
        'production_authorization_granted': False,
        'shadow_start_allowed': False,
        'investment_admission_granted': False,
        'portfolio_gate': 'BLOCKED_PRIVATE_INPUT',
        'position_guidance': None,
        'personal_capacity_confirmed': False,
        'verified_real_session_count': 0,
        'legacy_session_credit_migrated': False,
        'blockers': ['SUCCESSOR_OPERATIONAL_EVIDENCE_NOT_VERIFIED',
                     'PRODUCTION_SCOPE_NOT_AUTHORIZED'],
        'action': 'no_order',
    }

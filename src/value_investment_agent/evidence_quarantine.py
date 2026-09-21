"""Preserve invalidated evidence while withdrawing its verification eligibility."""
from copy import deepcopy
from datetime import datetime, timezone


REVENUE_SCOPE_REASON = 'total_revenue_used_as_operating_revenue'


def quarantine_metadata(point, run_id):
    metadata = deepcopy(point.get('metadata') or {})
    existing = metadata.get('evidence_quarantine')
    if existing:
        if existing.get('reason') != REVENUE_SCOPE_REASON:
            raise ValueError('Existing unrelated quarantine must not be overwritten')
        return metadata
    metadata['evidence_quarantine'] = {
        'reason': REVENUE_SCOPE_REASON,
        'at': datetime.now(timezone.utc).isoformat(),
        'run_id': str(run_id),
        'previous_validation_status': point['validation_status'],
        'previous_metadata': deepcopy(metadata),
    }
    metadata['automatic_cross_source_verification'] = False
    return metadata

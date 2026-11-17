from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.infrastructure.screening.financial_export_v2 import adopt_annual_export


def test_annual_adoption_preserves_verification_and_pit(tmp_path):
    annual = [dict(data_point_id='annual', symbol='600741', field_name='cash',
                   period_label='2025-12-31', validation_status='pending', value='7',
                   fetched_at='2026-09-20T00:00:00+00:00', metadata={})]
    annual.append(dict(annual[0], data_point_id='future', fetched_at='2026-10-21T00:00:00+00:00'))
    path = tmp_path / 'export.json'
    raw = json.dumps({'annual_points': annual}).encode()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    result, report = adopt_annual_export(path, sha256=digest,
        evaluation_at=datetime(2026, 10, 12, tzinfo=timezone.utc), base_points=[])
    assert result == annual[:1]
    assert report['added_accepted_rows'] == 0
    assert report['excluded'] == {'not_available_at_cutoff': 1}
    assert report['new_verification_or_approval_count'] == 0
    result2, report2 = adopt_annual_export(path, sha256=digest,
        evaluation_at=datetime(2026, 10, 12, tzinfo=timezone.utc), base_points=result)
    assert result2 == result
    assert report2['added_rows'] == 0
    with pytest.raises(ValueError, match='conflicting retained financial identity'):
        adopt_annual_export(path, sha256=digest,
            evaluation_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
            base_points=[dict(annual[0], value='8')])
    with pytest.raises(ValueError, match='hash mismatch'):
        adopt_annual_export(path, sha256='0' * 64,
            evaluation_at=datetime(2026, 10, 12, tzinfo=timezone.utc), base_points=[])

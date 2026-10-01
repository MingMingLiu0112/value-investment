from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.historical_validation.workbench_cutoff_replay import replay_workbench_cutoffs


def fixture(root):
    source = root / 'original.txt'
    source.write_text('synthetic test evidence', encoding='utf-8')
    record = dict(path='original.txt', sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  observed_at='2026-09-30T21:00:00+08:00')
    payload = dict(schema_version='product-existing-research-workbench-v1', symbol='600887',
        generated_at='2026-10-01T03:00:00+00:00', action='no_order', suggested_state='NOT_READY',
        position_guidance=None, research=dict(action='no_order', suggested_state='NOT_READY',
            position_guidance=None, source_records=[record], valuation={'valuation_date': '2026-06-30'},
            dependency_view={'observed_at': record['observed_at']}, blockers=['No approved current quote']))
    path = root / 'result.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return dict(root=root, workbench_path=path,
                workbench_sha256=hashlib.sha256(path.read_bytes()).hexdigest()), source


def test_cutoff_replay_never_backdates_valuation_or_claims_strategy(tmp_path):
    args, source = fixture(tmp_path)
    before = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)
    after = datetime(2026, 10, 1, 3, tzinfo=timezone.utc)
    output = tmp_path / 'runtime/replay.json'
    result = replay_workbench_cutoffs(**args, cutoffs=[before, after], output=output)
    assert result['rows'][0]['valuation'] is None
    assert result['rows'][0]['evidence_refs'] == []
    assert result['rows'][1]['valuation']['valuation_date'] == '2026-06-30'
    assert result['result_known_at'] == after.isoformat()
    assert not result['strict_pit_admitted']
    assert not result['historical_execution_validated']
    from value_investment_agent.presentation.read_models.existing_research_report import render_cutoff_replay_report
    report = render_cutoff_replay_report(result)
    assert 'RESULT_NOT_YET_OBSERVED' in report
    assert 'No historical execution' in report
    for row in result['rows']:
        assert row['action'] == 'no_order' and row['suggested_state'] == 'NOT_READY'
        assert row['fills'] == [] and row['orders'] == []
    with pytest.raises(FileExistsError):
        replay_workbench_cutoffs(**args, cutoffs=[after], output=output)
    source.write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='original hash'):
        replay_workbench_cutoffs(**args, cutoffs=[after])


@pytest.mark.parametrize('points', [[], [datetime(2026, 10, 1)],
    [datetime(2026, 10, 2, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc)],
    [datetime(2026, 10, 1, tzinfo=timezone.utc)] * 2])
def test_invalid_cutoffs_fail_closed(tmp_path, points):
    args, _ = fixture(tmp_path)
    with pytest.raises(ValueError):
        replay_workbench_cutoffs(**args, cutoffs=points)


def test_external_output_refused(tmp_path):
    args, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match='runtime'):
        replay_workbench_cutoffs(**args, cutoffs=[datetime(2026, 10, 1, tzinfo=timezone.utc)],
                                output=tmp_path / 'not-runtime.json')

import json
from pathlib import Path

from value_investment_agent.application.hotspot.continuity import evaluate_theme_continuity


def _report(path, session):
    path.write_text(json.dumps({
        'schema_version': 'hotspot-observation-report-v1', 'action': 'no_order',
        'classification_as_of': session,
        'themes': [{'theme': 'Synthetic sector', 'classification': 'SINA_SHENWAN',
                    'status': 'HISTORICAL_SNAPSHOT_OBSERVATION', 'equal_weight_change_percent': '2'}],
    }), encoding='utf-8')
    return path


def test_distinct_dated_sessions_only(tmp_path):
    first = _report(tmp_path / 'first.json', '2026-10-08')
    duplicate = _report(tmp_path / 'duplicate.json', '2026-10-08')
    assert evaluate_theme_continuity([first, duplicate])['status'] == 'UNKNOWN'
    second = _report(tmp_path / 'second.json', '2026-10-09')
    result = evaluate_theme_continuity([first, duplicate, second])
    assert result['status'] == 'OBSERVED'
    assert result['session_dates'] == ['2026-10-08', '2026-10-09']
    assert result['action'] == 'no_order'
    assert 'entry_review_eligible' not in result


def test_undated_retained_reports_cannot_claim_continuity(tmp_path):
    first = _report(tmp_path / 'first.json', 'UNKNOWN')
    second = _report(tmp_path / 'second.json', 'UNKNOWN')
    assert evaluate_theme_continuity([first, second])['status'] == 'UNKNOWN'

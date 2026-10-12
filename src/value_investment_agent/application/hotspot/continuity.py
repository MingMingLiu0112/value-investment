"""Evidence-bound theme continuity across distinct retained sessions."""
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json

from value_investment_agent.application.product.common import sha256_file


def evaluate_theme_continuity(report_paths: list[Path]) -> dict:
    """Only dated industry observations can establish descriptive continuity."""
    by_date = {}
    for path in report_paths:
        report = json.loads(path.read_text(encoding='utf-8'))
        if report.get('action') != 'no_order' or report.get('schema_version') != 'hotspot-observation-report-v1':
            raise ValueError('Unsupported hotspot report')
        session = report.get('classification_as_of')
        try:
            if not isinstance(session, str) or date.fromisoformat(session).isoformat() != session:
                continue
        except ValueError:
            continue
        themes = {}
        for row in report.get('themes', []):
            if row.get('classification') != 'SINA_SHENWAN' or row.get('status') != 'HISTORICAL_SNAPSHOT_OBSERVATION':
                continue
            try:
                value = Decimal(row['equal_weight_change_percent'])
            except (KeyError, InvalidOperation, TypeError):
                continue
            if value.is_finite() and row.get('theme'):
                themes[row['theme']] = str(value)
        if themes:
            snapshot = {'themes': themes, 'source_sha256': sha256_file(path)}
            if session in by_date and by_date[session]['themes'] != themes:
                return {'status': 'UNKNOWN', 'reason': 'Conflicting snapshots for one session',
                        'session_dates': sorted(by_date), 'themes': [], 'action': 'no_order'}
            by_date[session] = snapshot
    dates = sorted(by_date)
    if len(dates) < 2:
        return {'status': 'UNKNOWN', 'reason': 'Fewer than two distinct dated industry sessions',
                'session_dates': dates, 'themes': [], 'action': 'no_order'}
    common = set.intersection(*(set(by_date[day]['themes']) for day in dates))
    return {'status': 'OBSERVED', 'reason': 'Descriptive same-theme observations across retained sessions only',
            'session_dates': dates,
            'themes': [{'theme': name, 'session_changes_percent': {day: by_date[day]['themes'][name] for day in dates}}
                       for name in sorted(common)],
            'source_sha256_by_date': {day: by_date[day]['source_sha256'] for day in dates},
            'action': 'no_order'}

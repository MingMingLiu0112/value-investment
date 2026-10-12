"""Evidence-bound, research-only hotspot follow-up queue."""

from datetime import date
import json
from pathlib import Path

from value_investment_agent.application.product.common import sha256_file

from .continuity import evaluate_theme_continuity


def _day(value):
    try:
        if isinstance(value, str) and date.fromisoformat(value).isoformat() == value:
            return value
    except ValueError:
        pass
    raise ValueError('Hotspot queue requires an explicit ISO session date')


def build_hotspot_watch_queue(report_bindings: list[dict]) -> dict:
    """Build follow-ups from hash-pinned, dated scan reports, newest session first."""
    if not report_bindings:
        raise ValueError('Hotspot queue requires retained reports')
    reports = []
    for binding in report_bindings:
        path = Path(binding['path'])
        expected = binding['sha256']
        if not isinstance(expected, str) or len(expected) != 64 or sha256_file(path) != expected:
            raise ValueError('Hotspot report hash mismatch')
        report = json.loads(path.read_text(encoding='utf-8'))
        if sha256_file(path) != expected:
            raise ValueError('Hotspot report changed while reading')
        if report.get('schema_version') != 'hotspot-observation-report-v1' or report.get('action') != 'no_order':
            raise ValueError('Unsupported hotspot report')
        session = _day(report.get('classification_as_of'))
        quote_day = _day(report.get('confirmed_market_date'))
        if session != quote_day:
            raise ValueError('Industry session and confirmed quote date differ')
        sources = {source.get('sha256') for source in report.get('sources', [])
                   if isinstance(source, dict) and source.get('role') == 'industry'}
        if not sources:
            raise ValueError('Industry source evidence missing')
        themes = {row['theme'] for row in report.get('themes', [])
                  if isinstance(row, dict) and row.get('theme')
                  and row.get('classification') == 'SINA_SHENWAN'
                  and row.get('status') == 'HISTORICAL_SNAPSHOT_OBSERVATION'}
        quotes = {row['symbol']: row for row in report.get('dated_quote_observations', [])
                  if isinstance(row, dict) and row.get('quote_date') == session
                  and row.get('status') == 'DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION'
                  and row.get('action') == 'no_order'}
        reports.append((session, path, expected, report, themes, sources, quotes))

    continuity = evaluate_theme_continuity([item[1] for item in reports])
    latest = max(item[0] for item in reports)
    rows = []
    seen = set()
    continuous = {row['theme'] for row in continuity.get('themes', [])} if continuity['status'] == 'OBSERVED' else set()
    for session, path, digest, report, themes, sources, quotes in reports:
        if session != latest:
            continue
        for observation in report.get('observation_list', []):
            if not isinstance(observation, dict) or observation.get('action') != 'no_order':
                continue
            symbol, theme = observation.get('symbol'), observation.get('industry')
            if not isinstance(symbol, str) or not symbol.isdigit() or len(symbol) != 6:
                continue
            if theme not in themes or symbol not in quotes:
                continue
            if not set(observation.get('source_refs', [])) & sources:
                raise ValueError('Observation industry source reference mismatch')
            key = (symbol, theme)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'symbol': symbol, 'theme': theme, 'date': session,
                'evidence': {'report_path': str(path), 'report_sha256': digest,
                             'industry_source_sha256': sorted(set(observation['source_refs']) & sources),
                             'quote_source_hashes': quotes[symbol].get('source_hashes', [])},
                'priority': 'REVIEW_CONTINUITY' if theme in continuous else 'REVIEW_NEW_OBSERVATION',
                'next_action': 'Verify theme catalyst, dated bars, and independent risk/value research',
                'action': 'no_order',
            })
    rows.sort(key=lambda row: (row['priority'] != 'REVIEW_CONTINUITY', row['theme'], row['symbol']))
    return {'schema_version': 'hotspot-watch-queue-v1', 'status': 'HOTSPOT_WATCH_QUEUE',
            'scope': 'RESEARCH_ONLY', 'date': latest, 'continuity_status': continuity['status'],
            'items': rows, 'action': 'no_order'}

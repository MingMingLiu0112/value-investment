from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.hotspot.baostock_price_case import load_baostock_history
from value_investment_agent.application.hotspot.structure_replay import build_baostock_structure_observation
from value_investment_agent.domain.hotspot.current_price import aggregate_sessions, SESSION_TIMES

NOW = datetime.fromisoformat('2026-10-25T07:00:00+00:00')


def snapshot(root):
    """Synthetic transport fixture, not market or PIT evidence."""
    folder = root / 'runtime/sample'
    folder.mkdir(parents=True)
    days = ['2026-10-' + str(n) for n in (12, 13, 14, 15, 16, 19, 20)]
    series = {}
    for period in ('15m', '60m'):
        series[period] = [dict(time=day + ' ' + clock, open='10', high='11', low='9', close='10',
            volume='100' if period == '15m' else '400',
            amount='1000' if period == '15m' else '4000')
            for day in days for clock in SESSION_TIMES[period]]
    series['daily'] = aggregate_sessions(series['60m'])
    refs = []
    for frequency, period in (('d', 'daily'), ('15', '15m'), ('60', '60m')):
        fields = ['date', 'code', 'open', 'high', 'low', 'close', 'volume', 'amount', 'adjustflag']
        if period != 'daily':
            fields.insert(1, 'time')
        rows = []
        for row in series[period]:
            values = dict(row, date=row['time'][:10], code='sz.000938', adjustflag='3')
            if period != 'daily':
                values['time'] = datetime.fromisoformat(row['time']).strftime('%Y%m%d%H%M%S') + '000'
            rows.append([values[f] for f in fields])
        path = folder / (frequency + '.json')
        path.write_text(json.dumps(dict(fields=fields, rows=rows, error_code='0',
            fetched_at='2026-10-25T06:00:01+00:00')), encoding='utf-8')
        refs.append(dict(frequency=frequency, path=path.relative_to(root).as_posix(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), error_code='0', rows=len(rows)))
    attempt = dict(provider='BaoStock official SDK 0.9.4', endpoint='public-api.baostock.com:10030',
        symbol='sz.000938', adjustflag='3', action='no_order', login={'error_code': '0'},
        start_date=days[0], end_date=days[-1], started_at='2026-10-25T06:00:00+00:00',
        finished_at='2026-10-25T06:00:02+00:00', queries=refs)
    return seal(root, attempt)


def seal(root, attempt):
    path = root / 'runtime/sample/attempt.json'
    path.write_text(json.dumps(attempt), encoding='utf-8')
    return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_cold_consumer_uses_existing_structure_and_keeps_research_boundary(tmp_path):
    binding = snapshot(tmp_path)
    original = {p: p.read_bytes() for p in (tmp_path / 'runtime').rglob('*.json')}
    report = build_baostock_structure_observation(root=tmp_path, binding=binding, now=NOW)
    assert report['description']['status'] == 'DESCRIPTIVE_OBSERVATION_NOT_ADMITTED'
    assert report['description']['bar_counts'] == {'daily': 7, '60m': 28, '15m': 112}
    assert report['strategy_validation'] == 'NOT_PROVEN'
    assert report['formal_eligibility'] is report['strict_pit_admitted'] is report['strict_oos_admitted'] is False
    assert report['action'] == 'no_order'
    assert all(p.read_bytes() == raw for p, raw in original.items())
    assert report == build_baostock_structure_observation(root=tmp_path, binding=binding, now=NOW)


@pytest.mark.parametrize('fault', ['identity', 'adjustment', 'missing', 'unit', 'duplicate', 'future', 'hash', 'hour_shift'])
def test_source_faults_fail_closed_even_with_resealed_request(tmp_path, fault):
    binding = snapshot(tmp_path)
    attempt = json.loads((tmp_path / binding['path']).read_bytes())
    ref = attempt['queries'][1]
    path = tmp_path / ref['path']
    payload = json.loads(path.read_bytes())
    if fault == 'identity':
        payload['rows'][0][2] = 'sz.000001'
    elif fault == 'adjustment':
        payload['rows'][0][-1] = '2'
    elif fault == 'missing':
        payload['rows'].pop()
        ref['rows'] -= 1
    elif fault == 'unit':
        payload['rows'][0][7] = '1'
    elif fault == 'duplicate':
        payload['rows'][1] = deepcopy(payload['rows'][0])
    elif fault == 'future':
        payload['fetched_at'] = '2026-10-26T00:00:00+00:00'
    elif fault == 'hash':
        payload['rows'][0][3] = '10.1'
    elif fault == 'hour_shift':
        payload['rows'][0][7:9] = ['110', '1100']
        payload['rows'][4][7:9] = ['90', '900']
    path.write_text(json.dumps(payload), encoding='utf-8')
    if fault != 'hash':
        ref['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    binding = seal(tmp_path, attempt)
    with pytest.raises(ValueError):
        load_baostock_history(root=tmp_path, binding=binding, now=NOW)


def test_actual_retained_baostock_sample_does_not_hide_daily_minute_conflict():
    raw_path = os.environ.get('HOTSPOT_BAOSTOCK_H1_ATTEMPT')
    if not raw_path:
        pytest.skip('Actual public snapshot is not distributed with code')
    path = Path(raw_path).resolve()
    root = Path(os.environ['HOTSPOT_BAOSTOCK_H1_ROOT']).resolve()
    binding = dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='conflict'):
        build_baostock_structure_observation(root=root, binding=binding, now=NOW)


@pytest.mark.parametrize('target', ['attempt', 'd', '15', '60'])
def test_source_changed_during_calculation_is_rejected(tmp_path, monkeypatch, target):
    from value_investment_agent.infrastructure.hotspot import baostock_price_case as module

    binding = snapshot(tmp_path)
    path = tmp_path / ('runtime/sample/attempt.json' if target == 'attempt'
                       else 'runtime/sample/' + target + '.json')
    aggregate = module.aggregate_sessions
    changed = False

    def drift(rows):
        nonlocal changed
        result = aggregate(rows)
        if not changed:
            path.write_bytes(path.read_bytes() + b' ')
            changed = True
        return result

    monkeypatch.setattr(module, 'aggregate_sessions', drift)
    with pytest.raises(ValueError, match='hash mismatch'):
        module.load_baostock_history(root=tmp_path, binding=binding, now=NOW)

"""Verify the latest committed tracking run and its immutable source chain."""
import hashlib
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute("SET statement_timeout='30s'")
    run = db.execute("SELECT * FROM task_runs WHERE task_name='track-candidates' ORDER BY started_at DESC LIMIT 1").fetchone()
    assert run and run['status'] == 'succeeded', 'Latest tracking run not successful'
    members = db.execute('SELECT * FROM market_screen_results WHERE screen_date=(SELECT max(screen_date) FROM market_screen_results) ORDER BY symbol').fetchall()
    rows = db.execute('SELECT * FROM candidate_tracking_observations WHERE run_id=%s ORDER BY symbol', (run['run_id'],)).fetchall()
    assert len(rows) == run['details']['candidate_count'] == len(members)
    assert [r['symbol'] for r in rows] == [m['symbol'] for m in members]
    assert [r['observation']['membership'] for r in rows] == json.loads(json.dumps(members, default=str))
    sources = {str(r['source_id']) for r in rows}
    assert len(sources) == 1
    source = db.execute('SELECT * FROM raw_documents WHERE document_id=%s', (rows[0]['source_id'],)).fetchone()
    raw = Path(source['local_path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == source['sha256']
    envelope = json.loads(raw)
    assert envelope['run_id'] == str(run['run_id'])
    assert hashlib.sha256(envelope['snapshot_json'].encode()).hexdigest() == envelope['snapshot_sha256']
    prices = db.execute("SELECT * FROM data_points WHERE source_id=%s AND field_name='current_price'", (rows[0]['source_id'],)).fetchall()
    expected = {r['symbol']:r['observation'] for r in rows if r['observation']['current_price'] is not None}
    assert len(prices) == len(expected)
    from decimal import Decimal
    for p in prices:
        observation = expected[p['symbol']]
        assert p['value'] == Decimal(observation['current_price'])
        assert (p['validation_status']=='verified') == (observation['quote_status']=='matched')
    print(json.dumps({'run_id':str(run['run_id']), 'observations':len(rows), 'prices':len(prices),
        'blocked':sum(r['signal_blocked'] for r in rows), 'source_sha256':source['sha256'],
        'membership_unchanged':True, 'evidence_chain_verified':True}), flush=True)
    db.rollback()

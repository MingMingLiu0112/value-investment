"""Replay retained market evidence for the real pool using rollback-only temporary tables."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from candidate_tracking import track_candidates, store_tracking_observations, normalize_tracking_quotes
from value_investment_agent.db import connect, begin_run
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute("SET statement_timeout='30s'")
    db.execute("SET lock_timeout='3s'")
    members = db.execute('SELECT * FROM market_screen_results WHERE screen_date=(SELECT max(screen_date) FROM market_screen_results) ORDER BY symbol').fetchall()
    if not members or len({str(m['source_id']) for m in members}) != 1:
        raise ValueError('Require a nonempty coherent pool snapshot')
    source = db.execute('SELECT * FROM raw_documents WHERE document_id=%s', (members[0]['source_id'],)).fetchone()
    raw = Path(source['local_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source['sha256']:
        raise ValueError('Retained market snapshot hash mismatch')
    snapshot = json.loads(raw)
    quotes = normalize_tracking_quotes(snapshot['rows'])
    observations = track_candidates(members, quotes, source['fetched_at'].isoformat())
    assert {r['symbol'] for r in observations} == {m['symbol'] for m in members}
    assert all(r['membership']['initial_score'] == m['initial_score'] for r,m in zip(observations,members))
    db.execute('CREATE TEMP TABLE task_runs (LIKE public.task_runs INCLUDING ALL)')
    db.execute('CREATE TEMP TABLE instruments (LIKE public.instruments INCLUDING ALL)')
    db.execute('CREATE TEMP TABLE raw_documents (LIKE public.raw_documents INCLUDING ALL)')
    db.execute('INSERT INTO instruments SELECT * FROM public.instruments WHERE symbol=ANY(%s)', ([m['symbol'] for m in members],))
    db.execute('INSERT INTO raw_documents SELECT * FROM public.raw_documents WHERE document_id=%s', (source['document_id'],))
    schema = Path('/staged/tracking_schema.sql').read_text()
    db.execute(schema.replace('CREATE TABLE IF NOT EXISTS candidate_tracking_observations', 'CREATE TEMP TABLE candidate_tracking_observations', 1))
    run = begin_run(db, 'replay-current-pool-rollback-only')
    store_tracking_observations(db,run,source['document_id'],observations)
    actual = db.execute('SELECT symbol,observation FROM candidate_tracking_observations ORDER BY symbol').fetchall()
    assert [r['observation'] for r in actual] == json.loads(json.dumps(observations,default=str))
    result = {'members':len(members),'retained_market_rows':len(quotes),
        'statuses':dict(Counter(r['quote_status'] for r in observations)),
        'blocked':sum(r['signal_blocked'] for r in observations),
        'valuation_conflict_fields':dict(Counter(field for r in observations for field in r['valuation_field_conflicts'])),
        'risk_warnings':sum(r['risk_warning'] for r in observations),
        'conflict_samples':[{'symbol':r['symbol'],'conflicts':r['valuation_field_conflicts']}
                            for r in observations if r['valuation_field_conflicts']][:5],
        'observation_time':source['fetched_at'].isoformat(),'source_sha256':source['sha256'],
        'round_trip_verified':True,'membership_preserved':True,'production_writes':False}
    db.rollback()
print(json.dumps(result))

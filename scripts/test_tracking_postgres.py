"""Exercise tracking storage on a temporary PostgreSQL table; roll back all work."""
import json
from datetime import datetime, timezone
from pathlib import Path
from candidate_tracking import store_tracking_observations, track_candidates
from value_investment_agent.db import connect, begin_run
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute("SET lock_timeout='3s'")
    db.execute("SET statement_timeout='20s'")
    schema = Path('/staged/tracking_schema.sql').read_text()
    db.execute('CREATE TEMP TABLE task_runs (LIKE public.task_runs INCLUDING ALL)')
    db.execute('CREATE TEMP TABLE instruments (LIKE public.instruments INCLUDING ALL)')
    db.execute('CREATE TEMP TABLE raw_documents (LIKE public.raw_documents INCLUDING ALL)')
    db.execute('INSERT INTO instruments SELECT * FROM public.instruments ORDER BY symbol LIMIT 1')
    db.execute('INSERT INTO raw_documents SELECT * FROM public.raw_documents LIMIT 1')
    db.execute(schema.replace('CREATE TABLE IF NOT EXISTS candidate_tracking_observations',
                             'CREATE TEMP TABLE candidate_tracking_observations', 1))
    source = db.execute('SELECT document_id FROM raw_documents LIMIT 1').fetchone()['document_id']
    symbol = db.execute('SELECT symbol FROM instruments ORDER BY symbol LIMIT 1').fetchone()['symbol']
    run = begin_run(db, 'test-tracking-rollback-only')
    now = datetime.now(timezone.utc)
    observations = track_candidates([{'symbol':symbol,'initial_score':'60'}], [], now.isoformat(), now=now)
    assert store_tracking_observations(db, run, source, observations) == 1
    assert store_tracking_observations(db, run, source, observations) == 1
    assert db.execute('SELECT count(*) AS n FROM candidate_tracking_observations').fetchone()['n'] == 1
    try:
        with db.transaction():
            store_tracking_observations(db, run, source, [{**observations[0], 'quote_status':'stale_quote'}])
    except ValueError as error:
        assert 'differs' in str(error)
    else:
        raise AssertionError('Changed retry must fail')
    retained = db.execute('SELECT observation FROM candidate_tracking_observations').fetchone()['observation']
    assert retained == observations[0]
    second = begin_run(db, 'test-tracking-second-run')
    assert store_tracking_observations(db, second, source, observations) == 1
    assert db.execute('SELECT count(*) AS n FROM candidate_tracking_observations').fetchone()['n'] == 2
    db.rollback()
    assert db.execute('SELECT count(*) AS n FROM task_runs WHERE run_id=ANY(%s)', ([run,second],)).fetchone()['n'] == 0
    db.rollback()
print(json.dumps({'postgres_test':'passed','idempotent_retry':True,'conflicting_retry_rejected':True,
                  'new_run_appends':True,'test_runs_rolled_back':True}))

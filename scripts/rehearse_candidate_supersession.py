"""Exercise actual update SQL against session-local temporary tables only."""
import json
import uuid
from candidate_migration import supersede_unpromoted
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute("SET statement_timeout='15s'")
    db.execute('CREATE TEMP TABLE filing_candidates (candidate_id uuid PRIMARY KEY, status text)')
    db.execute('CREATE TEMP TABLE data_points (metadata jsonb)')
    ids = [uuid.uuid4() for _ in range(3)]
    for identifier in ids:
        db.execute('INSERT INTO pg_temp.filing_candidates VALUES (%s,%s)',
                   (identifier, 'candidate_pending_automated_verification'))
    db.execute('INSERT INTO pg_temp.data_points VALUES (%s::jsonb)',
               (json.dumps({'candidate_id': str(ids[1])}),))
    db.execute("UPDATE pg_temp.filing_candidates SET status='automatically_verified' WHERE candidate_id=%s", (ids[2],))
    db.execute('SAVEPOINT before_update')
    assert supersede_unpromoted(db, [ids[0]]) == 1
    assert db.execute('SELECT status FROM pg_temp.filing_candidates WHERE candidate_id=%s',
                      (ids[0],)).fetchone()['status'] == 'superseded_by_parser'
    db.execute('ROLLBACK TO SAVEPOINT before_update')
    assert db.execute('SELECT status FROM pg_temp.filing_candidates WHERE candidate_id=%s',
                      (ids[0],)).fetchone()['status'] == 'candidate_pending_automated_verification'
    for protected in ids[1:]:
        try:
            supersede_unpromoted(db, [protected])
        except ValueError:
            pass
        else:
            raise AssertionError('Protected candidate was modified')
    db.rollback()
    print(json.dumps({'temporary_tables_only':True, 'update_passed':True,
                      'rollback_passed':True, 'fact_and_status_protection_passed':True}))

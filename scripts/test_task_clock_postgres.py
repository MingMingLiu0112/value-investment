"""Validate task timestamps using temporary tables, never business task rows."""
import ast
import json
from pathlib import Path
import sys
import uuid

from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def main():
    tree = ast.parse(Path(sys.argv[1]).read_text(encoding='utf-8'))
    names = {'begin_run', 'end_run', 'record_failed_run'}
    source = '\n\n'.join(ast.unparse(n) for n in tree.body
                          if isinstance(n, ast.FunctionDef) and n.name in names)
    namespace = {'uuid': uuid, 'json': json}
    exec('from __future__ import annotations\n' + source, namespace)
    begin, end, fail = (namespace[n] for n in ('begin_run', 'end_run', 'record_failed_run'))
    with connect(get_settings().database_url) as db:
        db.execute("SET statement_timeout='10s'")
        db.execute('CREATE TEMP TABLE task_runs(run_id uuid PRIMARY KEY,task_name text,'
                   'started_at timestamptz,finished_at timestamptz,status text,details jsonb)')
        db.commit()
        ident = begin(db, 'normal')
        db.execute('SELECT pg_sleep(0.05)')
        end(db, ident, 'succeeded', {})
        row = db.execute('SELECT * FROM task_runs WHERE run_id=%s', (ident,)).fetchone()
        elapsed = (row['finished_at'] - row['started_at']).total_seconds()
        assert elapsed >= .05
        db.commit()

        lost = begin(db, 'rolled_back')
        fail(db, lost, 'rolled_back', {'error': 'injected research test'})
        row = db.execute('SELECT * FROM task_runs WHERE run_id=%s', (lost,)).fetchone()
        assert row['details']['start_time_reconstructed'] is True
        db.commit()

        retained = begin(db, 'committed_start')
        original = db.execute('SELECT started_at FROM task_runs WHERE run_id=%s',
                              (retained,)).fetchone()['started_at']
        db.commit()
        fail(db, retained, 'committed_start', {'error': 'injected research test'})
        row = db.execute('SELECT * FROM task_runs WHERE run_id=%s', (retained,)).fetchone()
        assert row['started_at'] == original
        assert row['details']['start_time_reconstructed'] is False
        assert row['finished_at'] >= original
        print(json.dumps({'temporary_tables_only': True, 'checks_passed': 3,
                          'normal_elapsed_seconds': elapsed}))


if __name__ == '__main__':
    main()

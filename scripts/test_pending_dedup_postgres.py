"""Exercise staged record storage against temporary tables, with explicit rollback."""
import importlib.util
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from psycopg import sql
from value_investment_agent.db import connect
from value_investment_agent.models import SourceRecord
from value_investment_agent.settings import get_settings

spec = importlib.util.spec_from_file_location('value_investment_agent.dedup_probe',Path(__file__).with_name('db.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with connect(get_settings().database_url) as db:
    for table in ('raw_documents','data_points'):
        db.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE public.{} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)').format(
            sql.Identifier(table),sql.Identifier(table)))
    db.execute('SET LOCAL search_path=pg_temp')
    record = SourceRecord('000001','revenue','2025-12-31',Decimal(100),'CNY','test',
        'https://example.invalid/fixture',None,datetime.now(timezone.utc),'test',b'fixture',
        point_metadata={'scope':'consolidated'})
    first = module.store_record(db,record,'pending')
    assert module.store_record(db,record,'pending') == first
    changed = module.store_record(db,replace(record,value=Decimal(101)),'pending')
    assert changed != first
    scoped = module.store_record(db,replace(record,point_metadata={'scope':'parent'}),'pending')
    assert scoped not in (first,changed)
    verified = module.store_record(db,record,'verified')
    assert verified not in (first,changed,scoped)
    assert module.store_record(db,record,'pending') == first
    assert db.execute('SELECT count(*) AS n FROM data_points').fetchone()['n'] == 4
    db.rollback()
print(json.dumps({'temporary_tables_only':True,'exact_duplicate_reused':True,
                  'value_and_scope_changes_retained':True,'verified_record_independent':True,'rolled_back':True}))

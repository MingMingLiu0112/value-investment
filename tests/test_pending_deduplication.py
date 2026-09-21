from datetime import datetime,timezone
from decimal import Decimal
from types import SimpleNamespace
from value_investment_agent import db
from value_investment_agent.models import SourceRecord


def test_identical_pending_record_reuses_id_but_verified_promotion_is_new(monkeypatch):
    monkeypatch.setattr(db,'_store_document',lambda *args,**kwargs:'source')
    calls = []
    class Connection:
        def execute(self,sql,params):
            calls.append((sql,params))
            return SimpleNamespace(fetchone=lambda:{'data_point_id':'existing'})
    record = SourceRecord('000001','revenue','2025-12-31',Decimal(100),'CNY','source','url',
        None,datetime.now(timezone.utc),'test',b'raw',point_metadata={'scope':'consolidated'})
    assert db.store_record(Connection(),record,'pending') == 'existing'
    assert not any('INSERT INTO data_points' in sql for sql,_ in calls)
    sql,params = calls[0]
    for predicate in ['field_name=%s','period_label=%s','value=%s','unit=%s','source_id=%s','metadata=%s::jsonb']:
        assert predicate in sql
    assert params[:6] == ('000001','revenue','2025-12-31',Decimal(100),'CNY','source')
    calls.clear()
    assert db.store_record(Connection(),record,'verified') != 'existing'
    assert len(calls) == 1 and 'INSERT INTO data_points' in calls[0][0]

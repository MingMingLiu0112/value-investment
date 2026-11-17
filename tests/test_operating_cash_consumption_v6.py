from contextlib import nullcontext
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import pytest
from value_investment_agent.application.research import operating_cash_consumption_v6 as mod

NOW=datetime(2026,11,5,tzinfo=timezone.utc)

def test_failed_repair_does_not_replay_or_admit_research(tmp_path,monkeypatch):
    (tmp_path/'input.json').write_text('{}')
    spec=dict(symbol='600323',task_id='TEST_ONLY',created_at=NOW.isoformat(),repair_requested_at=NOW.isoformat(),repair_of={},source_binding={},mode='TEST_ONLY')
    state=dict(status='FAILED',updated_at=NOW.isoformat(),error_code='REJECTED')
    service=SimpleNamespace(_directory=lambda x:tmp_path,_lock=lambda x:nullcontext(),_load=lambda x:(spec,state,{}))
    monkeypatch.setattr(mod.repair,'OperatingHorizonTaskService',lambda root:service)
    monkeypatch.setattr(mod.base,'read_operating_cash_consumption',lambda **kw:dict(consumption_fingerprint='base'))
    def forbidden(**kw):raise AssertionError('must not replay failed response')
    monkeypatch.setattr(mod.full,'read_operating_cash_consumption',forbidden)
    result=mod.read_operating_cash_consumption(root=tmp_path,task={'symbol':'600323'},now=NOW)
    row=result['annual_research_supplement']
    assert row['status']=='FAILED' and row['years']=={} and row['condition_price'] is None
    assert row['source_status'].startswith('NOT_REPLAYED') and not row['formal_eligibility']
    with pytest.raises(ValueError,match='AFTER_CONSUMPTION'):
        mod.read_operating_cash_consumption(root=tmp_path,task={'symbol':'600323'},now=NOW-timedelta(seconds=1))
    state['status']='SUCCEEDED'
    with pytest.raises(AssertionError,match='must not replay'):
        mod.read_operating_cash_consumption(root=tmp_path,task={'symbol':'600323'},now=NOW)
    state['status']='FAILED';spec['symbol']='000568'
    with pytest.raises(AssertionError,match='must not replay'):
        mod.read_operating_cash_consumption(root=tmp_path,task={'symbol':'600323'},now=NOW)

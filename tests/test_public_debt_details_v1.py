"""Offline full-balance collection and cold replay contract tests."""
import json
from datetime import datetime, timezone
import pytest
from value_investment_agent.infrastructure.screening import public_debt_details_v1 as m


def row(symbol='600887'):
    return dict(SECURITY_CODE=symbol, SECUCODE=symbol+'.SH', SECURITY_TYPE_CODE='058001001',
        REPORT_DATE='2025-12-31 00:00:00', REPORT_TYPE='年报', ORG_TYPE='通用', CURRENCY='CNY',
        NOTICE_DATE='2026-04-30 00:00:00', UPDATE_DATE='2026-10-30 00:00:00',
        SHORT_LOAN=123.45, BOND_PAYABLE=None, LONG_LOAN=0)


def page(rows=None,count=1,pages=1):
    return m._json(dict(success=True,result=dict(count=count,pages=pages,data=rows or [row()])))


@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'_read_response',lambda *a:page())
    monkeypatch.setattr(m.time,'sleep',lambda *a:None)
    return tmp_path,tmp_path/'runtime/full-balance'


def collect(env):return m.collect(env[0],env[1],'2025-12-31',True)
def load(env,b):return m.load(env[0],b,datetime.now(timezone.utc))


def change(env,b,mutate,raw_page=False):
    p=env[0]/b['path'];x=json.loads(p.read_bytes())
    if raw_page:
        d=x['sources']['balance']['pages'][0];q=env[0]/d['path'];v=json.loads(q.read_bytes());mutate(v)
        raw=m._json(v);q.write_bytes(raw);d['sha256']=m._sha(raw)
    else:mutate(x)
    raw=m._json(x);p.write_bytes(raw);return dict(b,sha256=m._sha(raw))


def test_success_preserves_blanks_zero_and_no_grants_readonly(env,monkeypatch):
    b=collect(env);x=load(env,b);v=x['balance']['600887']['raw']
    assert x['status']=='COMPLETE' and v['BOND_PAYABLE'] is None and v['LONG_LOAN']==0
    assert not x['complete_debt_verified'] and not x['formal_admission'] and not x['historical_pit_eligible']
    assert x['balance']['600887']['source_ref']['availability_basis']=='FIRST_OBSERVED_NOT_HISTORICAL_NOTICE'
    monkeypatch.setattr(m,'_read_response',lambda *a:pytest.fail('GET network'))
    before={p:p.read_bytes() for p in env[1].rglob('*') if p.is_file()}
    assert load(env,b)==x and before=={p:p.read_bytes() for p in before}
    with pytest.raises(FileExistsError):collect(env)


@pytest.mark.parametrize('field,value',[
    ('SECURITY_CODE','A04021'),('CURRENCY','USD'),('REPORT_TYPE','母公司年报'),('ORG_TYPE','银行'),('SECUCODE','600887.SZ'),
    ('SECURITY_TYPE_CODE','058001008'),('REPORT_DATE','2024-12-31 00:00:00'),
    ('NOTICE_DATE','2099-01-01 00:00:00'),('UPDATE_DATE','invalid')])
def test_resigned_wrong_identity_scope_period_clock_rejected(env,field,value):
    b=change(env,collect(env),lambda x:x['result']['data'][0].update({field:value}),True)
    with pytest.raises(ValueError):load(env,b)


@pytest.mark.parametrize('kind',['hash','url','clock','total','missing','status','path'])
def test_manifest_guards(env,kind):
    b=collect(env)
    def mutate(x):
        d=x['sources']['balance']['pages'][0]
        if kind=='hash':d['sha256']='0'*64
        if kind=='url':d['source_url']+='bad'
        if kind=='clock':d['acquired_at']='2099-01-01T00:00:00+00:00'
        if kind=='total':x['sources']['balance']['row_count']=2
        if kind=='status':x['status']='UNAVAILABLE'
        if kind=='path':d['path']='../outside.json'
    b=change(env,b,mutate)
    if kind=='missing':(env[1]/'balance/page-001.json').unlink()
    with pytest.raises((ValueError,OSError)):load(env,b)


def test_duplicate_rejected(env):
    b=change(env,collect(env),lambda x:x['result'].update(count=2,data=[row(),row()]),True)
    with pytest.raises(ValueError,match='duplicate'):load(env,b)


def test_pagination_complete_and_drift_no_partial_release(env,monkeypatch):
    calls=[]
    def fetch(session,url):
        calls.append(url)
        if 'pageNumber=1&' in url:return page([row(str(600000+n)) for n in range(200)],201,2)
        return page([row('601999')],202,2)
    monkeypatch.setattr(m,'_read_response',fetch)
    x=load(env,collect(env));assert x['status']=='UNAVAILABLE' and x['balance']=={} and x['errors']
    assert len(calls)==2 and (env[1]/'balance/page-002.json').exists()


def test_two_pages_complete(env,monkeypatch):
    def fetch(session,url):
        return page([row(str(600000+n)) for n in range(200)],201,2) if 'pageNumber=1&' in url else page([row('601999')],201,2)
    monkeypatch.setattr(m,'_read_response',fetch)
    x=load(env,collect(env));assert x['status']=='COMPLETE' and len(x['balance'])==201


def test_permission_and_bounds(env):
    with pytest.raises(ValueError):m.collect(*env,'2025-12-31',False)
    with pytest.raises(ValueError):m.collect(*env,'2025-06-30',True)
    with pytest.raises(ValueError):m._parse_page(page(count=12001,pages=61))
    assert 'columns=ALL' in m._url('balance','2025-12-31',1)
    from urllib.parse import parse_qs,urlparse
    assert '(SECURITY_CODE<="999999")' in parse_qs(urlparse(m._url('balance','2025-12-31',1)).query)['filter'][0]


def test_failed_raw_hash_still_required(env,monkeypatch):
    monkeypatch.setattr(m,'_read_response',lambda *a:b'{"success":false}')
    b=collect(env);assert load(env,b)['status']=='UNAVAILABLE'
    (env[1]/'balance/page-001.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):load(env,b)

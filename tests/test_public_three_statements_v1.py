"""Bounded three-statement collection and cold replay, no test network."""
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from value_investment_agent.infrastructure.screening import public_three_statements_v1 as m


def row(symbol='600519'):
    return dict(SECURITY_CODE=symbol, SECUCODE=symbol+'.SH', SECURITY_TYPE_CODE='058001001',
                TRADE_MARKET_CODE='069001001001', REPORT_DATE='2025-12-31 00:00:00',
                NOTICE_DATE='2026-04-17 00:00:00', UPDATE_DATE='2026-04-18 00:00:00',
                NET_PROFIT=123.45, MONETARYFUNDS=None)


def page(rows=None, count=1, pages=1):
    return m._json(dict(success=True, result=dict(count=count, pages=pages, data=rows or [row()])))


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls=[]
    def fetch(session,url):
        calls.append(url)
        return page()
    monkeypatch.setattr(m,'_read_response',fetch)
    monkeypatch.setattr(m.time,'sleep',lambda seconds:None)
    return tmp_path,tmp_path/'runtime/three-statements/test',calls


def collect(env): return m.collect(env[0],env[1],'2025-12-31',True)
def load(env,binding):return m.load(env[0],binding,datetime.now(timezone.utc))

def rewrite(env,binding,mutate):
    path=env[0]/binding['path'];value=json.loads(path.read_bytes());mutate(value)
    raw=m._json(value);path.write_bytes(raw)
    return dict(binding,sha256=m._sha(raw))


def change_page(env,binding,mutate):
    manifest=json.loads((env[0]/binding['path']).read_bytes())
    descriptor=manifest['sources']['income']['pages'][0]
    path=env[0]/descriptor['path'];value=json.loads(path.read_bytes());mutate(value)
    raw=m._json(value);path.write_bytes(raw);descriptor['sha256']=m._sha(raw)
    target=env[0]/binding['path'];raw=m._json(manifest);target.write_bytes(raw)
    return dict(binding,sha256=m._sha(raw))


def test_three_roles_exact_requests_and_readonly_replay(env,monkeypatch):
    binding=collect(env);result=load(env,binding)
    assert result['status']=='COMPLETE' and result['formal_admission'] is False
    assert result['assurance']=='E1_PROVIDER_OBSERVATIONS'
    assert result['balance']['600519']['raw']['MONETARYFUNDS'] is None
    assert str(result['income']['600519']['raw']['NET_PROFIT'])=='123.45'
    assert len(env[2])==3
    for url in env[2]:
        query=parse_qs(urlparse(url).query)
        assert query['columns']==['ALL'] and query['sortColumns']==['NOTICE_DATE,SECURITY_CODE']
        assert query['sortTypes']==['-1,-1'] and query['pageSize']==['500']
        assert 'TRADE_MARKET_CODE!="069001017"' in query['filter'][0]
    before={p:p.read_bytes() for p in env[1].rglob('*.json')}
    def no_network(*args,**kwargs):raise AssertionError('network forbidden')
    monkeypatch.setattr(m,'_read_response',no_network)
    assert load(env,binding)==result
    assert before=={p:p.read_bytes() for p in before}
    with pytest.raises(FileExistsError):collect(env)


def test_auth_period_and_path_before_network(env):
    with pytest.raises(ValueError):m.collect(env[0],env[1],'2025-12-31',False)
    with pytest.raises(ValueError):m.collect(env[0],env[1],'2025-06-30',True)
    with pytest.raises(ValueError):m.collect(env[0],env[0]/'outside','2025-12-31',True)
    assert not env[2] and not env[1].exists()


def test_one_source_failure_retains_bytes_and_other_roles(env,monkeypatch):
    def fetch(session,url):
        return b'{"success":false}' if 'RPT_DMSK_FN_INCOME' in url else page()
    monkeypatch.setattr(m,'_read_response',fetch)
    binding=collect(env);result=load(env,binding)
    assert result['status']=='PARTIAL' and result['income']=={}
    assert result['balance'] and result['cashflow']
    assert result['source_status']['income']=='FAILED'
    assert result['errors'][0]['role']=='income'
    assert (env[1]/'income/page-001.json').read_bytes()==b'{"success":false}'


def test_all_failed_is_unavailable_not_complete(env,monkeypatch):
    def fetch(*args):raise ValueError('bounded failure')
    monkeypatch.setattr(m,'_read_response',fetch)
    result=load(env,collect(env))
    assert result['status']=='UNAVAILABLE' and len(result['errors'])==3


@pytest.mark.parametrize('field,value',[
    ('SECURITY_CODE','830001'),('SECUCODE','600519.SZ'),('SECURITY_TYPE_CODE','WRONG'),
    ('TRADE_MARKET_CODE','069001017'),('REPORT_DATE','2024-12-31 00:00:00'),
    ('NOTICE_DATE','2099-01-01 00:00:00'),('UPDATE_DATE','invalid')])
def test_resigned_identity_period_dates_rejected(env,field,value):
    binding=change_page(env,collect(env),lambda p:p['result']['data'][0].update({field:value}))
    with pytest.raises(ValueError):load(env,binding)


def test_duplicate_identity_and_total_rejected(env):
    def duplicate(p):p['result'].update(count=2,data=[row(),row()])
    binding=change_page(env,collect(env),duplicate)
    with pytest.raises(ValueError,match='duplicate'):load(env,binding)


@pytest.mark.parametrize('mutation',['hash','url','future','naive','status','path','count'])
def test_manifest_and_binding_guards(env,mutation):
    binding=collect(env)
    def mutate(manifest):
        d=manifest['sources']['income']['pages'][0]
        if mutation=='hash':d['sha256']='0'*64
        if mutation=='url':d['source_url']=d['source_url'].replace('INCOME','BALANCE')
        if mutation=='future':d['acquired_at']='2099-01-01T00:00:00+00:00'
        if mutation=='naive':d['acquired_at']='2026-01-01T00:00:00'
        if mutation=='status':manifest['status']='PARTIAL'
        if mutation=='path':d['path']='../outside.json'
        if mutation=='count':manifest['sources']['income']['row_count']=2
    binding=rewrite(env,binding,mutate)
    with pytest.raises((ValueError,OSError)):load(env,binding)


def test_page_count_drift_fails_role_without_promoting_first_page(env,monkeypatch):
    def fetch(session,url):
        if 'RPT_DMSK_FN_INCOME' not in url:return page()
        number=parse_qs(urlparse(url).query)['pageNumber'][0]
        if number=='1':return page([row(str(600000+n)) for n in range(500)],501,2)
        return page([row('601999')],502,2)
    monkeypatch.setattr(m,'_read_response',fetch)
    binding=collect(env);result=load(env,binding)
    assert result['status']=='PARTIAL' and not result['income']
    assert (env[1]/'income/page-002.json').exists()


def test_missing_page_never_silently_reuses_old_success(env):
    binding=collect(env)
    (env[1]/'balance/page-001.json').unlink()
    with pytest.raises(FileNotFoundError):load(env,binding)


def test_isolated_restore_replays_without_network_or_relabelled_time(env,monkeypatch):
    import shutil
    binding=collect(env)
    expected=load(env,binding)
    restore_root=env[0]/'isolated'
    shutil.copytree(env[1],restore_root/'runtime/three-statements/test')
    def forbidden(*args,**kwargs):raise AssertionError('network forbidden')
    monkeypatch.setattr(m,'_read_response',forbidden)
    assert m.load(restore_root,binding,datetime.now(timezone.utc))==expected


def test_failed_source_raw_hash_is_still_enforced(env,monkeypatch):
    monkeypatch.setattr(m,'_read_response',lambda session,url:b'{"success":false}' if 'INCOME' in url else page())
    binding=collect(env)
    (env[1]/'income/page-001.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):load(env,binding)


def test_future_manifest_and_naive_evaluation_rejected(env):
    binding=collect(env)
    with pytest.raises(ValueError,match='aware'):m.load(env[0],binding,datetime(2026,11,2))
    binding=rewrite(env,binding,lambda value:value.update(available_at='2099-01-01T00:00:00+00:00'))
    with pytest.raises(ValueError,match='cutoff'):load(env,binding)

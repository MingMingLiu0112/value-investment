"""Sina source orchestration and strict replay; no test network."""
import json
from datetime import datetime, timezone

import pytest
from value_investment_agent.infrastructure.screening import sina_financial_statements_v1 as m


@pytest.fixture
def env(tmp_path,monkeypatch):
    calls=[]
    def collector(*,root,symbol,output_dir,statement,allow_network):
        role=statement.value;calls.append((symbol,role,allow_network))
        output_dir.mkdir(parents=True)
        source=m.STATEMENT_SOURCES[statement]
        reports={}
        for year in (2025,2024):
            reports[str(year)+'1231']=dict(rType='合并期末',rCurrency='CNY',publish_date=str(year+1)+'0430',
                data=[dict(item_title='货币资金',item_field='CURFDS',item_source=source,item_value='123.450000',item_precision='f2'),
                      dict(item_title='应付债券',item_field='BDSPAYA',item_source=source,item_value=None),
                      dict(item_title='流动负债',item_field='',item_source=source,item_value='')])
        raw=m._json(dict(result=dict(status=dict(code=0),data=dict(report_list=reports,
             report_date=[dict(date_value=k) for k in reports]))))
        path=output_dir/'original.json';path.write_bytes(raw)
        acquired=datetime.now(timezone.utc).isoformat()
        descriptor=dict(path=path.relative_to(root).as_posix(),sha256=m._sha(raw),
                        source_url=m._url(symbol,role),acquired_at=acquired)
        receipt=dict(url=descriptor['source_url'],path=descriptor['path'],sha256=descriptor['sha256'],
                     acquired_at=acquired,bytes=len(raw),action='no_order')
        receipt_path=output_dir/'acquisition.json';receipt_path.write_bytes(m._json(receipt))
        descriptor['receipt']=dict(path=receipt_path.relative_to(root).as_posix(),sha256=m._sha(receipt_path.read_bytes()))
        return descriptor
    monkeypatch.setattr(m,'collect_sina_statement_original',collector)
    return tmp_path,tmp_path/'runtime/sina/test',calls


def collect(env):return m.collect(env[0],env[1],['600519','600887'],'2025-12-31',True)
def load(env,binding):return m.load(env[0],binding,datetime.now(timezone.utc))


def resign(env,binding,mutator,body=False):
    path=env[0]/binding['path'];manifest=json.loads(path.read_bytes())
    if body:
        descriptor=manifest['sources'][0]['descriptor'];raw_path=env[0]/descriptor['path']
        payload=json.loads(raw_path.read_bytes());mutator(payload)
        raw=m._json(payload);raw_path.write_bytes(raw);descriptor['sha256']=m._sha(raw)
        rp=env[0]/descriptor['receipt']['path'];receipt=json.loads(rp.read_bytes())
        receipt.update(sha256=descriptor['sha256'],bytes=len(raw));rp.write_bytes(m._json(receipt))
        descriptor['receipt']['sha256']=m._sha(rp.read_bytes())
    else:mutator(manifest)
    path.write_bytes(m._json(manifest));return dict(binding,sha256=m._sha(path.read_bytes()))


def test_existing_collector_reused_two_symbols_three_roles_and_prior(env,monkeypatch):
    binding=collect(env);result=load(env,binding)
    assert len(env[2])==6 and result['status']=='COMPLETE'
    for company in result['symbols'].values():
        assert set(company['statements'])==set(m.ROLES)
        assert set(company['comparatives']['2024-12-31'])==set(m.ROLES)
        rows=company['statements']['balance']['rows']
        assert rows[0]['raw_value']=='123.450000' and rows[0]['unit'] is None
        assert rows[0]['currency']=='CNY' and rows[1]['value'] is None and rows[2]['value'] is None
        assert company['statements']['balance']['complete_debt'] is None
    before={p:p.read_bytes() for p in env[1].rglob('*.json')}
    monkeypatch.setattr(m,'collect_sina_statement_original',lambda **kw:pytest.fail('network'))
    assert load(env,binding)==result and before=={p:p.read_bytes() for p in before}


@pytest.mark.parametrize('field,value',[('rType','母公司期末'),('rCurrency','USD'),('publish_date','20990430')])
def test_scope_currency_future_publication_rejected(env,field,value):
    binding=resign(env,collect(env),lambda p:p['result']['data']['report_list']['20251231'].update({field:value}),True)
    with pytest.raises(ValueError):load(env,binding)


@pytest.mark.parametrize('field,value',[('item_source','lrb'),('item_value','NaN'),('item_value',True)])
def test_wrong_statement_nonfinite_and_boolean_rejected(env,field,value):
    binding=resign(env,collect(env),lambda p:p['result']['data']['report_list']['20251231']['data'][0].update({field:value}),True)
    with pytest.raises(ValueError):load(env,binding)


def test_missing_prior_is_explicit_partial_not_zero(env):
    binding=resign(env,collect(env),lambda p:p['result']['data']['report_list'].pop('20241231'),True)
    result=load(env,binding)
    assert result['status']=='PARTIAL'
    assert 'balance' not in result['symbols']['600519']['comparatives']['2024-12-31']
    assert result['errors'][0]['period']=='2024-12-31'


def test_repeated_native_labels_preserved(env):
    def duplicate(p):
        rows=p['result']['data']['report_list']['20251231']['data'];rows.append(dict(rows[0]))
    result=load(env,resign(env,collect(env),duplicate,True))
    rows=result['symbols']['600519']['statements']['balance']['rows']
    assert len(rows)==4 and rows[0]['row_index']!=rows[-1]['row_index']


@pytest.mark.parametrize('mutation',['hash','receipt','future','url','duplicate','path'])
def test_manifest_identity_and_bound_bytes(env,mutation):
    binding=collect(env)
    def change(manifest):
        d=manifest['sources'][0]['descriptor']
        if mutation=='hash':d['sha256']='0'*64
        if mutation=='receipt':d['receipt']['sha256']='0'*64
        if mutation=='future':d['acquired_at']='2099-01-01T00:00:00+00:00'
        if mutation=='url':d['source_url']=m._url('600887','balance')
        if mutation=='duplicate':manifest['sources'][1]=manifest['sources'][0]
        if mutation=='path':d['path']='../outside.json'
    with pytest.raises((ValueError,OSError)):load(env,resign(env,binding,change))


def test_failed_source_keeps_other_roles_and_failure(env,monkeypatch):
    old=m.collect_sina_statement_original
    def collector(**kw):
        if kw['symbol']=='600519' and kw['statement']==m.SinaStatement.INCOME:raise ValueError('access denied')
        return old(**kw)
    monkeypatch.setattr(m,'collect_sina_statement_original',collector)
    result=load(env,collect(env))
    assert result['status']=='PARTIAL' and len(result['symbols']['600887']['statements'])==3
    assert 'income' not in result['symbols']['600519']['statements']
    assert result['errors'][0]['message']=='access denied'


def test_auth_symbol_limit_and_no_overwrite(env):
    with pytest.raises(ValueError):m.collect(env[0],env[1],['600519'],'2025-12-31',False)
    with pytest.raises(ValueError):m.collect(env[0],env[1],['600519']*7,'2025-12-31',True)
    collect(env)
    with pytest.raises(FileExistsError):collect(env)


def test_isolated_copy_replay_keeps_source_times(env):
    import shutil
    binding=collect(env);expected=load(env,binding)
    isolated=env[0]/'restored';shutil.copytree(env[1],isolated/'runtime/sina/test')
    assert m.load(isolated,binding,datetime.now(timezone.utc))==expected

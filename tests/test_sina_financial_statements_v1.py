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
        # Fully rebind the success attempt for parser-focused mutation tests.
        ab=manifest['sources'][0]['attempts'][-1];ap=env[0]/ab['path']
        attempt=json.loads(ap.read_bytes());attempt['descriptor']=descriptor
        ap.write_bytes(m._json(attempt));ab['sha256']=m._sha(ap.read_bytes())
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


def transport_error(status=None, retry_after=False):
    if status is None:
        return m.requests.exceptions.ReadTimeout('single attempt timed out')
    response=m.requests.Response();response.status_code=status
    if retry_after:response.headers['Retry-After']='1'
    return m.requests.HTTPError('HTTP '+str(status),response=response)


@pytest.mark.parametrize('failure',[transport_error(),m.requests.ConnectionError('connection lost'),transport_error(503)])
def test_retry_once_in_fresh_directory_then_strict_success(env,monkeypatch,failure):
    original=m.collect_sina_statement_original;folders=[]
    def collector(**kw):
        if kw['symbol']=='600519' and kw['statement']==m.SinaStatement.INCOME:
            folders.append(kw['output_dir'])
            if len(folders)==1:
                kw['output_dir'].mkdir(parents=True)
                (kw['output_dir']/'partial.raw').write_bytes(b'first attempt retained')
                raise failure
        return original(**kw)
    monkeypatch.setattr(m,'collect_sina_statement_original',collector)
    monkeypatch.setattr(m.time,'sleep',lambda seconds:None)
    binding=collect(env);result=load(env,binding)
    assert result['status']=='COMPLETE' and len(folders)==2 and folders[0]!=folders[1]
    assert (folders[0]/'partial.raw').read_bytes()==b'first attempt retained'
    manifest=json.loads((env[0]/binding['path']).read_bytes())
    entry=next(e for e in manifest['sources'] if e['symbol']=='600519' and e['role']=='income')
    assert len(entry['attempts'])==2 and 'error' not in entry
    first=json.loads((env[0]/entry['attempts'][0]['path']).read_bytes())
    second=json.loads((env[0]/entry['attempts'][1]['path']).read_bytes())
    assert first['status']=='FAILED' and first['retry_scheduled'] is True
    assert second['status']=='COMPLETE' and second['descriptor']==entry['descriptor']


@pytest.mark.parametrize('failure',[
    ValueError('identity mismatch'),json.JSONDecodeError('invalid JSON','x',0),
    ValueError('scope mismatch'),PermissionError('denied'),transport_error(401),
    transport_error(403),transport_error(429),transport_error(503,True),
    m.requests.exceptions.SSLError('certificate invalid')])
def test_nonretryable_failure_calls_collector_only_once(env,monkeypatch,failure):
    original=m.collect_sina_statement_original;attempts=[]
    def collector(**kw):
        if kw['symbol']=='600519' and kw['statement']==m.SinaStatement.INCOME:
            attempts.append(kw['output_dir']);raise failure
        return original(**kw)
    monkeypatch.setattr(m,'collect_sina_statement_original',collector)
    monkeypatch.setattr(m.time,'sleep',lambda seconds:pytest.fail('unexpected retry'))
    result=load(env,collect(env))
    assert len(attempts)==1 and result['status']=='PARTIAL'
    assert 'income' not in result['symbols']['600519']['statements']


def test_two_timeouts_stop_and_preserve_both_attempt_receipts(env,monkeypatch):
    original=m.collect_sina_statement_original;attempts=[]
    def collector(**kw):
        if kw['symbol']=='600519' and kw['statement']==m.SinaStatement.INCOME:
            attempts.append(kw['output_dir']);raise transport_error()
        return original(**kw)
    monkeypatch.setattr(m,'collect_sina_statement_original',collector)
    monkeypatch.setattr(m.time,'sleep',lambda seconds:None)
    binding=collect(env);result=load(env,binding)
    assert len(attempts)==2 and result['status']=='PARTIAL'
    manifest=json.loads((env[0]/binding['path']).read_bytes())
    entry=next(e for e in manifest['sources'] if e['symbol']=='600519' and e['role']=='income')
    assert len(entry['attempts'])==2 and entry['descriptor'] is None
    records=[json.loads((env[0]/b['path']).read_bytes()) for b in entry['attempts']]
    assert [r['retry_scheduled'] for r in records]==[True,False]
    assert all(r['status']=='FAILED' for r in records)


def test_legacy_without_attempts_still_replays(env):
    binding=collect(env)
    binding=resign(env,binding,lambda value:[e.pop('attempts') for e in value['sources']])
    assert load(env,binding)['status']=='COMPLETE'


@pytest.mark.parametrize('mutation',['bytes','symbol','role','number','naive','future','reverse',
                                    'descriptor','request','raw_hash','receipt_hash','receipt_content',
                                    'empty','too_many'])
def test_attempt_binding_identity_time_and_descriptor_rejected(env,mutation):
    binding=collect(env)
    path=env[0]/binding['path'];manifest=json.loads(path.read_bytes())
    entry=manifest['sources'][0];ab=entry['attempts'][0];ap=env[0]/ab['path']
    attempt=json.loads(ap.read_bytes())
    if mutation=='bytes':ap.write_bytes(ap.read_bytes()+b' ')
    elif mutation=='empty':entry['attempts']=[]
    elif mutation=='too_many':entry['attempts']*=3
    else:
        if mutation=='symbol':attempt['symbol']='600887'
        if mutation=='role':attempt['role']='income'
        if mutation=='number':attempt['attempt']=2
        if mutation=='naive':attempt['started_at']='2026-01-01T00:00:00'
        if mutation=='future':attempt['finished_at']='2099-01-01T00:00:00+00:00'
        if mutation=='reverse':attempt['started_at']=attempt['finished_at'];attempt['finished_at']=manifest['started_at']
        if mutation=='descriptor':attempt['descriptor']=None
        if mutation=='request':attempt['descriptor']['source_url']=m._url('600887','balance')
        if mutation=='raw_hash':attempt['descriptor']['sha256']='0'*64
        if mutation=='receipt_hash':attempt['descriptor']['receipt']['sha256']='0'*64
        if mutation=='receipt_content':
            rb=attempt['descriptor']['receipt'];rp=env[0]/rb['path'];receipt=json.loads(rp.read_bytes())
            receipt['bytes']+=1;rp.write_bytes(m._json(receipt));rb['sha256']=m._sha(rp.read_bytes())
        ap.write_bytes(m._json(attempt));ab['sha256']=m._sha(ap.read_bytes())
    path.write_bytes(m._json(manifest));binding['sha256']=m._sha(path.read_bytes())
    with pytest.raises(ValueError):load(env,binding)


def test_failed_json_attempt_replays_bound_bytes_without_parsing_them(env,monkeypatch):
    original=m.collect_sina_statement_original
    def collector(**kw):
        descriptor=original(**kw)
        if kw['symbol']=='600519' and kw['statement']==m.SinaStatement.INCOME:
            path=kw['root']/descriptor['path'];path.write_bytes(b'not JSON response')
            rp=kw['root']/descriptor['receipt']['path'];receipt=json.loads(rp.read_bytes())
            receipt.update(sha256=m._sha(path.read_bytes()),bytes=len(path.read_bytes()))
            rp.write_bytes(m._json(receipt))
            raise ValueError('failed source JSON')
        return descriptor
    monkeypatch.setattr(m,'collect_sina_statement_original',collector)
    binding=collect(env)
    assert load(env,binding)['status']=='PARTIAL'
    manifest=json.loads((env[0]/binding['path']).read_bytes())
    entry=next(e for e in manifest['sources'] if e['symbol']=='600519' and e['role']=='income')
    (env[0]/entry['descriptor']['path']).write_bytes(b'tampered invalid JSON')
    with pytest.raises(ValueError,match='hash'):load(env,binding)

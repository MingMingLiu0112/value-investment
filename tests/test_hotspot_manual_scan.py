from datetime import datetime,timezone,date
from decimal import Decimal
from pathlib import Path
import json
import pytest
from value_investment_agent.application.hotspot.manual import run_manual_scan
from value_investment_agent.application.hotspot.scan import scan_market_hotspots
from value_investment_agent.infrastructure.hotspot.sources import read_bound
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.domain.hotspot.price_behavior import describe_bars,observation_gates
from value_investment_agent.virtual_account import VirtualAccount,replay,dated_research_fee,ORDER_TERMS_VERSION


def _bundle(root):
    (root/'runtime').mkdir()
    def bind(name,data):
        p=root/'runtime'/name
        p.write_text(json.dumps(data),encoding='utf-8')
        return dict(path=p.relative_to(root).as_posix(),sha256=sha256_file(p),available_at='2026-09-23T12:00:00+00:00',source_url='https://example.test/synthetic')
    market=bind('market.json',dict(fetched_at='2026-09-23T12:00:00+00:00',rows=[dict(code='sz000651',name='synthetic issuer',zxj='10')]))
    industry=bind('industry.json',dict(fetched_at='2026-09-23T12:00:00+00:00',rows=[dict(code='000651',name='synthetic issuer',trade='10',**{'class':'synthetic industry'},changepercent=2,amount=10000)]))
    raw=bind('bars.json',dict(code=0,data={'sz000651':{'day':[[f'2026-09-{day:02}','10','10','11','9','100'] for day in range(17,23)]}}))
    history=bind('manifest.json',dict(symbol='000651',created_at=raw['available_at'],quote_date='2026-09-22',tencent_close='10',provider_documents={'tencent':dict(path=raw['path'],sha256=raw['sha256'],fetched_at=raw['available_at'],source_url=raw['source_url'])}))
    config=root/'bundle.json'
    config.write_text(json.dumps(dict(schema_version='hotspot-manual-scan-config-v1',action='no_order',limit=12,market=market,industry=industry,history=history)))
    return config


def test_complete_replay_is_semantically_idempotent_and_never_admitted(tmp_path):
    config=_bundle(tmp_path)
    outputs=[]
    for name,hour in [('one',13),('two',14)]:
        result=run_manual_scan(root=tmp_path,output=tmp_path/'runtime'/name,offline_bundle=config,offline_sha256=sha256_file(config),cutoff=datetime(2026,9,23,hour,tzinfo=timezone.utc))
        report=json.loads((tmp_path/result['report_path']).read_text())
        assert result['sha256']==sha256_file(tmp_path/result['report_path'])
        assert report['action']=='no_order' and not report['entry_review_eligible']
        assert all(not gate['passed'] for gate in report['gates'].values())
        assert report['observation_list'][0]['source_refs']
        assert report['price_behavior']['periods']['60m']['status']=='UNKNOWN'
        outputs.append(report)
    assert outputs[0]['semantic_content']==outputs[1]['semantic_content']
    assert outputs[0]['observed_at']!=outputs[1]['observed_at']
    with pytest.raises(FileExistsError):
        run_manual_scan(root=tmp_path,output=tmp_path/'runtime/one',offline_bundle=config,offline_sha256=sha256_file(config))


def test_offline_bundle_hash_and_admission_override_rejected(tmp_path):
    config=_bundle(tmp_path)
    with pytest.raises(ValueError,match='Offline bundle hash'):
        run_manual_scan(root=tmp_path,output=tmp_path/'runtime/out',offline_bundle=config,offline_sha256='0'*64)
    data=json.loads(config.read_text())
    data['gates']={'Shadow':True}
    config.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='overrides'):
        run_manual_scan(root=tmp_path,output=tmp_path/'runtime/out',offline_bundle=config,offline_sha256=sha256_file(config))


def test_network_failure_fallback_is_visible(monkeypatch,tmp_path):
    from value_investment_agent.application.hotspot import manual
    config=_bundle(tmp_path)
    (tmp_path/'config').mkdir()
    (tmp_path/'config/hotspot-manual-scan-v1.json').write_bytes(config.read_bytes())
    def failed(): raise OSError('synthetic provider outage')
    monkeypatch.setattr(manual,'fetch_tencent_board_rank',failed)
    monkeypatch.setattr(manual,'fetch_sina_industry_quotes',failed)
    monkeypatch.setattr(manual,'collect_session_bundle',lambda symbols: (_ for _ in ()).throw(OSError('synthetic dated source outage')))
    result=run_manual_scan(root=tmp_path,output=tmp_path/'runtime/network')
    report=json.loads((tmp_path/result['report_path']).read_text())
    assert report['collection']['fallback'] is True
    assert all(a['status']=='RETAINED_OLD_CACHE_FALLBACK' for a in report['collection']['attempts'] if a['role'] in ('market','industry'))
    assert report['confirmed_market_date'] is None


def test_network_quote_subset_uses_bound_history_symbol(monkeypatch,tmp_path):
    from value_investment_agent.application.hotspot import manual
    config=_bundle(tmp_path)
    data=json.loads(config.read_text())
    history=tmp_path/data['history']['path']
    manifest=json.loads(history.read_text())
    manifest['symbol']='123456'
    history.write_text(json.dumps(manifest),encoding='utf-8')
    data['history']['sha256']=sha256_file(history)
    (tmp_path/'config').mkdir()
    (tmp_path/'config/hotspot-manual-scan-v1.json').write_text(json.dumps(data),encoding='utf-8')
    def failed(): raise OSError('synthetic provider outage')
    monkeypatch.setattr(manual,'fetch_tencent_board_rank',failed)
    monkeypatch.setattr(manual,'fetch_sina_industry_quotes',failed)
    captured=[]
    def collect(symbols):
        captured.extend(symbols)
        raise OSError('synthetic dated source outage')
    monkeypatch.setattr(manual,'collect_session_bundle',collect)
    def scan(**kwargs):
        (kwargs['output']/'report.json').write_text('{"action":"no_order"}',encoding='utf-8')
    monkeypatch.setattr(manual,'scan_market_hotspots',scan)
    run_manual_scan(root=tmp_path,output=tmp_path/'runtime/network')
    assert captured==['000651','123456']


@pytest.mark.parametrize('conflicting', [False,True])
def test_real_parser_binds_quote_dates_without_dating_industry(tmp_path,conflicting):
    import base64,hashlib
    config=_bundle(tmp_path)
    tx=['0']*31
    tx[1]='synthetic';tx[2]='000651';tx[3]='10';tx[5]='10';tx[6]='100';tx[30]='20261009150000'
    sina=['0']*33
    sina[0]='synthetic';sina[1]='10';sina[3]='10';sina[8]='100';sina[30]='2026-10-08' if conflicting else '2026-10-09';sina[31]='15:00:00';sina[32]='00'
    documents={}
    for provider,text,url in [('tencent','v_sz000651="'+'~'.join(tx)+'";','https://qt.gtimg.cn/q=sz000651'),('sina','var hq_str_sz000651="'+','.join(sina)+'";','https://hq.sinajs.cn/list=sz000651')]:
        raw=text.encode('gb18030')
        documents[provider]=dict(source_url=url,fetched_at='2026-10-11T12:00:00+00:00',sha256=hashlib.sha256(raw).hexdigest(),raw_base64=base64.b64encode(raw).decode())
    quotes=tmp_path/'runtime/dated.json'
    quotes.write_text(json.dumps(dict(documents=documents,references={'000651':{'document_refs':{'tencent':'tencent','sina':'sina'}}})))
    bundle=json.loads(config.read_text())
    bundle['dated_quotes']=dict(path='runtime/dated.json',sha256=sha256_file(quotes),available_at='2026-10-11T12:00:00+00:00',source_url='https://qt.gtimg.cn/q=')
    config.write_text(json.dumps(bundle))
    result=run_manual_scan(root=tmp_path,output=tmp_path/'runtime/out',offline_bundle=config,offline_sha256=sha256_file(config),cutoff=datetime(2026,10,11,13,tzinfo=timezone.utc))
    report=json.loads((tmp_path/result['report_path']).read_text())
    assert report['confirmed_market_date']==(None if conflicting else '2026-10-09')
    assert report['confirmed_market_date_scope']=='DATED_QUOTE_SUBSET_ONLY_NOT_INDUSTRY_SNAPSHOT'
    assert report['observation_list'][0]['confirmed_market_date'] is None
    assert 'agent_explanation' not in report
    assert not report['entry_review_eligible']


def test_hash_and_future_evidence_rejected(tmp_path):
    (tmp_path/'runtime').mkdir()
    p=tmp_path/'runtime/raw.json'
    p.write_text('{}')
    b=dict(path='runtime/raw.json',sha256=sha256_file(p),available_at='2026-10-11T10:00:00+00:00')
    with pytest.raises(ValueError,match='not available'):
        read_bound(tmp_path,b,datetime(2026,10,11,9,tzinfo=timezone.utc))
    p.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='hash mismatch'):
        read_bound(tmp_path,b,datetime(2026,10,12,tzinfo=timezone.utc))


def test_source_escape_rejected(tmp_path):
    with pytest.raises(ValueError):
        read_bound(tmp_path,dict(path='../outside',sha256='0'*64,available_at='2026-10-11T00:00:00+00:00'),datetime.now(timezone.utc))


def test_no_intraday_synthesis_or_breakout_admission():
    bars=[dict(date=f'2026-09-{i:02}',open='10',close='10',high='11',low='9',volume='100') for i in range(1,7)]
    bars[-1].update(close='12',high='12')
    out=describe_bars(bars)
    assert out['breakout'] and not out['execution_admitted']
    assert out['volume_confirmation']=='UNKNOWN'
    assert describe_bars(bars[:3])['status']=='UNKNOWN'


def _sessions():
    return [dict(date=d,open='100',close='100',execution_ready=True,price_limit_down='90',price_limit_up='110') for d in ['2025-01-06','2025-01-07','2025-01-08']]


def _proposal():
    return dict(state='proposed_entry',decision_id='synthetic-hotspot-not-signal',quantity=100,execution_terms=dict(
        version=ORDER_TERMS_VERSION,valid_session='2025-01-07',limit_price='101',cash_budget_cny='10100',
        liquidity_budget_cny='20000',liquidity_as_of='2025-01-06',slippage_bps='10',basis_id='SYNTHETIC_ONLY'))


def test_reuse_replay_t1_fees_slippage_and_idempotence():
    account,rows=replay(_sessions()[:2],{'2025-01-06':_proposal()},fee_calculator=dated_research_fee)
    fill=rows[1]['fill']
    assert fill['price']=='100.10' and fill['fee_cny']=='5.10'
    assert fill['execution_scope']=='daily_simulation_assumption_not_real_fill'
    assert account.sellable_shares(date(2025,1,7))==0
    assert account.sellable_shares(date(2025,1,8))==100
    assert replay(_sessions()[:2],{},account,fee_calculator=dated_research_fee)[1]==[]


@pytest.mark.parametrize('patch,reason',[
    ({'open':'110'},'opening_at_or_outside_price_limit'),
    ({'execution_status':'blocked_suspension'},'session_not_executable'),
    ({'execution_ready':None},'execution_state_unknown'),
    ({'price_limit_up':None},'price_limit_state_unknown'),
])
def test_replay_rejects_limit_suspension_unknown(patch,reason):
    bars=_sessions()[:2]
    bars[1].update(patch)
    account,rows=replay(bars,{'2025-01-06':_proposal()},fee_calculator=dated_research_fee)
    assert rows[1]['fill'] is None and rows[1]['rejected_order_reason']==reason
    assert account.cash==Decimal('1000000')

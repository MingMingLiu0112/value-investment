"""A+B scoped public screening; reuse existing M2 economics, no trade authority."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from ...domain.discovery.sse_main_pool_v1 import VERSION, CHANNELS, project_outcome
from ...domain.discovery.value_candidate_selection import observation_conditions, rank_research_candidates
from ...infrastructure.screening import sse_main_sources_v1 as sources
from ...infrastructure.screening.evidence_screen_v3 import build_discovery_receipt
from ...m2_discovery_engine import M2ScreeningPolicy, merge_market_snapshots
from ...m2_market_data import parse_tencent_board, parse_sina_industry
from ...m2_opportunity_discovery import EvidenceReference
from ..product.common import require_inside, write_new_bytes
from .public_financial_input import build_financial_input, verify_public_supplement
from ...domain.discovery.financial_gap_diagnostics_v1 import build_diagnostics, statement_observations
from ...infrastructure.screening import public_three_statements_v1 as three_statements
from ...financial_institutions import provisional_financial_type
from ...financial_quality import _accepted
from copy import deepcopy

POINTER = '.tmp/sse-main-screening-current.json'
SCOPE = 'SSE_MAIN_A_ONLY'


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')


def _binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


def _read(root, ref):
    if not isinstance(ref, dict) or set(ref) != {'path','sha256'}:
        raise ValueError('EXACT_SCREEN_BINDING_REQUIRED')
    name=Path(ref['path'])
    if name.is_absolute() or '..' in name.parts:
        raise ValueError('RELATIVE_SCREEN_BINDING_REQUIRED')
    path=require_inside(root/'runtime/sse-main-screening',root/name,'SSE screening')
    raw=path.read_bytes()
    if len(raw)>40_000_000 or sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('SCREEN_SOURCE_HASH_MISMATCH')
    return json.loads(raw)


def implementation():
    import inspect
    from ...domain.discovery import sse_main_pool_v1, value_candidate_selection, financial_gap_diagnostics_v1
    from ... import m2_discovery_engine, m2_opportunity_discovery, m2_market_data, financial_quality, official_universe, financial_institutions
    from ...infrastructure.screening import evidence_screen_v3, public_financial_snapshot
    modules=[sse_main_pool_v1,value_candidate_selection,financial_gap_diagnostics_v1,three_statements,m2_discovery_engine,m2_opportunity_discovery,
             m2_market_data,financial_quality,official_universe,financial_institutions,evidence_screen_v3,public_financial_snapshot,sources]
    paths=[Path(__file__),*[Path(inspect.getfile(m)) for m in modules],Path(__file__).with_name('public_financial_input.py')]
    base=Path(__file__).resolve().parents[4]
    return {p.resolve().relative_to(base).as_posix():sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in paths}


def compile_inputs(*, root, inputs, now, run_id):
    payload=sources.verify_inputs(root,inputs,now,financial_verifier=verify_public_supplement)
    official=payload['official']
    records=official['records']
    if not records or any(r['exchange']!='SSE' or r['board']!='主板' or r['security_type']!='A股' for r in records):
        raise ValueError('SSE_MAIN_A_IDENTITY_REQUIRED')
    symbols={r['symbol'] for r in records}
    if len(symbols)!=len(records):raise ValueError('DUPLICATE_OFFICIAL_SYMBOL')
    filtered={}
    for role,parser in [('tencent',parse_tencent_board),('sina',parse_sina_industry)]:
        raw=payload[role];parsed=parser(raw)
        if len(parsed)!=len(raw['rows']):raise ValueError('QUOTE_ROW_CORRESPONDENCE_CHANGED')
        filtered[role]=dict(raw,rows=[r for r,v in zip(raw['rows'],parsed) if v['symbol'] in symbols])
    refs={}
    for role,ref in sorted(inputs['inputs'].items()):
        source_url=(ref.get('request_identity',{}).get('url') or payload[role].get('source_url') or 'SOURCE_REFERENCES_IN_BOUND_INPUT')
        refs[role]=EvidenceReference(id=role,path=ref['path'],sha256=ref['sha256'],source_name=role,
            source_url=source_url,fetched_at=datetime.fromisoformat(ref['fetched_at']))
    generated=datetime.fromisoformat(inputs['finished_at'])
    all_points=list(payload['financial']['points'])
    supplement=None
    if inputs.get('financial_supplement'):
        supplement=three_statements.load(root,inputs['financial_supplement'],now)
        supplement_period=supplement['period']
        observed_period=(payload['financial'].get('public_financial_input') or {}).get('period')
        if observed_period and supplement_period!=observed_period:
            raise ValueError('SUPPLEMENT_REPORT_PERIOD_MISMATCH')
        all_points.extend(p for p in statement_observations(supplement,period=supplement_period) if p['symbol'] in symbols)
        acquired=datetime.fromisoformat(supplement['available_at'])
        generated=max(generated,acquired)
        ref=inputs['financial_supplement']
        refs['financial_supplement']=EvidenceReference(id='financial_supplement',path=ref['path'],sha256=ref['sha256'],
            source_name='Eastmoney same-period three statements',source_url='https://datacenter-web.eastmoney.com/api/data/v1/get',fetched_at=acquired)
    receipt=build_discovery_receipt(run_id=run_id,generated_at=generated,official_payload=official,
        tencent_payload=filtered['tencent'],sina_payload=filtered['sina'],dividend_payload=payload['dividend'],
        financial_points=all_points,quote_date=generated.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        run_refs=refs,policy=M2ScreeningPolicy(),quote_date_verified=False)
    receipt_payload=receipt.as_policy()
    official_records={r.symbol:r for r in receipt.universe.records}
    quotes,conflicts=merge_market_snapshots(parse_tencent_board(filtered['tencent']),
        parse_sina_industry(filtered['sina']),official_records,quote_date=receipt.quote_date,
        price_tolerance=M2ScreeningPolicy().price_tolerance)
    evaluations={}
    for channel,result in receipt_payload['channel_results'].items():
        for ev in result['evaluations']:
            evaluations.setdefault(ev['symbol'],[]).append(dict(ev,channel=channel))
    points={}
    for point in all_points:points.setdefault(point['symbol'],[]).append(point)
    ranked=[]
    for security in records:
        symbol=security['symbol'];ev=evaluations.get(symbol,[])
        conditions,period=observation_conditions(points.get(symbol,[]),now=generated)
        quote=quotes.get(symbol)
        risk='ST' in security['name'].upper() or bool(quote and 'ST' in quote.name.upper())
        outcome=project_outcome(ev,risk_warning=risk,price_conflict=symbol in conflicts)
        specialized=any(e['status']=='UNSUPPORTED' for e in ev)
        if specialized:
            for c in conditions:c['favorable']=None
        quote=quotes.get(symbol)
        verified_fields={p['field_name'] for p in points.get(symbol,[]) if p.get('period_label')==period and _accepted(p)}
        kind=provisional_financial_type(security['name'],quote.industry if quote else security.get('official_industry'))
        financial_data,applicability=build_diagnostics(points.get(symbol,[]),period=period,
            institution_kind=kind,verified_fields=verified_fields)
        actual_missing=[f['label'] for f in financial_data['fields'] if f['status']=='MISSING']
        if kind is None:
            for e in ev:
                if e['channel']=='quality' and e['status']=='DATA_GAP':
                    e['native_reason']=e['reason']
                    e['reason']=(f"已取得{financial_data['available_count']}/9项普通企业指标，正式核验{financial_data['verified_count']}/9；"
                        +"实际缺失："+('、'.join(actual_missing) or '无，但来源核验或完整口径尚未满足')+"。已有未核验数据不等于没有数据。")
            outcome['gaps']=[g for g in outcome['gaps'] if not g.startswith('quality:')]
            if financial_data['verified_count']<9:
                outcome['gaps'].insert(0,f"质量核验未齐；已有{financial_data['available_count']}/9项数据，实际缺失："+('、'.join(actual_missing) or '无'))
        row=dict(symbol=symbol,company_name=security['name'],name=security['name'],
            industry=quote.industry if quote else security.get('official_industry'),
            profile_status='SPECIALIZED_RESEARCH_REQUIRED' if specialized else 'GENERAL_RESEARCH',
            conditions=conditions,period=period,risk_warning=risk,price_conflict=symbol in conflicts,
            channel_evaluations=ev,updated_at=generated.isoformat(),financial_data=financial_data,applicability=applicability,**outcome)
        # Data-gap fields remain explicit even when another cheap channel passes.
        if row['status']=='CANDIDATE':
            labels=dict(quality='质量',dividend_cash_return='股息现金回报',value='低估值线索',cyclical='周期研究')
            row['reason']='；'.join(labels[e['channel']]+'：'+(e.get('trigger_reasons') or [e['reason']])[0] for e in ev if e['channel'] in row['channels'])
        row['gaps']+=['财务及分红为初筛来源观察，尚非完整法定事实核验。','尚未完成企业经营、分红持续性和适用估值研究。','行情真实交易日未单独核验，不形成当前条件买价。']
        row.update(reference_price=str(quote.current_price) if quote and quote.current_price is not None else None,
                   quote_date=None,quote_observed_at=payload['tencent'].get('fetched_at'),
                   financial_quality_status='NOT_GRANTED',formal_eligibility=False,buy_eligible=False,action='no_order')
        ranked.append(row)
    ranked,_=rank_research_candidates(ranked,limit=200)
    candidates=[r for r in ranked if r['status']=='CANDIDATE']
    others=[r for r in ranked if r['status']!='CANDIDATE']
    for rank,row in enumerate(candidates,1):row['research_priority_rank']=rank
    rows=candidates+others
    counts=Counter(r['status'] for r in rows)
    result=dict(schema_version=VERSION,scope=SCOPE,action='no_order',formal_eligibility=False,
        buy_eligible=False,status='PARTIAL',run_id=run_id,rule_version=receipt.rule_version,
        policy=M2ScreeningPolicy().as_policy(),available_at=generated.isoformat(),
        quote_date=None,quote_date_verified=False,observation_date=receipt.quote_date,
        quote_status='PROVIDER_OBSERVATION_NOT_VERIFIED_TRADE_DATE',
        source_status=inputs['status'],coverage_complete=len(rows)==len(records),
        counts=dict(universe=len(rows),candidate=counts['CANDIDATE'],excluded=counts['EXCLUDED'],unassessable=counts['UNASSESSABLE']),
        channel_counts={c:dict(Counter(e['status'] for r in rows for e in r['channel_evaluations'] if e['channel']==c)) for c in CHANNELS},
        rows=rows,source_refs=[dict(path=v['path'],sha256=v['sha256']) for _,v in sorted(inputs['inputs'].items())],
        blockers=['INITIAL_SCREENING_NOT_BUY_ADVICE','PROVIDER_FINANCIAL_NOT_OFFICIAL_ADMISSION','QUOTE_TRADE_DATE_UNVERIFIED'],
        financial_supplement_status=supplement['status'] if supplement else 'NOT_COLLECTED',
        financial_data_summary=dict(
            general_company_count=sum(r['applicability']['kind'] is None for r in rows),
            institutions_by_type=dict(Counter(r['applicability']['label'] for r in rows if r['applicability']['kind'] is not None)),
            full_observation_count=sum(r['financial_data']['missing_count']==0 and r['applicability']['kind'] is None for r in rows),
            available_fields=sum(r['financial_data']['available_count'] for r in rows if r['applicability']['kind'] is None),
            missing_fields=sum(r['financial_data']['missing_count'] for r in rows if r['applicability']['kind'] is None)),
        assurance='PUBLIC_SOURCE_OBSERVATION_E1_NOT_DEEP_RESEARCH',implementation=implementation())
    if inputs.get('financial_supplement'):result['source_refs'].append(inputs['financial_supplement'])
    return result,receipt_payload


def refresh(*,root,allow_network=False):
    root=Path(root).resolve()
    if allow_network is not True:raise ValueError('EXPLICIT_PUBLIC_NETWORK_AUTHORIZATION_REQUIRED')
    run_id='sse-main-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]
    output=root/'runtime/sse-main-screening'/run_id
    inputs=sources.collect_inputs(root,output,allow_network=True,
        financial_builder=build_financial_input,financial_verifier=verify_public_supplement)
    verified=sources.verify_inputs(root,inputs,datetime.now(timezone.utc),financial_verifier=verify_public_supplement)
    period=(verified['financial'].get('public_financial_input') or {}).get('period')
    if not period:raise ValueError('EXPLICIT_COLLECTED_ANNUAL_PERIOD_REQUIRED')
    inputs['financial_supplement']=three_statements.collect(root,output/'three-statements',period,True)
    return publish_inputs(root=root, inputs=inputs, output=output, run_id=run_id)



def enrich_current(*,root,allow_network=False):
    if allow_network is not True:raise ValueError('EXPLICIT_PUBLIC_NETWORK_AUTHORIZATION_REQUIRED')
    root=Path(root).resolve()
    pointer=json.loads((root/POINTER).read_bytes())
    manifest=_read(root,pointer['manifest'])
    inputs=deepcopy(manifest['inputs'])
    old=sources.verify_inputs(root,inputs,datetime.now(timezone.utc),financial_verifier=verify_public_supplement)
    period=(old['financial'].get('public_financial_input') or {}).get('period')
    if not period:raise ValueError('EXPLICIT_RETAINED_ANNUAL_PERIOD_REQUIRED')
    run_id='sse-main-financial-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]
    output=root/'runtime/sse-main-screening'/run_id
    inputs['financial_supplement']=three_statements.collect(root,output/'three-statements',period,True)
    return publish_inputs(root=root,inputs=inputs,output=output,run_id=run_id)


def publish_inputs(*, root, inputs, output, run_id):
    root=Path(root).resolve()
    output=require_inside(root/'runtime/sse-main-screening',Path(output),'SSE output')
    output.mkdir(parents=True, exist_ok=True)
    now=datetime.now(timezone.utc)
    result,receipt=compile_inputs(root=root,inputs=inputs,now=now,run_id=run_id)
    write_new_bytes(output/'screening.json',_bytes(result))
    write_new_bytes(output/'receipt.json',_bytes(receipt))
    manifest=dict(schema_version=VERSION,scope=SCOPE,action='no_order',run_id=run_id,
        inputs=inputs,result=_binding(root,output/'screening.json'),receipt=_binding(root,output/'receipt.json'),
        generated_at=now.isoformat(),implementation=implementation())
    write_new_bytes(output/'manifest.json',_bytes(manifest))
    pointer=root/POINTER;pointer.parent.mkdir(exist_ok=True)
    if pointer.exists():
        write_new_bytes(output/'previous-pointer.json',pointer.read_bytes())
    pending=pointer.with_name(pointer.name+'.'+uuid4().hex+'.part')
    write_new_bytes(pending,_bytes(dict(schema_version=VERSION,action='no_order',
        manifest=_binding(root,output/'manifest.json'))))
    pending.replace(pointer)
    return dict(run_id=run_id,counts=result['counts'],manifest=_binding(root,output/'manifest.json'),action='no_order')


def read_screen(*,root,now,offset=0,limit=20,query='',status='CANDIDATE'):
    if now.utcoffset() is None or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100 or status not in {'ALL','CANDIDATE','EXCLUDED','UNASSESSABLE'} or len(query)>80:
        raise ValueError('INVALID_SCOPED_SCREEN_QUERY')
    root=Path(root).resolve()
    try:
        pointer=json.loads((root/POINTER).read_bytes())
        if pointer.get('schema_version')!=VERSION or pointer.get('action')!='no_order':raise ValueError('INVALID_SCOPED_SCREEN_POINTER')
        manifest=_read(root,pointer['manifest'])
        if manifest.get('schema_version')!=VERSION or manifest.get('scope')!=SCOPE or manifest.get('action')!='no_order':raise ValueError('INVALID_SCOPED_SCREEN_MANIFEST')
        if manifest['implementation']!=implementation():raise ValueError('SCREEN_IMPLEMENTATION_CHANGED_REPLAY_REQUIRED')
        stamp=datetime.fromisoformat(manifest['generated_at'])
        if stamp.utcoffset() is None or stamp>now:raise ValueError('FUTURE_SCREEN_MANIFEST')
        result,receipt=compile_inputs(root=root,inputs=manifest['inputs'],now=now,run_id=manifest['run_id'])
        stored_result=_read(root,manifest['result'])
        stored_receipt=_read(root,manifest['receipt'])
        if _bytes(result)!=_bytes(stored_result):
            raise ValueError('SCREEN_RESULT_REPLAY_MISMATCH:' + ','.join(k for k in result if _bytes(result[k])!=_bytes(stored_result.get(k))))
        if _bytes(receipt)!=_bytes(stored_receipt):
            raise ValueError('SCREEN_RECEIPT_REPLAY_MISMATCH:' + ','.join(k for k in receipt if _bytes(receipt[k])!=_bytes(stored_receipt.get(k))))
        rows=result.pop('rows')
        needle=query.strip().casefold()
        rows=[r for r in rows if (status=='ALL' or r['status']==status) and
              (not needle or any(needle in str(r.get(k,'' )).casefold() for k in ['symbol','name','industry']))]
        result.update(pagination=dict(offset=offset,limit=limit,total=len(rows)),
            items=rows[offset:offset+limit],read_at=now.isoformat(),
            snapshot_age_hours=max(0,(now-datetime.fromisoformat(result['available_at'])).total_seconds()/3600))
        if result['snapshot_age_hours']>24:
            result['source_status']='HISTORICAL_SNAPSHOT_SOURCE_REVALIDATED'
            result['blockers'].append('HISTORICAL_SNAPSHOT_NOT_TODAY_REFRESH')
        result['source_refs']=[pointer['manifest'],*result['source_refs']]
        return result
    except (OSError,ValueError,TypeError,KeyError) as error:
        return dict(schema_version=VERSION,scope=SCOPE,action='no_order',formal_eligibility=False,
            status='UNAVAILABLE',source_status='REVALIDATION_FAILED',counts=dict(universe=0,candidate=0,excluded=0,unassessable=0),
            coverage_complete=False,quote_date=None,quote_date_verified=False,available_at=None,read_at=now.isoformat(),
            items=[],pagination=dict(offset=offset,limit=limit,total=None),source_refs=[],
            rule_version=VERSION,blockers=['SOURCE_UNAVAILABLE_NOT_ZERO_CANDIDATES',str(error)[:160]])

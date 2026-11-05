"""Independent retained filings stay usable when candidate replay is rejected."""
from datetime import datetime, timezone, timedelta
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

from value_investment_agent.application.research import value_economic_assessment as economic
from value_investment_agent.application.research import value_research_analysis as native
from value_investment_agent.application.product.research_draft import load_current_research_analysis

SPEC='docs/current/two-company-earnings-bridge-20261024/sources.json'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


def test_missing_independent_sources_do_not_mask_original_replay_error(tmp_path,monkeypatch):
    def rejected(**_):raise ValueError('TEST_ONLY pending candidate implementation drift')
    monkeypatch.setattr(native,'load_current_value_research_analysis',rejected)
    result=load_current_research_analysis(tmp_path,'600887')
    assert result['status']=='SOURCE_OR_REPLAY_UNAVAILABLE'
    assert result['arithmetic_complete'] is result['action_admitted'] is False
    assert result['scenarios']==[] and 'implementation drift' in result['blockers'][0]
    assert 'historical_operating_review' not in result


@pytest.mark.parametrize('fault',['schema','symbol','duplicate','future'])
def test_independent_spec_rejects_invalid_identity_and_future_without_figures(tmp_path,fault):
    now=datetime.now(timezone.utc)
    items=[dict(symbol='600887',source_id=str(i),extra_fields=[],
                published_date='2026-08-27',original_acquired_at=None) for i in range(2)]
    spec=dict(schema_version='two-company-earnings-source-spec-v1',
        scope='RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION',action='no_order',
        companies={'600887':items},common_fields=[])
    if fault=='schema':spec['schema_version']='unknown'
    elif fault=='symbol':items[1]['symbol']='600519'
    elif fault=='duplicate':items[1]['source_id']=items[0]['source_id']
    else:items[0]['original_acquired_at']=(now+timedelta(days=1)).isoformat()
    write(tmp_path/SPEC,spec)
    review=economic.load_retained_operating_bridge(root=tmp_path,symbol='600887',now=now)
    assert review['status']=='SOURCE_REVALIDATION_FAILED'
    assert 'h1_change' not in review and 'historical_ttm_cny' not in review


@pytest.mark.parametrize('fault',['spec','raw','execution'])
def test_independent_observation_final_rechecks_entire_closure(tmp_path,monkeypatch,fault):
    code_root=Path(economic.__file__).resolve().parents[4]
    for ref in economic._EXECUTED_OPERATING_BINDINGS:
        target=tmp_path/ref['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(code_root/ref['path'],target)
    items=[]
    for index,periods in enumerate([['FY2025','FY2024'],['H12026','H12025']]):
        path=f'runtime/TEST_ONLY-{index}.pdf'
        original=tmp_path/path;original.parent.mkdir(parents=True,exist_ok=True)
        original.write_bytes(b'TEST_ONLY closure probe, not parsed financial data')
        items.append(dict(symbol='600887',source_id=f'TEST_ONLY-{index}',path=path,
            sha256=hashlib.sha256(original.read_bytes()).hexdigest(),source_url='https://example.test/TEST_ONLY.pdf',
            published_date='2026-08-27',original_acquired_at=None,periods=periods,extra_fields=[]))
    write(tmp_path/SPEC,dict(schema_version='two-company-earnings-source-spec-v1',
        scope='RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION',action='no_order',
        companies={'600887':items},common_fields=[]))
    def computation(**_):
        # TEST_ONLY simulated late mutation; no real financial parsing claimed.
        result={key:None for key in ('schema_version','scope','breakdown_status','h1_change','annual_change',
            'commercial_subtotal','unallocated_balances_cny','normalized_parent_profit_cny','normalized_range',
            'tax_rate_assumption','parent_attribution_assumption','normalization_open_items','interpretation_limits')}
        result.update(symbol='600887',action='no_order',g3_changed=False,price_admitted=False,
            strategy_admitted=False,normalized_earnings_admitted=False,
            source_bindings=items,ttm={'lines_cny':{'ex_parent_profit':'TEST_ONLY_NOT_A_NUMBER'}})
        target={'spec':tmp_path/SPEC,'raw':tmp_path/items[0]['path'],
            'execution':tmp_path/economic._EXECUTED_OPERATING_BINDINGS[-1]['path']}[fault]
        target.write_bytes(target.read_bytes()+b' ')
        return result
    monkeypatch.setattr(economic,'research_from_retained_sources',computation)
    result=economic.load_retained_operating_bridge(root=tmp_path,symbol='600887',now=datetime.now(timezone.utc))
    assert result['status']=='SOURCE_REVALIDATION_FAILED'
    assert 'historical_ttm_cny' not in result and 'h1_change' not in result


@pytest.mark.skipif(not os.environ.get('RETAINED_OPERATING_CONSUMER_ROOT'),reason='Explicit public original root required')
def test_real_600887_rejected_candidate_and_actual_official_bridge_http(tmp_path,monkeypatch):
    root=Path(os.environ['RETAINED_OPERATING_CONSUMER_ROOT']).resolve()
    spec=json.loads((root/SPEC).read_bytes())
    sources=spec['companies']['600887']
    before={row['path']:hashlib.sha256((root/row['path']).read_bytes()).hexdigest() for row in sources}
    assert all(before[row['path']]==row['sha256'] for row in sources)
    result=load_current_research_analysis(root,'600887',now=datetime.now(timezone.utc))
    assert result['status']=='SOURCE_OR_REPLAY_UNAVAILABLE'
    assert 'implementation drift' in str(result['blockers'])
    review=result['historical_operating_review']
    assert review['status']=='SOURCE_VERIFIED_HISTORICAL_DRIVERS_NOT_NORMALIZED'
    assert review['context_scope']=='INDEPENDENT_RETAINED_FILINGS_V1'
    assert review['historical_ttm_cny']=='9647734710.01'
    assert review['normalized_parent_profit_cny'] is None
    assert 'candidate_binding' not in review and 'input_descriptor_sha256' not in review
    assert result['arithmetic_complete'] is result['action_admitted'] is False
    assert result['scenarios']==[] and result['source_bindings']==[]
    assert review['g3_changed'] is review['price_admitted'] is review['strategy_admitted'] is False
    assert all(row['original_acquired_at'] is None for row in review['source_bindings'])
    # Real cold calculation has no read-time timestamp in its content identity.
    second=economic.load_retained_operating_bridge(root=root,symbol='600887',now=datetime.now(timezone.utc))
    assert {k:v for k,v in second.items() if k!='read_at'}=={k:v for k,v in review.items() if k!='read_at'}
    for source in sources:
        target=tmp_path/source['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/source['path'],target)
    write(tmp_path/SPEC,spec)
    for ref in review['execution_bindings']:
        target=tmp_path/ref['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/ref['path'],target)
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateStoreUnavailable
    def no_private(**_):raise PrivateStoreUnavailable('TEST_ONLY no account access')
    monkeypatch.setattr(private_routes,'resolve_private_root',no_private)
    # Native public projection against real retained inputs, with only private
    # access denied. ASGI TestClient binds no socket or running 8001 process.
    bootstrap='TEST_ONLY-'+('x'*48)
    client=TestClient(create_app(root,port=8791,bootstrap_secret=bootstrap),
        base_url='http://127.0.0.1:8791',client=('127.0.0.1',51000))
    client.headers.update({'host':'127.0.0.1:8791','origin':'http://127.0.0.1:8791'})
    unlock=client.post('/api/v1/private/session/unlock',json={'bootstrap_token':bootstrap})
    assert unlock.status_code==200
    client.headers['x-local-session']=unlock.json()['token']
    response=client.get('/api/v1/decisions/600887')
    assert response.status_code==200
    body=response.json()
    assert body['action']=='no_order'
    http_review=body['decision']['price_action_plan']['research_analysis']['historical_operating_review']
    assert {k:v for k,v in http_review.items() if k!='read_at'}=={k:v for k,v in review.items() if k!='read_at'}
    assert {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in before}==before
    destination=os.environ.get('RETAINED_OPERATING_CONSUMER_OUTPUT')
    if destination:
        output=Path(destination).resolve()
        assert output.is_relative_to(root/'.tmp') and not output.exists()
        write(output,dict(scope='ACTUAL_PUBLIC_REFERENCES_LOCAL_TESTCLIENT_NOT_LIVE_8001',
            native_analysis=result,isolated_http=body,source_hashes=before))
    forged=deepcopy(spec)
    forged['companies']={'601621':[dict(row,symbol='601621') for row in sources]}
    write(tmp_path/SPEC,forged)
    wrong=economic.load_retained_operating_bridge(root=tmp_path,symbol='601621',now=datetime.now(timezone.utc))
    assert wrong['status']=='SOURCE_REVALIDATION_FAILED'
    assert 'h1_change' not in wrong and 'historical_ttm_cny' not in wrong
    write(tmp_path/SPEC,spec)
    # Real bytes and source-spec drift both fail closed without clearing the
    # existing valuation failure. Neither test touches original/current files.
    def rejected(**_):raise ValueError(result['blockers'][0])
    monkeypatch.setattr(native,'load_current_value_research_analysis',rejected)
    first=tmp_path/sources[0]['path']
    first.write_bytes(first.read_bytes()+b' ')
    failed=load_current_research_analysis(tmp_path,'600887')
    assert failed['status']=='SOURCE_OR_REPLAY_UNAVAILABLE'
    assert failed['historical_operating_review']['status']=='SOURCE_REVALIDATION_FAILED'
    assert 'h1_change' not in failed['historical_operating_review']
    client.close()

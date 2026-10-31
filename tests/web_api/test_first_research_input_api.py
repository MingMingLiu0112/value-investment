"""TEST_ONLY public first-input view; never real economic/source acceptance."""
from copy import deepcopy
import json

import pytest

from test_first_research_input_v1 import first, run, put, NOW
from web_api.test_held_continuity_api import client_for
from value_investment_agent.application.product import first_research_input_view_v1 as view
from value_investment_agent.application.research import first_research_input_v1 as engine

ROUTE='/api/v1/first-research-inputs/'


def snapshot(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def registered(first,monkeypatch):
    root,spec,manifest,assumptions,cold,calls,save=first
    compiled=run(first)
    put(root,view.REGISTRY,dict(schema_version=view.SCHEMA,action='no_order',
        cases={'600887':dict(receipt=compiled['receipt_binding'])}))
    # Only invented TEST_ONLY transport decoding is injected. Receipt/package
    # hashes and existing engine cold recomputation still execute on every GET.
    def replay(**kwargs):
        return engine.replay_first_research_input(**kwargs,fact_replay=cold)
    monkeypatch.setattr(view,'replay_first_research_input',replay)
    return root,compiled,calls


def test_public_positive_view_cold_replays_without_account_or_writes(registered,monkeypatch):
    root,compiled,calls=registered
    from datetime import datetime
    from value_investment_agent.presentation.web_api import first_research_input_routes as routes
    class TestOnlyClock(datetime):
        @classmethod
        def now(cls,tz=None):
            return NOW
    monkeypatch.setattr(routes,'datetime',TestOnlyClock)
    client,_=client_for(root,root/'TEST_ONLY-private-journal.jsonl',monkeypatch)
    assert client.get('/api/v1/private/portfolio/held-continuity').status_code==401
    before=snapshot(root)
    count=len(calls)
    for _ in range(2):
        response=client.get(ROUTE+'600887')
        assert response.status_code==200,response.text
        assert response.headers['cache-control']=='no-store'
        body=response.json()
        assert body['status']=='SOURCE_BOUND_FIRST_INPUT_COMPILED',body.get('reason')
        assert body['native_fact_count']>0 and body['sources'] and body['operating_assumptions']
        assert body['input_fingerprint']==compiled['cold_recompile']['input_fingerprint']
        assert body['valuation_status']=='conditional_research_only'
        assert body['main_valuation_range'] is None and body['main_range_adopted'] is False
        assert body['formal_eligibility'] is False and body['action']=='no_order'
        assert body['current_price'] is None and body['personal_quantity'] is None
        assert body['user_acceptance']=='NOT_CONFIRMED'
        assert len(body['annual_ledgers']['base']['rows'])==10
    assert len(calls)==count+2
    assert snapshot(root)==before


@pytest.mark.parametrize('registered_empty',[False,True])
def test_public_missing_registry_or_symbol_read_only(tmp_path,monkeypatch,registered_empty):
    if registered_empty:
        put(tmp_path,view.REGISTRY,dict(schema_version=view.SCHEMA,action='no_order',cases={}))
    client,_=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    before=snapshot(tmp_path)
    response=client.get(ROUTE+'000333')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['status']=='NOT_STARTED'
    assert response.json()['reason']=='FIRST_INPUT_NOT_REGISTERED'
    assert snapshot(tmp_path)==before
    assert client.get(ROUTE+'bad').status_code==422


@pytest.mark.parametrize('damage',['json','schema','action','cases','entry','hash','missing_receipt','path'])
def test_invalid_registry_fails_closed_without_replay_or_write(tmp_path,monkeypatch,damage):
    receipt=put(tmp_path,'runtime/TEST_ONLY-receipt.json',dict(symbol='600887',action='no_order'))
    registry=dict(schema_version=view.SCHEMA,action='no_order',cases={'600887':dict(receipt=receipt)})
    if damage=='schema': registry['schema_version']='TEST_ONLY-invalid'
    if damage=='action': registry['action']='order'
    if damage=='cases': registry['cases']=[]
    if damage=='entry': registry['cases']['600887']['unexpected']=True
    if damage=='hash': receipt['sha256']='0'*64
    if damage=='missing_receipt': (tmp_path/receipt['path']).unlink()
    if damage=='path': receipt['path']='../TEST_ONLY-escape.json'
    put(tmp_path,view.REGISTRY,registry)
    if damage=='json': (tmp_path/view.REGISTRY).write_bytes(b'{TEST_ONLY broken')
    def forbidden(**kwargs):
        raise AssertionError('Invalid registry must not cold replay')
    monkeypatch.setattr(view,'replay_first_research_input',forbidden)
    client,_=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    before=snapshot(tmp_path)
    response=client.get(ROUTE+'600887')
    assert response.status_code==200,response.text
    body=response.json()
    assert body['status']=='UNASSESSABLE' and body['reason']
    assert body['formal_eligibility'] is False and body['main_valuation_range'] is None
    assert snapshot(tmp_path)==before


@pytest.mark.parametrize('damage',['source','issuer','formal'])
def test_reader_rejects_tampered_source_issuer_and_adoption(registered,monkeypatch,damage):
    root,compiled,_=registered
    if damage=='source':
        receipt=json.loads((root/compiled['receipt_binding']['path']).read_bytes())
        target=root/receipt['source_bindings'][0]['path']
        target.write_bytes(b'TEST_ONLY tampered consumed source')
    else:
        original=view.replay_first_research_input
        def altered(**kwargs):
            result=deepcopy(original(**kwargs))
            if damage=='issuer': result['research_case']['symbol']='000333'
            else: result['formal_eligibility']=True
            return result
        monkeypatch.setattr(view,'replay_first_research_input',altered)
    before=snapshot(root)
    result=view.read_first_research_input(root=root,symbol='600887',now=NOW)
    assert result['status']=='UNASSESSABLE' and result['reason']
    assert not result['formal_eligibility'] and result['main_valuation_range'] is None
    assert snapshot(root)==before

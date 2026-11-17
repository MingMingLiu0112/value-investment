"""Read-only presentation of explicit, source-bound no-model research."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from test_research_only_mode import sample, put, NOW
from value_investment_agent.application.product.research_draft import load_current_research_draft
from value_investment_agent.m1_valuation_package_builder import build_descriptor


DRAFT = 'artifacts/current/TEST_ONLY-research-only/draft.json'


def bind(root, package, *, package_path='runtime/package.json', preserve_package_bytes=False):
    if preserve_package_bytes:
        assert json.loads((root/package_path).read_bytes()) == package
        digest=hashlib.sha256((root/package_path).read_bytes()).hexdigest()
    else:
        digest = put(root/package_path, package)
    descriptor = build_descriptor(package, root=root)
    envelope = dict(schema_version='public-research-only-draft-v1', research_mode='research_only_v1',
        symbol=package['symbol'], status='RESEARCH_DRAFT_NOT_APPROVED', action='no_order',
        research_as_of=descriptor.point_in_time.research_as_of.isoformat(),
        available_at=descriptor.point_in_time.available_at.isoformat(),
        research_input_binding=dict(package=dict(path=package_path, sha256=digest), input_sha256=descriptor.input_sha256))
    publish(root, envelope)
    return envelope


def publish(root, envelope):
    digest=put(root/DRAFT, envelope)
    put(root/'config/current-research-drafts.json',dict(schema_version='current-research-drafts-v1',
        action='no_order', drafts={envelope['symbol']:dict(path=DRAFT,sha256=digest)},
        economic_comparisons={'TEST_ONLY':'Independent optional field; not a draft'}))


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_native_read_replay_is_pure_and_preserves_unknown_not_no_trade(sample):
    root, package=sample
    bind(root, package)
    before=inventory(root)
    result=load_current_research_draft(root,'000544',now=NOW)
    assert result is not None
    assert result['native_status']=='UNSUPPORTED' and result['assessment_status']=='UNASSESSABLE'
    assert result['observations'][0]['value']=='-1.00'
    assert result['observations_verified'] is False and result['confidence']=='LOW'
    for key in ('valuation','quote_fact','model_validity','price_bridge','gates'):
        assert result[key] is None
    assert result['input_verification']['economic_approval'] is False
    assert result['input_verification']['source_contract_status']=='SOURCE_CUTOFF_VALIDATED_NO_SCENARIOS_OR_FACT_ADMISSION'
    assert inventory(root)==before
    assert load_current_research_draft(root,'000544',now=NOW)==result


def test_generic_command_labels_source_only_without_scenario_claim(sample):
    from test_research_only_mode import scope
    from value_investment_agent.application.product.company_research import run_company_research_for_symbol
    root,package=sample
    put(root/'runtime/package.json',package)
    before=inventory(root)
    result=run_company_research_for_symbol(root=root,symbol='000544',
        package_path=root/'runtime/package.json',schedule_request=scope())['result']
    assert result['source_verification']['source_contract_status']=='SOURCE_CUTOFF_VALIDATED_NO_SCENARIOS_OR_FACT_ADMISSION'
    assert result['valuation'] is result['price_bridge'] is None
    assert inventory(root)==before


def test_case_subset_and_fact_sources_are_merged_without_duplicate_ids(sample):
    from value_investment_agent.application.product.source_bound_inputs import source_catalog_sha256
    root,package=sample
    extra=deepcopy(package['sources'][0])
    extra['id']='TEST_ONLY_second_official'
    package['sources'].append(extra)
    package['source_contract']['source_catalog']=deepcopy(package['sources'])
    package['source_contract']['source_catalog_sha256']=source_catalog_sha256(package['sources'])
    # A Case may cite a subset while typed observations cite all admitted-to-
    # research originals. Compatible locator detail must survive deduplication.
    package['research_case']['evidence_refs']=[dict(package['research_case']['evidence_refs'][0],page=1)]
    package['facts']['evidence_refs'].append(dict(package['facts']['evidence_refs'][0],id=extra['id']))
    package['facts']['observations'].append(dict(field_name='TEST_ONLY_second_cash',value='3.00',
        period_label='2026-06-30',unit='CNY',evidence_refs=[extra['id']]))
    bind(root,package)
    result=load_current_research_draft(root,'000544',now=NOW)
    assert result is not None
    sources={row['id']:row for row in result['evidence']}
    assert len(sources)==len(result['evidence'])==2
    assert sources['TEST_ONLY_official']['page']==1
    assert all(ref in sources for row in result['observations'] for ref in row['evidence_refs'])
    assert sources[extra['id']]['sha256']==extra['sha256']
    assert sources[extra['id']]['url']==extra['location']


def test_same_evidence_id_with_conflicting_locator_is_rejected(sample):
    root,package=sample
    package['research_case']['evidence_refs']=[dict(package['research_case']['evidence_refs'][0],page=1)]
    package['facts']['evidence_refs']=[dict(package['facts']['evidence_refs'][0],page=2)]
    bind(root,package)
    assert load_current_research_draft(root,'000544',now=NOW) is None


@pytest.mark.parametrize('mutation',['mode','schema','symbol','valuation','quote_fact','quantity',
    'approval','display','input_hash','package_hash','escape','future','research_day'])
def test_envelope_cannot_promote_research_or_inject_display(sample,mutation):
    root, package=sample
    draft=bind(root, package)
    if mutation=='mode':draft['research_mode']='research_only_v999'
    elif mutation=='schema':draft['schema_version']='public-research-only-draft-v999'
    elif mutation=='symbol':draft['symbol']='600519'
    elif mutation=='valuation':draft['valuation']={'status':'READY'}
    elif mutation=='quote_fact':draft['quote_fact']={'current_price':'10'}
    elif mutation=='quantity':draft['quantity']=100
    elif mutation=='approval':draft['economic_approval']=True
    elif mutation=='display':draft['observations']=[dict(value='999')]
    elif mutation=='input_hash':draft['research_input_binding']['input_sha256']='0'*64
    elif mutation=='package_hash':draft['research_input_binding']['package']['sha256']='0'*64
    elif mutation=='escape':draft['research_input_binding']['package']['path']='../outside.json'
    elif mutation=='future':draft['available_at']=(NOW+timedelta(days=1)).isoformat()
    elif mutation=='research_day':draft['research_as_of']='2026-10-23'
    publish(root,draft)
    assert load_current_research_draft(root,'000544',now=NOW) is None


@pytest.mark.parametrize('mutation',['raw','package','future_pit','catalog','wrong_issuer','mode'])
def test_bound_input_is_reverified_even_after_resealing_envelope(sample,mutation):
    root,package=sample
    draft=bind(root,package)
    if mutation=='raw':(root/'runtime/TEST_ONLY.pdf').write_bytes(b'TEST_ONLY changed')
    else:
        if mutation=='package':package['facts']['observations'][0]['value']='2.0'
        elif mutation=='future_pit':package['point_in_time']['available_at']='2099-01-01T00:00:00+00:00'
        elif mutation=='catalog':package['source_contract']['source_catalog_sha256']='0'*64
        elif mutation=='wrong_issuer':package['sources'][0]['issuer_identity']['security_code']='600519'
        elif mutation=='mode':package['research_mode']='valuation'
        draft['research_input_binding']['package']['sha256']=put(root/'runtime/package.json',package)
        publish(root,draft)
    assert load_current_research_draft(root,'000544',now=NOW) is None


@pytest.mark.parametrize('mutation',['raw','package','draft','pointer'])
def test_final_source_and_pointer_closure_after_native_replay(sample,monkeypatch,mutation):
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    root,package=sample
    bind(root,package)
    original=InMemoryResearchArtifactRepository.save_object
    changed=False
    def save(self,*args,**kwargs):
        nonlocal changed
        result=original(self,*args,**kwargs)
        if not changed:
            changed=True
            target={'raw':'runtime/TEST_ONLY.pdf','package':'runtime/package.json',
                    'draft':DRAFT,'pointer':'config/current-research-drafts.json'}[mutation]
            path=root/target
            path.write_bytes(path.read_bytes()+b' ')
        return result
    monkeypatch.setattr(InMemoryResearchArtifactRepository,'save_object',save)
    assert load_current_research_draft(root,'000544',now=NOW) is None


def test_real_000544_existing_http_read_without_registry_or_artifact_writes(tmp_path,monkeypatch):
    """Real official bytes; isolated test publication shell is explicitly TEST_ONLY."""
    root_name=os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    package_name=os.environ.get('RESEARCH_ONLY_REAL_PACKAGE')
    expected=os.environ.get('RESEARCH_ONLY_REAL_PACKAGE_SHA256')
    if not(root_name and package_name and expected):
        pytest.skip('Explicit public package/hash opt-in required')
    real=Path(root_name).resolve()
    path=real/package_name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
    package=json.loads(path.read_bytes())
    original={row['local_path']:hashlib.sha256((real/row['local_path']).read_bytes()).hexdigest()
              for row in package['sources']}
    for relative,sha in original.items():
        target=tmp_path/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(real/relative,target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==sha
    # Existing TestClient constructor writes only its TEST_ONLY public snapshot
    # shell. Neither real current pointers nor actual publication are touched.
    import sys
    sys.path.insert(0,str(Path(__file__).parent/'web_api'))
    from test_read_api import _fixture
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateStoreUnavailable
    def no_private(**kwargs):
        raise PrivateStoreUnavailable('TEST_ONLY no private account access')
    monkeypatch.setattr(private_routes,'resolve_private_root',no_private)
    client=_fixture(tmp_path,snapshot_overrides={'opportunities':[dict(symbol='000544',
        company_name='中原环保',action='no_order',valuation_status={'code':'NOT_READY'},why_now='TEST_ONLY snapshot shell')]})
    before=client.get('/api/v1/decisions/000544').json()
    package_copy=tmp_path/package_name
    package_copy.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,package_copy)
    assert hashlib.sha256(package_copy.read_bytes()).hexdigest()==expected
    envelope=bind(tmp_path,package,package_path=package_name,preserve_package_bytes=True)
    files=inventory(tmp_path)
    response=client.get('/api/v1/decisions/000544')
    assert response.status_code==200
    after=response.json()
    assert after['decision']==before['decision']
    # The existing preview shell stamps the read clock, not a new publication.
    assert {k:v for k,v in after['publication'].items() if k!='generated_at'} == {
        k:v for k,v in before['publication'].items() if k!='generated_at'}
    draft=after['research_draft']
    assert draft['assessment_status']=='UNASSESSABLE' and len(draft['observations'])==10
    assert draft['research_input_binding']['package']['sha256']==expected
    assert draft['quote_fact'] is draft['valuation'] is None
    assert any('RESTATED_H1' in b for b in draft['blockers'])
    assert len(draft['research_topics'])==5
    assert inventory(tmp_path)==files
    assert {relative:hashlib.sha256((real/relative).read_bytes()).hexdigest() for relative in original}==original
    destination=os.environ.get('RESEARCH_ONLY_DRAFT_HTTP_OUTPUT')
    if destination:
        output=Path(destination).resolve()
        assert output.is_relative_to(real/'.tmp') and not output.exists()
        result_hash=put(output,after)
        put(output.parent/'receipt.json',dict(
            schema_version='research-only-draft-http-preview-v1',status='PASS',
            scope='ACTUAL_PUBLIC_REFERENCES_LOCAL_TESTCLIENT_NOT_LIVE_8001',
            result_sha256=result_hash,result_path=output.relative_to(real).as_posix(),
            isolated_project_root=str(tmp_path),candidate_binding=envelope['research_input_binding'],
            source_sha256_before=original,source_sha256_after=original,
            formal_decision_unchanged=True,publication_identity_unchanged=True,
            get_wrote_files=False,current_pointer_modified=False,
            simulated_snapshot_shell=True,assessment_status='UNASSESSABLE',action='no_order'))
    client.close()

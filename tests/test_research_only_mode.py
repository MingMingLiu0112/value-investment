"""Explicit no-model research through native descriptor/runner/codecs, no approval."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.product.company_research import run_company_research_for_symbol
from value_investment_agent.application.product.source_bound_inputs import source_catalog_sha256
from value_investment_agent.domain.research.research_only_facts import (
    ResearchOnlyFacts, RESEARCH_ONLY_MODE, UNASSIGNED_PROFILE, NO_MODEL, NO_MODEL_VERSION, SOURCE_SCHEMA,
)
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import (
    build_research_run_spec, descriptor_from_payload, facts_to_payload, facts_from_payload,
)
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_codecs import decode_artifact
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_profile import PROFILES

NOW = datetime(2026,10,24,tzinfo=timezone.utc)


def put(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def sample(tmp_path):
    raw=tmp_path/'runtime/TEST_ONLY.pdf'
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'TEST_ONLY official-source transport fixture, not real financial data')
    sha=hashlib.sha256(raw.read_bytes()).hexdigest()
    source=dict(id='TEST_ONLY_official',kind='official_issuer_filing',
        location='https://static.cninfo.com.cn/TEST_ONLY.pdf',local_path='runtime/TEST_ONLY.pdf',sha256=sha,
        published_at='2026-08-01T00:00:00+00:00',retrieved_at=NOW.isoformat(),
        parser_version='TEST_ONLY',source_available_at=NOW.isoformat(),availability_basis='TEST_ONLY_ACTUAL_LOCAL_CLOCK',
        report_period='2026-06-30',
        issuer_identity=dict(venue='CNINFO',security_code='000544',issuer_name='TEST_ONLY',organization_id=None))
    ref=dict(id=source['id'],path=source['local_path'],sha256=sha,source_url=source['location'])
    case=dict(symbol='000544',name='TEST_ONLY environmental research',as_of='2026-10-24',
        run_id='TEST_ONLY-no-model',generated_at=NOW.isoformat(),research_version='TEST_ONLY-v1',
        industry='TEST_ONLY',investment_path='research only; no model assigned',
        thesis='TEST_ONLY investigate cash conversion',return_driver='TEST_ONLY not established',
        mispricing_hypothesis='TEST_ONLY not established',financial_summary={},positives=[],
        counter_evidence=[],thesis_breakers=[],next_events=[],evidence_status='partial',
        valuation_status='not_ready',research_status='incomplete',blockers=['BUSINESS_RESEARCH_REQUIRED'],
        evidence_refs=[ref],quote_date=None,financial_period='2026-06-30',
        missing_date_reasons=dict(quote_date='No verified quote supplied'))
    package=dict(schema_version='m1-valuation-package-v2',research_mode=RESEARCH_ONLY_MODE,
        descriptor_version='TEST_ONLY-research-v1',symbol='000544',name=case['name'],
        profile_id=UNASSIGNED_PROFILE,requested_model=None,run_id=case['run_id'],research_case=case,
        point_in_time=dict(report_period='2026-06-30',research_as_of='2026-10-24',valuation_date='2026-06-30',
            available_at=NOW.isoformat(),computed_at=NOW.isoformat()),
        dependencies=dict(rule_version='TEST_ONLY-research',model_id=NO_MODEL,model_version=NO_MODEL_VERSION),
        sources=[source],source_contract=dict(schema_version=SOURCE_SCHEMA,cutoff_at=NOW.isoformat(),
            source_catalog=[source],source_catalog_sha256=source_catalog_sha256([source])),
        facts=dict(kind='research_only',symbol='000544',as_of='2026-06-30',verified=False,confidence='LOW',
            scenario_inputs=None,blockers=['MODEL_APPLICABILITY_UNASSESSED'],evidence_refs=[ref],
            observations=[dict(field_name='TEST_ONLY_cash',value='-1.00',unit='CNY',
                period_label='2026-06-30',evidence_refs=[ref['id']])]))
    put(tmp_path/'config/research-evidence-stop-ledger-v1.json',dict(schema_version='research-evidence-stop-ledger-v1',stops=[]))
    return tmp_path,package


def scope():
    return dict(schema_version='research-schedule-request-v1',symbol='000544',source_id='CNINFO',
        period='FY2025-H12026',research_question_id='TEST_ONLY-applicability',blocker_id='new-case',
        new_evidence_ids=[],reopen_condition_met=False)


def test_explicit_mode_runs_native_repository_and_codecs_without_router(sample):
    root,package=sample
    descriptor=build_descriptor(package,root=root)
    assert descriptor_from_payload(descriptor.as_policy()).as_policy()==descriptor.as_policy()
    assert len(PROFILES)==3 and UNASSIGNED_PROFILE not in PROFILES
    facts=descriptor.facts
    copy=facts.observations
    copy[0]['value']='999'
    assert facts.observations[0]['value']=='-1.00'
    assert facts_from_payload(facts_to_payload(facts))==facts
    class NoModelRouter:
        def route(self,*args):raise AssertionError('Research-only called valuation router')
    service=ResearchApplicationService(InMemoryResearchArtifactRepository(),router=NoModelRouter(),now_utc=lambda:NOW)
    outcome=service.run_company_research(build_research_run_spec(descriptor))
    assert outcome.status=='UNSUPPORTED'
    assert outcome.stored_artifacts and len(outcome.stored_artifacts)==2
    for field in ('valuation','model_validity','price_bridge','decision_recommendation','quote_snapshot',
                  'gate','assumptions','distribution_result','pre_decision_eligibility','current_status'):
        assert getattr(outcome,field) is None
    for stored in outcome.stored_artifacts:
        restored=decode_artifact(stored.envelope.identity.artifact_type,stored.envelope.payload_object())
        assert restored.symbol=='000544'


def test_actual_common_entry_completes_and_retains_no_valuation(sample):
    root,package=sample
    path=root/'runtime/package.json';put(path,package)
    before=(root/'config/research-evidence-stop-ledger-v1.json').read_bytes()
    result=run_company_research_for_symbol(root=root,symbol='000544',package_path=path,
        schedule_request=scope(),output_path=root/'runtime/result.json')
    assert result['result']['status']=='UNSUPPORTED'
    assert result['result']['valuation'] is result['result']['price_bridge'] is None
    assert result['result']['decision_recommendation'] is None
    assert result['result']['source_verification']['status']=='LOCAL_BYTES_VERIFIED'
    assert result['result']['action']=='no_order'
    assert (root/'config/research-evidence-stop-ledger-v1.json').read_bytes()==before


@pytest.mark.parametrize('change', ['mode_missing','mode_unknown','profile','schema','model','verified',
    'confidence','scenarios','quote','approval','source_hash','catalog_hash','foreign_symbol',
    'future_source','future_case','evidence_hash','evidence_path','evidence_url','future_observation',
    'wrong_observation_period','future_report','future_publication_date','missing_contract'])
def test_research_only_is_not_fallback_or_admission_bypass(sample,change):
    root,p=sample;p=deepcopy(p)
    if change=='mode_missing':p.pop('research_mode')
    elif change=='mode_unknown':p['research_mode']='research_only_v999'
    elif change=='profile':p['profile_id']='mature_manufacturing'
    elif change=='schema':p['schema_version']='m1-valuation-package-v999'
    elif change=='model':p['requested_model']='fcff'
    elif change=='verified':p['facts']['verified']=True
    elif change=='confidence':p['facts']['confidence']='HIGH'
    elif change=='scenarios':p['facts']['scenario_inputs']={}
    elif change=='quote':p['quote']={}
    elif change=='approval':p['human_research_approval']={}
    elif change=='source_hash':p['sources'][0]['sha256']='0'*64
    elif change=='catalog_hash':p['source_contract']['source_catalog_sha256']='0'*64
    elif change=='foreign_symbol':p['sources'][0]['issuer_identity']['security_code']='600519'
    elif change=='future_source':p['sources'][0]['source_available_at']=(NOW+timedelta(days=1)).isoformat()
    elif change=='future_case':p['research_case']['generated_at']=(NOW+timedelta(days=1)).isoformat()
    elif change=='evidence_hash':p['facts']['evidence_refs'][0]['sha256']='0'*64
    elif change=='evidence_path':p['research_case']['evidence_refs'][0]['path']='runtime/OTHER.pdf'
    elif change=='evidence_url':p['research_case']['evidence_refs'][0]['source_url']='https://example.org/OTHER.pdf'
    elif change=='future_observation':p['facts']['observations'][0]['period_label']='2027-06-30'
    elif change=='wrong_observation_period':p['facts']['observations'][0]['period_label']='2025-12-31'
    elif change=='future_report':p['sources'][0]['report_period']='2027-06-30'
    elif change=='future_publication_date':p['sources'][0]['published_date']='2099-01-01'
    elif change=='missing_contract':p.pop('source_contract')
    if change not in ['catalog_hash','missing_contract']:
        # Reseal the catalog deliberately: identity/time/evidence gates must
        # still reject an internally coherent but semantically invalid input.
        p['source_contract']['source_catalog']=deepcopy(p['sources'])
        p['source_contract']['source_catalog_sha256']=source_catalog_sha256(p['sources'])
    with pytest.raises((ValueError,TypeError,FileNotFoundError)):
        build_descriptor(p,root=root)


def test_direct_spec_cannot_restore_market_or_approval(sample):
    root,p=sample
    spec=build_research_run_spec(build_descriptor(p,root=root))
    for changes in (dict(research_mode='valuation'),dict(profile_id='quality_compounder'),
                    dict(requested_model='fcff'),dict(model_version='fcff-v1'),dict(quote={}),
                    dict(human_research_approval={}),dict(entry_thesis={})): 
        with pytest.raises((ValueError,TypeError)):
            replace(spec,**changes)


def test_real_file_drift_after_repository_save_is_rejected_by_native_runner(sample,monkeypatch):
    root,p=sample;path=root/'runtime/package.json';put(path,p)
    original=InMemoryResearchArtifactRepository.save_object
    def drift(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        (root/'runtime/TEST_ONLY.pdf').write_bytes(b'TEST_ONLY altered after consumption')
        return result
    monkeypatch.setattr(InMemoryResearchArtifactRepository,'save_object',drift)
    with pytest.raises(ValueError,match='source-bound package source changed'):
        run_company_research_for_symbol(root=root,symbol='000544',package_path=path,schedule_request=scope())


def test_direct_spec_rejects_duplicate_sources_and_future_output(sample):
    root,p=sample;spec=build_research_run_spec(build_descriptor(p,root=root))
    with pytest.raises(ValueError,match='identities differ'):
        replace(spec,input_sources=spec.input_sources*2)
    service=ResearchApplicationService(now_utc=lambda:NOW-timedelta(seconds=1))
    with pytest.raises(ValueError,match='current clock'):
        service.run_company_research(spec)


def test_observation_fact_codec_cannot_promote_verified_or_scenario(sample):
    root,p=sample;facts=build_descriptor(p,root=root).facts
    for key,value in [('verified',True),('confidence','HIGH'),('scenario_inputs',{}),('operating_inputs',{})]:
        payload=facts_to_payload(facts);payload[key]=value
        with pytest.raises(ValueError):facts_from_payload(payload)


def test_real_000544_entry_source_closure_and_old_rejected_input():
    root_name=os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    package_name=os.environ.get('RESEARCH_ONLY_REAL_PACKAGE')
    package_sha=os.environ.get('RESEARCH_ONLY_REAL_PACKAGE_SHA256')
    if not (root_name and package_name and package_sha):
        pytest.skip('Explicit actual public package and hash required; no source discovery')
    root=Path(root_name).resolve();path=root/package_name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==package_sha
    p=json.loads(path.read_bytes());assert p['symbol']=='000544'
    before={s['local_path']:hashlib.sha256((root/s['local_path']).read_bytes()).hexdigest() for s in p['sources']}
    descriptor=build_descriptor(p,root=root)
    result=run_company_research_for_symbol(root=root,symbol='000544',package_path=path,
        schedule_request=json.loads((path.parent/'scope.json').read_bytes()))['result']
    assert result['status']=='UNSUPPORTED' and result['valuation'] is result['price_bridge'] is None
    assert result['decision_recommendation'] is None and result['action']=='no_order'
    restored={}
    for row in result['artifact_bundle']['artifacts']:
        assert hashlib.sha256(row['canonical_payload'].encode('utf-8')).hexdigest()==row['payload_sha256']
        kind=row['identity']['artifact_type']
        restored[kind]=decode_artifact(kind,json.loads(row['canonical_payload']))
    assert len(restored['financial_facts'].observations)==10
    assert restored['financial_facts'].verified is False
    assert restored['research_case'].quote_date is None
    assert descriptor_from_payload(descriptor.as_policy()).input_sha256==descriptor.input_sha256
    assert {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in before}==before
    old=json.loads((path.parent.parent/'research-only-entry-input.json').read_bytes())
    with pytest.raises(ValueError,match='Unknown valuation facts kind: research_only'):
        build_descriptor(old,root=root)

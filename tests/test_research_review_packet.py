"""Consumed synthetic contracts, not issuer or investment acceptance."""
import json
from pathlib import Path
import pytest
from test_current_decision_surface import decision_workbench
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.application.product.research_review_packet import build_research_review_packet
from value_investment_agent.application.product.company_research import _serialize_outcome
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_artifact_codecs import artifact_payload


def inputs(root):
    work = decision_workbench()
    objects = verify_current_decision_workbench(work).dependency_objects
    facts = artifact_payload(objects['financial_facts'])[1]
    facts['kind'] = facts['facts_type']
    case = artifact_payload(objects['research_case'])[1]
    folder = root / 'runtime'
    folder.mkdir()
    original = folder / 'original.md'
    original.write_text('synthetic original', encoding='utf-8')
    reference = dict(id='facts', path='runtime/original.md', sha256=sha256_file(original))
    facts['evidence_refs'] = [reference]
    package = dict(schema_version='m1-valuation-package-v1', symbol=work['symbol'],
        descriptor_version='synthetic-review-v1', name=case['name'],
        profile_id='quality_compounder', run_id='synthetic-review',
        point_in_time=dict(report_period=case['as_of'], research_as_of=case['as_of'],
            valuation_date=facts['as_of'], available_at='2026-09-22T10:00:00+00:00',
            computed_at='2026-09-22T11:00:00+00:00'),
        dependencies=dict(rule_version='synthetic-v1', model_id='residual_income_or_equity_value',
            model_version='residual-income-equity-shared-v1'),
        research_case=case, facts=facts,
        sources=[dict(id='facts', kind='official_issuer_filing',
            location='https://static.cninfo.com.cn/synthetic.pdf', local_path='runtime/original.md',
            sha256=reference['sha256'], published_at='2026-09-21T00:00:00+08:00')],
        assumptions=dict(evidence_refs=[reference], assumptions=[dict(name='cost_of_equity',
            unit='decimal', bear='0.10', base='0.10', bull='0.10', basis='synthetic basis',
            rationale='synthetic countercase', confidence='low', sensitivity='high',
            evidence_refs=[reference])]),
        assumption_bindings=[dict(assumption_name='cost_of_equity', scenario=scenario,
            field_path='cost_of_equity', expected_value='0.10', evidence_refs=[reference])
            for scenario in ('bear', 'base', 'bull')],
        source_contract=dict(fact_anchors=[dict(source_id='facts', physical_page=1)]))
    wp, pp = folder/'workbench.json', folder/'package.json'
    pp.write_text(json.dumps(package), encoding='utf-8')
    descriptor = build_descriptor(package, root=root)
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(
        build_research_run_spec(descriptor))
    work = _serialize_outcome(outcome)
    work.update(schema_version='product-current-workbench-request-v1',
        generated_at='2026-09-22T12:00:00+00:00', research_status=outcome.status,
        portfolio_input_status='BLOCKED_PRIVATE_INPUT', position_guidance=None,
        input_descriptor_sha256=descriptor.input_sha256,
        research_receipt=dict(command='company_research', symbol=work['symbol'], action='no_order',
            input_sha256=dict(valuation_package=sha256_file(pp))))
    wp.write_text(json.dumps(work), encoding='utf-8')
    return wp, pp


def run(root, wp, pp):
    return build_research_review_packet(root=root, package_path=pp,
        package_sha256=sha256_file(pp), workbench_path=wp, workbench_sha256=sha256_file(wp),
        output_path=root/'runtime/review.json')


def test_review_consumes_actual_contract_without_granting_approval(tmp_path):
    wp, pp = inputs(tmp_path)
    result=run(tmp_path, wp, pp)
    assert result['approval_changed'] is False
    assert result['position_guidance'] is None and result['action']=='no_order'
    assert result['consumed_operating_inputs']
    consumed = verify_current_decision_workbench(json.loads(wp.read_text())).dependency_objects
    assert result['valuation_status']==artifact_payload(consumed['valuation'])[1]['status']
    assert result['source_bindings'][0]['sha256']==sha256_file(pp)
    assert result['input_descriptor_sha256']==json.loads(wp.read_text())['input_descriptor_sha256']
    assert result['assumptions'][0]['consumption_bindings']
    with pytest.raises(FileExistsError): run(tmp_path, wp, pp)


def test_review_rejects_other_model_inputs_despite_matching_symbol(tmp_path):
    wp, pp = inputs(tmp_path)
    package=json.loads(pp.read_text(encoding='utf-8'))
    package['facts']['operating_inputs']['ordinary_shares']='999'
    pp.write_text(json.dumps(package),encoding='utf-8')
    with pytest.raises(ValueError,match='differs from consumed'): run(tmp_path,wp,pp)
    assert not (tmp_path/'runtime/review.json').exists()


def test_review_source_drift_never_creates_approval_packet(tmp_path):
    wp, pp = inputs(tmp_path)
    (tmp_path/'runtime/original.md').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='source hash mismatch'): run(tmp_path,wp,pp)


@pytest.mark.parametrize('field', ['sources', 'assumption_bindings', 'anchors', 'availability',
    'case', 'facts', 'assumptions'])
def test_same_values_do_not_allow_another_package_version(tmp_path, field):
    wp, pp = inputs(tmp_path)
    package = json.loads(pp.read_text(encoding='utf-8'))
    if field == 'sources':
        package['sources'][0]['location'] = 'https://static.cninfo.com.cn/other.pdf'
    elif field == 'assumption_bindings':
        package['assumption_bindings'][0]['evidence_refs'][0]['id'] = 'other'
    elif field == 'anchors':
        package['source_contract']['fact_anchors'][0]['source_id'] = 'UNBOUND'
    elif field == 'availability':
        package['sources'][0]['source_available_at'] = '2099-01-01T00:00:00+08:00'
    elif field == 'case':
        package['research_case']['thesis'] += ' other explanation'
    elif field == 'facts':
        package['facts']['evidence_refs'][0]['sha256'] = 'f'*64
    else:
        package['assumptions']['assumptions'][0]['rationale'] = 'other rationale'
    pp.write_text(json.dumps(package), encoding='utf-8')
    with pytest.raises(ValueError, match='consumed package binding'):
        run(tmp_path, wp, pp)
    assert not (tmp_path/'runtime/review.json').exists()


@pytest.mark.parametrize('field', ['source', 'binding', 'case', 'facts', 'assumptions'])
def test_receipt_alone_cannot_substitute_consumed_descriptor(tmp_path, field):
    wp, pp = inputs(tmp_path)
    package = json.loads(pp.read_text(encoding='utf-8'))
    if field == 'source':
        package['sources'][0]['location'] = 'https://static.cninfo.com.cn/other.pdf'
    elif field == 'binding':
        package['assumption_bindings'][0]['evidence_refs'][0]['id'] = 'other'
    elif field == 'case':
        package['research_case']['thesis'] += ' other explanation'
    elif field == 'facts':
        package['facts']['confidence'] = 'other'
    else:
        package['assumptions']['assumptions'][0]['rationale'] = 'other rationale'
    pp.write_text(json.dumps(package), encoding='utf-8')
    work = json.loads(wp.read_text(encoding='utf-8'))
    work['research_receipt']['input_sha256']['valuation_package'] = sha256_file(pp)
    wp.write_text(json.dumps(work), encoding='utf-8')
    with pytest.raises(ValueError, match='consumed source/input descriptor'):
        run(tmp_path, wp, pp)
    assert not (tmp_path/'runtime/review.json').exists()


@pytest.mark.parametrize('field', ['research_case', 'financial_facts', 'valuation_assumptions'])
def test_descriptor_claim_cannot_substitute_replayed_objects(tmp_path, field):
    wp, pp = inputs(tmp_path)
    package = json.loads(pp.read_text(encoding='utf-8'))
    if field == 'research_case':
        package['research_case']['thesis'] += ' other explanation'
    elif field == 'financial_facts':
        package['facts']['evidence_refs'][0]['sha256'] = 'f'*64
    else:
        package['assumptions']['assumptions'][0]['rationale'] = 'other rationale'
    pp.write_text(json.dumps(package), encoding='utf-8')
    work = json.loads(wp.read_text(encoding='utf-8'))
    work['research_receipt']['input_sha256']['valuation_package'] = sha256_file(pp)
    work['input_descriptor_sha256'] = build_descriptor(package, root=tmp_path).input_sha256
    wp.write_text(json.dumps(work), encoding='utf-8')
    with pytest.raises(ValueError, match=f'consumed {field}'):
        run(tmp_path, wp, pp)
    assert not (tmp_path/'runtime/review.json').exists()


@pytest.mark.parametrize('binding', ['research_receipt', 'input_descriptor_sha256'])
def test_missing_consumption_binding_fails_closed(tmp_path, binding):
    wp, pp = inputs(tmp_path)
    work = json.loads(wp.read_text(encoding='utf-8'))
    work.pop(binding)
    wp.write_text(json.dumps(work), encoding='utf-8')
    with pytest.raises(ValueError, match='differs from consumed'):
        run(tmp_path, wp, pp)


def test_legacy_facts_type_normalizes_to_the_consumed_descriptor(tmp_path):
    wp, pp = inputs(tmp_path)
    package = json.loads(pp.read_text(encoding='utf-8'))
    package['facts'].pop('kind')
    pp.write_text(json.dumps(package), encoding='utf-8')
    work = json.loads(wp.read_text(encoding='utf-8'))
    work['research_receipt']['input_sha256']['valuation_package'] = sha256_file(pp)
    wp.write_text(json.dumps(work), encoding='utf-8')
    result = run(tmp_path, wp, pp)
    assert result['input_descriptor_sha256'] == work['input_descriptor_sha256']
    assert result['approval_changed'] is False


@pytest.mark.parametrize('symbol', ['600519', '000651', '600741', '600887'])
def test_retained_real_and_legacy_workbenches_keep_exact_consumption(symbol, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    case = json.loads((root/'config/daily-trade-assistant-v1.json').read_text(encoding='utf-8'))['cases'][symbol]
    package = root/case['package']
    workbench = root/'runtime/daily-trade-assistant/20261011-d2-p1-p8-real-v2'/symbol/'workbench.json'
    if not package.is_file() or not workbench.is_file():
        pytest.skip('retained local research evidence is unavailable in this checkout')
    from value_investment_agent.application.product import research_review_packet as service
    captured = []
    monkeypatch.setattr(service, 'write_new_json', lambda path, value: captured.append(value))
    result = build_research_review_packet(root=root, package_path=package,
        package_sha256=case['package_sha256'], workbench_path=workbench,
        workbench_sha256=sha256_file(workbench), output_path=root/'runtime/read-only-review-check.json')
    assert captured == [result]
    assert result['research_admitted'] is False and result['approval_changed'] is False
    assert result['action'] == 'no_order' and result['position_guidance'] is None
    assert result['input_descriptor_sha256'] == json.loads(workbench.read_text(encoding='utf-8'))['input_descriptor_sha256']

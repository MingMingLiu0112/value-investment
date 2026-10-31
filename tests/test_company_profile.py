"""C-only profile qualification; existing research paths are not reclassified as C."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os

import pytest

from test_research_only_mode import sample
from value_investment_agent.application.research import company_profile as mod
from value_investment_agent.application.product.source_bound_inputs import source_catalog_sha256
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.infrastructure.filings import pdf_text
from value_investment_agent.valuation_router import route_profile

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


@pytest.fixture
def package(sample):
    root, payload = sample
    payload['profile_id'] = 'quality_compounder'
    payload['research_case']['financial_summary']['pending_model_limits'] = ['TEST_ONLY capital and funding constraints unresolved']
    return root, payload


@pytest.mark.parametrize('profile,text', [
    ('quality_compounder', '公司主要从事乳品生产与销售，采购原料奶，通过经销与直销渠道销售液态奶。'),
    ('mature_manufacturing', '公司主要从事家用电器生产与销售，采购零部件并制造空调。'),
    ('cyclical_cash_return', '公司主要从事煤炭开采及煤炭销售，价格受供需影响。'),
])
def test_business_family_constrains_existing_templates_without_symbol_routing(package, monkeypatch, profile, text):
    root, payload = package
    payload['profile_id'] = profile
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: ['证券代码：000544 TEST_ONLY\n' + text])
    result = mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)
    assert result['template_candidate'] == profile
    assert result['profile_id'] == profile
    assert text.startswith(result['evidence_refs'][0]['excerpt'])
    assert result['evidence_refs'][0]['physical_page'] == 1
    assert result['economic_evidence'][0]['value']
    assert result['route_qualification']['economic_quality_proven'] is False
    assert result['route_qualification']['approved'] is False
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert route_profile(profile).required_inputs


@pytest.mark.parametrize('damage', ['profile', 'financial', 'ambiguous', 'industry_only', 'hash',
    'identity', 'period', 'future_available', 'no_capital', 'catalog'])
def test_source_negative_cases_fail_closed(package, monkeypatch, damage):
    root, payload = package
    text = '公司主要从事乳品生产与销售，采购原料奶并销售液态奶。'
    if damage == 'profile': payload['profile_id'] = 'mature_manufacturing'
    if damage == 'financial': payload['name'] = payload['research_case']['name'] = 'TEST_ONLY银行'
    if damage == 'ambiguous': text += '公司主要从事煤炭开采及煤炭销售。'
    if damage == 'industry_only': text = '乳品行业及白酒行业估值比较；没有本公司主营披露。'
    if damage == 'hash': (root / payload['sources'][0]['local_path']).write_bytes(b'TEST_ONLY changed')
    if damage == 'identity': payload['sources'][0]['issuer_identity']['security_code'] = '600519'
    if damage == 'period': payload['research_case']['financial_period'] = '2025-12-31'
    if damage == 'future_available': payload['sources'][0]['source_available_at'] = (NOW + timedelta(days=1)).isoformat()
    if damage == 'no_capital': payload['research_case']['financial_summary'] = {}
    payload['source_contract']['source_catalog_sha256'] = source_catalog_sha256(payload['sources'])
    if damage == 'catalog': payload['sources'][0]['location'] += '?drift'
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: ['证券代码：000544 TEST_ONLY\n' + text])
    with pytest.raises(ValueError):
        mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)


def test_today_reconstruction_is_not_historical_public_availability(package, monkeypatch):
    root, payload = package
    payload['sources'][0]['retrieved_at'] = (NOW - timedelta(hours=1)).isoformat()
    payload['source_contract']['source_catalog_sha256'] = source_catalog_sha256(payload['sources'])
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: ['证券代码：000544 TEST_ONLY\n公司主要从事乳品生产与销售。'])
    result = mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)
    assert result['template_candidate'] == 'quality_compounder'
    assert result['route_qualification']['approved'] is False


def test_validator_cannot_recurse_to_analysis_or_route(package, monkeypatch):
    root, payload = package
    def forbidden(*args, **kwargs):
        raise AssertionError('pre-route validation must not call analysis or router')
    monkeypatch.setattr(mod, 'project_value_research_analysis', forbidden)
    monkeypatch.setattr(mod, 'route_profile', forbidden)
    monkeypatch.setattr(mod, 'load_current_pending_candidate_supplement', forbidden)
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: ['证券代码：000544 TEST_ONLY\n公司主要从事乳品生产与销售。'])
    assert mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)['status'] == 'REPORTED_BUSINESS_TEMPLATE_CANDIDATE'


def test_unknown_symbol_has_no_profile_and_does_not_search_or_write(tmp_path):
    result = mod.load_company_profile(root=tmp_path, symbol='600001', now=NOW)
    assert result['status'] == 'UNASSESSABLE'
    assert result['profile'] is result['route'] is result['business_model'] is None
    assert result['action'] == 'no_order' and not result['formal_eligibility']
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('symbol', ['600519', '600887'])
def test_actual_current_sources_to_new_c_consumption_without_writes(symbol):
    location = os.environ.get('VALUE_COMPANY_PROFILE_REAL_ROOT')
    if not location:
        pytest.skip('Explicit retained real-input root required')
    root = Path(location)
    pointer = root / 'config/current-research-drafts.json'
    before = pointer.read_bytes()
    registry = json.loads(before)
    binding = registry['pending_candidates'][symbol]
    package_path = (root / binding['path']).parent / 'package.json'
    package = json.loads(package_path.read_bytes())
    hashes = {s['local_path']:sha256_file(root/s['local_path']) for s in package['sources']
              if s['kind'] == 'official_issuer_filing'}
    result = mod.load_company_profile(root=root, symbol=symbol, now=NOW)
    assert result['status'] == 'SOURCE_BOUND_PROFILE'
    assert result['consumption_status'] == 'C_PROFILE_VALIDATED_AND_EXISTING_ANALYSIS_REPLAYED'
    assert result['profile_validation'] == 'REPORTED_BUSINESS_TEMPLATE_CANDIDATE'
    assert result['reported_business_family'] == 'consumer_products'
    assert result['business_model'] != result['profile']['business_model']
    assert result['economic_evidence'] and result['route']['required_inputs']
    assert result['counter_evidence'] and result['invalidation_conditions']
    assert all(row['page'] > 0 and row['hash'] and row['excerpt'] for row in result['evidence_refs'])
    assert result['route_qualification']['approved'] is False
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert pointer.read_bytes() == before
    assert {path:sha256_file(root/path) for path in hashes} == hashes
    wrong = deepcopy(package)
    wrong['profile_id'] = 'cyclical_cash_return'
    with pytest.raises(ValueError, match='SOURCE_ECONOMIC_PROFILE_MISMATCH'):
        mod.validate_company_profile_for_package(root=root, package=wrong, now=NOW)


def test_raw_report_issuer_cannot_be_relabelled_by_catalog(package, monkeypatch):
    root, payload = package
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k:
        ['证券代码：600519 OTHER_ISSUER 公司主要从事乳品生产与销售。'])
    with pytest.raises(ValueError, match='official cover issuer mismatch'):
        mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)


def test_invalid_current_binding_never_falls_back_to_an_older_candidate(tmp_path, monkeypatch):
    path = tmp_path / 'config/current-research-drafts.json'
    path.parent.mkdir()
    path.write_text(json.dumps(dict(schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={'600519':dict(path='runtime/missing/candidate.json', sha256='a'*64)})), encoding='utf-8')
    def forbidden(**kwargs):
        raise AssertionError('Invalid current research must never fall back')
    monkeypatch.setattr(mod, 'load_current_pending_replay', forbidden)
    with pytest.raises((ValueError, OSError)):
        mod.load_company_profile(root=tmp_path, symbol='600519', now=NOW)


@pytest.mark.parametrize('text', [
    '公司主要业务是商业银行存贷款业务，主要客户包括家用电器制造企业。',
    '公司主要从事服务业务，主要客户包括家用电器生产销售企业。',
    '公司主要从事采购业务，供应商为家用电器生产企业。',
    '公司主要从事非家电业务，不生产家用电器。',
    '公司主要从事煤炭以外的服务，不从事煤炭开采。',
])
def test_customer_supplier_negation_and_financial_business_cannot_support_a_template(package, monkeypatch, text):
    root, payload = package
    payload['profile_id'] = 'mature_manufacturing'
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: ['证券代码：000544 TEST_ONLY\n' + text])
    with pytest.raises(ValueError):
        mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)


def test_cross_page_mixed_own_business_is_not_first_match_wins(package, monkeypatch):
    root, payload = package
    payload['profile_id'] = 'mature_manufacturing'
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: [
        '证券代码：000544 TEST_ONLY 公司主要从事家用电器生产销售。',
        '公司主要从事煤炭开采，收入占比70%。三、核心竞争力分析'])
    with pytest.raises(ValueError, match='AMBIGUOUS'):
        mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)


def test_truncated_business_section_is_unknown_instead_of_a_positive(package, monkeypatch):
    root, payload = package
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: [
        '证券代码：000544 TEST_ONLY 公司主要从事乳品生产销售。'] + ['主营章节继续'] * 40)
    with pytest.raises(ValueError, match='COMPLETENESS_UNKNOWN'):
        mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)


def test_c_validation_fingerprint_binds_source_and_capital_evidence(package, monkeypatch):
    root, payload = package
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k:
        ['证券代码：000544 TEST_ONLY 公司主要从事乳品生产销售。'])
    first = mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)
    payload['research_case']['financial_summary']['pending_model_limits'].append('new TEST_ONLY cash constraint')
    second = mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)
    assert first['validation_sha256'] != second['validation_sha256']
    assert first['implementation_sha256'] == second['implementation_sha256']


def test_unknown_cross_page_own_business_blocks_known_manufacturing(package, monkeypatch):
    root, payload = package
    payload['profile_id'] = 'mature_manufacturing'
    pages = ['证券代码：000544 TEST_ONLY 公司主要从事家用电器生产销售。',
             '公司主要从事房地产开发，房地产贡献70%收入。三、核心竞争力分析']
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: pages)
    recorded = mod._reported_activities(pages)
    assert len(recorded) == 2 and recorded[1][0] == 2
    assert recorded[1][2] == set() and '房地产开发' in recorded[1][1]
    with pytest.raises(ValueError, match='UNSUPPORTED_OWN_BUSINESS_BLOCKS_SINGLE_PROFILE.*page=2:.*房地产'):
        mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)


def test_bank_customers_do_not_make_own_manufacturing_a_financial_business(package, monkeypatch):
    root, payload = package
    payload['profile_id'] = 'mature_manufacturing'
    monkeypatch.setattr(pdf_text, 'extract_pages', lambda *a, **k: [
        '证券代码：000544 TEST_ONLY 公司主要从事家电生产销售，主要客户包括商业银行。'])
    result = mod.validate_company_profile_for_package(root=root, package=payload, now=NOW)
    assert result['reported_business_family'] == 'manufacturing'
    assert result['template_candidate'] == 'mature_manufacturing'
    assert result['route_qualification']['approved'] is False
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'

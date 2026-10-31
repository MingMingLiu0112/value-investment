"""Exact source-only receipts, not ResearchCase/model execution or approval."""
from datetime import datetime, timedelta, timezone
import json
from copy import deepcopy
import tempfile
import os
from pathlib import Path

import pytest

from test_official_report_acquisition import transport, acquire
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research import company_profile_sources_v1 as mod
from value_investment_agent.infrastructure.filings import official_report_acquisition as acquisition


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return dict(path=path, sha256=sha256_file(target))


@pytest.fixture
def registered(tmp_path, transport, monkeypatch):
    packet = acquire(tmp_path)
    binding = dict(path='runtime/new/receipt.json', sha256=sha256_file(tmp_path/'runtime/new/receipt.json'))
    registry = dict(schema_version=mod.REGISTRY_SCHEMA, action='no_order', entries={
        '000544':dict(issuer_name='中原环保', period='2025-12-31', receipt_binding=binding)})
    write(tmp_path, mod.REGISTRY_PATH, registry)
    state = dict(pages=[transport['cover'],
        '公司主要从事家用电器生产与销售，主要客户包括商业银行。公司资本开支与营运资本影响现金流量。三、核心竞争力分析'])
    monkeypatch.setattr(acquisition, 'validate_pdf_original', lambda _: None)
    monkeypatch.setattr(mod, 'extract_pages', lambda *a, **k: list(state['pages']))
    def forbidden(*args, **kwargs):
        raise AssertionError('source-only read must not acquire/download/construct a ResearchCase')
    monkeypatch.setattr(acquisition, 'acquire_official_report', forbidden)
    monkeypatch.setattr(acquisition, 'download_official_pdf', forbidden)
    return tmp_path, registry, state


def load(root, **kwargs):
    return mod.load_source_company_profile(root=root, symbol='000544',
        now=datetime.now(timezone.utc)+timedelta(seconds=1), **kwargs)


@pytest.mark.parametrize('business,profile,model', [
    ('公司主要从事家用电器生产销售。', 'mature_manufacturing', 'fcff'),
    ('公司主要从事煤炭开采和煤炭销售。', 'cyclical_cash_return', 'cyclical_normalized'),
    ('公司主要从事乳品生产销售。', 'quality_compounder', 'residual_income_or_equity_value'),
])
def test_source_receipt_to_existing_route_missing_inputs_and_no_model_execution(registered, monkeypatch, business, profile, model):
    root, _, state = registered
    state['pages'][1] = business + '现金分红依赖偿债资金安排。三、核心竞争力分析'
    before = {p.relative_to(root).as_posix():sha256_file(p) for p in root.rglob('*') if p.is_file()}
    result = load(root)
    assert result['status'] == 'SOURCE_BOUND_ROUTE_ONLY'
    assert result['valuation_status'] == 'VALUATION_INPUTS_PENDING'
    assert result['route']['profile_id'] == profile and result['route']['selected_model'] == model
    assert result['applicability_contract']['version'] == 'c-profile-applicability-v1'
    assert result['missing_inputs'] == result['route']['required_inputs']
    assert all(isinstance(name, str) for name in result['missing_inputs'])
    assert all(row['status'] == 'MISSING' for row in result['input_assessment'])
    assert [row['name'] for row in result['economic_input_assessment']] == result['missing_economic_inputs']
    assert result['missing_economic_inputs'] and result['economic_evidence']
    assert result['evidence_refs'][0]['page'] == 2 and business.rstrip('。') in result['business_model']
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert result['source_verification']['strict_historical_pit'] is False
    assert result['consumption_status'] == 'SOURCE_ONLY_NOT_MODEL_REPLAY'
    assert len(result['input_fingerprint']) == 64
    assert before == {p.relative_to(root).as_posix():sha256_file(p) for p in root.rglob('*') if p.is_file()}


def test_financial_refusal_preserves_official_body_dates_hash_and_reason(registered):
    root, _, state = registered
    state['pages'][1] = '公司主要业务是商业银行存贷款业务，主要客户包括家用电器制造企业。'
    result = load(root)
    assert result['status'] == 'MODEL_NOT_APPLICABLE'
    assert result['route'] is result['profile'] is None
    assert result['classification_reason'] == 'FINANCIAL_MAIN_BUSINESS_REQUIRES_SPECIALIZED_MODEL'
    assert '商业银行' in result['business_model']
    assert result['evidence_refs'][0]['page'] == 2
    assert result['evidence_refs'][0]['hash'] and result['published_date'] and result['available_at']
    assert result['formal_eligibility'] is False
    assert result['refusal_evidence']['pages'] == [2]
    assert '第2页' in result['refusal_conditions'][0]


@pytest.mark.parametrize('body', [
    ['公司主要从事家电生产销售。', '公司主要从事房地产开发，房地产贡献70%收入。'],
    ['公司主要从事家电生产销售。', '公司主要从事煤炭开采销售。'],
    ['公司主要从事服务业务，主要客户包括家用电器制造企业。'],
    ['公司主要从事非家电业务，不生产家用电器。'],
])
def test_unknown_mixed_customer_and_negation_do_not_get_routes(registered, body):
    root, _, state = registered
    state['pages'] = state['pages'][:1] + body
    result = load(root)
    assert result['status'] == 'UNASSESSABLE' and result['route'] is None
    assert result['classification_reason'] == 'UNKNOWN_OR_MIXED_OWN_BUSINESS'
    assert result['evidence_refs']  # rejection keeps the reported source, including negation


def test_truncated_chapter_never_means_complete_company_business(registered):
    root, _, state = registered
    state['pages'] = [state['pages'][0], '公司主要从事家电生产销售。'] + ['继续主营章节']*39
    result = load(root)
    assert result['classification_reason'] == 'BUSINESS_SECTION_COMPLETENESS_UNKNOWN'
    assert result['route'] is None and result['evidence_refs']


@pytest.mark.parametrize('damage', ['registry_hash', 'receipt', 'pdf', 'index', 'issuer', 'period', 'profile_claim'])
def test_exact_source_chain_corruption_never_falls_back(registered, damage):
    root, registry, _ = registered
    entry = registry['entries']['000544']
    explicit = None
    if damage == 'registry_hash':
        explicit = dict(path=mod.REGISTRY_PATH, sha256='a'*64)
    elif damage in {'receipt', 'pdf', 'index'}:
        packet = json.loads((root/entry['receipt_binding']['path']).read_bytes())
        path = entry['receipt_binding']['path'] if damage == 'receipt' else (
            packet['source']['path'] if damage == 'pdf' else packet['index_bindings'][0]['path'])
        (root/path).write_bytes(b'TEST_ONLY tampered')
    else:
        if damage == 'issuer': entry['issuer_name'] = '另一家公司'
        if damage == 'period': entry['period'] = '2026-06-30'
        if damage == 'profile_claim': entry['profile_id'] = 'mature_manufacturing'
        write(root, mod.REGISTRY_PATH, registry)
    with pytest.raises((ValueError, OSError)):
        load(root, registry_binding=explicit)


def test_receipt_available_after_requested_cutoff_is_rejected(registered):
    root, registry, _ = registered
    packet = json.loads((root/registry['entries']['000544']['receipt_binding']['path']).read_bytes())
    with pytest.raises(ValueError, match='cutoff'):
        mod.load_source_company_profile(root=root, symbol='000544',
            now=datetime.fromisoformat(packet['started_at'])-timedelta(seconds=1))


def test_registry_absence_is_not_directory_discovery(tmp_path):
    folder = tmp_path/'runtime/newer-looking'
    folder.mkdir(parents=True)
    (folder/'receipt.json').write_text('{}', encoding='utf-8')
    assert load(tmp_path)['status'] == 'UNASSESSABLE'
    with pytest.raises((ValueError, OSError)):
        load(tmp_path, registry_binding=dict(path='config/missing.json', sha256='a'*64))


def test_explicit_registry_binding_and_refusal_fingerprint_bind_sources(registered):
    root, _, state = registered
    binding = dict(path=mod.REGISTRY_PATH, sha256=sha256_file(root/mod.REGISTRY_PATH))
    result = load(root, registry_binding=binding)
    assert result['source_bindings'][0] == binding
    state['pages'][1] = '公司主要业务是商业银行存贷款。'
    refused = load(root, registry_binding=binding)
    assert result['input_fingerprint'] != refused['input_fingerprint']


@pytest.mark.parametrize('symbol,profile', [('000333','mature_manufacturing'),
    ('601088','cyclical_cash_return'), ('600036',None)])
def test_actual_fixed_source_receipts(symbol, profile):
    location = os.environ.get('VALUE_SOURCE_COMPANY_PROFILE_REAL_ROOT')
    if not location:
        pytest.skip('Explicit fixed source-C registry/root required')
    root = Path(location)
    explicit = json.loads(os.environ['VALUE_SOURCE_COMPANY_PROFILE_REGISTRY_BINDING']) if os.environ.get('VALUE_SOURCE_COMPANY_PROFILE_REGISTRY_BINDING') else None
    pointer = root/(explicit['path'] if explicit else mod.REGISTRY_PATH)
    before = pointer.read_bytes()
    result = mod.load_source_company_profile(root=root, symbol=symbol, now=datetime.now(timezone.utc), registry_binding=explicit)
    assert result['evidence_refs'] and result['available_at'] and result['report_period']
    assert result['classification_method'] == 'FIXED_SOURCE_SECTION_REVIEW_NOT_GENERAL_CLASSIFIER'
    assert result['fixed_section_review_version'] == 'c-fixed-three-section-review-v1'
    assert len(result['reviewed_section_sha256']) == 64
    if profile is None:
        assert result['status'] == 'MODEL_NOT_APPLICABLE' and result['route'] is None
        assert result['profile'] is None and result['classification_reason']
    else:
        assert result['status'] == 'SOURCE_BOUND_ROUTE_ONLY', result['classification_reason']
        assert result['profile']['profile_id'] == profile
        assert result['missing_inputs'] and result['valuation_status'] == 'VALUATION_INPUTS_PENDING'
    assert not result['formal_eligibility'] and result['action'] == 'no_order'
    assert pointer.read_bytes() == before


def test_unverified_financial_pdf_never_becomes_company_refusal_evidence(registered, monkeypatch):
    root, registry, state = registered
    registry['entries']['000544']['issuer_name'] = '未验证金融发行人'
    write(root, mod.REGISTRY_PATH, registry)
    def forbidden(*a, **k):
        raise AssertionError('classification ran before official issuer verification')
    monkeypatch.setattr(mod, 'extract_pages', forbidden)
    with pytest.raises(ValueError):
        load(root)


@pytest.mark.parametrize('damage', ['origin_manifest', 'full_section', 'identity_pages', 'clock', 'period'])
def test_fixed_real_lineage_mutations_rejected_without_changing_originals(damage):
    location = os.environ.get('VALUE_SOURCE_COMPANY_PROFILE_REAL_ROOT')
    if not location:
        pytest.skip('Explicit fixed source-C registry/root required')
    root = Path(location)
    explicit = json.loads(os.environ['VALUE_SOURCE_COMPANY_PROFILE_REGISTRY_BINDING']) if os.environ.get('VALUE_SOURCE_COMPANY_PROFILE_REGISTRY_BINDING') else None
    registry_path = root/(explicit['path'] if explicit else mod.REGISTRY_PATH)
    registry = json.loads(registry_path.read_bytes())
    entry = deepcopy(registry['entries']['000333'])
    packet = json.loads((root/entry['receipt_binding']['path']).read_bytes())
    before = sha256_file(root/packet['source']['path'])
    with tempfile.TemporaryDirectory(dir=root/'.tmp',prefix='csrc-') as folder:
        relative = Path(folder).relative_to(root).as_posix()
        if damage == 'origin_manifest':
            packet['origin']['manifest']['sha256'] = '0'*64
        elif damage == 'full_section':
            section = json.loads((root/entry['main_business_section']['path']).read_bytes())
            section['full_text'] += '公司主要从事房地产开发。'
            entry['main_business_section'] = write(root, relative+'/section.json', section)
        elif damage == 'identity_pages':
            entry['identity_pages'] = [10]
        elif damage == 'period':
            # Keep every declaration consistent while reusing the same real H1 PDF.
            # A generic "else -> interim" title match must not admit January 1.
            entry['period'] = packet['period'] = packet['source']['period'] = '2026-01-01'
            for field in ('main_business_section', 'evidence_pages'):
                metadata = json.loads((root/entry[field]['path']).read_bytes())
                metadata['period'] = entry['period']
                entry[field] = write(root, relative+'/'+field+'.json', metadata)
        else:
            packet['source']['available_at'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        entry['receipt_binding'] = write(root, relative+'/receipt.json', packet)
        binding = write(root, relative+'/registry.json', dict(schema_version=mod.REGISTRY_SCHEMA,
            action='no_order',entries={'000333':entry}))
        with pytest.raises(ValueError):
            mod.load_source_company_profile(root=root,symbol='000333',now=datetime.now(timezone.utc),registry_binding=binding)
    assert sha256_file(root/packet['source']['path']) == before


def test_fixed_section_policy_is_frozen_case_review_not_general_classification():
    assert mod.FIXED_SECTION_REVIEW_VERSION == 'c-fixed-three-section-review-v1'
    assert len(mod.FIXED_SECTION_POLICIES) == 3
    assert {row['family'] for row in mod.FIXED_SECTION_POLICIES.values()} == {
        'manufacturing', 'commodity_operations', 'financial_institution'}
    assert all(len(digest) == 64 for digest in mod.FIXED_SECTION_POLICIES)
    assert all(row['scopes'] and row['limitation'] for row in mod.FIXED_SECTION_POLICIES.values())

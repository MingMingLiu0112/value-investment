"""Product hypotheses: source semantics, native cash replay and existing API."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_source_native_economic_review_v1 import public_js2, snapshot
from value_investment_agent.infrastructure.filings import operating_erosion_sources as sources
from value_investment_agent.application.product import source_native_economic_review_v1 as review
from value_investment_agent.application.research import product_operating_research as research
from value_investment_agent.presentation.web_api.source_native_economic_routes import register_source_native_economic_routes


TABLE = '''贵州茅台酒股份有限公司2026 年半年度报告
3、销售情况
单位：万元 币种：人民币
茅台酒 系列酒 直销 批发代理 国内 国外
报告期主要业务收入
7,772,443.79 1,293,418.65 5,196,204.70 3,869,657.74 8,962,212.26 103,650.18
注：不属于表内金额 4,026,356.42 万元。
4、经销商情况
'''


@pytest.fixture
def product_source(tmp_path, monkeypatch):
    original = tmp_path/'TEST_ONLY-original.pdf'
    original.write_bytes(b'TEST_ONLY layout contract, not an official retained report')
    source = dict(id='cninfo:1225475868', kind='official_issuer_filing',
        issuer_identity=dict(security_code='600519'), local_path=original.name,
        sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        location='https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF')
    pages = ['']*7+[TABLE]
    monkeypatch.setattr(sources, 'extract_pages', lambda *_a, **_kw: pages)
    return tmp_path, source, pages


def test_product_table_reconciles_three_views_and_keeps_other_revenue(product_source):
    root, source, _ = product_source
    result = sources.read_product_revenue_sources(root=root, sources=[source], interim_revenue='90703260964.48')
    assert result['product_revenue_cny'] == dict(moutai='77724437900.00',
        series='12934186500.00', other='44636564.48')
    assert result['physical_page'] == 8
    assert result['ttm_product_revenue_status'] == 'NOT_DISCLOSED_BY_THIS_TABLE'


@pytest.mark.parametrize('damage', ['currency', 'unit', 'owner', 'column', 'channel', 'duplicate', 'hash', 'revenue'])
def test_product_table_cannot_silently_change_scope_or_units(product_source, damage):
    root, source, pages = product_source
    revenue = '90703260964.48'
    if damage == 'currency': pages[7] = TABLE.replace('人民币', '美元')
    if damage == 'unit': pages[7] = TABLE.replace('万元', '元')
    if damage == 'owner': pages[7] = TABLE.replace('贵州茅台酒股份有限公司', '其他公司')
    if damage == 'column': pages[7] = TABLE.replace('茅台酒 系列酒', '系列酒 茅台酒')
    if damage == 'channel': pages[7] = TABLE.replace('5,196,204.70', '5,196,204.71')
    if damage == 'duplicate': pages[7] = TABLE+TABLE
    if damage == 'hash': (root/source['local_path']).write_bytes(b'TEST_ONLY drift')
    if damage == 'revenue': revenue = '1'
    with pytest.raises(ValueError):
        sources.read_product_revenue_sources(root=root, sources=[source], interim_revenue=revenue)


def test_real_product_research_native_cash_ddm_and_existing_api(public_js2):
    root, ref, _ = public_js2
    before = snapshot(root)
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref)
    product = result['product_operating_research']
    assert product['status'] == 'CONDITIONAL_OPERATING_RESEARCH_NOT_APPROVED', product
    assert product['assumption_scope'] == 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'
    assert product['product_source']['product_revenue_cny']['other'] == '44636564.48'
    assert product['normalized_parent_profit_cny'] is None
    assert product['research_admitted'] is product['price_admitted'] is product['formal_eligibility'] is False
    with localcontext() as context:
        context.prec = 48
        shares = D(result['share_basis']['ordinary_shares'])
        for row in product['scenarios']:
            values = row['native_scenario_inputs']
            cost = D(values['cost_of_equity'])
            flows = row['annual_cash_rows']
            explicit = sum((D(c['dividend_paid'])/(1+cost)**c['year'] for c in flows), D(0))
            terminal = D(row['terminal_profit'])/cost/(1+cost)**5
            assert abs(D(row['per_historical_share_cny'])-(explicit+terminal)/shares) < D('1E-30')
            assert D(row['ke_plus_200bp_per_historical_share_cny']) < D(row['per_historical_share_cny'])
            assert all(D(c['parent_retained_profit_close']) >= 0 for c in flows)
        first = product['scenarios'][1]['operating_rows'][0]
        anchor = product['historical_ttm']
        ratio = product['product_source']['product_revenue_cny']
        total = sum(map(D, ratio.values()))
        expected_revenue = D(anchor['operating_revenue'])*(
            D(ratio['moutai'])/total*D('1.01')+D(ratio['series'])/total*D('.95')+D(ratio['other'])/total)
        assert abs(D(first['revenue'])-expected_revenue) < D('1E-30')
        assert D(first['revenue']) != D(anchor['operating_revenue'])
    app = FastAPI()
    register_source_native_economic_routes(app, project=root)
    # The existing registry selects this exact candidate; no new product entry.
    registry = root/'config/user-research-workflow-v1.json'
    registry.parent.mkdir(exist_ok=True)
    registry.write_text(json.dumps(dict(schema_version='user-research-workflow-v1', action='no_order',
        supplemental_review_candidates={'600519':ref})), encoding='utf-8')
    with TestClient(app) as client:
        response = client.get('/api/v1/value-economic-review/600519')
    assert response.status_code == 200, response.text
    assert response.json()['product_operating_research']['scenarios'] == product['scenarios']
    after = snapshot(root)
    assert {k:v for k,v in after.items() if k != registry.relative_to(root).as_posix()} == before


def test_new_assumptions_are_not_backdated_into_old_research(public_js2):
    root, ref, _ = public_js2
    result = review.build_source_native_economic_review(root=root, candidate_binding=ref,
        now=datetime(2026, 10, 24, 23, 59, tzinfo=timezone.utc))
    product = result['product_operating_research']
    assert product['status'] == 'NOT_YET_AVAILABLE' and product['scenarios'] == []


def test_policy_changed_during_calculation_is_rejected(public_js2, monkeypatch):
    root, ref, _ = public_js2
    kernel = research._shared_scenario_calculation
    changed = False
    def changing(*args, **kwargs):
        nonlocal changed
        value = kernel(*args, **kwargs)
        if not changed:
            path = root/research.POLICY_PATH
            path.write_bytes(path.read_bytes()+b'\nTEST_ONLY drift')
            changed = True
        return value
    monkeypatch.setattr(research, '_shared_scenario_calculation', changing)
    with pytest.raises(ValueError, match='changed during research'):
        review.build_source_native_economic_review(root=root, candidate_binding=ref)


def test_real_paths_can_enter_existing_unsigned_candidate_contract(public_js2):
    from value_investment_agent.application.product.source_native_candidate_v2 import verify_source_native_candidate
    root, baseline, _ = public_js2
    before = snapshot(root)
    target = root/'runtime/TEST_ONLY-product-operating-candidate'
    result = research.prepare_product_operating_candidate(root=root, candidate_binding=baseline, output_dir=target)
    ref = result['candidate_binding']
    candidate = verify_source_native_candidate(root=root, path=root/ref['path'], expected_sha256=ref['sha256'])
    assert candidate['research_admitted'] is candidate['primary_registered'] is candidate['price_admitted'] is False
    package = json.loads((root/candidate['source_package_binding']['path']).read_bytes())
    saved = package['research_case']['financial_summary']['product_operating_research']
    assert saved['policy_binding']['path'].endswith('/assumptions.json')
    assert saved['assumption_scope'] == 'RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST'
    assert result['current_registry_changed'] is False
    assert result['formal_eligibility'] is False
    assert {key:research.sha256_file(root/key) for key in before} == before
    assert candidate['candidate_valuation']['base_value'] != json.loads((root/baseline['path']).read_bytes())['candidate_valuation']['base_value']
    with pytest.raises(FileExistsError):
        research.prepare_product_operating_candidate(root=root, candidate_binding=baseline, output_dir=target)

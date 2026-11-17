"""Single-source reported balance arithmetic only; fixtures are TEST_ONLY."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import value_evidence_enrichment_v1 as app
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as parser
from value_investment_agent.financial_quality import _accepted

NOW = datetime(2026,10,25,3,tzinfo=timezone.utc)


def pages():
    return ['TEST_ONLY 测试股份有限公司 股票代码：000498; 2025年年度报告\n'
            '公司的中文名称 测试股份有限公司\n'
            '1、合并资产负债表\n编制单位：测试股份有限公司\n2025年12月31日\n'
            '单位：元\n项目 期末余额 期初余额\n资产总计 100.00 80.00',
            '负债合计 70.00 55.00\n归属于母公司所有者权益合计 20.00 15.00\n'
            '少数股东权益 10.00 10.00\n所有者权益合计 30.00 25.00\n'
            '负债和所有者权益总计 100.00 80.00\n2、母公司资产负债表\n'
            '资产总计 999.00 888.00\n负债合计 666.00 555.00\n所有者权益合计 333.00 333.00',
            '本集团编制本财务报表时所采用的货币为人民币。']


@pytest.fixture
def source(tmp_path,monkeypatch):
    raw = tmp_path/'official.pdf'
    raw.write_bytes(b'TEST_ONLY official boundary, not a real PDF')
    text = pages()
    monkeypatch.setattr(parser,'extract_pages',lambda path,limit: text[:limit])
    source = parser.RetainedAnnualSource('000498','2025-12-31','official.pdf',
        hashlib.sha256(raw.read_bytes()).hexdigest(),'https://static.cninfo.com.cn/TEST_ONLY.pdf',
        '2026-10-25T01:00:00+00:00')
    return source,text


def enrich(root,source,points=None):
    return app.enrich_retained_company(root,source,points or [],evaluation_at=NOW,
        cache_dir=root/'.tmp/official-balance-tests')


def ratio(result):
    return [p for p in result['adopted_points'] if p['field_name']=='debt_ratio']


def test_exact_two_columns_only_admit_derived_ratio(tmp_path,source):
    src,text=source
    result=enrich(tmp_path,src)
    point,=ratio(result)
    assert point['value']=='70.0' and point['unit']=='percent'
    assert _accepted(point)
    assert len(result['adopted_points'])==1
    assert result['before']['coverage_ratio']==Decimal('0.0000')
    assert result['after']['coverage_ratio']==Decimal('0.1111')
    assert result['after']['total_score'] is None
    assert result['after']['calculation_details']['accepted_fields']==['debt_ratio']
    assert result['debt_scope']['value'] is None and not result['debt_scope']['complete_debt_verified']
    assert result['formal_eligibility'] is False and result['action']=='no_order'
    m=point['metadata']
    assert m['automatic_cross_source_verification'] is False
    assert m['single_source_balance_verification'] is True
    assert m['assurance_basis']=='source_reported_only'
    assert m['derivation_rule_pit_status']=='NOT_ADMITTED' and not m['economic_approval']
    proof=m['balance_reconciliation']
    assert Decimal(proof['current_residual'])==Decimal(proof['prior_residual'])==0
    assert proof['equity_basis']=='TOTAL_EQUITY_INCLUDING_NCI_AND_OTHER_EQUITY'
    assert proof['owner_evidence']['legal_name']==proof['owner_evidence']['compiler_name']=='测试股份有限公司'
    assert len({r['table_context_id'] for r in proof['balance_rows']})==1
    assert len(m['input_fact_ids'])==3
    for row in proof['balance_rows']:
        assert row['excerpt'] in text[row['page']-1]
        assert row['issuer']=='测试股份有限公司' and row['prior_value'] is not None
    rebuilt,_=app.consume_retained_enrichment(tmp_path,[point],[asdict(src)],evaluation_at=NOW)
    assert rebuilt==[point]


@pytest.mark.parametrize('fault',['unit','reversed_header','swap_one_row','parent','parent_equity',
    'missing_equity','unbalanced_current','unbalanced_prior','zero_assets','negative_liabilities',
    'issuer','single_equity','extra_column','unknown_currency'])
def test_evidence_or_identity_failure_cannot_admit(tmp_path,source,fault):
    src,text=source
    if fault=='unit': text[0]=text[0].replace('单位：元','单位：美元')
    elif fault=='reversed_header': text[0]=text[0].replace('期末余额 期初余额','期初余额 期末余额')
    elif fault=='swap_one_row': text[1]=text[1].replace('所有者权益合计 30.00 25.00','所有者权益合计 25.00 30.00')
    elif fault=='parent': text[0]=text[0].replace('合并资产负债表','母公司资产负债表')
    elif fault=='parent_equity': text[1]=text[1].replace('所有者权益合计 30.00 25.00','归属于母公司所有者权益合计 30.00 25.00')
    elif fault=='missing_equity': text[1]=text[1].replace('所有者权益合计 30.00 25.00','')
    elif fault=='unbalanced_current': text[1]=text[1].replace('30.00 25.00','31.00 25.00')
    elif fault=='unbalanced_prior': text[1]=text[1].replace('30.00 25.00','30.00 26.00')
    elif fault=='zero_assets': text[0]=text[0].replace('100.00 80.00','0.00 80.00')
    elif fault=='negative_liabilities': text[1]=text[1].replace('70.00 55.00','-70.00 55.00')
    elif fault=='issuer': text[0]=text[0].replace('编制单位：测试股份有限公司','编制单位：其他股份有限公司')
    elif fault=='single_equity': text[1]=text[1].replace('30.00 25.00','30.00')
    elif fault=='extra_column': text[1]=text[1].replace('30.00 25.00','30.00 25.00 20.00')
    elif fault=='unknown_currency': text[-1]='境外子公司以人民币为记账本位币。'
    result=enrich(tmp_path,src)
    assert ratio(result)==[]
    assert result['after']['coverage_ratio']==0


def test_negative_total_equity_is_not_missing_or_zero(tmp_path,source):
    src,text=source
    text[1]=text[1].replace('70.00 55.00','120.00 90.00').replace('30.00 25.00','-20.00 -10.00')
    point,=ratio(enrich(tmp_path,src))
    assert Decimal(point['value'])==120 and _accepted(point)


@pytest.mark.parametrize('field',['total_assets','total_liabilities','total_equity','debt_ratio'])
def test_existing_admitted_conflict_prevents_fallback(tmp_path,source,field):
    src,_=source
    existing=dict(symbol=src.symbol,period_label=src.period,field_name=field,value='1',
        unit='percent' if field=='debt_ratio' else 'CNY',data_point_id='TEST_ONLY-accepted',
        validation_status='verified',created_at=src.available_at,
        metadata=dict(automatic_cross_source_verification=True,statement_scope='consolidated'))
    result=enrich(tmp_path,src,[existing])
    assert ratio(result)==[]
    assert result['balance_ratio_adoption']['status']=='SOURCE_CONFLICT'


@pytest.mark.parametrize('field',['cash','net_income','total_assets','total_equity','interest_bearing_debt'])
def test_label_cannot_release_other_fields(tmp_path,source,field):
    point,=ratio(enrich(tmp_path,source[0]))
    point['field_name']=field
    point['metadata']['automatic_cross_source_verification']=True
    assert not _accepted(point)


@pytest.mark.parametrize('fault',['method','amount','unit','hash','source_missing','future','original'])
def test_cold_consumption_rejects_tampering_or_future_source(tmp_path,source,fault):
    src,_=source
    point,=ratio(enrich(tmp_path,src))
    if fault=='method': point['metadata']['verification_method']='FAKE_METHOD'
    elif fault=='amount': point['value']='1'
    elif fault=='unit': point['unit']='CNY'
    elif fault=='hash': point['sha256']='f'*64
    elif fault=='future': src=replace(src,available_at='2027-01-01T00:00:00+00:00')
    elif fault=='original': (tmp_path/src.path).write_bytes(b'TEST_ONLY tampered original')
    with pytest.raises(ValueError):
        app.consume_retained_enrichment(tmp_path,[point],[] if fault=='source_missing' else [asdict(src)],evaluation_at=NOW)


def test_binding_changes_with_reported_amounts_not_saved_pass(tmp_path,source):
    src,text=source
    first,=ratio(enrich(tmp_path,src))
    text[1]=text[1].replace('70.00 55.00','60.00 55.00').replace('30.00 25.00','40.00 25.00')
    # Same source bytes is intentionally a TEST_ONLY PDF boundary mutation.
    # Clearing only this test's cache forces actual extraction against the fixture.
    with pytest.raises(ValueError,match='differs from original'):
        enrich(tmp_path,src)
    for path in (tmp_path/'.tmp/official-balance-tests').glob('*.json'): path.unlink()
    second,=ratio(enrich(tmp_path,src))
    assert first['data_point_id']!=second['data_point_id']
    assert Decimal(second['value'])==60


@pytest.mark.parametrize('fault',['method','single_flag','cross_flag','proof','scope','quarantine','owner'])
def test_acceptance_requires_exact_method_and_single_source_flags(tmp_path,source,fault):
    point,=ratio(enrich(tmp_path,source[0]))
    m=point['metadata']
    if fault=='method': m['verification_method']='OFFICIAL_BALANCE_RECONCILIATION_V0'
    elif fault=='single_flag': m['single_source_balance_verification']=False
    elif fault=='cross_flag': m['automatic_cross_source_verification']=True
    elif fault=='proof': m['balance_reconciliation']['status']='SAVED_PASS'
    elif fault=='scope': m['statement_scope']='parent'
    elif fault=='quarantine': m['evidence_quarantine']=True
    elif fault=='owner': m['balance_reconciliation'].pop('owner_evidence')
    assert not _accepted(point)


@pytest.mark.parametrize('fault',['subsidiary_balanced','no_legal_name','short_name','conflicting_legal_name',
    'issuer_assets_subsidiary_liabilities','issuer_assets_second_issuer_table'])
def test_table_owner_and_context_cannot_be_borrowed(tmp_path,source,fault):
    src,text=source
    if fault=='subsidiary_balanced':
        # The subsidiary appears on the cover too and has its own exact A=L+E.
        # Neither a cover substring nor arithmetic proves table ownership.
        text[0]=text[0].replace('TEST_ONLY','TEST_ONLY 测试股份有限公司子公司有限公司',1)
        text[0]=text[0].replace('编制单位：测试股份有限公司','编制单位：测试股份有限公司子公司有限公司')
    elif fault=='no_legal_name':
        text[0]=text[0].replace('公司的中文名称 测试股份有限公司\n','')
    elif fault=='short_name':
        text[0]=text[0].replace('公司的中文名称 测试股份有限公司','公司的中文简称 测试')
    elif fault=='conflicting_legal_name':
        text[0]=text[0].replace('公司的中文名称 测试股份有限公司',
            '公司的中文名称 测试股份有限公司\n公司的中文名称 其他股份有限公司')
    else:
        owner='测试股份有限公司子公司有限公司' if fault=='issuer_assets_subsidiary_liabilities' else '测试股份有限公司'
        text[1]='合并资产负债表\n编制单位：'+owner+'\n2025年12月31日\n单位：元\n项目 期末余额 期初余额\n负债合计 70.00 55.00\n所有者权益合计 30.00 25.00'
    assert ratio(enrich(tmp_path,src))==[]


@pytest.mark.parametrize('declaration',[
    '编制单位：测试子公司有限公司',
    '子公司资产负债表\n编制单位：测试子公司有限公司',
    '项目 期初余额 期末余额',
    '项目 2024年12月31日 2025年12月31日',
    '项目 2026年12月31日 2025年12月31日',
    '单位：万元', '币种：美元'])
def test_continuation_cannot_inherit_group_context_after_conflict(tmp_path,source,declaration):
    src,text=source
    # Group A=100/80 on the first page; the next page's L=70/55 and
    # E=30/25 reconcile arithmetically but belong to an incompatible context.
    text[1]=declaration+'\n'+text[1]
    result=enrich(tmp_path,src)
    assert ratio(result)==[]
    assert result['after']['coverage_ratio']==0


@pytest.mark.parametrize('declaration',[
    '', '编制单位：测试股份有限公司',
    '合并资产负债表（续）\n编制单位：测试股份有限公司\n单位：元\n项目 期末余额 期初余额'])
def test_plain_or_explicit_same_owner_continuation_preserves_context(tmp_path,source,declaration):
    src,text=source
    text[1]=declaration+'\n'+text[1]
    point,=ratio(enrich(tmp_path,src))
    proof=point['metadata']['balance_reconciliation']
    assert point['value']=='70.0'
    assert len({r['table_context_id'] for r in proof['balance_rows']})==1
    assert proof['owner_evidence']['legal_name']==proof['owner_evidence']['compiler_name']


def test_real_000498_single_official_reconciliation():
    raw=os.environ.get('OFFICIAL_BALANCE_REAL_ROOT')
    if not raw: pytest.skip('Explicit retained public root required; no download')
    root=Path(raw)
    path=root/'runtime/daily-marketwide/20261025T0017454129658Z/research-priority-v2-enrichment/000498-official-original/receipt.json'
    source=parser.RetainedAnnualSource(**json.loads(path.read_bytes())['source'])
    before=hashlib.sha256((root/source.path).read_bytes()).hexdigest()
    result=enrich(root,source)
    point,=ratio(result)
    with localcontext() as ctx:
        ctx.prec=48
        assert Decimal(point['value'])==Decimal('139525056417.84')/Decimal('182362833542.24')*100
    rows=point['metadata']['balance_reconciliation']['balance_rows']
    owner=point['metadata']['balance_reconciliation']['owner_evidence']
    assert owner['legal_name']==owner['compiler_name']=='山东高速路桥集团股份有限公司'
    assert owner['legal_name_page']==owner['security_code_page']==6
    assert owner['compiler_page']==151 and owner['security_code']=='000498'
    assert all(r['table_context_id']==point['metadata']['balance_reconciliation']['table_context_id'] for r in rows)
    assert point['available_at']==source.available_at
    assert [(r['field_name'],r['value'],r['prior_value'],r['page']) for r in rows]==[
        ('total_assets','182362833542.24','163366692298.90',152),
        ('total_liabilities','139525056417.84','127977390316.40',153),
        ('total_equity','42837777124.40','35389301982.50',153)]
    assert result['after']['coverage_ratio']==Decimal('0.1111')
    assert result['after']['total_score'] is None and result['debt_scope']['value'] is None
    rebuilt,_=app.consume_retained_enrichment(root,[point],[asdict(source)],evaluation_at=NOW)
    assert rebuilt==[point]
    assert hashlib.sha256((root/source.path).read_bytes()).hexdigest()==before==source.sha256

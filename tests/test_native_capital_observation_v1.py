"""Native report grammar and explicit real retained originals, no network."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings import native_capital_observation_v1 as mod
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages


def sample(symbol='000001',label='半年度报告'):
    return ['测试股份有限公司2026年'+label,
        '股票代码 '+symbol+' 股票上市证券交易所 深圳证券交易所 公司的中文名称 测试股份有限公司',
        '单位：股 本次变动前 本次变动增减（＋，－） 本次变动后 其他 小计',
        '三、股份总数 1,000 100.00% -10 -10 990 100.00% 股份变动的原因',
        '截至2026年6月3日，公司完成了10股限制性股票回购注销工作。',
        '二、本报告期利润分配及资本公积金转增股本情况 '
        '公司计划半年度不派发现金红利，不送红股，不以公积金转增股本。三、其他',
        '十七、资产负债表日后事项1、利润分配情况 '
        '审议通过2025年度利润分配预案：现金分红金额为100.00元（含税）。2、销售退回',
        '本财务报表于2026年8月25日由本公司董事会批准报出。']


def test_structure_not_symbol_selects_quantity_and_scheme_fields():
    pages=sample()
    before=deepcopy(pages)
    result=mod.parse_native_capital_observation(pages,symbol='000001')
    assert result['status']=='VERIFIED' and result['kind']==result['report_kind']=='interim'
    assert result['report_period']==result['period_end']=='2026-06-30'
    assert result['ordinary_shares']=='990' and result['shares_before']=='1000'
    assert result['cancelled_shares']=='10' and result['declared_ordinary_dividend_cny']=='100.00'
    assert result['dividend_fiscal_year']=='2025' and result['payment_completion_state']=='UNKNOWN'
    assert result['closing_continuity_proven'] is False and result['formal_eligibility'] is False
    assert result['action']=='no_order' and result['dividend_policy']['status']=='UNKNOWN'
    assert result['published_date']==result['available_at']=='UNKNOWN'
    assert pages==before
    for ref in result['evidence_refs']:assert ref['excerpt'] in pages[ref['physical_page']-1]


@pytest.mark.parametrize('label,period,kind',[
    ('年度报告','2026-12-31','annual'),('半年度报告','2026-06-30','interim'),
    ('第一季度报告','2026-03-31','q1'),('第三季度报告','2026-09-30','q3'),
    ('三季度报告','2026-09-30','q3')])
def test_report_kind_and_date_without_guessing_unknown_share_quantity(label,period,kind):
    pages=sample(label=label)[:2]+['股本 990.00 1000.00 单位：元']
    result=mod.parse_native_capital_observation(pages,symbol='000001')
    assert result['kind']==kind and result['report_period']==period
    assert result['ordinary_shares']=='UNKNOWN' and 'ordinary_shares' in result['unknowns']
    assert result['declared_ordinary_dividend_cny']=='UNKNOWN'


@pytest.mark.parametrize('damage',['symbol','summary','unit','rollforward','duplicate',
    'cancellation_amount','future_cancellation','statement_date'])
def test_identity_units_columns_and_arithmetic_fail_closed(damage):
    pages=sample()
    if damage=='symbol':pages[1]=pages[1].replace('000001','000002')
    if damage=='summary':pages[0]+='摘要'
    if damage=='unit':pages[2]=pages[2].replace('单位：股','单位：元')
    if damage=='rollforward':pages[3]=pages[3].replace('990','989')
    if damage=='duplicate':pages.insert(4,pages[3])
    if damage=='cancellation_amount':pages[4]=pages[4].replace('10股','11股')
    if damage=='future_cancellation':pages[4]=pages[4].replace('6月3日','7月3日')
    if damage=='statement_date':pages.append('合并资产负债表编制单位：测试股份有限公司2026年9月30日')
    with pytest.raises(ValueError):mod.parse_native_capital_observation(pages,symbol='000001')


def test_other_dividend_table_never_replaces_missing_distribution_scheme():
    pages=sample()
    pages[6]='39、未分配利润 单位：元 项目 本期 上期 应付普通股股利 999.00 888.00'
    result=mod.parse_native_capital_observation(pages,symbol='000001')
    assert result['declared_ordinary_dividend_cny']=='UNKNOWN'
    assert result['dividend_fiscal_year']=='UNKNOWN'


@pytest.fixture(scope='module')
def real_sources():
    configured=os.environ.get('NATIVE_CAPITAL_REAL_ROOT')
    if configured is None:pytest.skip('Real PDF acceptance requires NATIVE_CAPITAL_REAL_ROOT')
    assert configured.strip(),'Explicit source root cannot be empty'
    root=Path(configured).resolve(strict=True)
    base=root/'runtime/e2-first-input-000568-20261031'
    receipt=json.loads((base/'receipt.json').read_bytes())
    h1=root/receipt['source']['path']
    assert hashlib.sha256(h1.read_bytes()).hexdigest()==receipt['source']['sha256']
    pages=extract_pages(h1)
    sealed=json.loads((base/'selected-pages.json').read_bytes())
    assert all(pages[int(page)-1]==text for page,text in sealed.items())
    result={'h1':pages}
    alignment=root/'runtime/value-000568-current-alignment-20261101'
    packet=json.loads((alignment/'source-receipt.json').read_bytes())
    for ident in ('1225481717','1225576512','1225639079'):
        refs=[row for row in packet['records'] if row['source_id']=='cninfo:'+ident]
        assert len(refs)==1 and refs[0]['status']=='ACQUIRED'
        path=root/refs[0]['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==refs[0]['sha256']
        decoded=extract_pages(path)
        saved=json.loads((alignment/(ident+'-pages.json')).read_bytes())
        assert len(decoded)==len(saved)
        assert [mod._compact(p) for p in decoded]==[mod._compact(p) for p in saved]
        result[ident]=decoded
    return result


def test_real_h1_original_exact_fields_and_policy_without_payment_or_pit(real_sources):
    result=mod.parse_native_capital_observation(real_sources['h1'],symbol='000568')
    assert result['kind']=='interim' and result['report_period']=='2026-06-30'
    assert result['ordinary_shares']=='1471901463' and result['shares_before']=='1471941963'
    assert result['cancelled_shares']=='40500' and result['cancellation_date']=='2026-06-03'
    assert result['declared_ordinary_dividend_cny']=='6501567650.57'
    assert result['dividend_fiscal_year']=='2025' and result['report_approved_date']=='2026-08-25'
    assert result['term_pages']['ordinary_shares']==[30]
    assert result['term_pages']['declared_ordinary_dividend_cny']==[130]
    policy=result['dividend_policy']
    assert policy['status']=='VERIFIED' and policy['evidence_pages']==[21]
    assert [(p['fiscal_year'],p['minimum_payout_ratio'],p['minimum_distribution_cny']) for p in policy['policies']]==[
        (2024,'0.65','8500000000'),(2025,'0.7','8500000000'),(2026,'0.75','8500000000')]
    assert policy['period_basis']=='FISCAL_YEAR_NOT_ROLLING'
    for row in policy['policies']:
        assert row['currency']=='CNY' and row['scope']=='consolidated_parent'
        assert '可持续发展' in mod._compact(row['excerpt']) and '保证正常经营和长远发展' in mod._compact(row['excerpt'])
        assert row['excerpt'] in real_sources['h1'][row['physical_page']-1]
    assert result['payment_completion_state']=='UNKNOWN' and result['available_at']=='UNKNOWN'
    assert not result['closing_continuity_proven'] and not result['formal_eligibility']


def test_real_implementation_is_schedule_not_actual_account_payment(real_sources):
    result=mod.parse_native_capital_observation(real_sources['1225481717'],symbol='000568')
    assert result['kind']=='dividend_implementation' and result['report_period']=='2025-12-31'
    assert result['observation_date']=='2026-08-20'
    assert result['declared_ordinary_dividend_cny']=='6501567650.57'
    assert result['distribution_base_shares']==result['ordinary_shares']=='1471901463'
    assert result['excluded_repurchase_shares']=='0'
    assert result['dividend_per_10_shares_cny']=='44.171215'
    assert result['record_date']=='2026-08-27'
    assert result['ex_date']==result['agency_payment_date']=='2026-08-28'
    assert result['payment_completion_state']=='UNKNOWN' and result['cancelled_shares']=='UNKNOWN'
    assert not result['closing_continuity_proven'] and result['action']=='no_order'


def test_real_unlock_keeps_total_and_never_cancels_june_shares_twice(real_sources):
    result=mod.parse_native_capital_observation(real_sources['1225576512'],symbol='000568')
    assert result['kind']=='share_unlock_notice' and result['report_period']=='2026-09-23'
    assert result['share_effective_date']=='2026-09-28'
    assert result['shares_before']==result['ordinary_shares']=='1471901463'
    assert result['net_share_change']=='0' and result['cancelled_shares']=='UNKNOWN'
    assert result['historical_cancelled_shares']=='40500' and result['historical_cancellation_date']=='2026-06-03'
    assert result['term_pages']['ordinary_shares']==[12]
    assert '以限制性股票解除限售事项完成后' in mod._compact(result['share_table_qualification'])
    assert not result['closing_continuity_proven']


def test_real_q3_ytd_is_not_single_quarter_or_monetary_share_quantity(real_sources):
    pages=real_sources['1225639079']
    result=mod.parse_native_capital_observation(pages,symbol='000568')
    assert result['kind']=='q3' and result['report_period']=='2026-09-30'
    assert result['ordinary_shares']=='UNKNOWN' and result['cancelled_shares']=='UNKNOWN'
    update=result['financial_update']
    assert update['status']=='VERIFIED' and update['period_start']=='2026-01-01'
    assert update['period_end']=='2026-09-30' and update['period_basis']=='YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER'
    assert update['fields']['revenue_cny']['value']=='14667616562.73'
    assert update['fields']['parent_profit_cny']['value']=='5671059241.53'
    assert update['fields']['revenue_cny']['scope']=='consolidated'
    assert update['fields']['parent_profit_cny']['scope']=='consolidated_parent'
    assert mod.parse_native_capital_observation([p.replace('第三季度报告','三季度报告') for p in pages],symbol='000568')['kind']=='q3'


@pytest.mark.parametrize('change',['ratio_word','limitation','fiscal_range'])
def test_real_policy_unrecognized_sentence_or_missing_qualification_is_unknown(real_sources,change):
    pages=deepcopy(real_sources['h1'])
    if change=='ratio_word':pages[20]=pages[20].replace('65%、70%、75%','65%、70%')
    if change=='limitation':pages[20]=pages[20].replace('在兼顾公司可持续发展的前提下','')
    if change=='fiscal_range':
        pages[20]=pages[20].replace('2024-2026','2023-2026')
        with pytest.raises(ValueError,match='POLICY_RANGE_UNSUPPORTED'):
            mod.parse_native_capital_observation(pages,symbol='000568')
        return
    result=mod.parse_native_capital_observation(pages,symbol='000568')
    assert result['dividend_policy']['status']=='UNKNOWN' and result['dividend_policy']['policies']==[]


def test_real_unlock_changed_total_and_implementation_wrong_date_rejected(real_sources):
    pages=deepcopy(real_sources['1225576512'])
    pages[11]=pages[11].replace('1,471,901,463','1,471,901,462',1)
    with pytest.raises(ValueError):mod.parse_native_capital_observation(pages,symbol='000568')
    pages=deepcopy(real_sources['1225481717'])
    pages[2]=pages[2].replace('8 月 28 日','8 月 26 日').replace('8月28日','8月26日')
    with pytest.raises(ValueError):mod.parse_native_capital_observation(pages,symbol='000568')


def test_real_per_ten_rounding_difference_is_allowed_not_exact_equality(real_sources):
    result=mod.parse_native_capital_observation(real_sources['1225481717'],symbol='000568')
    shares=Decimal(result['distribution_base_shares'])
    total=Decimal(result['declared_ordinary_dividend_cny'])
    implied=Decimal(result['dividend_per_10_shares_cny'])*shares/10
    difference=abs(implied-total)
    tolerance=Decimal('0.0000005')*shares/10+Decimal('0.005')
    assert difference==Decimal('52.4712455')
    assert tolerance==Decimal('73.60007315') and difference<tolerance
    assert result['status']=='VERIFIED' and result['payment_completion_state']=='UNKNOWN'


@pytest.mark.parametrize('replacement',['4.171215','44.171216','44.171214'])
def test_real_implementation_changed_per_ten_outside_precision_interval_rejected(real_sources,replacement):
    pages=[p.replace('44.171215',replacement) for p in real_sources['1225481717']]
    with pytest.raises(ValueError,match='AMOUNT_OUTSIDE_DISCLOSED_PRECISION'):
        mod.parse_native_capital_observation(pages,symbol='000568')


def test_real_less_precise_per_ten_uses_its_own_printed_unit(real_sources):
    pages=[p.replace('44.171215','44.1712') for p in real_sources['1225481717']]
    result=mod.parse_native_capital_observation(pages,symbol='000568')
    assert result['status']=='VERIFIED' and result['dividend_per_10_shares_cny']=='44.1712'
    assert result['declared_ordinary_dividend_cny']=='6501567650.57'


def test_real_implementation_wrong_total_is_not_rescued_by_rounding(real_sources):
    pages=[p.replace('6,501,567,650.57','650,156,765.05') for p in real_sources['1225481717']]
    with pytest.raises(ValueError,match='AMOUNT_OUTSIDE_DISCLOSED_PRECISION'):
        mod.parse_native_capital_observation(pages,symbol='000568')

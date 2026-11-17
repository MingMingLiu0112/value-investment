"""Direct offline tests, including opt-in real retained PDF replay."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import shareholder_cash_evidence as service


NOW = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


@pytest.fixture(scope='module')
def root():
    value = os.environ.get('SHAREHOLDER_CASH_REPLAY_ROOT')
    if not value:
        pytest.skip('Set SHAREHOLDER_CASH_REPLAY_ROOT for offline retained originals')
    return Path(value)


def test_actual_offline_replay_and_no_source_mutation(root):
    with localcontext() as ctx:
        ctx.prec = 3
        result = service.load_shareholder_cash_evidence(root, '600519', NOW)
    assert result['status'] == 'SOURCE_REPLAYED_PARTIAL_ECONOMIC_OBSERVATIONS', result
    assert result['action'] == 'no_order'
    assert not result['research_admitted'] and not result['economic_approval']
    facts = result['detailed_observations']
    funds = [f for f in facts if f['kind'] == 'fund_uncalled_commitments']
    assert len(funds) == 2
    assert {f['period'] for f in funds} == {'FY2025', 'H12026'}
    for fact in funds:
        assert Decimal(fact['total_uncalled_cny']) == Decimal('6000000000')
        assert [Decimal(o['uncalled_cny']) for o in fact['obligations']] == [Decimal('3000000000')]*2
        assert fact['payment_schedule'] is None
    digital = next(f for f in facts if f['kind'] == 'digital_subsidiary_capital')
    assert [Decimal(digital[k]) for k in ('registered_cny','planned_cny','paid_cny','remaining_planned_cny')] == [
        Decimal('600000000'), Decimal('600000000'), Decimal('200000000'), Decimal('400000000')]
    cash = next(f for f in facts if f['kind'] == 'investment_income_cash')
    assert cash['value_cny'] == '101052220.78'
    assert cash['comparison_value_cny'] is None and cash['comparison_period'] == 'H12025'
    assert cash['scope'] == 'listed_parent_only' and cash['physical_pages'] == [35]
    reviews = [f for f in facts if f['verification_status'].startswith('SOURCE_BOUND_REVIEW')]
    assert len(reviews) == 4 and all(f['value_cny'] is None and not f['auto_admitted'] for f in reviews)
    assert all(f['source_binding']['sha256'] and f['physical_pages'] and f['evidence_excerpt'] for f in facts)
    before = {r['path']: service.sha256_file(root/r['path']) for r in result['source_bindings']}
    assert all(before[r['path']] == r['sha256'] for r in result['source_bindings'])
    assert result == service.load_shareholder_cash_evidence(root, '600519', NOW)
    assert before == {p: service.sha256_file(root/p) for p in before}


@pytest.mark.parametrize('amount', ['7.25', '19'])
def test_fund_values_are_extracted_not_matrix_constants(amount):
    pages = ['重要承诺事项 公司对甲基金和乙基金尚未履行的认缴出资余额均为人民币'+amount+'亿元。']
    parsed = service._fund(pages)
    assert Decimal(parsed['total_uncalled_cny']) == Decimal(amount)*200000000


@pytest.mark.parametrize('text', [
    '公司对甲和乙尚未履行的认缴出资余额均为人民币30亿元。',
    '重要承诺事项 公司对甲和甲尚未履行的认缴出资余额均为人民币30亿元。',
    '重要承诺事项 公司对甲和乙尚未履行的认缴出资余额均为人民币0亿元。',
])
def test_fund_rejects_missing_scope_duplicate_identity_and_invalid_amount(text):
    with pytest.raises(ValueError):
        service._fund([text])


def digital_pages(registered='900,000,000.00', paid='3'):
    return ['其他原因的合并范围变动 公司出资9亿元成立全资子公司甲数字科技有限公司，'
            '截至报告披露日已出资'+paid+'亿元。 企业集团的构成 单位：元 币种：人民币 注册资本',
            '甲数字科技有限公司 '+registered+' 重要的非全资子公司']


def test_digital_extracts_and_reconciles_independent_registration():
    result = service._digital(digital_pages())
    assert result['remaining_planned_cny'] == '600000000'
    assert result['legally_due_now'] is None


@pytest.mark.parametrize('registered,paid', [('600,000,000.00','3'), ('900,000,000.00','10')])
def test_digital_rejects_registration_mismatch_or_overpayment(registered, paid):
    with pytest.raises(ValueError, match='DIGITAL_REGISTERED_PLANNED_PAID_MISMATCH'):
        service._digital(digital_pages(registered, paid))


@pytest.mark.parametrize('fault,reason', [('hash','ORIGINAL_SHA256_MISMATCH'),
                                         ('future','SOURCE_NOT_YET_AVAILABLE'),
                                         ('naive','AWARE_CLOCK_REQUIRED')])
def test_source_rejections_return_no_amounts(root, monkeypatch, fault, reason):
    now = NOW
    if fault == 'hash':
        original = service.sha256_file
        monkeypatch.setattr(service, 'sha256_file', lambda p: 'bad' if str(p).endswith('.pdf') else original(p))
    elif fault == 'future':
        now = NOW.replace(year=2025)
    else:
        now = NOW.replace(tzinfo=None)
    result = service.load_shareholder_cash_evidence(root, '600519', now)
    assert result['status'] == 'SOURCE_REVALIDATION_FAILED' and reason in result['reason']
    assert result['observations'] == {} and result['source_bindings'] == []


def test_real_pdf_comparison_column_is_rejected(root):
    import json
    spec = json.loads((root/service.parent.SPEC).read_bytes())['companies']['600519'][1]
    with pytest.raises(ValueError, match='NOT_CURRENT_COLUMN'):
        service._verify_current_column(root/spec['path'], 35, '8,195,990,042.68',
                                       '15,224,606,455.02', '8,195,990,042.68')


def test_missing_registration_does_not_invent_sources(root):
    result = service.load_shareholder_cash_evidence(root, '000001', NOW)
    assert result['status'] == 'SOURCE_NOT_REGISTERED' and result['observations'] == {}


def test_real_replay_scope_mutation_fails_closed(root, monkeypatch):
    original = service.parent.extract_pages
    def changed(path):
        pages = original(path)
        return [p.replace('母公司现金流量表', '合并现金流量表') for p in pages]
    monkeypatch.setattr(service.parent, 'extract_pages', changed)
    result = service.load_shareholder_cash_evidence(root, '600519', NOW)
    assert result['status'] == 'SOURCE_REVALIDATION_FAILED'
    assert result['observations'] == {}


def test_failure_after_partial_parse_never_leaks_facts(root, monkeypatch):
    def reject(*args):
        raise ValueError('TEST_COLUMN_AMBIGUOUS')
    monkeypatch.setattr(service, '_verify_current_column', reject)
    result = service.load_shareholder_cash_evidence(root, '600519', NOW)
    assert 'TEST_COLUMN_AMBIGUOUS' in result['reason']
    assert result['observations'] == {} and result['source_bindings'] == []


def test_source_changes_during_second_read_are_rejected(root, monkeypatch):
    original_hash = service.sha256_file
    original_fund = service._fund
    changed = False
    def parse(pages):
        nonlocal changed
        result = original_fund(pages)
        changed = True
        return result
    def digest(path):
        if changed and str(path).endswith('.pdf'):
            return 'changed'
        return original_hash(path)
    monkeypatch.setattr(service, '_fund', parse)
    monkeypatch.setattr(service, 'sha256_file', digest)
    result = service.load_shareholder_cash_evidence(root, '600519', NOW)
    assert result['status'] == 'SOURCE_REVALIDATION_FAILED'
    assert 'CHANGED' in result['reason']
    assert result['observations'] == {}


@pytest.mark.parametrize('row', ['', '101,052,220.78 99.00', '101,052,220.78\n99.00'])
def test_interim_incomplete_or_two_column_layout_never_auto_admitted(row):
    statement = dict(rows={'cfo_cny': {'physical_page': 1}}, periods=['H12026','H12025'])
    text = '母公司现金流量表\n取得投资收益收到的现金 ' + row
    with pytest.raises(ValueError, match='H1_SINGLE_PRINTED'):
        service._interim([text], statement, Path('unused.pdf'))


def test_named_root_contract(root):
    result = service.load_shareholder_cash_evidence(root, '600519', NOW)
    named = result['observations']
    expected = dict(fund_uncalled_total_cny='6000000000', digital_registered_cny='600000000',
                    digital_paid_cny='200000000', digital_remaining_cny='400000000',
                    interim_investment_cash_current_cny='101052220.78',
                    interim_investment_cash_comparative_cny=None)
    assert set(named) == set(expected)
    for key, value in expected.items():
        row = named[key]
        assert row['value'] is None if value is None else Decimal(row['value']) == Decimal(value)
        assert row['classification'].startswith('SOURCE_VERIFIED_')
        assert row['source_refs'][0]['sha256'] and row['source_refs'][0]['physical_pages']
        assert row['period'] == ('H12025' if key.endswith('comparative_cny') else 'H12026')
    assert Decimal(named['digital_remaining_cny']['value']) == (
        Decimal(named['digital_registered_cny']['value']) - Decimal(named['digital_paid_cny']['value']))

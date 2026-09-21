from datetime import datetime, timezone
from copy import deepcopy
import pytest

from value_investment_agent.reminders import build_reminders
from value_investment_agent.financial_quality import GENERAL_FIELDS
from test_quote_sessions import evidence as make_session_evidence

NOW=datetime(2026,9,7,8,tzinfo=timezone.utc)


def payload(price=60):
    evidence={'validation_status':'verified','fetched_at':NOW.isoformat(),'created_at':NOW.isoformat(),
              'period_label':'2026-09-07','metadata':{'automatic_cross_source_verification':True,
              'quote_session_evidence':make_session_evidence(price=price)}}
    return {'generated_at':NOW.isoformat(),
        'market_candidates':[{'symbol':'000333','name':'样例制造','sector':'机械','board':'主板','initial_score':'60','current_price':price}],
        'financial_quality':[{'symbol':'000333','quality_status':'已验证','total_score':80}],
        'valuations':[{'symbol':'000333','build_signal':'建仓候选','calculated_at':NOW.isoformat(),
                       'calculation_details':{'price_source_id':'price','fair_value_source_id':'fair'}}],
        'points':[dict(evidence,symbol='000333',field_name='current_price',value=price,source_id='price'),
                  dict(evidence,symbol='000333',field_name='fair_value',value=100,source_id='fair')]
                  + [dict(evidence,symbol='000333',field_name=f,value=10,source_id=f,period_label='2026-06-30',
                          metadata={**evidence['metadata'],
                                    **({'complete_debt_verified': True} if f == 'interest_bearing_debt' else {})})
                     for f in GENERAL_FIELDS]}


def test_buy_requires_verified_current_evidence_not_low_pe_alone():
    p=payload()
    assert build_reminders(p,now=NOW)[0]['category']=='买入研究候选'
    p['points'][1]['validation_status']='pending'
    alert=build_reminders(p,now=NOW)[0]
    assert alert['category']=='重点观察'
    assert alert['signal_blocked']


def test_missing_debt_scope_blocks_buy_even_with_cached_verified_quality():
    p = payload()
    debt = next(row for row in p['points'] if row['field_name'] == 'interest_bearing_debt')
    del debt['metadata']['complete_debt_verified']
    alert = build_reminders(p, now=NOW)[0]
    assert alert['signal_blocked']
    assert alert['category'] != '买入研究候选'
    assert any(not check['passed'] for check in alert['decision_checks']
               if check['name'] == '最新同报告期指标')


def test_missing_fair_value_does_not_mislabel_valid_quote():
    p = payload()
    p['points'][1]['value'] = None
    alert = build_reminders(p, now=NOW)[0]
    check = next(c for c in alert['decision_checks'] if c['name'] == '现价与合理价数值')
    assert check['reasons'] == ['合理价缺失或数值无效']
    assert alert['signal_blocked']
    assert alert['decision_price'] == '60'


def test_unknown_position_never_becomes_a_sell_instruction():
    p=payload(120)
    assert build_reminders(p,now=NOW)[0]['category']=='估值偏高'
    assert build_reminders(p,{'000333':100},NOW)[0]['category']=='减仓研究候选'
    assert build_reminders(payload(90),{'000333':100},NOW)[0]['category']=='估值观察'


@pytest.mark.parametrize('prices', [('220.20','220.49'), ('357.20','357.60'),
    ('367.28','367.25'), ('490.85','490.89'), ('15.27','15.28'), ('20.97','20.99')])
def test_observed_price_conflicts_can_flip_trigger_with_hypothetical_fair_value(prices):
    # Only prices reproduce observed conflicts. All financial evidence, fair
    # values and holdings here are synthetic, not actual historical decisions.
    from decimal import Decimal
    low, high = sorted(map(Decimal, prices))
    midpoint = (low + high) / 2
    for fair, expected in [(midpoint / Decimal('.7'), ['买入研究候选', '估值观察']),
                           (midpoint, ['估值观察', '减仓研究候选'])]:
        actual = []
        for price in (low, high):
            p = payload(str(price))
            p['points'][1]['value'] = str(fair)
            actual.append(build_reminders(p, {'000333':100}, NOW)[0]['category'])
        assert actual == expected


def test_staleness_missing_quality_and_changed_evidence_block_trades():
    base=payload()
    for mutate in [lambda p:p.update(generated_at='2020-01-01T00:00:00+00:00'),
                   lambda p:p['financial_quality'].clear(),
                   lambda p:p['valuations'][0]['calculation_details'].update(price_source_id='old')]:
        p=deepcopy(base); mutate(p)
        assert build_reminders(p,now=NOW)[0]['signal_blocked']


def test_legacy_batch_level_market_verification_is_not_enough():
    p=payload()
    p['points'][0]['metadata']['market_snapshot_source_id']='legacy'
    assert build_reminders(p,now=NOW)[0]['signal_blocked']


def test_banks_do_not_pass_with_general_company_quality():
    p=payload(); p['market_candidates'][0].update(name='样例银行',sector='银行')
    assert build_reminders(p,now=NOW)[0]['signal_blocked']


def test_annual_quality_cannot_bypass_incomplete_latest_report():
    p=payload()
    p['points'][-1]['validation_status']='pending'
    alert=build_reminders(p,now=NOW)[0]
    assert alert['signal_blocked']
    assert any('年度评分不能替代中期跟踪' in reason for reason in alert['reasons'])


def tracking_payload():
    p = payload()
    p['candidate_tracking'] = [{'symbol':'000333','quote_as_of':NOW.isoformat(),
        'signal_blocked':False,'quote_status':'matched','source_id':'price',
        'current_price':60,'risk_warning':False,'valuation_field_conflicts':{}}]
    return p


def test_matching_daily_tracking_preserves_other_gates():
    p = tracking_payload()
    assert build_reminders(p,now=NOW)[0]['category'] == '买入研究候选'
    p['points'][1]['validation_status'] = 'pending'
    assert build_reminders(p,now=NOW)[0]['signal_blocked']


def test_decision_checks_are_the_exact_signal_gate_reasons():
    p = tracking_payload()
    good = build_reminders(p,now=NOW)[0]
    assert len(good['decision_checks']) == 8
    assert all(c['passed'] for c in good['decision_checks'])
    assert good['decision_price'] == '60' and good['decision_fair_value'] == '100'
    assert good['known_holding'] is None
    p['points'][1]['validation_status'] = 'pending'
    p['financial_quality'] = []
    bad = build_reminders(p,now=NOW)[0]
    assert [r for c in bad['decision_checks'] for r in c['reasons']] == bad['reasons']
    assert sum(not c['passed'] for c in bad['decision_checks']) == 2


@pytest.mark.parametrize('changes', [
    {'signal_blocked':True}, {'quote_status':'missing_quote'},
    {'quote_as_of':'2020-01-01T00:00:00+00:00'}, {'risk_warning':True},
    {'valuation_field_conflicts':{'pe':{'a':12,'b':20}}},
    {'source_id':'old'}, {'source_id':None}, {'current_price':61},
])
def test_daily_tracking_failure_cannot_fall_back_to_valid_old_valuation(changes):
    p = tracking_payload()
    p['candidate_tracking'][0].update(changes)
    alert = build_reminders(p,now=NOW)[0]
    assert alert['signal_blocked'] and alert['category'] != '买入研究候选'


@pytest.mark.parametrize('mode', ['missing','duplicate','null'])
def test_incomplete_tracking_batch_blocks(mode):
    p = tracking_payload()
    p['candidate_tracking'] = ([] if mode == 'missing' else None if mode == 'null'
                               else p['candidate_tracking'] * 2)
    assert build_reminders(p,now=NOW)[0]['signal_blocked']


@pytest.mark.parametrize('packet', [None, make_session_evidence(day='2026-09-04'),
                                  make_session_evidence(clock='10:00:00')])
def test_download_recency_cannot_approve_unknown_old_or_intraday_quote(packet):
    p = payload()
    p['points'][0]['metadata']['quote_session_evidence'] = packet
    alert = build_reminders(p, now=NOW)[0]
    assert alert['signal_blocked'] and alert['category'] != '买入研究候选'
    assert not next(c for c in alert['decision_checks'] if c['name'] == '行情验证与时效')['passed']

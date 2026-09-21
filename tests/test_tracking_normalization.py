import pytest
from datetime import datetime, timezone
from value_investment_agent.candidate_tracking import normalize_tracking_quotes
from value_investment_agent.candidate_tracking import track_candidates


def test_chinese_provider_fields_keep_above_screen_thresholds():
    rows = normalize_tracking_quotes([{'代码':'000333','名称':'company','最新价':100,
        '市盈率-动态':30,'市净率':4,'总市值':1000}])
    assert rows[0]['symbol'] == '000333'
    assert rows[0]['pe'] == 30 and rows[0]['pb'] == 4


def test_missing_price_is_not_copied_from_other_fields():
    row = normalize_tracking_quotes([{'symbol':'000333','pe':15}])[0]
    assert row['current_price'] is None


@pytest.mark.parametrize('row', [
    {'代码':'000333','symbol':'600519'},
    {'symbol':'000333','最新价':100,'current_price':90},
    {'symbol':'bad'}, {},
])
def test_invalid_or_conflicting_fields_fail_loudly(row):
    with pytest.raises(ValueError):
        normalize_tracking_quotes([row])


def test_leading_zero_normalization():
    assert normalize_tracking_quotes([{'code':333}])[0]['symbol'] == '000333'


def test_conflicting_valuation_is_retained_and_blocks_only_affected_company():
    now = datetime(2026,9,8,8,tzinfo=timezone.utc)
    proof = {'status':'matched','tencent_price':'100','sina_price':'100','sina_url':'source'}
    raw = [{'symbol':'000333','current_price':'100','市盈率-动态':'12','pe':'20','price_cross_check':proof},
           {'symbol':'600519','current_price':'100','pe':'20','price_cross_check':proof}]
    normalized = normalize_tracking_quotes(raw)
    rows = track_candidates([{'symbol':r['symbol']} for r in raw],normalized,now.isoformat(),now=now)
    assert len(rows) == 2
    assert rows[0]['pe'] is None and rows[0]['signal_blocked']
    assert rows[0]['quote_status'] == 'matched'
    assert rows[0]['valuation_field_conflicts']['pe'] == {'市盈率-动态':'12','pe':'20'}
    assert not rows[1]['signal_blocked']
    assert raw[0]['pe'] == '20'

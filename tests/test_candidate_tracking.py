from copy import deepcopy
from datetime import datetime, timezone
import pytest
from value_investment_agent.candidate_tracking import track_candidates


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    import value_investment_agent.candidate_tracking as module
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 8, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, 'datetime', Clock)


MEMBER = {'symbol': '000333', 'initial_score': '60', 'screen_date': '2026-09-01',
          'current_price': '70', 'board': 'main'}


def quote(**changes):
    return {'symbol': '000333', 'name': 'company', 'current_price': '100',
            'pe': '30', 'pb': '4', 'price_cross_check': {'status': 'matched',
            'tencent_price': '100', 'sina_price': '100', 'sina_url': 'https://vip.stock.finance.sina.com.cn/mkt/#hs_a'}, **changes}


def test_price_rise_does_not_remove_candidate_or_rewrite_entry_score():
    member = deepcopy(MEMBER)
    row = track_candidates([member], [quote()], '2026-09-08T16:00:00+08:00')[0]
    assert row['membership'] == MEMBER and member == MEMBER
    assert row['pe'] == '30' and row['pb'] == '4'
    assert not row['signal_blocked']


def test_missing_quote_retains_member_but_never_relabels_old_price_as_new():
    row = track_candidates([MEMBER], [], '2026-09-08T16:00:00+08:00')[0]
    assert row['current_price'] is None and row['signal_blocked']
    assert row['membership']['current_price'] == '70'


@pytest.mark.parametrize('change', [
    {'current_price': 'NaN'}, {'current_price': '0'},
    {'price_cross_check': {'status': 'conflict'}}, {'price_cross_check': {}},
    {'name': '*ST company'},
])
def test_risk_or_unreliable_quote_blocks_without_dropping_company(change):
    rows = track_candidates([MEMBER], [quote(**change)], '2026-09-08T16:00:00+08:00')
    assert len(rows) == 1 and rows[0]['signal_blocked']


def test_nonmembers_not_added_by_daily_tracking():
    assert track_candidates([], [quote()], '2026-09-08T16:00:00+08:00') == []


def test_duplicate_quotes_rejected():
    with pytest.raises(ValueError, match='Duplicate tracked quote'):
        track_candidates([MEMBER], [quote(), quote()], '2026-09-08T16:00:00+08:00')


@pytest.mark.parametrize('proof', [
    {'status': 'matched'},
    {'status': 'matched', 'tencent_price': '99', 'sina_price': '100', 'sina_url': 'source'},
    {'status': 'matched', 'tencent_price': '100', 'sina_price': '110', 'sina_url': 'source'},
    ['matched'],
])
def test_matched_label_cannot_replace_actual_evidence(proof):
    assert track_candidates([MEMBER], [quote(price_cross_check=proof)],
                            '2026-09-08T16:00:00+08:00')[0]['signal_blocked']


def test_old_quote_remains_blocked():
    assert track_candidates([MEMBER], [quote()], '2026-09-01T16:00:00+08:00')[0]['quote_status'] == 'stale_quote'


def test_naive_time_rejected():
    with pytest.raises(ValueError, match='timezone'):
        track_candidates([MEMBER], [quote()], '2026-09-08T16:00:00')

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_midea_suspensions import reconcile


def event():
    return {'start_date': '2018-09-10', 'resume_date': '2018-10-29'}


def test_half_open_suspension_and_unexplained_dates():
    result = reconcile({'sz000333': {'2018-10-29'},
                        'peer': {'2018-09-10', '2018-10-26', '2018-10-29', '2019-02-20'}}, [event()])
    assert result['explained_peer_date_count'] == 2
    assert result['unexplained_peer_dates'] == ['2019-02-20']
    assert result['backtest_ready'] is False


@pytest.mark.parametrize('observed', [{'2018-09-10', '2018-10-29'}, set()])
def test_conflicting_bar_or_missing_resumption_fails(observed):
    with pytest.raises(ValueError):
        reconcile({'sz000333': observed, 'peer': {'2018-09-10'}}, [event()])


def test_duplicate_intervals_fail():
    with pytest.raises(ValueError):
        reconcile({'sz000333': {'2018-10-29'}, 'peer': {'2018-09-10'}}, [event(), event()])

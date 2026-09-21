import pytest
from value_investment_agent.account_path_metrics import account_path_metrics


def row(day, equity):
    return dict(date=day, equity=equity, cash=0, shares=1, close=equity)


def test_cross_year_opening_carries_previous_close_and_recovers():
    result = account_path_metrics([row('2020-01-02', 80), row('2020-01-03', 100), row('2020-01-06', 120)], opening_equity=100, opening_date='2019-12-31')
    assert float(result['marked_return']) == pytest.approx(.2)
    assert float(result['max_drawdown']) == pytest.approx(.2)
    assert result['drawdown_peak_date'] == '2019-12-31'
    assert result['drawdown_recovery_date'] == '2020-01-03'


def test_new_worst_drawdown_resets_prior_recovery():
    result = account_path_metrics([row('2020-01-02', 80), row('2020-01-03', 100), row('2020-01-06', 60)], opening_equity=100, opening_date='2019-12-31')
    assert float(result['max_drawdown']) == pytest.approx(.4)
    assert result['drawdown_recovery_date'] is None


@pytest.mark.parametrize('rows', [[], [row('2020-01-02', 0)], [row('2020-01-02', float('nan'))], [row('2020-01-02', 100), row('2020-01-02', 110)]])
def test_invalid_paths_fail(rows):
    with pytest.raises(ValueError):
        account_path_metrics(rows, opening_equity=100, opening_date='2020-01-01')

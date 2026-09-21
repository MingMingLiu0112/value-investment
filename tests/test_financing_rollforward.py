import pytest
from value_investment_agent.financing_rollforward import AMOUNTS, reconciles, reconciles_table


def test_official_000411_2025_total_reconciles():
    row = dict(zip(AMOUNTS, ['2845794781.76','7676503207.85','358737056.69',
                            '6675219938.53','193159483.42','4012655624.35']))
    assert reconciles(row)
    row['closing'] = '4012655624.34'
    assert not reconciles(row)


@pytest.mark.parametrize('missing', [None,'','NaN','Infinity'])
def test_missing_or_nonfinite_is_not_zero(missing):
    row = dict.fromkeys(AMOUNTS,'0')
    row['noncash_decrease'] = missing
    assert not reconciles(row)


def test_all_columns_and_total_must_reconcile():
    first = dict(zip(AMOUNTS,['10','2','1','3','0','10']))
    second = dict(zip(AMOUNTS,['20','4','2','6','0','20']))
    total = dict(zip(AMOUNTS,['30','6','3','9','0','30']))
    assert reconciles_table([first,second],total)
    assert not reconciles_table([first,first],total)
    assert not reconciles_table([],total)
    del first['noncash_decrease']
    assert not reconciles_table([first,second],total)

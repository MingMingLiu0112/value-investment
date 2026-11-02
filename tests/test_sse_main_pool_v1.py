from copy import deepcopy
import pytest
from value_investment_agent.domain.discovery.sse_main_pool_v1 import CHANNELS, project_outcome


def rows(status='REJECTED'):
    return [dict(channel=c, status=status, reason=c+' explicit reason') for c in CHANNELS]


def test_real_zero_is_not_missing_data():
    assert project_outcome(rows())['status'] == 'EXCLUDED'
    data=rows();data[0]['status']='DATA_GAP'
    assert project_outcome(data)['status'] == 'UNASSESSABLE'


def test_budget_is_not_economic_rejection():
    data=rows();data[2]['status']='BUDGET_EXCLUDED'
    assert project_outcome(data)['status']=='CANDIDATE'
    assert project_outcome(data)['channels']==['value']


def test_one_pass_does_not_erase_other_channel_gap():
    data=rows();data[0]['status']='DATA_GAP';data[2]['status']='PASS'
    out=project_outcome(data)
    assert out['status']=='CANDIDATE' and len(out['gaps'])==1
    assert project_outcome(data,risk_warning=True)['status']=='EXCLUDED'
    assert project_outcome(data,price_conflict=True)['status']=='UNASSESSABLE'


@pytest.mark.parametrize('bad', [[],rows()[:-1],rows()+[rows()[0]], [dict(channel=c,status='BUY',reason='x') for c in CHANNELS]])
def test_incomplete_or_new_action_is_rejected(bad):
    with pytest.raises(ValueError):project_outcome(bad)

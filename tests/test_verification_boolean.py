import pytest

from value_investment_agent.derived_financials import _accepted as derived_accepted
from value_investment_agent.financial_quality import _accepted as financial_accepted
from value_investment_agent.quality import automatically_verified


@pytest.mark.parametrize('check', [derived_accepted, financial_accepted, automatically_verified])
@pytest.mark.parametrize('flag', ['false', 'true', 1, 0, None, False, [], {}])
def test_only_boolean_true_can_approve_cross_source_verification(check, flag):
    point = {'validation_status': 'verified',
             'metadata': {'automatic_cross_source_verification': flag}}
    assert not check(point)


@pytest.mark.parametrize('check', [derived_accepted, financial_accepted, automatically_verified])
def test_true_still_requires_nonquarantined_evidence(check):
    point = {'validation_status': 'verified',
             'metadata': {'automatic_cross_source_verification': True}}
    assert check(point)
    point['metadata']['evidence_quarantine'] = True
    assert not check(point)

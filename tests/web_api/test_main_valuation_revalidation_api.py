"""TEST_ONLY read models through the real public route; no financial acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import sys
from types import ModuleType, SimpleNamespace

import pytest

from web_api.test_live_operating_research_api import api, reviewed_result, BASE
from test_operating_cash_consumption_v1 import no_io_effects
from value_investment_agent.application.research import (
    operating_cash_consumption_v1 as cash,
    current_capital_observation_v1 as capital,
    operating_distribution_review_v1 as distribution,
    parent_funding_review_v1 as funding,
)


@pytest.fixture
def revalidation(api, monkeypatch):
    client, _, data, root = api
    task = reviewed_result()
    task['symbol'] = '000568'
    data.rows = [task]
    siblings = {}
    for module, function, key in (
        (cash, 'read_operating_cash_consumption', 'cash_consumption'),
        (capital, 'read_current_capital_observation', 'current_capital_observation'),
        (distribution, 'read_operating_distribution_review', 'fiscal_distribution_review'),
        (funding, 'read_registered_parent_funding_review', 'parent_funding_review'),
    ):
        value = dict(status='TEST_ONLY_EXISTING_RESEARCH', action='no_order',
                     formal_eligibility=False, marker=key)
        siblings[key] = deepcopy(value)
        monkeypatch.setattr(module, function, lambda *a, _value=value, **k: deepcopy(_value))
    comparison = {'status': 'TEST_ONLY_COMPARISON'}
    monkeypatch.setattr(funding, 'compare_parent_cash_opening', lambda *a: deepcopy(comparison))
    siblings['parent_funding_review']['cash_input_comparison'] = comparison
    control = SimpleNamespace(calls=[], failure=None, value=dict(
        status='TEST_ONLY_CONDITIONAL_REVALIDATION', action='no_order',
        formal_eligibility=False, current_comparable=False, personal_quantity=None))

    def readmodel(*, root, symbol, now):
        control.calls.append(dict(root=root, symbol=symbol, now=now))
        if control.failure is not None:
            raise control.failure
        return deepcopy(control.value)

    # Explicit read-model replacement, including the route's lazy import boundary.
    # This tests transport while the independent consumer is being implemented.
    name = 'value_investment_agent.application.research.main_valuation_revalidation_v1'
    module = ModuleType(name)
    module.read_main_valuation_revalidation = readmodel
    monkeypatch.setitem(sys.modules, name, module)
    return client, data, root, control, siblings


def public_get(case):
    client, data, root, control, siblings = case
    original = deepcopy(data.rows)
    snapshot = lambda: {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                        for p in root.rglob('*') if p.is_file()}
    before = snapshot()
    started = datetime.now(timezone.utc)
    assert 'x-local-session' not in client.headers and not client.cookies
    # Start TestClient's Windows event-loop self-pipe before denying sockets;
    # the route itself still executes entirely under the no-I/O guard.
    with client:
        with no_io_effects():
            responses = [client.get(BASE + '/companies/000568') for _ in range(2)]
    ended = datetime.now(timezone.utc)
    assert snapshot() == before and data.rows == original
    assert data.provider_calls == []
    assert data.calls == [('list', '000568'), ('list', '000568')]
    assert len(control.calls) == 2
    for call in control.calls:
        assert call['root'] == root and call['symbol'] == '000568'
        assert started <= call['now'] <= ended
    for response in responses:
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        body = response.json()
        assert body['action'] == 'no_order' and body['formal_eligibility'] is False
        assert body['main_range_adopted'] is False and body['approval_changed'] is False
        assert body['condition_price'] is None and body['personal_quantity'] is None
        assert body['research_draft'] == original[0]['research_draft']
        assert body['independent_review'] == original[0]['independent_review']
        for key, value in siblings.items():
            assert body[key] == value
    return responses[-1].json()


def test_public_revalidation_no_auth_no_writes_no_paid_calls(revalidation):
    body = public_get(revalidation)
    assert body['status'] == 'SUCCEEDED'
    assert body['main_valuation_revalidation'] == revalidation[3].value


@pytest.mark.parametrize('status', ['NOT_STARTED', 'PARTIAL', 'UNASSESSABLE'])
def test_readmodel_failure_reason_preserved_without_erasing_other_research(revalidation, status):
    revalidation[3].value.update(status=status, reason='TEST_ONLY_EXACT_SOURCE_HASH_MISMATCH')
    body = public_get(revalidation)
    assert body['status'] == 'SUCCEEDED'
    assert body['main_valuation_revalidation'] == revalidation[3].value


@pytest.mark.parametrize('error_type', [ValueError, OSError, KeyError, TypeError])
def test_exception_isolated_with_exact_reason(revalidation, error_type):
    failure = error_type('TEST_ONLY_EXACT_REVALIDATION_BINDING_FAILURE')
    revalidation[3].failure = failure
    body = public_get(revalidation)
    assert body['status'] == 'SUCCEEDED'
    assert body['main_valuation_revalidation'] == dict(
        status='UNASSESSABLE', reason=str(failure), action='no_order',
        formal_eligibility=False, current_comparable=False, personal_quantity=None)


def test_verified_partial_d2_keeps_own_reason_and_revalidation_failure(revalidation):
    task = revalidation[1].rows[0]
    task.update(status='FAILED', error_code='DAILY_BUDGET_EXHAUSTED_BEFORE_CALL')
    revalidation[3].failure = ValueError('TEST_ONLY_NEW_SOURCE_NOT_VERIFIED')
    body = public_get(revalidation)
    assert body['status'] == 'PARTIAL' and body['execution_status'] == 'FAILED'
    assert body['reason'] == 'DAILY_BUDGET_EXHAUSTED_BEFORE_CALL'
    assert body['main_valuation_revalidation']['reason'] == 'TEST_ONLY_NEW_SOURCE_NOT_VERIFIED'

"""Synthetic accounts only: explicit confirmations and retries never change holdings."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from test_private_ips_policy import service, confirm_policy
from value_investment_agent.application.portfolio import private_risk_experience as experience
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalConflict, JournalValidationError,
)

NOW = datetime.fromisoformat("2026-10-15T10:00:00+08:00")


def costs(revision=1, **changes):
    request = {"idempotency_key": "costs", "expected_revision": revision, "acknowledged": True,
        "costs": {key: "0" for key in experience.COST_FIELDS},
        "confirmed_at": NOW.isoformat(), "valid_until": (NOW + timedelta(days=1)).isoformat(),
        "confirmation_note": "SYNTHETIC explicitly confirmed cost scenario"}
    request.update(changes)
    return request


def test_cost_persistence_parallel_retry_and_no_cash_or_policy_mutation(service, tmp_path):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    before = service.portfolio_view()
    request = costs()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: adapter.confirm_costs(request, now=NOW), range(2)))
    assert results[0] == results[1]
    assert len(service.records()) == 2
    assert service.records()[-1]["changes_holdings"] is False
    restarted = experience.PrivateRiskExperienceService(PrivateJournal(service.journal.path))
    context = restarted.context(symbol="300364", repository_root=tmp_path, now=NOW)
    assert context["cost_profile"]["costs"] == request["costs"]
    assert context["policy"] is None
    assert context["verified_rules"] == {}
    after = service.portfolio_view()
    for field in ("cash_cny", "positions", "policy", "trades"):
        assert before[field] == after[field]
    with pytest.raises(JournalConflict, match="不同内容"):
        adapter.confirm_costs(costs(confirmation_note="changed"), now=NOW)
    with pytest.raises(JournalConflict) as error:
        adapter.confirm_costs(costs(idempotency_key="new"), now=NOW)
    assert error.value.code == "VERSION_CONFLICT"


@pytest.mark.parametrize("changes", [
    {"acknowledged": False}, {"acknowledged": "true"}, {"confirmation_note": " "},
    {"costs": {}}, {"costs": {"gap_stress_cny": "0"}},
    {"costs": {**{key: "0" for key in experience.COST_FIELDS}, "buy_fee_fraction": True}},
    {"costs": {**{key: "0" for key in experience.COST_FIELDS}, "buy_fee_fraction": "NaN"}},
    {"costs": {**{key: "0" for key in experience.COST_FIELDS}, "buy_fee_fraction": "1.01"}},
    {"valid_until": NOW.isoformat()}, {"confirmed_at": (NOW + timedelta(seconds=1)).isoformat()},
])
def test_invalid_costs_never_append(service, changes):
    before = service.journal.path.read_bytes()
    with pytest.raises(JournalValidationError):
        experience.PrivateRiskExperienceService(service.journal).confirm_costs(costs(**changes), now=NOW)
    assert before == service.journal.path.read_bytes()


def test_expired_latest_cost_never_resurrects_old_profile(service, tmp_path):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    adapter.confirm_costs(costs(valid_until=(NOW + timedelta(days=30)).isoformat()), now=NOW)
    adapter.confirm_costs(costs(2, idempotency_key="replacement"), now=NOW)
    context = adapter.context(symbol="300364", repository_root=tmp_path, now=NOW + timedelta(days=2))
    assert context["cost_profile"] is None


def test_only_effective_confirmed_ips_is_read_without_default_notional(service, tmp_path):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    confirm_policy(service)
    context = adapter.context(symbol="300364", repository_root=tmp_path, now=NOW)
    assert context["policy"]["hotspot_budget_cny"] == "2000"
    assert "max_trade_notional_cny" not in context["policy"]
    assert context["cost_profile"] is None
    assert context["verified_rules"] == {}


def test_initial_holdings_reconciliation_without_any_fills_and_stable_retries(service):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    request = {"idempotency_key": "reconcile", "expected_revision": 1,
        "reconciled_at": NOW.isoformat(), "confirmation_note": "SYNTHETIC opening balances checked",
        "cash_checked": True, "positions_checked": True, "fills_checked": True}
    before = service.portfolio_view()
    with pytest.raises(JournalValidationError):
        adapter.confirm_reconciliation({**request, "cash_checked": False})
    assert len(service.records()) == 1
    response, digest = adapter.confirm_reconciliation(request)
    assert adapter.confirm_reconciliation(request) == (response, digest)
    assert response["status"] == "RECONCILED"
    assert response["reconciliation_scope"] == "INTERNAL_JOURNAL_REPLAY"
    after = PrivatePortfolioService(PrivateJournal(service.journal.path)).portfolio_view()
    assert after["reconciliation"]["status"] == "RECONCILED"
    for field in ("cash_cny", "positions", "trades"):
        assert before[field] == after[field]


def test_initial_reconciliation_still_rejects_old_timestamp(service):
    with pytest.raises(JournalValidationError):
        service.reconcile({"idempotency_key": "old", "expected_revision": 1,
            "reconciled_at": "2026-10-09T20:00:00+08:00", "confirmation_note": "SYNTHETIC"})


@pytest.mark.parametrize("kind", ["broker_statement", "account_statement", "custodian_statement"])
def test_external_statement_reference_is_explicit_and_idempotent_without_fills(service, kind):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    request = {"idempotency_key": "external", "expected_revision": 1,
        "reconciled_at": NOW.isoformat(), "confirmation_note": "SYNTHETIC personally checked external statement",
        "cash_checked": True, "positions_checked": True, "fills_checked": True,
        "account_evidence": {"id": "STATEMENT-TEST-ONLY", "kind": kind}}
    response, digest = adapter.confirm_reconciliation(request)
    assert response["reconciliation_scope"] == "EXTERNAL_ACCOUNT_STATEMENT"
    assert adapter.confirm_reconciliation(request) == (response, digest)
    assert len(service.records()) == 2
    assert service.records()[-1]["body"]["account_evidence"] == request["account_evidence"]
    assert service.portfolio_view()["reconciliation"]["scope"] == "EXTERNAL_ACCOUNT_STATEMENT"
    with pytest.raises(JournalConflict) as error:
        adapter.confirm_reconciliation({**request, "account_evidence": {"id": "CHANGED", "kind": kind}})
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("evidence", [{"id": " ", "kind": "broker_statement"},
    {"id": "SYNTHETIC", "kind": "unknown"}, {"id": "SYNTHETIC"}])
def test_external_statement_requires_real_reference_and_kind(service, evidence):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    with pytest.raises(JournalValidationError):
        adapter.confirm_reconciliation({"idempotency_key": "external", "expected_revision": 1,
            "reconciled_at": NOW.isoformat(), "confirmation_note": "SYNTHETIC",
            "cash_checked": True, "positions_checked": True, "fills_checked": True,
            "account_evidence": evidence})
    assert len(service.records()) == 1


def test_internal_replay_keeps_external_gap_until_explicit_statement_confirmation(service, tmp_path):
    adapter = experience.PrivateRiskExperienceService(service.journal)
    request = {"idempotency_key": "internal", "expected_revision": 1,
        "reconciled_at": NOW.isoformat(), "confirmation_note": "SYNTHETIC",
        "cash_checked": True, "positions_checked": True, "fills_checked": True}
    adapter.confirm_reconciliation(request)
    internal = experience.risk_facts_and_gaps(service.journal, repository_root=tmp_path, now=NOW)
    assert "EXTERNAL_ACCOUNT_RECONCILIATION_MISSING" in internal["blockers"]
    assert internal["facts"]["reconciliation_status"] == "RECONCILED"
    assert internal["facts"]["cash_cny"] == "8000"
    assert internal["engine"]["position_guidance"] is None
    adapter.confirm_reconciliation({**request, "idempotency_key": "external", "expected_revision": 2,
        "account_evidence": {"id": "STATEMENT-SYNTHETIC", "kind": "account_statement"}})
    external = experience.risk_facts_and_gaps(service.journal, repository_root=tmp_path, now=NOW)
    assert "EXTERNAL_ACCOUNT_RECONCILIATION_MISSING" not in external["blockers"]
    assert external["blockers"]  # Other genuine risk inputs remain unknown.
    assert external["facts"]["cash_cny"] == "8000"


def test_blocked_engine_keeps_account_facts_and_unknown_market_inputs(service, tmp_path):
    result = experience.risk_facts_and_gaps(service.journal, repository_root=tmp_path, now=NOW)
    assert result["facts"]["cash_cny"] == "8000"
    assert result["facts"]["cost_basis_total_cny"] == "2000"
    assert result["facts"]["positions"][0]["market_value_cny"] is None
    assert result["blockers"]
    assert result["engine"]["position_guidance"] is None


def test_root_routes_share_isolated_journal_auth_and_external_confirmation(service, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession

    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: service.journal.path)
    app = FastAPI()
    secret = "SYNTHETIC-risk-experience-" + "0" * 40
    private_routes.register_private_routes(app, tmp_path, sessions=LocalOperatorSession(bootstrap_secret=secret), port=8001)
    prefix = "/api/v1/private/portfolio/"
    with TestClient(app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 51000)) as client:
        client.headers["origin"] = "http://127.0.0.1:8001"
        assert client.get(prefix + "risk-context/300364").status_code == 401
        for route in ("costs/confirm", "reconciliation/confirm"):
            assert client.post(prefix + route, json={}).status_code == 401
        token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
        client.headers["x-local-session"] = token
        assert client.get(prefix + "risk-context/300364").json()["cost_profile"] is None
        first = client.post(prefix + "costs/confirm", json=costs())
        assert first.status_code == 200, first.text
        assert client.post(prefix + "costs/confirm", json=costs()).json() == first.json()
        assert client.get(prefix + "risk-context/300364").json()["cost_profile"]["costs"] == costs()["costs"]
        request = {"idempotency_key": "route-reconcile", "expected_revision": 2,
            "reconciled_at": NOW.isoformat(), "confirmation_note": "SYNTHETIC checked statement",
            "cash_checked": True, "positions_checked": True, "fills_checked": True,
            "account_evidence": {"id": "STATEMENT-SYNTHETIC", "kind": "broker_statement"}}
        bad = client.post(prefix + "reconciliation/confirm", json={**request, "cash_checked": False})
        assert bad.status_code == 422
        confirmed = client.post(prefix + "reconciliation/confirm", json=request)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["reconciliation_scope"] == "EXTERNAL_ACCOUNT_STATEMENT"
        assert client.post(prefix + "reconciliation/confirm", json=request).json() == confirmed.json()
        assert len(service.records()) == 3

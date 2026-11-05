"""Isolated TEST_ONLY private amounts; never derive actual risk from a stop."""
from datetime import datetime
import hashlib
import json

import pytest

from test_private_ips_policy import service, confirm_policy
from test_portfolio_risk_assessment import _attributes
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalConflict, JournalValidationError,
)
from value_investment_agent.application.product import dual_sleeve_risk as file_review

NOW = datetime.fromisoformat("2026-10-14T20:00:00+08:00")


@pytest.fixture(autouse=True)
def isolated_clock(monkeypatch):
    from value_investment_agent.application.portfolio import private_portfolio_service as journal_module
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(NOW.isoformat())
    monkeypatch.setattr(journal_module, "datetime", Clock)


@pytest.fixture
def pinned(service, tmp_path, monkeypatch):
    confirm_policy(service)
    service.reconcile(dict(idempotency_key="TEST_ONLY-reconciled", expected_revision=len(service.records()),
        reconciled_at=NOW.isoformat(), confirmation_note="TEST_ONLY external statement",
        account_evidence={"id": "TEST_ONLY-statement", "kind": "broker_statement"}))
    monkeypatch.setattr(projection, "_verified_prices", lambda *a: {"300364": {
        "price_cny": "20", "trade_date": NOW.date().isoformat(), "price_admitted": True,
        "current_pit": True, "bundle_sha256": "a" * 64}})
    monkeypatch.setattr(projection, "_verified_attributes", lambda *a, **k: [
        _attributes(symbol="300364").as_policy()])
    replayed = service._replay(service.records())
    data = projection.build_risk_input(replayed, sellable_as_of=NOW.date(),
        repository_root=tmp_path, generated_at=NOW)
    for row in data["allocations"]:
        row.update(committed_risk_cny="100", evidence_ref="TEST_ONLY-explicit-confirmed-risk-basis")
    path = tmp_path / "TEST_ONLY-private-risk.json"
    # Isolated IO substitutes only the outside-Git private directory gate. The
    # real loader still checks exact bytes, JSON, ACTUAL and the risk contract.
    def isolated_path(candidate, **kwargs):
        assert candidate == path and kwargs["private_root"] == tmp_path
        assert candidate.name.startswith("TEST_ONLY")
        return candidate
    monkeypatch.setattr(file_review, "require_private_data_path", isolated_path)
    source = dict(input_path=str(path), private_root=str(tmp_path),
        journal_revision=len(service.records()), journal_tip_sha256=service.records()[-1]["record_sha256"])
    def save():
        path.write_text(json.dumps(data), encoding="utf-8")
        source["input_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save()
    return service, tmp_path, data, source, save


def review(pinned, *, source=True):
    service, root, _, binding, _ = pinned
    return projection.review_private_risk_rehearsal(service.journal,
        generated_at=NOW, today=NOW.date(), repository_root=root,
        committed_risk_source=binding if source else None)


def test_explicit_pinned_existing_contract_supplies_risk_without_journal_writes(pinned):
    service, _, _, binding, _ = pinned
    before = service.journal.path.read_bytes()
    unknown = review(pinned, source=False)
    assert "CORE_VALUE:risk_unknown" in unknown["blockers"]
    result = review(pinned)
    assert "CORE_VALUE:risk_unknown" not in result["blockers"]
    assert result["engine"]["sleeves"]["CORE_VALUE"]["committed_risk_cny"] == "100"
    assert result["engine"]["sleeves"]["CORE_VALUE"]["available_risk_cny"] == "1300"
    assert result["facts"] == unknown["facts"]
    assert result["committed_risk"]["source_binding"]["input_sha256"] == binding["input_sha256"]
    assert result["committed_risk"]["status"] == "COMPLETE"
    assert "input_path" not in result["committed_risk"]["source_binding"]
    assert service.journal.path.read_bytes() == before


def test_explicit_zero_is_not_a_default_for_unknown_risk(pinned):
    _, _, data, _, save = pinned
    data["allocations"][0]["committed_risk_cny"] = "0"
    save()
    result = review(pinned)
    assert result["committed_risk"]["status"] == "COMPLETE"
    assert result["engine"]["sleeves"]["CORE_VALUE"]["committed_risk_cny"] == "0"
    assert review(pinned, source=False)["committed_risk"]["status"] == "BLOCKED_PRIVATE_INPUT"


def test_future_journal_cannot_supply_a_current_risk_binding(pinned):
    service, root, _, source, _ = pinned
    with pytest.raises(ValueError, match="Future or out-of-order"):
        projection.review_private_risk_rehearsal(service.journal,
            generated_at=NOW.replace(hour=19), today=NOW.date(), repository_root=root,
            committed_risk_source=source)


@pytest.mark.parametrize("fault", ["hash", "revision", "tip", "simulated", "account", "cash", "policy",
    "quantity", "sellable", "cost", "sleeve", "unknown_risk", "exhausted", "negative", "missing_evidence"])
def test_pinned_source_cannot_override_current_journal_or_risk_gates(pinned, fault):
    service, _, data, binding, save = pinned
    if fault == "hash": binding["input_sha256"] = "b" * 64
    elif fault == "revision": binding["journal_revision"] -= 1
    elif fault == "tip": binding["journal_tip_sha256"] = "b" * 64
    elif fault == "simulated": data["namespace"] = "SIMULATED"
    elif fault == "account": data["portfolio"]["snapshot"]["account_scope"] = "OTHER"
    elif fault == "cash": data["portfolio"]["snapshot"]["cash_cny"] = "9999"
    elif fault == "policy": data["portfolio"]["policy"]["max_single_security_pct"] = "79"
    elif fault == "quantity": data["allocations"][0]["quantity"] = "99"
    elif fault == "sellable": data["allocations"][0]["sellable_quantity"] = "50"
    elif fault == "cost": data["allocations"][0]["cost_basis_cny"] = "1999"
    elif fault == "sleeve": data["allocations"][0]["sleeve"] = "HOTSPOT_SATELLITE"
    elif fault == "unknown_risk": data["allocations"][0]["committed_risk_cny"] = None
    elif fault == "exhausted": data["allocations"][0]["committed_risk_cny"] = "1400"
    elif fault == "negative": data["allocations"][0]["committed_risk_cny"] = "-1"
    else: data["allocations"][0]["evidence_ref"] = ""
    if fault not in {"hash", "revision", "tip"}: save()
    before = service.journal.path.read_bytes()
    if fault in {"unknown_risk", "exhausted"}:
        result = review(pinned)
        code = "risk_unknown" if fault == "unknown_risk" else "risk_budget_exhausted"
        assert "CORE_VALUE:" + code in result["blockers"]
        assert result["engine"]["status"] != "RISK_REVIEW_CALCULATED"
    else:
        with pytest.raises((ValueError, JournalValidationError, JournalConflict)):
            review(pinned)
    assert service.journal.path.read_bytes() == before


def test_rebinding_stale_amount_does_not_survive_confirmed_fill(pinned):
    service, _, _, binding, _ = pinned
    _, digest = service.prepare_fill(dict(idempotency_key="TEST_ONLY-buy", expected_revision=len(service.records()),
        fill=dict(transaction_id="TEST_ONLY-buy", side="BUY", sleeve="CORE_VALUE", symbol="300364",
            exchange="SZSE", quantity="100", price_cny="20", fees_cny="5", trade_date="2026-10-14",
            next_sell_session="2026-10-15", trading_unit="100")))
    service.confirm_fill(dict(idempotency_key="TEST_ONLY-confirm", expected_revision=len(service.records()),
        prepared_record_sha256=digest, confirmed_at=NOW.isoformat(), confirmation_note="TEST_ONLY"))
    with pytest.raises(JournalConflict): review(pinned)
    binding.update(journal_revision=len(service.records()), journal_tip_sha256=service.records()[-1]["record_sha256"])
    with pytest.raises((ValueError, JournalValidationError)): review(pinned)


def test_journal_change_during_source_validation_rejects_review(pinned, monkeypatch):
    service, _, _, _, _ = pinned
    original = file_review.run_dual_sleeve_review
    def change(**kwargs):
        result = original(**kwargs)
        service.prepare_policy(dict(idempotency_key="TEST_ONLY-concurrent", expected_revision=len(service.records()),
            policy={"investable_assets_cny": "10000"}))
        return result
    monkeypatch.setattr(file_review, "run_dual_sleeve_review", change)
    with pytest.raises(JournalConflict, match="changed during"):
        review(pinned)


def test_actual_source_retains_existing_outside_repository_storage_boundary(pinned, monkeypatch):
    from value_investment_agent.private_portfolio_intake import require_private_data_path
    monkeypatch.setattr(file_review, "require_private_data_path", require_private_data_path)
    with pytest.raises(ValueError):
        review(pinned)


def test_held_projection_receives_only_explicitly_bound_risk_source(pinned):
    from value_investment_agent.application.portfolio.held_continuity import review_held_continuity
    service, root, _, binding, _ = pinned
    result = review_held_continuity(service.journal, repository_root=root, generated_at=NOW,
        authenticated_subject="LOCAL_OPERATOR", plan_provider=lambda symbol: None,
        committed_risk_source=binding)
    assert "CORE_VALUE:risk_unknown" not in result["risk"]["blockers"]
    decision = result["items"][0]["actionable_decisions"][0]
    assert decision["decision_action"] == "UNASSESSABLE"
    assert "PERSONAL_ENTRY_THESIS_CONFIRMATION_REQUIRED" in decision["blockers"]
    assert decision["broker_execution_permission"] is False


def test_unknown_risk_keeps_fee_aware_accounting_after_cross_sleeve_sale_and_restart(service, tmp_path):
    def fill(side, sleeve, quantity, price, key):
        fields = dict(transaction_id=key, side=side, sleeve=sleeve, symbol="300364", exchange="SZSE",
            quantity=quantity, price_cny=price, fees_cny="5", trade_date="2026-10-14")
        if side == "BUY": fields.update(next_sell_session="2026-10-15", trading_unit="100")
        _, digest = service.prepare_fill(dict(idempotency_key=key, expected_revision=len(service.records()), fill=fields))
        service.confirm_fill(dict(idempotency_key=key+"-confirmed", expected_revision=len(service.records()),
            prepared_record_sha256=digest, confirmed_at=NOW.isoformat(), confirmation_note="TEST_ONLY"))
    fill("BUY", "HOTSPOT_SATELLITE", "100", "10", "TEST_ONLY-hotspot-buy")
    fill("SELL", "CORE_VALUE", "50", "30", "TEST_ONLY-core-sale")
    journal = PrivateJournal(service.journal.path)
    restarted = PrivatePortfolioService(journal)
    before = journal.path.read_bytes()
    view = restarted.portfolio_view(generated_at=NOW)
    result = projection.review_private_risk_rehearsal(journal, generated_at=NOW,
        repository_root=tmp_path, today=NOW.date())
    assert view["cash_cny"] == result["facts"]["cash_cny"] == "8490"
    assert view["cost_basis_total_cny"] == result["facts"]["cost_basis_total_cny"] == "2005"
    assert view["realized_pnl_cny"] == result["facts"]["realized_pnl_cny"] == "495"
    missing = result["committed_risk"]["missing_inputs"]
    assert {(row["sleeve"], row["quantity"], row["cost_basis_cny"]) for row in missing} == {
        ("CORE_VALUE", "50", "1000"), ("HOTSPOT_SATELLITE", "100", "1005")}
    assert result["committed_risk"]["automatic_derivation"] is False
    assert result["engine"]["position_guidance"] is None
    assert journal.path.read_bytes() == before

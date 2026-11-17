"""Policy confirmation tests are isolated, never real approvals."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from value_investment_agent.application.decision import value_price_policy as app
from value_investment_agent.domain.decision.value_price_policy import (
    draft_value_price_policy, payload_hash, preview_draft_prices,
)

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def fixture(tmp_path, monkeypatch, *, rules=True, identity=True):
    path = tmp_path / "runtime" / "isolated.json"
    path.parent.mkdir()
    path.write_bytes(b"{}")
    plan = dict(symbol="600887", research_version="isolated-research", model_id="isolated-model" if identity else None,
        model_type="residual_income_or_equity_value", model_version="isolated-v1", profile_id="quality_compounder",
        valuation_input_version="a" * 64, valuation_date="2026-10-11", bear="10", base="12", bull="14",
        source_bindings=[dict(path="runtime/isolated.json", sha256=hashlib.sha256(b"{}").hexdigest())],
        blockers=["G3_PENDING"], action="no_order")
    monkeypatch.setattr(app, "_current_plan", lambda *args: plan)
    draft = draft_value_price_policy(plan, draft_id="isolated-draft", policy_id="isolated-policy",
        rule_version="isolated-rule-v1", profile_id="quality_compounder",
        effective_from=date(2026, 10, 15), effective_through=date(2026, 11, 14),
        rationale="Explicit isolated test choice", dividend_coverage_risk="Cash coverage unknown",
        rules=[dict(action="entry", scenario="bear", value_fraction="0.93", comparison="LTE",
                    rationale="Isolated explicit fraction; never a production default")] if rules else [])
    return plan, draft, path


def receipt(tmp_path, prepared, **changes):
    payload = dict(schema_version="value-price-policy-user-confirmation-v1", action="no_order",
        decision="CONFIRM", draft_sha256=prepared["draft_sha256"],
        prepared_sha256=prepared["prepared_sha256"], confirmed_at=NOW.isoformat(),
        actor="SYNTHETIC_TEST_ONLY")
    payload.update(changes)
    raw = json.dumps(payload).encode()
    path = tmp_path / "runtime/isolated-confirmation.json"
    path.write_bytes(raw)
    return dict(path="runtime/isolated-confirmation.json", sha256=hashlib.sha256(raw).hexdigest())


def test_empty_draft_has_no_default_prices_and_cannot_be_confirmed(tmp_path, monkeypatch):
    _, draft, _ = fixture(tmp_path, monkeypatch, rules=False, identity=False)
    assert all(v is None for v in preview_draft_prices(draft).values())
    prepared = app.prepare_value_price_policy(tmp_path, draft, now=NOW)
    assert prepared["status"] == "BLOCKED"
    assert "VALUE_POLICY_MODEL_IDENTITY_MISSING" in prepared["blockers"]
    assert "VALUE_POLICY_EXPLICIT_ACTION_RULES_REQUIRED" in prepared["blockers"]
    with pytest.raises(ValueError, match="not prepared"):
        app.confirm_value_price_policy(tmp_path, prepared, confirmation_binding={},
                                       authorize_confirmation=lambda r: True, now=NOW)


def test_prepare_is_not_registration_and_does_not_clear_g3(tmp_path, monkeypatch):
    _, draft, _ = fixture(tmp_path, monkeypatch)
    before = deepcopy(draft)
    prepared = app.prepare_value_price_policy(tmp_path, draft, now=NOW)
    assert prepared["draft_prices"]["entry"] == "9.30"
    assert prepared["status"] == "PREPARED_PENDING_USER_CONFIRMATION"
    assert prepared["registered"] is False and prepared["formal_eligibility"] is False
    assert prepared["portfolio_eligibility"] is None
    assert prepared["existing_research_blockers"] == ["G3_PENDING"]
    assert draft == before


def test_only_external_authorized_confirmation_returns_registry_candidate(tmp_path, monkeypatch):
    _, draft, _ = fixture(tmp_path, monkeypatch)
    prepared = app.prepare_value_price_policy(tmp_path, draft, now=NOW)
    binding = receipt(tmp_path, prepared)
    with pytest.raises(ValueError, match="authorized user"):
        app.confirm_value_price_policy(tmp_path, prepared, confirmation_binding=binding,
                                       authorize_confirmation=lambda r: False, now=NOW)
    result = app.confirm_value_price_policy(tmp_path, prepared, confirmation_binding=binding,
                                           authorize_confirmation=lambda r: r["actor"] == "SYNTHETIC_TEST_ONLY", now=NOW)
    assert result["status"] == "REGISTERED" and result["action"] == "no_order"
    assert result["policies"][0]["confirmation_binding"] == binding
    assert not (tmp_path / "config").exists()


@pytest.mark.parametrize("fault", ["source", "basis", "profile", "prepared", "receipt", "future"])
def test_tampering_or_basis_change_fails_closed(tmp_path, monkeypatch, fault):
    plan, draft, path = fixture(tmp_path, monkeypatch)
    prepared = app.prepare_value_price_policy(tmp_path, draft, now=NOW)
    binding = receipt(tmp_path, prepared)
    if fault == "source":
        path.write_bytes(b"changed")
    elif fault == "basis":
        plan["valuation_input_version"] = "b" * 64
    elif fault == "profile":
        plan["profile_id"] = "cyclical"
    elif fault == "prepared":
        prepared["draft"]["rules"][0]["value_fraction"] = "1.2"
    elif fault == "receipt":
        binding = receipt(tmp_path, prepared, prepared_sha256="c" * 64)
    else:
        binding = receipt(tmp_path, prepared, confirmed_at=(NOW + timedelta(days=1)).isoformat())
    with pytest.raises(ValueError):
        app.confirm_value_price_policy(tmp_path, prepared, confirmation_binding=binding,
                                       authorize_confirmation=lambda r: True, now=NOW)


def test_draft_change_requires_new_preparation_and_no_implicit_rule(tmp_path, monkeypatch):
    _, draft, _ = fixture(tmp_path, monkeypatch)
    changed = deepcopy(draft)
    changed["rules"][0].pop("value_fraction")
    with pytest.raises(KeyError):
        preview_draft_prices(changed)
    changed = deepcopy(draft)
    changed["rules"][0]["rationale"] = "Different rationale"
    assert payload_hash(draft) != payload_hash(changed)


def test_confirmed_candidate_is_compatible_with_existing_registered_policy_loader(tmp_path, monkeypatch):
    from value_investment_agent.application.decision import value_action_plan as plans
    _, draft, _ = fixture(tmp_path, monkeypatch)
    prepared = app.prepare_value_price_policy(tmp_path, draft, now=NOW)
    binding = receipt(tmp_path, prepared)
    candidate = app.confirm_value_price_policy(tmp_path, prepared, confirmation_binding=binding,
        authorize_confirmation=lambda r: r["actor"] == "SYNTHETIC_TEST_ONLY", now=NOW)
    raw = json.dumps(candidate).encode()
    (tmp_path / "runtime/isolated-registry.json").write_bytes(raw)
    registry_binding = dict(path="runtime/isolated-registry.json", sha256=hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(plans, "load_current_chain", lambda root: dict(model=dict(
        product_extensions=dict(value_action_policy_registry=registry_binding))))
    policy = plans.load_value_action_policy(root=tmp_path, binding=registry_binding,
                                            symbol="600887", now=NOW)
    assert policy.model_id == "isolated-model"
    assert policy.rules[0].value_fraction == Decimal("0.93")


def test_expired_or_invalid_rule_draft_cannot_prepare(tmp_path, monkeypatch):
    _, draft, _ = fixture(tmp_path, monkeypatch)
    draft["effective_from"] = "2026-09-01"
    draft["effective_through"] = "2026-10-13"
    assert "VALUE_POLICY_EXPIRED" in app.prepare_value_price_policy(tmp_path, draft, now=NOW)["blockers"]
    draft["rules"][0]["comparison"] = "GTE"
    with pytest.raises(ValueError, match="comparison"):
        app.prepare_value_price_policy(tmp_path, draft, now=NOW)

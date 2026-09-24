from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

from value_investment_agent.portfolio_contracts import (
    CONFIRMATION_DRAFT,
    CONFIRMATION_HUMAN,
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    QUANTITY_HUMAN_CONFIRMED,
    QUANTITY_PENDING_RECONCILIATION,
    RECONCILIATION_RECONCILED,
    RECONCILIATION_UNCONFIRMED,
    RISK_BALANCED,
    RISK_UNKNOWN,
    InvestorPolicyStatement,
    PortfolioHolding,
    PortfolioInputBundle,
    PortfolioSnapshot,
    investor_policy_statement_from_payload,
    portfolio_input_bundle_from_payload,
    portfolio_snapshot_from_payload,
)


AS_OF = date(2026, 9, 22)
CONFIRMED_AT = datetime(2026, 9, 22, 10, 30, tzinfo=timezone.utc)
AVAILABLE_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _policy(
    *,
    confirmation: str = CONFIRMATION_HUMAN,
    **changes,
) -> InvestorPolicyStatement:
    payload = {
        "policy_id": "user-policy-v1",
        "policy_version": "20260922-v1",
        "as_of": AS_OF,
        "confirmation_status": confirmation,
        "confirmed_at": CONFIRMED_AT if confirmation == CONFIRMATION_HUMAN else None,
        "account_scope": "个人A股长期账户",
        "investable_assets_cny": Decimal("1000000"),
        "minimum_cash_cny": Decimal("100000"),
        "emergency_cash_cny": Decimal("150000"),
        "liquidity_needs_cny": Decimal("50000"),
        "time_horizon_years": Decimal("10"),
        "max_single_security_pct": Decimal("15"),
        "max_single_industry_pct": Decimal("30"),
        "max_cyclical_exposure_pct": Decimal("25"),
        "dividend_income_goal_cny": Decimal("30000"),
        "risk_tolerance": RISK_BALANCED,
        "concentration_allowed": False,
        "tax_regime": "中国大陆个人证券账户",
        "restrictions": ("no_order", "no_leverage", "no_derivatives"),
        "evidence_refs": ({"id": "user-confirmation-v1"},),
    }
    payload.update(changes)
    return InvestorPolicyStatement(**payload)


def _holding(
    *,
    source: str = QUANTITY_HUMAN_CONFIRMED,
) -> PortfolioHolding:
    return PortfolioHolding(
        symbol="600519",
        exchange="SSE",
        quantity=Decimal("100"),
        cost_basis_cny=Decimal("150000"),
        market_value_cny=Decimal("160000"),
        quantity_source=source,
        corporate_action_adjusted=True,
        evidence_refs=({"id": f"{source}-600519"},),
    )


def _snapshot(
    *,
    namespace: str = NAMESPACE_ACTUAL,
    reconciliation: str = RECONCILIATION_RECONCILED,
    **changes,
) -> PortfolioSnapshot:
    payload = {
        "snapshot_id": "snapshot-v1",
        "snapshot_version": "20260922-v1",
        "as_of": AS_OF,
        "available_at": AVAILABLE_AT,
        "account_scope": "个人A股长期账户",
        "namespace": namespace,
        "cash_cny": Decimal("200000"),
        "holdings": (_holding(),),
        "reconciliation_status": reconciliation,
        "reconciled_at": CONFIRMED_AT if reconciliation == RECONCILIATION_RECONCILED else None,
        "evidence_refs": ({"id": "broker-statement-v1"},),
    }
    payload.update(changes)
    return PortfolioSnapshot(**payload)


def test_missing_policy_fails_closed_and_names_required_inputs():
    policy = InvestorPolicyStatement.missing(as_of=AS_OF)

    assert policy.is_human_confirmed is False
    assert not policy.can_support_guidance()
    assert "human_confirmation" in policy.missing_guidance_inputs()
    assert "investable_assets_cny" in policy.missing_guidance_inputs()
    assert policy.action == "no_order"
    assert policy.sensitivity == "PRIVATE_USER_CONFIRMED"


def test_confirmed_policy_round_trips_without_inventing_preferences():
    policy = _policy()

    assert policy.is_human_confirmed
    assert policy.can_support_guidance()
    restored = investor_policy_statement_from_payload(policy.as_policy())
    assert restored == policy
    assert json.loads(policy.to_json())["action"] == "no_order"
    assert "target_weight" not in policy.as_policy()
    assert "order_quantity" not in policy.as_policy()


def test_policy_rejects_invalid_amounts_percentages_and_draft_confirmation_time():
    with pytest.raises(ValueError, match="cannot be negative"):
        _policy(investable_assets_cny=Decimal("-1"))
    with pytest.raises(ValueError, match="must be in"):
        _policy(max_single_security_pct=Decimal("101"))
    with pytest.raises(ValueError, match="must be positive"):
        _policy(time_horizon_years=Decimal("0"))
    with pytest.raises(ValueError, match="cannot carry confirmed_at"):
        _policy(
            confirmation=CONFIRMATION_DRAFT,
            confirmed_at=CONFIRMED_AT,
        )
    with pytest.raises(ValueError, match="Unknown investor risk tolerance"):
        _policy(risk_tolerance="VERY_HIGH_UNREGISTERED")


def test_snapshot_requires_reconciliation_and_unique_confirmed_holdings():
    snapshot = _snapshot()

    assert snapshot.is_reconciled
    assert snapshot.can_support_real_guidance()
    restored = portfolio_snapshot_from_payload(snapshot.as_policy())
    assert restored == snapshot

    with pytest.raises(ValueError, match="unique by symbol"):
        _snapshot(holdings=(_holding(), _holding()))
    with pytest.raises(ValueError, match="requires reconciliation evidence"):
        _snapshot(evidence_refs=())
    with pytest.raises(ValueError, match="requires cash"):
        _snapshot(cash_cny=None)
    with pytest.raises(ValueError, match="confirmed holdings"):
        _snapshot(holdings=(_holding(source=QUANTITY_PENDING_RECONCILIATION),))


def test_snapshot_loader_rejects_string_boolean_and_nested_execution_key():
    payload = _snapshot().as_policy()
    payload["holdings"][0]["corporate_action_adjusted"] = "false"
    with pytest.raises(ValueError, match="must be boolean"):
        portfolio_snapshot_from_payload(payload)

    payload = _snapshot().as_policy()
    payload["holdings"][0]["target_weight"] = "10"
    with pytest.raises(ValueError, match="execution keys"):
        portfolio_snapshot_from_payload(payload)


def test_unreconciled_and_simulated_snapshots_cannot_drive_real_guidance():
    unreconciled = _snapshot(
        reconciliation=RECONCILIATION_UNCONFIRMED,
        reconciled_at=None,
    )
    simulated = _snapshot(namespace=NAMESPACE_SIMULATED)

    assert "reconciliation" in unreconciled.missing_guidance_inputs()
    assert not unreconciled.can_support_real_guidance()
    assert "actual_namespace" in simulated.missing_guidance_inputs()
    assert not simulated.can_support_real_guidance()


def test_bundle_requires_same_scope_and_earlier_or_equal_policy_date():
    bundle = PortfolioInputBundle(policy=_policy(), snapshot=_snapshot())

    assert bundle.can_support_guidance()
    restored = portfolio_input_bundle_from_payload(bundle.as_policy())
    assert restored == bundle
    assert bundle.missing_guidance_inputs() == ()
    assert bundle.action == "no_order"

    with pytest.raises(ValueError, match="account scopes must match"):
        PortfolioInputBundle(
            policy=_policy(account_scope="另一个账户"),
            snapshot=_snapshot(),
        )
    with pytest.raises(ValueError, match="cannot be dated after"):
        PortfolioInputBundle(
            policy=_policy(as_of=AS_OF.replace(day=23)),
            snapshot=_snapshot(as_of=AS_OF),
        )


def test_missing_bundle_never_claims_personal_guidance_capacity():
    bundle = PortfolioInputBundle.missing(as_of=AS_OF)

    assert not bundle.can_support_guidance()
    assert any(item.startswith("policy.") for item in bundle.missing_guidance_inputs())
    assert any(item.startswith("snapshot.") for item in bundle.missing_guidance_inputs())
    assert bundle.action == "no_order"
    assert bundle.sensitivity == "PRIVATE_USER_CONFIRMED"

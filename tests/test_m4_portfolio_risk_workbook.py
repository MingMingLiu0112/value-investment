from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path

import pytest

from value_investment_agent.portfolio_contracts import (
    CONFIRMATION_HUMAN,
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_RECONCILED,
    RISK_BALANCED,
    InvestorPolicyStatement,
    PortfolioHolding,
    PortfolioInputBundle,
    PortfolioSnapshot,
)
from value_investment_agent.portfolio_risk import (
    ASSESSMENT_NAMESPACE_SIMULATED,
    LIQUIDITY_LIQUID,
    SecurityRiskAttributes,
    build_portfolio_risk_assessment,
)
from value_investment_agent.m4_portfolio_risk_workbook import (
    BOUNDARY_SHEET,
    FINDINGS_SHEET,
    HOLDINGS_SHEET,
    OVERVIEW_SHEET,
    build_portfolio_risk_workbook,
    write_portfolio_risk_workbook,
)


AS_OF = date(2026, 9, 22)
CONFIRMED_AT = datetime(2026, 9, 22, 10, 30, tzinfo=timezone.utc)
AVAILABLE_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
GENERATED_AT = datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc)


def _assessment(
    *,
    snapshot_namespace: str = NAMESPACE_SIMULATED,
    assessment_namespace: str = ASSESSMENT_NAMESPACE_SIMULATED,
):
    policy = InvestorPolicyStatement(
        policy_id="sim-policy-v1",
        policy_version="20260922-v1",
        as_of=AS_OF,
        confirmation_status=CONFIRMATION_HUMAN,
        confirmed_at=CONFIRMED_AT,
        account_scope="SIMULATED_PUBLIC_DEMO",
        investable_assets_cny=Decimal("2000000"),
        minimum_cash_cny=Decimal("200000"),
        emergency_cash_cny=Decimal("300000"),
        liquidity_needs_cny=Decimal("100000"),
        time_horizon_years=Decimal("10"),
        max_single_security_pct=Decimal("25"),
        max_single_industry_pct=Decimal("40"),
        max_cyclical_exposure_pct=Decimal("30"),
        dividend_income_goal_cny=Decimal("30000"),
        risk_tolerance=RISK_BALANCED,
        concentration_allowed=False,
        tax_regime="模拟税务口径",
        restrictions=("no_order", "no_leverage"),
        evidence_refs=({"id": "sim-policy-confirmation"},),
    )

    def holding(symbol: str, market_value: str) -> PortfolioHolding:
        return PortfolioHolding(
            symbol=symbol,
            exchange="SSE" if symbol.startswith("6") else "SZSE",
            quantity=Decimal("100"),
            cost_basis_cny=Decimal(market_value),
            market_value_cny=Decimal(market_value),
            quantity_source=QUANTITY_HUMAN_CONFIRMED,
            corporate_action_adjusted=True,
            evidence_refs=({"id": f"sim-holding-{symbol}"},),
        )

    snapshot = PortfolioSnapshot(
        snapshot_id="sim-snapshot-v1",
        snapshot_version="20260922-v1",
        as_of=AS_OF,
        available_at=AVAILABLE_AT,
        account_scope="SIMULATED_PUBLIC_DEMO",
        namespace=snapshot_namespace,
        cash_cny=Decimal("350000"),
        holdings=(
            holding("600519", "500000"),
            holding("000333", "300000"),
            holding("601088", "450000"),
        ),
        reconciliation_status=RECONCILIATION_RECONCILED,
        reconciled_at=CONFIRMED_AT,
        evidence_refs=({"id": "sim-broker-statement"},),
    )
    attributes = {
        "600519": SecurityRiskAttributes(
            symbol="600519",
            industry="消费",
            cyclical=False,
            liquidity_profile=LIQUIDITY_LIQUID,
            common_factors=("brand",),
            evidence_refs=({"id": "sim-risk-600519"},),
        ),
        "000333": SecurityRiskAttributes(
            symbol="000333",
            industry="耐用制造",
            cyclical=False,
            liquidity_profile=LIQUIDITY_LIQUID,
            common_factors=("manufacturing",),
            evidence_refs=({"id": "sim-risk-000333"},),
        ),
        "601088": SecurityRiskAttributes(
            symbol="601088",
            industry="能源",
            cyclical=True,
            liquidity_profile=LIQUIDITY_LIQUID,
            common_factors=("energy_cycle",),
            evidence_refs=({"id": "sim-risk-601088"},),
        ),
    }
    return build_portfolio_risk_assessment(
        bundle=PortfolioInputBundle(policy=policy, snapshot=snapshot),
        security_attributes=attributes,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
        assessment_id="sim-risk-assessment-v1",
        assessment_namespace=assessment_namespace,
    )


def test_workbook_has_expected_sheets_and_no_forbidden_text():
    assessment = _assessment()
    workbook = build_portfolio_risk_workbook(
        assessment,
        security_names={"600519": "贵州茅台", "000333": "美的集团", "601088": "中国神华"},
    )
    text = "\n".join(
        str(cell.value)
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert workbook.sheetnames == [
        OVERVIEW_SHEET,
        HOLDINGS_SHEET,
        FINDINGS_SHEET,
        BOUNDARY_SHEET,
    ]
    assert workbook[OVERVIEW_SHEET]["A1"].value == "M4 组合风险与集中度（模拟演示）"
    assert workbook[OVERVIEW_SHEET]["A5"].value == "评估命名空间"
    assert "贵州茅台" in text
    assert "no_order" in text
    assert "SIMULATED" in text
    assert "目标仓位" not in text
    assert "下单" not in text
    assert "position_size" not in text


def test_public_workbook_rejects_actual_assessment():
    assessment = _assessment(
        snapshot_namespace=NAMESPACE_ACTUAL,
        assessment_namespace="ACTUAL",
    )
    with pytest.raises(ValueError, match="simulated assessment"):
        build_portfolio_risk_workbook(
            assessment
        )


def test_writer_is_hash_pinned_and_never_overwrites(tmp_path):
    result = write_portfolio_risk_workbook(
        _assessment(),
        output=tmp_path / "m4-risk.xlsx",
        root=tmp_path,
        security_names={"600519": "贵州茅台", "000333": "美的集团", "601088": "中国神华"},
    )
    target = tmp_path / result["workbook_path"]

    assert target.exists()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == result["workbook_sha256"]
    assert result["sheet_count"] == 4
    assert result["holding_count"] == 3
    assert result["action"] == "no_order"

    with pytest.raises(ValueError, match="already exists"):
        write_portfolio_risk_workbook(
            _assessment(),
            output=tmp_path / "m4-risk.xlsx",
            root=tmp_path,
        )

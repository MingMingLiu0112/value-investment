from datetime import date
from decimal import Decimal
from pathlib import Path

from value_investment_agent.current_execution_contract import build_current_execution_contract


ROOT = Path(__file__).resolve().parents[1]


def test_current_contract_fails_closed_when_next_session_has_no_dated_fee_or_liquidity_evidence():
    contract = build_current_execution_contract(
        root=ROOT,
        quote_report=ROOT / "runtime/quote-sessions/20260918T085008745232Z/report.json",
        suspension_evidence=ROOT / "runtime/exchange-suspension-probes/moutai-current-suspension-20260917T063254Z/evidence.json",
        liquidity_evidence=None,
        fee_policy_evidence=None,
        next_session=date(2026, 9, 21), prior_close=Decimal("1266.98"),
    )
    assert contract["execution_ready"] is False
    assert contract["trade_approved"] is False
    assert contract["price_limit_down"] == "1140.28"
    assert contract["price_limit_up"] == "1393.68"
    assert "dated_fee_policy_missing_for_next_session" in contract["blockers"]
    assert "prior_known_liquidity_budget_missing" in contract["blockers"]


def test_refreshed_official_suspension_and_fee_evidence_leave_only_liquidity_blocked():
    contract = build_current_execution_contract(
        root=ROOT,
        quote_report=ROOT / "runtime/quote-sessions/20260918T085008745232Z/report.json",
        suspension_evidence=ROOT / "runtime/exchange-suspension-probes/moutai-current-suspension-20260918T115153Z/evidence.json",
        liquidity_evidence=None,
        fee_policy_evidence=ROOT / "runtime/trading-rule-evidence/current-sse-paper-fee-policy-20260921/evidence.json",
        next_session=date(2026, 9, 21), prior_close=Decimal("1266.98"),
    )
    assert contract["execution_ready"] is False
    assert contract["blockers"] == ["prior_known_liquidity_budget_missing"]


def test_complete_prior_known_evidence_allows_only_paper_execution_mechanics():
    contract = build_current_execution_contract(
        root=ROOT,
        quote_report=ROOT / "runtime/quote-sessions/20260918T085008745232Z/report.json",
        suspension_evidence=ROOT / "runtime/exchange-suspension-probes/moutai-current-suspension-20260918T115153Z/evidence.json",
        liquidity_evidence=ROOT / "runtime/strategy-validation/moutai-prior-liquidity-budget-20260918/evidence.json",
        fee_policy_evidence=ROOT / "runtime/trading-rule-evidence/current-sse-paper-fee-policy-20260921/evidence.json",
        next_session=date(2026, 9, 21), prior_close=Decimal("1266.98"),
    )
    assert contract["execution_ready"] is True
    assert contract["blockers"] == []
    assert contract["trade_approved"] is False
    assert contract["live_eligible"] is False

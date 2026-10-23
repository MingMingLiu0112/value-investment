"""Disposable scripted account journey using the existing journal and risk engine."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ...domain.execution.exchange_calendar import next_exchange_session
from ...domain.portfolio.dual_sleeve_risk import CORE, HOTSPOT, review_dual_sleeve_risk
from ...portfolio_risk import SecurityRiskAttributes
from .private_portfolio_service import PrivateJournal, PrivatePortfolioService, JournalValidationError
from .private_risk_projection import _allocations_payload, _policy_payload, _snapshot_payload, _sleeve_policy


SCHEMA = "simulated-trade-journey-v1"
SYMBOL = format(600519, "06d")
ACCOUNT = "SIMULATED_DISPOSABLE_DUAL_SLEEVE_JOURNEY"


def _policy(day):
    return dict(investable_assets_cny="10000", core_value_budget_cny="5000",
        hotspot_budget_cny="3000", cash_reserve_cny="2000", minimum_cash_cny="2000",
        emergency_cash_cny="0", liquidity_needs_cny="0", max_single_security_pct="80",
        max_single_industry_pct="90", max_cyclical_exposure_pct="70", max_factor_pct="100",
        hotspot_single_trade_risk_pct="5", max_drawdown_pct="20", financing_allowed=False,
        risk_tools_allowed=False, dividend_income_goal_cny="0", effective_date=day.isoformat(),
        time_horizon_years="5", risk_tolerance="BALANCED", concentration_allowed=True,
        restrictions=["no_order", "SIMULATED_ONLY"], tax_regime="SIMULATED_FEE_FIXTURE",
        sleeves={CORE: dict(cash_cny="5000", risk_budget_cny="1000"),
            HOTSPOT: dict(cash_cny="3000", risk_budget_cny="500", single_security_risk_cny="300")})


def _replayed(service):
    state = service._replay(service.records())
    if state is None:
        raise ValueError("Simulation account was not initialized")
    return state


def _state(service, moment):
    replay = _replayed(service)
    view = service._portfolio_payload(replay, today=moment.date())
    _, sleeves, reserve = _sleeve_policy(replay)
    return dict(namespace="SIMULATED", cash_cny=view["cash_cny"], positions=view["positions"],
        realized_pnl_cny=view["realized_pnl_cny"], revision=view["revision"],
        pending_draft=view["pending_draft"] is not None, cash_reserve_cny=reserve,
        sleeve_cash_cny={name: row["cash_cny"] for name, row in sleeves.items()},
        confirmed_fees_cny=str(sum((Decimal(row["fees_cny"]) for row in replay.trades), Decimal(0))))


def _risk(service, moment, *, sleeve=None, price="10"):
    replay = _replayed(service)
    shared, sleeves, reserve = _sleeve_policy(replay)
    # Explicit hypothetical percentage caps coexist with the stricter fixed
    # capital budgets from the real adapter. Fees must not require transferring
    # cash from another sleeve simply to stay on an exact initial percentage.
    shared.update(policy_scope="SYNTHETIC_POLICY_ONLY", core_value_budget="0.60",
        tactical_hotspot_budget="0.35", cash_floor="0.05")
    marks = {SYMBOL: dict(price_cny=price, trade_date=moment.date().isoformat())}
    snapshot = _snapshot_payload(replay, marks)
    # The legacy journal has a fixed internal namespace. Only this disposable
    # adapter projects it as SIMULATED; no ACTUAL risk input is ever evaluated.
    snapshot["namespace"] = "SIMULATED"
    policy = _policy_payload(replay)
    policy["sensitivity"] = "SIMULATED_DEMONSTRATION"
    allocations = _allocations_payload(replay, moment.date())
    for row in allocations:
        row.update(committed_risk_cny="100", evidence_ref="SIMULATED_EXPLICIT_RISK_100_PER_SLEEVE")
    common = dict(symbol=SYMBOL, entry_price_cny=price, entry_slippage_cny="0",
        buy_fee_fraction="0", minimum_buy_fee_cny="5", lot_size=100,
        max_trade_notional_cny="1200", quote_as_of=moment.date().isoformat(),
        available_at=moment.isoformat(), valid_until=(moment + timedelta(hours=1)).isoformat(),
        liquidity_verified=True, limit_up=False, limit_down=False)
    hotspot = (dict(common, sleeve=HOTSPOT, stop_price_cny="9", gap_stress_cny="0.1",
        exit_slippage_cny="0.1", sell_fee_fraction="0", minimum_sell_fee_cny="5",
        research_version_sha256=sha256(b"SIMULATED_HOTSPOT_THESIS").hexdigest(),
        evidence_ref="SIMULATED_PRICE_AND_STRUCTURE") if sleeve == HOTSPOT else None)
    payload = dict(schema_version="dual-sleeve-risk-input-v1", action="no_order", namespace="SIMULATED",
        portfolio=dict(action="no_order", policy=policy, snapshot=snapshot),
        shared_budget=shared, sleeves=sleeves, cash_reserve_cny=reserve, allocations=allocations,
        security_attributes=[SecurityRiskAttributes(SYMBOL, "SIMULATED_INDUSTRY", False,
            "LIQUID", ("SIMULATED_COMMON_FACTOR",), ({"id": "SIMULATED_ATTRIBUTE"},)).as_policy()],
        hotspot_request=hotspot)
    return review_dual_sleeve_risk(payload, generated_at=moment, allow_synthetic=True,
        core_request=common if sleeve == CORE else None)


def run_simulated_trade_journey(root: Path, now: datetime) -> dict:
    """Run scripted intentions, then remove the entire isolated journal.

    Prices, research, policy and risk assertions below are explicitly synthetic.
    Confirmation calls exercise the existing ledger contract only; they grant
    no model, G3, human-review or actual-account approval.
    """
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Simulation requires an aware timestamp")
    root = Path(root).resolve(strict=True)
    temporary = root / ".tmp"
    if temporary.is_symlink():
        raise ValueError("Simulation temporary directory must not be a symlink")
    temporary.mkdir(exist_ok=True)
    if temporary.resolve().parent != root:
        raise ValueError("Simulation must remain within the supplied workspace")
    opening = datetime.fromisoformat("2026-10-20T15:30:00+08:00")
    later = opening.replace(day=21)
    if now < later:
        raise ValueError("Simulation clock cannot precede the final scripted session")
    clock = [opening]
    steps, idempotency = [], []
    with TemporaryDirectory(prefix="simulated-journey-", dir=temporary) as directory:
        journal = Path(directory) / "SIMULATED-journal.jsonl"
        service = PrivatePortfolioService(PrivateJournal(journal), clock=lambda: clock[0])
        service.initialize(dict(idempotency_key="SIMULATED-init", expected_revision=0,
            account_scope=ACCOUNT, as_of=opening.date().isoformat(), cash_cny="10000",
            holdings=[], sleeve_allocations={}, policy={}, confirmed_at=opening.isoformat(),
            confirmation_note="SIMULATED fixture initialization; no real account"))
        _, policy_hash = service.prepare_policy(dict(idempotency_key="SIMULATED-policy",
            expected_revision=len(service.records()), policy=_policy(opening.date())))
        service.confirm_policy(dict(idempotency_key="SIMULATED-policy-confirm",
            expected_revision=len(service.records()), prepared_record_sha256=policy_hash,
            confirmed_at=opening.isoformat(), confirmation_note="SIMULATED policy fixture only"))

        def reconcile(key):
            service.reconcile(dict(idempotency_key=key, expected_revision=len(service.records()),
                reconciled_at=clock[0].isoformat(), confirmation_note="SIMULATED internal replay only"))

        def fill(label, sleeve, side, price, rationale):
            reconcile("SIMULATED-reconcile-" + label)
            before = _state(service, clock[0])
            risk = _risk(service, clock[0], sleeve=sleeve if side == "BUY" else None, price=price)
            if side == "BUY":
                sizing = risk["core_quantity_review" if sleeve == CORE else "hotspot_quantity_review"]
                if sizing.get("review_quantity") is None or sizing["review_quantity"] < 100:
                    raise ValueError("Synthetic scenario rejected by existing risk engine: " + str(sizing))
            fields = dict(transaction_id="SIMULATED-" + label, side=side, sleeve=sleeve,
                symbol=SYMBOL, exchange="SSE", quantity="100", price_cny=price,
                fees_cny="5", trade_date=clock[0].date().isoformat())
            if side == "BUY":
                fields.update(trading_unit="100", next_sell_session=next_exchange_session(
                    "SSE", clock[0].date()).isoformat())
            prepared, digest = service.prepare_fill(dict(idempotency_key="SIMULATED-prepare-" + label,
                expected_revision=len(service.records()), fill=fields, note="SIMULATED scripted fill"))
            draft = _state(service, clock[0])
            if draft["cash_cny"] != before["cash_cny"] or draft["positions"] != before["positions"]:
                raise ValueError("Prepared draft altered confirmed holdings")
            request = dict(idempotency_key="SIMULATED-confirm-" + label,
                expected_revision=len(service.records()), prepared_record_sha256=digest,
                confirmed_at=clock[0].isoformat(), confirmation_note="SIMULATED confirmation fixture")
            first = service.confirm_fill(request)
            length = len(service.records())
            repeated = service.confirm_fill(request)
            idempotency.append(first == repeated and len(service.records()) == length)
            steps.append(dict(label=label, namespace="SIMULATED", intention=side,
                sleeve=sleeve, rationale=rationale, quantity="100", price_cny=price, fees_cny="5",
                before=before, prepared_state=draft, draft_cash_cny=prepared["draft"]["cash_cny"],
                after=_state(service, clock[0]), risk_review=risk, confirmation_idempotent=idempotency[-1]))

        fill("CORE_BUY", CORE, "BUY", "10", "SIMULATED: thesis intact; illustrative value exceeds price; risk capacity permits the scripted starter.")
        fill("HOTSPOT_BUY", HOTSPOT, "BUY", "10", "SIMULATED: breakout fixture meets predeclared structure, loss and sleeve cash constraints.")
        fill("CORE_ADD", CORE, "BUY", "9", "SIMULATED: price falls while assumed intrinsic value and original thesis remain unchanged; do not add on price alone.")
        reconcile("SIMULATED-reconcile-HOLD")
        held = _state(service, clock[0])
        steps.append(dict(label="HOLD", namespace="SIMULATED", intention="HOLD", sleeve=CORE,
            rationale="SIMULATED: original cash-generation thesis remains intact; no deterioration fixture is active.",
            before=held, after=held, risk_review=_risk(service, clock[0])))
        records_before = journal.read_bytes()
        try:
            service.prepare_fill(dict(idempotency_key="SIMULATED-same-day-sell",
                expected_revision=len(service.records()), fill=dict(transaction_id="SIMULATED-T1",
                    side="SELL", sleeve=CORE, symbol=SYMBOL, exchange="SSE", quantity="100",
                    price_cny="10", fees_cny="5", trade_date=opening.date().isoformat())))
        except JournalValidationError as error:
            if "insufficient sellable shares" not in str(error):
                raise
            rejected = journal.read_bytes() == records_before
        else:
            raise ValueError("Existing engine unexpectedly permitted a T+1 violation")
        steps.append(dict(label="T_PLUS_ONE_REJECTED", namespace="SIMULATED", intention="REJECTED",
            before=held, after=_state(service, clock[0]), rejected_without_journal_write=rejected,
            reason="Existing reconciliation engine rejected insufficient sellable shares."))
        clock[0] = later
        fill("CORE_REDUCE", CORE, "SELL", "11", "SIMULATED: reduce valuation exposure after partial thesis fulfillment; remaining thesis still intact.")
        fill("CORE_EXIT", CORE, "SELL", "11", "SIMULATED: new evidence fixture breaks the original cash-generation thesis; exit relates to the original reason for buying.")
        fill("HOTSPOT_EXIT", HOTSPOT, "SELL", "9", "SIMULATED: the original breakout fails at its protection condition after settlement; fill price is a fixture, not guaranteed execution.")
        reconcile("SIMULATED-reconcile-final")
        final = _state(service, clock[0])
        restarted = PrivatePortfolioService(PrivateJournal(journal), clock=lambda: clock[0])
        restart_equal = final == _state(restarted, clock[0])
        final_risk = _risk(restarted, clock[0])
        journal_hash = sha256(journal.read_bytes()).hexdigest()
        journal_count = len(service.records())
    result = dict(schema_version=SCHEMA, namespace="SIMULATED", action="no_order",
        status="SIMULATED_JOURNEY_COMPLETE", account_scope=ACCOUNT, generated_at=now.isoformat(),
        actual_account_used=False, broker_execution_permission=False, strategy_validated=False,
        approval_changed=False, steps=steps, final_state=final, final_risk_review=final_risk,
        checks=dict(confirmation_idempotency=all(idempotency), restart_equality=restart_equal,
            same_day_sell_rejected=rejected, temporary_journal_removed=not journal.exists(),
            prepared_drafts_have_no_cash_effect=all(row["before"]["cash_cny"] == row["prepared_state"]["cash_cny"]
                and row["before"]["positions"] == row["prepared_state"]["positions"]
                for row in steps if "prepared_state" in row)),
        journal_receipt=dict(sha256=journal_hash, record_count=journal_count, retained=False),
        assumptions=dict(all_inputs="SYNTHETIC_SCENARIO_NOT_OFFICIAL_RESEARCH", initial_cash_cny="10000",
            fees="5 CNY per confirmed fill; illustrative total cost, not a current exchange fee schedule",
            shared_symbol=SYMBOL, price_scope="SYNTHETIC_FIXED_PRICES_NOT_MARKET_QUOTES",
            shared_percentage_caps=dict(core="0.60", hotspot="0.35", cash_floor="0.05"),
            fixed_capital_budgets_cny=dict(core="5000", hotspot="3000", reserve="2000"),
            research="Illustrative cash-generation thesis; no actual ResearchGate, valuation or price approval",
            entry_thesis="SIMULATED: stable recurring earnings and distributions justify a starter; add only while unchanged; exit if permanently impaired",
            committed_risk="Explicit synthetic 100 CNY per held sleeve; not inferred actual risk",
            legacy_contract_flags="Confirmation and reconciliation fields exercise isolated fixtures only; no actual human or financial approval",
            dates=[opening.date().isoformat(), later.date().isoformat()]),
        actual_engine_provenance=dict(journal_service="PrivatePortfolioService", journal="PrivateJournal",
            cash_projection="private_risk_projection._sleeve_policy", settlement="web_reconciliation.prepare",
            risk="domain.portfolio.dual_sleeve_risk.review_dual_sleeve_risk", allow_synthetic=True,
            separate_ledger=False, test_imports=False, monkeypatch=False))
    return json.loads(json.dumps(result, allow_nan=False))

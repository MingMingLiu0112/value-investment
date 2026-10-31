"""Disposable scripted account journey using the existing journal and risk engine."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from ...domain.execution.exchange_calendar import next_exchange_session
from ...domain.portfolio.dual_sleeve_risk import CORE, HOTSPOT, review_dual_sleeve_risk
from ...portfolio_risk import SecurityRiskAttributes
from .private_portfolio_service import PrivateJournal, PrivatePortfolioService, JournalValidationError
from .private_risk_projection import _allocations_payload, _policy_payload, _snapshot_payload, _sleeve_policy


SCHEMA = "simulated-trade-journey-v1"
SYMBOL = format(600519, "06d")
ACCOUNT = "SIMULATED_DISPOSABLE_DUAL_SLEEVE_JOURNEY"


class SourceResearchVersionChanged(ValueError):
    """The explicit user-visible research identity no longer matches the source."""


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


def _source_bound_cases(root, symbols, now):
    from ..decision.current_value_plan import load_current_value_action_plans
    from ..decision.public_strategy_assessment import project_actionable_evaluation
    from ..research.value_research_analysis import _bound
    from ..product.common import load_json_object, normalize_symbol

    selected = tuple(normalize_symbol(symbol) for symbol in symbols)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Explicit unique research securities required")
    loaded = load_current_value_action_plans(root, symbols=selected, now=now)
    cases, protected = [], {}
    for symbol in selected:
        matches = [plan for plan in loaded['items'] if plan['symbol'] == symbol]
        if len(matches) != 1:
            raise ValueError("Exact current source-bound plan unavailable: " + symbol)
        plan = matches[0]
        analysis = plan.get('research_analysis') or {}
        if (analysis.get('status') != 'CONDITIONAL_ANALYSIS_VERIFIED'
                or analysis.get('arithmetic_complete') is not True
                or analysis.get('action') != 'no_order'
                or not analysis.get('research_version')
                or plan.get('research_version') != analysis['research_version']):
            raise ValueError("Current research attribution unavailable: " + symbol)
        binding = analysis['review_binding']['candidate_binding']
        candidate = load_json_object(_bound(root, binding), 'simulated public research reference')
        if (candidate['symbol'] != symbol or candidate['model_context'] != analysis['review_binding']['model_context']
                or plan.get('valuation_input_version') != analysis['input_descriptor_sha256']):
            raise ValueError("Current plan and candidate research differ")
        for ref in [*analysis['source_bindings'], *plan.get('source_bindings', []),
                    *candidate['source_bindings'], *candidate['implementation_bindings']]:
            pinned = dict(path=ref['path'], sha256=ref['sha256'])
            _bound(root, pinned)
            if pinned['path'] in protected and protected[pinned['path']] != pinned['sha256']:
                raise ValueError("Conflicting public research source bindings")
            protected[pinned['path']] = pinned['sha256']
        evaluation = project_actionable_evaluation(dict(symbol=symbol, strategy=CORE, price_action_plan=plan))
        if evaluation.get('eligibility') is not False:
            raise ValueError('Conditional rehearsal cannot represent admitted strategy decisions')
        reasons = list(dict.fromkeys([evaluation['decision_reason'], *plan.get('blockers', []),
            *plan.get('formal_eligibility_blockers', [])]))
        slots = [dict(intent=intent, outcome='WAIT' if intent == 'WAIT' else 'NO_ACTION',
            strategy_verdict=evaluation['decision_action'], reasons=reasons + ([] if intent in {'BUY', 'WAIT'} else
                ['ORIGINAL_ENTRY_AND_PERSONAL_RISK_NOT_ESTABLISHED']),
            formal_eligibility=False, review_quantity=None, action='no_order')
            for intent in ('BUY', 'ADD', 'HOLD', 'REDUCE', 'EXIT', 'WAIT')]
        cases.append(dict(symbol=symbol, company_name=analysis['company_name'],
            research=dict(candidate_binding=deepcopy(binding), research_version=analysis['research_version'],
                model_context=deepcopy(candidate['model_context']), generated_at=candidate['generated_at'],
                replayed_at=candidate.get('replayed_at'), research_as_of=analysis['research_as_of'],
                valuation_date=analysis['valuation_date'], available_at=analysis['available_at'],
                computed_at=analysis['computed_at'], thesis=deepcopy(analysis['thesis']),
                confidence=analysis['valuation']['confidence'],
                counter_evidence=deepcopy(analysis.get('counter_evidence', [])),
                thesis_breakers=deepcopy(analysis['thesis_breakers']),
                scope='SOURCE_BOUND_CONDITIONAL_RESEARCH_NOT_TRADE_APPROVAL'),
            plan=dict(research_version=plan['research_version'], signal_state=plan['signal_state'],
                candidate_action=plan['candidate_action'], verification_scope=plan['verification_scope']),
            evaluation=evaluation, action_slots=slots, action='no_order'))
    return cases, protected


def _manual_account_state(service):
    """Ledger accounting only: no production risk projection or namespace relabel."""
    replay = _replayed(service)
    view = service._portfolio_payload(replay, today=service._now().date())
    return dict({key: deepcopy(view[key]) for key in
            ('cash_cny', 'positions', 'realized_pnl_cny', 'revision', 'pending_draft')},
        confirmed_fees_cny=str(sum((Decimal(row['fees_cny']) for row in replay.trades), Decimal(0))))


def run_source_bound_simulated_trade_journey(root: Path, now: datetime, *,
        symbols, manual_fills=None, initial_cash_cny=None,
        workspace_root: Path | None = None, expected_candidates: list[dict] | None = None) -> dict:
    """Read current public research; optionally rehearse explicitly requested fills.

    Manual fills are independent hypothetical accounting, never strategy verdicts.
    A requested historical narrative is not an original PIT Entry. The legacy
    all-synthetic journey above remains a separate demonstration.
    """
    from ..research.value_research_analysis import _bound
    from .personal_entry_thesis import owned_entry_context

    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Source-bound journey requires an aware research clock")
    if now > datetime.now(now.tzinfo):
        raise ValueError("Source-bound journey cannot use a future research clock")
    root = Path(root).resolve(strict=True)
    if manual_fills is not None and not isinstance(manual_fills, list):
        raise ValueError("Manual rehearsal must be an explicit list")
    cases, protected = _source_bound_cases(root, symbols, now)
    by_symbol = {case['symbol']: case for case in cases}
    if expected_candidates is not None:
        identities = [dict(symbol=case['symbol'], candidate_binding=case['research']['candidate_binding'],
            research_version=case['research']['research_version']) for case in cases]
        if (not isinstance(expected_candidates, list)
                or any(not isinstance(row, dict) or not isinstance(row.get('symbol'), str)
                       for row in expected_candidates)
                or sorted(expected_candidates, key=lambda row: row['symbol'])
                != sorted(identities, key=lambda row: row['symbol'])):
            raise SourceResearchVersionChanged('Research changed after the displayed source read')

    def recheck():
        for path, digest in protected.items():
            _bound(root, dict(path=path, sha256=digest))

    manual = dict(status='NOT_REQUESTED', fills=[], account_state=None, journal_receipt=None,
                  temporary_journal_removed=True, actual_account_used=False)
    if manual_fills:
        if initial_cash_cny is None:
            raise ValueError('Manual rehearsal requires explicit opening cash')
        try:
            opening_day = date.fromisoformat(manual_fills[0]['fill']['trade_date'])
        except (KeyError, TypeError) as error:
            raise ValueError("Manual rehearsal requires an explicit first execution date") from error
        if opening_day > datetime.now(ZoneInfo('Asia/Shanghai')).date():
            raise ValueError("Hypothetical execution cannot be in the future")
        workspace = Path(workspace_root or root).resolve(strict=True)
        temporary = workspace / '.tmp'
        if temporary.is_symlink():
            raise ValueError("Simulation temporary directory must not be a symlink")
        temporary.mkdir(exist_ok=True)
        if temporary.resolve().parent != workspace:
            raise ValueError("Simulation must remain inside workspace .tmp")
        with TemporaryDirectory(prefix='source-bound-simulated-', dir=temporary) as directory:
            journal = Path(directory) / 'SIMULATED-journal.jsonl'
            service = PrivatePortfolioService(PrivateJournal(journal))
            recorded = service._now()
            service.initialize(dict(idempotency_key='SIMULATED-init', expected_revision=0,
                account_scope='SIMULATED_SOURCE_BOUND_MANUAL_REHEARSAL',
                as_of=opening_day.isoformat(), cash_cny=initial_cash_cny, holdings=[],
                sleeve_allocations={}, policy={}, confirmed_at=recorded.isoformat(),
                confirmation_note='Explicit simulated bookkeeping only; no real account or approval'))
            rows, t1 = [], []
            for index, request in enumerate(manual_fills):
                if not isinstance(request, dict) or set(request) - {'fill', 'research_reference'}:
                    raise ValueError("Unsupported manual rehearsal fields")
                fill = deepcopy(request['fill'])
                if (fill.get('symbol') not in by_symbol or fill.get('sleeve') != CORE
                        or set(fill) & {'judgment_snapshot', 'decision_id', 'research_version'}):
                    raise ValueError("Manual fill must use selected research and server-derived attribution")
                if date_from_fill := fill.get('trade_date'):
                    if date.fromisoformat(date_from_fill) > datetime.now(ZoneInfo('Asia/Shanghai')).date():
                        raise ValueError("Hypothetical execution cannot be in the future")
                if fill.get('side') == 'BUY' and 'next_sell_session' not in fill:
                    fill['next_sell_session'] = next_exchange_session(
                        fill['exchange'], date.fromisoformat(fill['trade_date'])).isoformat()
                reference = request.get('research_reference')
                if reference not in (None, 'HISTORICAL_RECONSTRUCTION'):
                    raise ValueError("Only explicit historical research-reference reconstruction is supported")
                case = by_symbol[fill['symbol']]
                research = case['research']
                fill.update(decision_id=fill['symbol'], research_version=research['research_version'])
                recheck()
                before = _manual_account_state(service)
                prepared, digest = service.prepare_fill(dict(idempotency_key=f'SIMULATED-prepare-{index}',
                    expected_revision=len(service.records()), fill=fill,
                    note='Explicit hypothetical manual fill; not a strategy instruction'), repository_root=root)
                draft = _manual_account_state(service)
                if before['cash_cny'] != draft['cash_cny'] or before['positions'] != draft['positions']:
                    raise ValueError("Prepared draft changed confirmed accounting")
                confirmation = dict(idempotency_key=f'SIMULATED-confirm-{index}', expected_revision=len(service.records()),
                    prepared_record_sha256=digest, confirmed_at=service._now().isoformat(),
                    confirmation_note='SIMULATED manual confirmation, not investment approval')
                confirmed, fill_hash = service.confirm_fill(confirmation)
                count = len(service.records())
                repeated = service.confirm_fill(confirmation)
                idempotent = repeated == (confirmed, fill_hash) and len(service.records()) == count
                fill_record = next(row for row in service.records() if row['record_sha256'] == fill_hash)
                actual_fill = fill_record['body']['fill']
                snapshot = actual_fill.get('judgment_snapshot')
                historical = None
                if reference is not None:
                    if fill['side'] != 'BUY':
                        raise ValueError("Historical Entry narrative requires a buy fill")
                    breakers = [item if isinstance(item, str) else item['text'] for item in research['thesis_breakers']]
                    historical, _ = service.confirm_entry_thesis(dict(
                        idempotency_key=f'SIMULATED-reference-{index}', expected_revision=len(service.records()),
                        fill_record_sha256=fill_hash, binding_mode='HISTORICAL_RECONSTRUCTION',
                        read_and_confirmed=True, confirmation_note='SIMULATED historical research reference only',
                        reconstruction=dict(thesis=research['thesis'],
                            hold_logic=('Research reference only; no approved HOLD, ADD, risk or original PIT Entry. '
                                + json.dumps(research['candidate_binding'], sort_keys=True)),
                            invalidation_conditions=breakers, research_version=research['research_version'],
                            strategy_version='SOURCE_BOUND_PENDING_ARITHMETIC_NOT_APPROVAL')),
                        authenticated_subject='SIMULATED_REHEARSAL_SUBJECT', repository_root=root)
                context = owned_entry_context(records=service.records(), symbol=fill['symbol'], sleeve=CORE,
                    authenticated_subject='SIMULATED_REHEARSAL_SUBJECT', as_of=service._now())
                rows.append(dict(symbol=fill['symbol'], side=fill['side'],
                    scope='EXPLICIT_SIMULATED_MANUAL_FILL_NOT_STRATEGY_ACTION', fill=actual_fill,
                    execution_price_scope='CALLER_SUPPLIED_HYPOTHETICAL_FILL_NOT_QUOTE_OR_FAIR_VALUE',
                    fill_record_sha256=fill_hash, recorded_at=fill_record['recorded_at'],
                    source_candidate_binding=deepcopy(research['candidate_binding']),
                    prepared_status=prepared['status'], confirmed_status=confirmed['status'],
                    prepared_cash_unchanged=True, confirmation_idempotent=idempotent,
                    snapshot_status=('EXACT_PUBLICATION_RECORDING_TIME_REFERENCE_NOT_PRETRADE'
                        if snapshot else 'SNAPSHOT_UNAVAILABLE_NO_EXACT_PUBLISHED_RESEARCH'),
                    historical_reference_status=historical['status'] if historical else 'NOT_REQUESTED',
                    historical_reference_scope='NOT_ORIGINAL_PIT_ENTRY' if historical else None,
                    original_entry_advisory_eligible=context['advisory_dependencies_valid'],
                    entry_blockers=context['blockers'], after=_manual_account_state(service)))
                if fill['side'] == 'BUY':
                    sellable = sum((lot.quantity for lot in _replayed(service).state.lots
                        if lot.symbol == fill['symbol'] and lot.sleeve == CORE
                        and lot.sellable_on <= date.fromisoformat(fill['trade_date'])), Decimal(0))
                    if sellable >= Decimal(fill['quantity']):
                        rows[-1]['t1_negative_status'] = 'NOT_APPLICABLE_OLDER_SELLABLE_LOTS'
                        continue
                    sell = {key: actual_fill[key] for key in
                            ('symbol', 'exchange', 'quantity', 'price_cny', 'fees_cny', 'trade_date', 'sleeve')}
                    sell.update(side='SELL', transaction_id=f'SIMULATED-T1-{index}')
                    prior = journal.read_bytes()
                    try:
                        service.prepare_fill(dict(idempotency_key=f'SIMULATED-T1-{index}',
                            expected_revision=len(service.records()), fill=sell))
                    except JournalValidationError as error:
                        if 'insufficient sellable shares' not in str(error):
                            raise
                        t1.append(journal.read_bytes() == prior)
                        rows[-1]['t1_negative_status'] = 'REJECTED_WITHOUT_JOURNAL_WRITE'
                    else:
                        raise ValueError("T+1 negative unexpectedly permitted")
            recheck()
            final = _manual_account_state(service)
            restart = PrivatePortfolioService(PrivateJournal(journal))
            if _manual_account_state(restart) != final:
                raise ValueError("Restart accounting differs")
            manual = dict(status='EXPLICIT_SIMULATED_RECORDS_ONLY', fills=rows, account_state=final,
                accounting_baseline=dict(as_of=opening_day.isoformat(), cash_cny=initial_cash_cny,
                    scope='SYNTHETIC_OPENING_CASH_NOT_HISTORICAL_ACCOUNT_EVIDENCE'),
                restart_equal=True, same_session_sell_rejected=all(t1) if t1 else None,
                t1_negative_checks=len(t1),
                journal_receipt=dict(sha256=sha256(journal.read_bytes()).hexdigest(),
                    record_count=len(service.records()), retained=False), actual_account_used=False)
        manual['temporary_journal_removed'] = not journal.exists()
    recheck()
    return dict(schema_version='source-bound-simulated-trade-journey-v1', action='no_order',
        namespace='SIMULATED', research_namespace='PUBLIC_SOURCE_BOUND', research_evaluated_at=now.isoformat(),
        scope='PUBLIC_RESEARCH_WITH_OPTIONAL_ISOLATED_MANUAL_ACCOUNTING',
        cases=cases, manual_rehearsal=manual, source_files_verified=len(protected),
        strategy_validated=False, approval_changed=False, broker_execution_permission=False,
        position_guidance=None, personal_risk_evaluated=False)


def _dual_hotspot_source(root, binding, now):
    from ..hotspot.simulated_lifecycle import load_simulated_hotspot_lifecycle

    verified = load_simulated_hotspot_lifecycle(root, binding, now)
    report = verified['report']
    entry = report['entry_reference']
    return dict(sleeve=HOTSPOT, symbol=report['symbol'], receipt_binding=deepcopy(binding),
        source_scope=report['market_source_scope'], historical_only=True,
        current_signal=False, current_pit=False, entry_reference=deepcopy(entry),
        entry_freeze_sha256=report['entry_freeze_sha256'],
        lifecycle_reviews=[deepcopy(row['lifecycle_review']) for row in report['steps']],
        strategy_validated=False, formal_eligibility=False, review_quantity=None,
        action_slots=[dict(intent=intent, outcome='WAIT' if intent == 'WAIT' else 'NO_ACTION',
            reasons=['RETAINED_SIMULATION_NOT_CURRENT_STRATEGY_OR_OWNED_ENTRY',
                'PRICE_COMPARABILITY_AND_STRATEGY_ADMISSION_NOT_PROVEN'],
            review_quantity=None, formal_eligibility=False, action='no_order')
            for intent in ('BUY', 'ADD', 'HOLD', 'REDUCE', 'EXIT', 'WAIT')], action='no_order')


def _dual_account_view(service, account, *, moment=None):
    from .private_risk_projection import build_risk_input, sleeve_cash_review

    replay = _replayed(service)
    moment = moment or service._now()
    marks = {symbol: dict(price_cny=price, trade_date=moment.date().isoformat())
        for symbol, price in account['hypothetical_marks'].items()}
    # Existing aggregation partitions each security into sleeves, never duplicate NAV.
    snapshot = _snapshot_payload(replay, marks)
    marked = all(row['market_value_cny'] is not None for row in snapshot['holdings'])
    equity = (Decimal(snapshot['cash_cny']) + sum(
        (Decimal(row['market_value_cny']) for row in snapshot['holdings']), Decimal(0))) if marked else None
    payload = build_risk_input(replay, sellable_as_of=moment.date(), namespace='SIMULATED',
        generated_at=moment, _prices=marks)
    payload['portfolio']['snapshot']['namespace'] = 'SIMULATED'
    payload['portfolio']['policy']['sensitivity'] = 'TEST_ONLY_DISPOSABLE_ACCOUNT'
    if payload['shared_budget'] is not None:
        payload['shared_budget']['policy_scope'] = 'SYNTHETIC_POLICY_ONLY'
    risk = review_dual_sleeve_risk(payload, generated_at=moment, allow_synthetic=True)
    return dict(_manual_account_state(service), sleeve_cash_review=sleeve_cash_review(replay),
        aggregate_holdings=snapshot['holdings'], hypothetical_equity_cny=str(equity) if equity is not None else None,
        mark_scope='CALLER_TEST_ONLY_MARKS_NOT_CURRENT_QUOTES_OR_INTRINSIC_VALUE',
        risk_review=risk, risk_scope='DISPOSABLE_ACCOUNT_MISSING_RISK_INPUTS_REMAIN_BLOCKED')


def _validate_dual_account(account, now):
    from ...domain.portfolio.dual_sleeve_risk import decimal

    if (not isinstance(account, dict) or set(account) != {'namespace', 'confirmed', 'opening_day',
            'initial_cash_cny', 'policy', 'hypothetical_marks'}
            or account['namespace'] != 'TEST_ONLY' or account['confirmed'] is not True):
        raise ValueError('Explicit confirmed TEST_ONLY hypothetical account required')
    day = date.fromisoformat(account['opening_day'])
    if day > now.astimezone(ZoneInfo('Asia/Shanghai')).date():
        raise ValueError('Future hypothetical account date')
    cash = decimal(account['initial_cash_cny'], 'opening cash', positive=True)
    policy = account['policy']
    if (not isinstance(policy, dict) or decimal(policy['investable_assets_cny'], 'policy assets') != cash
            or policy['effective_date'] != day.isoformat()
            or not {'no_order', 'SIMULATED_ONLY'} <= set(policy['restrictions'])):
        raise ValueError('Hypothetical policy must match account date/cash and simulated scope')
    reserve = decimal(policy['cash_reserve_cny'], 'reserve')
    if sum((decimal(policy['sleeves'][name]['cash_cny'], name) for name in (CORE, HOTSPOT)), reserve) != cash:
        raise ValueError('Sleeve cash and reserve must partition the one opening cash balance')
    for name, field in ((CORE, 'core_value_budget_cny'), (HOTSPOT, 'hotspot_budget_cny')):
        if decimal(policy['sleeves'][name]['cash_cny'], name) > decimal(policy[field], field):
            raise ValueError('Sleeve cash exceeds explicit capital budget')
    if not isinstance(account['hypothetical_marks'], dict):
        raise ValueError('Explicit hypothetical marks mapping required (empty allowed)')
    for price in account['hypothetical_marks'].values():
        decimal(price, 'hypothetical mark', positive=True)
    return day


def _dual_consumed_entries(before, after, entries, fill, request):
    """Attribute native confirmed FIFO deltas, never choose lots for the ledger."""
    consumed = []
    for digest, original in before.items():
        quantity = Decimal(original['remaining_quantity']) - Decimal(after[digest]['remaining_quantity'])
        if quantity < 0:
            raise ValueError('Native sell unexpectedly increased an original Entry')
        if quantity == 0:
            continue
        transaction = original['transaction_id']
        if (original['symbol'], original['exchange'], original['sleeve']) != (
                fill['symbol'], fill['exchange'], fill['sleeve']):
            raise ValueError('Native sell consumed an unrelated Entry')
        reference = entries.get(transaction)
        if reference is None or reference['fill_record_sha256'] != digest:
            raise ValueError('Consumed original Entry narrative unavailable')
        consumed.append(dict(transaction_id=transaction, quantity=str(quantity),
            original_entry_reference=deepcopy(reference)))
    if sum((Decimal(row['quantity']) for row in consumed), Decimal(0)) != Decimal(fill['quantity']):
        raise ValueError('Original Entry consumption does not equal the native confirmed sell')
    linked = request.get('entry_transaction_id')
    if len(consumed) == 1:
        if linked != consumed[0]['transaction_id']:
            raise ValueError('Sell Entry reference differs from native FIFO consumption')
    elif linked is not None:
        raise ValueError('Multi-Entry FIFO sell cannot claim a single original Entry')
    rationales = request.get('entry_rationales')
    if rationales is None and len(consumed) == 1:
        rationales = {consumed[0]['transaction_id']: request['rationale']}
    if (not isinstance(rationales, dict) or set(rationales) != {row['transaction_id'] for row in consumed}
            or any(not isinstance(reason, str) or not reason.strip() for reason in rationales.values())):
        raise ValueError('Exact per-consumed-Entry manual rationale required for FIFO sell')
    for row in consumed:
        row['manual_rationale'] = rationales[row['transaction_id']]
        row['consistency_scope'] = 'MANUAL_REASON_COMPARED_WITH_RECONSTRUCTED_THESIS_NOT_APPROVAL'
    return consumed


def _dual_manual_rehearsal(*, workspace, core_root, account, requests, cases, hotspot, recheck, now):
    from .personal_entry_thesis import owned_entry_context, resolve_personal_entry_thesis, _sources

    opening = _validate_dual_account(account, now)
    sources = {(CORE, case['symbol']): dict(version=case['research']['research_version'],
        reference=case['research']) for case in cases}
    sources[(HOTSPOT, hotspot['symbol'])] = dict(version=hotspot['entry_freeze_sha256'], reference=hotspot)
    temporary = workspace / '.tmp'
    if temporary.is_symlink():
        raise ValueError('Simulation .tmp cannot be a symlink')
    temporary.mkdir(exist_ok=True)
    if temporary.resolve().parent != workspace:
        raise ValueError('Simulation must stay in workspace .tmp')
    rows, entries = [], {}
    with TemporaryDirectory(prefix='source-bound-dual-', dir=temporary) as directory:
        journal = Path(directory) / 'SIMULATED-journal.jsonl'
        service = PrivatePortfolioService(PrivateJournal(journal))
        service.initialize(dict(idempotency_key='SIMULATED-init', expected_revision=0,
            account_scope='TEST_ONLY_SOURCE_BOUND_DUAL_REHEARSAL', as_of=opening.isoformat(),
            cash_cny=account['initial_cash_cny'], holdings=[], sleeve_allocations={}, policy={},
            confirmed_at=service._now().isoformat(), confirmation_note='Explicit TEST_ONLY disposable account'))
        _, digest = service.prepare_policy(dict(idempotency_key='SIMULATED-policy',
            expected_revision=len(service.records()), policy=account['policy']))
        service.confirm_policy(dict(idempotency_key='SIMULATED-confirm-policy',
            expected_revision=len(service.records()), prepared_record_sha256=digest,
            confirmed_at=service._now().isoformat(), confirmation_note='Explicit hypothetical budgets, not real IPS'))
        for index, request in enumerate(requests):
            if (not isinstance(request, dict) or set(request) - {'fill', 'intent', 'rationale',
                    'entry_transaction_id', 'entry_narrative', 'requested_quantity', 'entry_rationales'}):
                raise ValueError('Unsupported dual rehearsal request')
            fill = deepcopy(request['fill'])
            if set(fill) - {'transaction_id', 'side', 'sleeve', 'symbol', 'exchange', 'quantity',
                    'price_cny', 'fees_cny', 'trade_date', 'trading_unit', 'next_sell_session'}:
                raise ValueError('Caller cannot supply Entry, snapshot, model context or authority')
            key = (fill['sleeve'], fill['symbol'])
            if key not in sources:
                raise ValueError('Manual fill differs from selected source/sleeve')
            if (fill['symbol'][0] not in {'0', '3', '6'}
                    or fill['exchange'] != ('SSE' if fill['symbol'].startswith('6') else 'SZSE')):
                raise ValueError('Manual fill exchange differs from source security')
            intent, rationale = request['intent'], request['rationale']
            if (intent not in {'BUY', 'ADD', 'REDUCE', 'EXIT'} or not isinstance(rationale, str)
                    or not rationale.strip() or fill['side'] != ('BUY' if intent in {'BUY', 'ADD'} else 'SELL')):
                raise ValueError('Explicit manual intention, matching side and rationale required')
            day = date.fromisoformat(fill['trade_date'])
            if not opening <= day <= now.astimezone(ZoneInfo('Asia/Shanghai')).date():
                raise ValueError('Hypothetical fill is outside the declared nonfuture account window')
            linked = request.get('entry_transaction_id')
            if intent == 'BUY':
                if linked is not None or 'entry_narrative' not in request or 'entry_rationales' in request:
                    raise ValueError('Opening BUY requires explicit retrospective Entry narrative')
            elif ('entry_narrative' in request
                    or (linked is not None and (linked not in entries or entries[linked]['key'] != key))
                    or (intent == 'ADD' and (linked is None or 'entry_rationales' in request))
                    or (fill['side'] == 'SELL' and linked is None and 'entry_rationales' not in request)):
                raise ValueError('Followup must reference the original same-security/sleeve Entry')
            if fill['side'] == 'BUY' and 'next_sell_session' not in fill:
                fill['next_sell_session'] = next_exchange_session(fill['exchange'], day).isoformat()
            quantity = Decimal(fill['quantity'])
            requested = Decimal(request.get('requested_quantity', fill['quantity']))
            if not requested.is_finite() or requested < quantity or requested != requested.to_integral_value():
                raise ValueError('Partial-fill requested quantity must cover the actual fill')
            replay = _replayed(service)
            if intent != 'BUY':
                resolved = resolve_personal_entry_thesis(records=service.records(),
                    account_scope='TEST_ONLY_SOURCE_BOUND_DUAL_REHEARSAL',
                    expected_revision=len(service.records()), as_of=service._now(),
                    authenticated_subject='SIMULATED_DUAL_SUBJECT')
                if linked is not None and not any(
                        row['fill_record_sha256'] == entries[linked]['fill_record_sha256']
                        and Decimal(row['remaining_quantity']) > 0 for row in resolved['items']):
                    raise ValueError('Referenced original Entry is no longer held')
                held = sum((lot.quantity for lot in replay.state.lots
                    if (lot.sleeve, lot.symbol) == key), Decimal(0))
                if ((intent == 'EXIT' and quantity != held)
                        or (intent == 'REDUCE' and quantity >= held)):
                    raise ValueError('Manual REDUCE/EXIT label must match the actual remaining position')
            _, sleeves, reserve = _sleeve_policy(replay)
            if fill['side'] == 'BUY':
                debit = quantity * Decimal(fill['price_cny']) + Decimal(fill['fees_cny'])
                if (debit > Decimal(sleeves[key[0]]['cash_cny'])
                        or replay.state.cash_cny - debit < max(Decimal(reserve),
                            Decimal(account['policy']['minimum_cash_cny']))):
                    raise ValueError('Explicit hypothetical sleeve cash/shared reserve exceeded')
            recheck()
            before = _dual_account_view(service, account)
            original_sources = _sources(service.records())[0] if fill['side'] == 'SELL' else None
            # Do not attach value model context to HOTSPOT or fabricate a public judgment.
            prepared, digest = service.prepare_fill(dict(idempotency_key=f'SIMULATED-fill-{index}',
                expected_revision=len(service.records()), fill=fill,
                note='Manual hypothesis, not strategy recommendation: ' + rationale))
            draft = _manual_account_state(service)
            if draft['cash_cny'] != before['cash_cny'] or draft['positions'] != before['positions']:
                raise ValueError('Draft changed confirmed accounting')
            confirmation = dict(idempotency_key=f'SIMULATED-confirm-{index}',
                expected_revision=len(service.records()), prepared_record_sha256=digest,
                confirmed_at=service._now().isoformat(), confirmation_note='Explicit TEST_ONLY manual bookkeeping')
            confirmed = service.confirm_fill(confirmation)
            count = len(service.records())
            if service.confirm_fill(confirmation) != confirmed or len(service.records()) != count:
                raise ValueError('Fill confirmation is not idempotent')
            fill_hash = confirmed[1]
            consumed = (_dual_consumed_entries(original_sources, _sources(service.records())[0],
                entries, fill, request) if fill['side'] == 'SELL' else [])
            if fill['side'] == 'BUY':
                narrative = deepcopy(request['entry_narrative'] if intent == 'BUY' else entries[linked]['narrative'])
                if set(narrative) != {'thesis', 'hold_logic', 'invalidation_conditions'}:
                    raise ValueError('Explicit Entry thesis, hold logic and invalidation conditions required')
                service.confirm_entry_thesis(dict(idempotency_key=f'SIMULATED-entry-{index}',
                    expected_revision=len(service.records()), fill_record_sha256=fill_hash,
                    binding_mode='HISTORICAL_RECONSTRUCTION', read_and_confirmed=True,
                    reconstruction=dict(narrative, research_version=sources[key]['version'],
                        strategy_version='TEST_ONLY_SOURCE_BOUND_MANUAL_NOT_STRATEGY_APPROVAL'),
                    confirmation_note='Retrospective hypothetical reference; not original PIT Entry'),
                    authenticated_subject='SIMULATED_DUAL_SUBJECT', repository_root=core_root)
                entries[fill['transaction_id']] = dict(key=key, narrative=narrative,
                    fill_record_sha256=fill_hash)
            context = owned_entry_context(records=service.records(), symbol=fill['symbol'], sleeve=fill['sleeve'],
                authenticated_subject='SIMULATED_DUAL_SUBJECT', as_of=service._now())
            if context['advisory_dependencies_valid'] is not False:
                raise ValueError('Hypothetical Entry unexpectedly became advisory eligible')
            rows.append(dict(intent=intent, fill=fill, fill_record_sha256=fill_hash,
                rationale=rationale,
                original_entry_transaction_id=(consumed[0]['transaction_id'] if len(consumed) == 1
                    else None if consumed else linked),
                original_entry_reference=(deepcopy(consumed[0]['original_entry_reference']) if len(consumed) == 1
                    else None if consumed else deepcopy(entries.get(linked or fill['transaction_id']))),
                consumed_original_entries=consumed,
                source_version=sources[key]['version'], source_reference=deepcopy(sources[key]['reference']),
                scope='EXPLICIT_MANUAL_HYPOTHESIS_NOT_SYSTEM_ACTION',
                execution_price_scope='CALLER_HYPOTHETICAL_NOT_MARKET_FILL',
                fee_scope='CALLER_TOTAL_COST_HYPOTHESIS_NOT_VERIFIED_FEE_SCHEDULE',
                requested_quantity=str(requested), unfilled_quantity=str(requested - quantity),
                unfilled_scope='INFORMATION_ONLY_NOT_OPEN_ORDER', confirmation_idempotent=True,
                prepared_cash_unchanged=True, original_pit_proven=False,
                original_entry_advisory_eligible=False, entry_blockers=context['blockers'],
                before=before, after=_dual_account_view(service, account)))
        recheck()
        final_clock = service._now()
        final = _dual_account_view(service, account, moment=final_clock)
        restarted = PrivatePortfolioService(PrivateJournal(journal))
        if _dual_account_view(restarted, account, moment=final_clock) != final:
            raise ValueError('Dual-sleeve restart accounting differs')
        receipt = dict(sha256=sha256(journal.read_bytes()).hexdigest(), record_count=len(service.records()), retained=False)
    return dict(status='EXPLICIT_SIMULATED_RECORDS_ONLY', fills=rows, account_state=final,
        restart_equal=True, temporary_journal_removed=not journal.exists(), journal_receipt=receipt,
        assumptions=deepcopy(account), actual_account_used=False, persistent_simulated_portfolio=False)


def run_source_bound_dual_sleeve_journey(*, core_root: Path, hotspot_root: Path,
        workspace_root: Path, now: datetime, core_symbols, hotspot_receipt_binding: dict,
        expected_sources: dict | None = None, test_only_account: dict | None = None,
        manual_fills: list[dict] | None = None) -> dict:
    """Read native value research + sealed swing replay, optionally one disposable account.

    No sources authorize a fill. Only explicit TEST_ONLY manual hypotheses create
    an isolated journal; the retained swing account is read, never reused/copied.
    Source cutoffs remain historical and confirmations use the actual wall clock.
    """
    from ..research.value_research_analysis import _bound

    if (not isinstance(now, datetime) or now.utcoffset() is None
            or now > datetime.now(now.tzinfo)):
        raise ValueError('An aware, nonfuture source evaluation clock is required')
    core_root, hotspot_root, workspace = (Path(path).resolve(strict=True)
        for path in (core_root, hotspot_root, workspace_root))
    if manual_fills is not None and not isinstance(manual_fills, list):
        raise ValueError('Manual hypotheses must be an explicit list')
    binding = deepcopy(hotspot_receipt_binding)
    core_symbols = tuple(core_symbols)
    cases, protected = _source_bound_cases(core_root, core_symbols, now)
    hotspot = _dual_hotspot_source(hotspot_root, binding, now)
    identity = dict(core=[dict(symbol=case['symbol'], candidate_binding=case['research']['candidate_binding'],
        research_version=case['research']['research_version']) for case in cases],
        hotspot=dict(symbol=hotspot['symbol'], receipt_binding=binding,
            entry_freeze_sha256=hotspot['entry_freeze_sha256']))
    if expected_sources is not None and expected_sources != identity:
        raise SourceResearchVersionChanged('Displayed dual source identities changed')

    def recheck():
        for path, digest in protected.items():
            _bound(core_root, dict(path=path, sha256=digest))
        current, _ = _source_bound_cases(core_root, core_symbols, now)
        if current != cases or _dual_hotspot_source(hotspot_root, binding, now) != hotspot:
            raise SourceResearchVersionChanged('Source changed during the dual rehearsal')

    manual = dict(status='NOT_REQUESTED', fills=[], account_state=None, journal_receipt=None,
        temporary_journal_removed=True, actual_account_used=False, persistent_simulated_portfolio=False)
    if manual_fills:
        if expected_sources is None:
            raise ValueError('Manual rehearsal requires the displayed exact source identities')
        manual = _dual_manual_rehearsal(workspace=workspace, core_root=core_root,
            account=deepcopy(test_only_account), requests=deepcopy(manual_fills), cases=cases,
            hotspot=hotspot, recheck=recheck, now=now)
    recheck()
    return dict(schema_version='source-bound-dual-sleeve-journey-v1', namespace='SIMULATED',
        action='no_order', scope='DISPOSABLE_SOURCE_BOUND_REHEARSAL_NOT_PERSISTENT_PORTFOLIO',
        research_evaluated_at=now.isoformat(), source_identity=identity, core_cases=cases,
        hotspot_case=hotspot, manual_rehearsal=manual, actual_account_used=False,
        formal_eligibility=False, strategy_validated=False, approval_changed=False,
        broker_execution_permission=False, position_guidance=None)

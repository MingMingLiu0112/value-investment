"""TEST_ONLY owned actions: concentration alerts must not suppress risk reduction."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from test_personal_entry_thesis import case  # noqa: F401
from test_owned_held_actions import confirmed_context, inputs
from test_d2_conditional_shared_service import synthetic_chain  # noqa: F401
from test_p7_signed_review_workflow import _complete_signed_case, _registered_policy_fixture
from test_advisory_decision_recommendation_v3 import _entry, _consistency
from test_private_ips_policy import full_policy
from test_portfolio_risk_assessment import _attributes
from value_investment_agent.application.portfolio import personal_entry_thesis as thesis
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio import private_portfolio_service as ledger
from value_investment_agent.application.portfolio.held_continuity import (
    owned_held_action, evaluate_owned_held_advisory, project_held_continuity, SELL_REVIEW_SCHEMA,
)
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_artifacts import ResearchArtifactIdentity
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry


CONCENTRATION = [
    "CORE_VALUE:single_security_concentration:300364",
    "aggregate:single_security_concentration",
    "shared:single_security_cap:300364",
]


@pytest.mark.parametrize("selected,action", [("TRIM_CANDIDATE", "REDUCE"), ("SELL_CANDIDATE", "EXIT")])
def test_known_concentration_kept_visible_without_vetoing_verified_sell(case, tmp_path, selected, action):
    context = confirmed_context(case, tmp_path)
    args = inputs(context, selected)
    args["risk"]["engine"].update(status="REVIEW_REQUIRED", blockers=CONCENTRATION.copy())
    args["risk"]["blockers"] = CONCENTRATION.copy()
    original = deepcopy(args["risk"])
    before = case[1].journal.path.read_bytes()

    result = owned_held_action(**args)

    assert result["decision_action"] == action, result["blockers"]
    assert result["risk_warnings"] == CONCENTRATION
    assert result["personal_risk_status"] == "REVIEW_REQUIRED"
    assert result["risk_reduction_only"] is True
    assert result["risk_resolution_verified"] is False
    assert result["review_quantity"] == (50 if action == "REDUCE" else 100)
    assert result["original_thesis"] == context["entry_thesis"].thesis
    assert result["action"] == "no_order" and result["broker_execution_permission"] is False
    assert args["risk"] == original and case[1].journal.path.read_bytes() == before


@pytest.mark.parametrize("selected", ["HOLD", "ADD_CANDIDATE"])
def test_concentration_is_not_waived_for_hold_or_add(case, tmp_path, selected):
    args = inputs(confirmed_context(case, tmp_path), "SELL_CANDIDATE")
    args["risk"]["engine"].update(status="REVIEW_REQUIRED", blockers=CONCENTRATION.copy())
    args["risk"]["blockers"] = CONCENTRATION.copy()
    args["advisory_provider"] = lambda: (selected, [], {})
    result = owned_held_action(**args)
    assert result["decision_action"] == "UNASSESSABLE"
    assert result["review_quantity"] is None
    assert set(CONCENTRATION) <= set(result["blockers"])


@pytest.mark.parametrize("fault", [
    "CORE_VALUE:risk_unknown", "HOTSPOT_SATELLITE:liquidity_review:300364",
    "DISPLAY_ONLY_HELD_MARK_NOT_FORMAL_PRICE_INPUT", "EXTERNAL_ACCOUNT_RECONCILIATION_MISSING",
    "security_attributes.missing", "UNKNOWN_FUTURE_RISK_CODE", "CORE_VALUE:budget_exceeded",
])
def test_unknown_or_execution_risk_still_blocks_sell(case, tmp_path, fault):
    args = inputs(confirmed_context(case, tmp_path), "SELL_CANDIDATE")
    args["risk"]["engine"].update(status="REVIEW_REQUIRED", blockers=[*CONCENTRATION, fault])
    args["risk"]["blockers"] = [*CONCENTRATION, fault]
    result = owned_held_action(**args)
    assert result["decision_action"] == "UNASSESSABLE"
    assert result["review_quantity"] is None and fault in result["blockers"]


@pytest.mark.parametrize("source", ["envelope", "engine"])
@pytest.mark.parametrize("malformed", [[None], [{}], [[]], [True], [1], [""], {}, "not-a-list"])
def test_malformed_risk_codes_fail_closed_instead_of_throwing(case, tmp_path, source, malformed):
    args = inputs(confirmed_context(case, tmp_path), "SELL_CANDIDATE")
    args["risk"]["engine"].update(status="REVIEW_REQUIRED", blockers=CONCENTRATION.copy())
    args["risk"]["blockers"] = CONCENTRATION.copy()
    target = args["risk"] if source == "envelope" else args["risk"]["engine"]
    target["blockers"] = deepcopy(malformed)
    result = owned_held_action(**args)
    assert result["decision_action"] == "UNASSESSABLE"
    assert result["review_quantity"] is None
    assert "PRIVATE_RISK_BLOCKERS_INVALID" in result["blockers"]
    report = project_held_continuity(
        [dict(symbol="300364", exchange="SZSE", quantity="100", sleeves=[args["sleeve_position"]])],
        args["risk"], selected_symbols=(), plan_provider=lambda symbol: args["plan"],
        generated_at=datetime.fromisoformat("2026-10-15T20:00:00+08:00"),
        entry_context_provider=lambda *a: args["context"],
        advisory_provider=lambda *a: args["advisory_provider"](),
        sell_review_request=args["sell_review_request"])
    assert "PRIVATE_RISK_BLOCKERS_INVALID" in report["items"][0]["data_gaps"]
    assert report["items"][0]["actionable_decision"]["decision_action"] == "UNASSESSABLE"


@pytest.mark.parametrize("fault", [
    "t_plus_one", "stale_revision", "no_request", "unknown_status", "wrong_namespace",
    "account", "sleeve", "entry_hash", "wrong_action", "over_quantity", "partial_exit",
    "stale_plan", "risk_revision", "blocked_envelope",
])
def test_concentration_never_overrides_owned_sell_guards(case, tmp_path, fault):
    args = inputs(confirmed_context(case, tmp_path), "SELL_CANDIDATE")
    args["risk"]["engine"].update(status="REVIEW_REQUIRED", blockers=CONCENTRATION.copy())
    args["risk"]["blockers"] = CONCENTRATION.copy()
    if fault == "t_plus_one":
        args["sleeve_position"]["sellable_quantity"] = "0"
    elif fault == "stale_revision":
        args["sell_review_request"]["expected_revision"] -= 1
    elif fault == "no_request":
        args["sell_review_request"] = None
    elif fault == "unknown_status":
        args["risk"]["engine"]["status"] = "BLOCKED_PRIVATE_INPUT"
    elif fault == "wrong_namespace":
        args["risk"]["engine"]["namespace"] = "SIMULATED"
    elif fault == "account":
        args["sell_review_request"]["account_scope"] = "TEST_ONLY-other-account"
    elif fault == "sleeve":
        args["sell_review_request"]["sleeve"] = "HOTSPOT_SATELLITE"
    elif fault == "entry_hash":
        args["sell_review_request"]["entry_thesis_record_sha256"] = "0"*64
    elif fault == "wrong_action":
        args["sell_review_request"]["requested_action"] = "REDUCE"
    elif fault == "over_quantity":
        args["sell_review_request"]["requested_quantity"] = 101
    elif fault == "partial_exit":
        args["sell_review_request"]["requested_quantity"] = 50
    elif fault == "stale_plan":
        args["plan"]["signal_state"] = "STALE"
    elif fault == "risk_revision":
        args["risk"]["facts"]["revision"] += 1
    else:
        args["risk"]["status"] = "BLOCKED_PRIVATE_INPUT"
    result = owned_held_action(**args)
    assert result["decision_action"] == "UNASSESSABLE"
    assert result["review_quantity"] is None and result["formal_eligibility"] is False


@pytest.mark.parametrize("concentrated", [False, True])
def test_signed_owned_dual_sleeve_cash_risk_manual_sales_and_cold_thesis_replay(
        synthetic_chain, monkeypatch, concentrated):
    """Real ledger/risk/v3 engines; source adapters and research are TEST_ONLY."""
    root = synthetic_chain[0]
    restored, _, _ = _complete_signed_case(synthetic_chain, monkeypatch)
    _registered_policy_fixture(root, restored)
    symbol = restored.recommendation.symbol
    opened = datetime.fromisoformat("2026-09-18T20:00:00+08:00")
    clock = [opened]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0] if tz is None else clock[0].astimezone(tz)

    opened = Clock.fromisoformat(opened.isoformat())
    clock[0] = opened
    from value_investment_agent import research_artifact_repository as repositories
    monkeypatch.setattr(ledger, "datetime", Clock)
    monkeypatch.setattr(repositories, "datetime", Clock)
    service = ledger.PrivatePortfolioService(
        ledger.PrivateJournal(root / "TEST_ONLY-two-sleeve/journal.jsonl"), clock=lambda: clock[0])
    service.initialize(dict(idempotency_key="TEST_ONLY-init", expected_revision=0,
        account_scope="TEST_ONLY_TWO_SLEEVE_CONCENTRATION", as_of=opened.date().isoformat(),
        cash_cny="10000", holdings=[], sleeve_allocations={}, policy={},
        confirmed_at=opened.isoformat(), confirmation_note="TEST_ONLY isolated baseline"))
    policy = full_policy()
    policy.update(effective_date=opened.date().isoformat(),
                  max_single_security_pct="20" if concentrated else "80")
    policy["sleeves"]["CORE_VALUE"]["cash_cny"] = "7000"
    _, digest = service.prepare_policy(dict(idempotency_key="TEST_ONLY-policy", expected_revision=1, policy=policy))
    service.confirm_policy(dict(idempotency_key="TEST_ONLY-policy-confirm", expected_revision=2,
        prepared_record_sha256=digest, confirmed_at=opened.isoformat(), confirmation_note="TEST_ONLY IPS"))

    def fill(side, sleeve, quantity, key):
        fields = dict(transaction_id=key, side=side, sleeve=sleeve, symbol=symbol, exchange="SSE",
            quantity=str(quantity), price_cny="5", fees_cny="0", trade_date=clock[0].date().isoformat())
        if side == "BUY":
            fields.update(next_sell_session="2026-09-21", trading_unit="100")
        _, prepared = service.prepare_fill(dict(idempotency_key=key, expected_revision=len(service.records()), fill=fields))
        return service.confirm_fill(dict(idempotency_key=key+"-confirmed", expected_revision=len(service.records()),
            prepared_record_sha256=prepared, confirmed_at=clock[0].isoformat(), confirmation_note="TEST_ONLY manual fill"))

    repository = InMemoryResearchArtifactRepository()

    def save(value):
        kind, payload = artifact_payload(value)
        return repository.save_object(value, identity=ResearchArtifactIdentity(scope_type="security",
            scope_key=symbol, artifact_type=kind, schema_version=payload["schema_version"],
            as_of=getattr(value, "as_of", value.entry_date if hasattr(value, "entry_date") else opened.date()),
            available_at=clock[0]), run_id="TEST_ONLY-two-sleeve")

    original_bindings = {}
    for sleeve, quantity in (("CORE_VALUE", 400), ("HOTSPOT_SATELLITE", 200)):
        _, bought = fill("BUY", sleeve, quantity, "TEST_ONLY-open-"+sleeve)
        entry = save(replace(_entry(), symbol=symbol, entry_date=opened.date(), confirmed_at=opened,
            entry_price=Decimal("5"), entry_id="TEST_ONLY-entry-"+sleeve))
        consistency = save(replace(_consistency("CONSISTENT"), symbol=symbol, as_of=opened.date(),
            entry_id="TEST_ONLY-entry-"+sleeve))
        _, binding = thesis.PersonalEntryThesisService(service.journal, repository=repository).confirm(
            dict(idempotency_key="TEST_ONLY-bind-"+sleeve, expected_revision=len(service.records()),
                fill_record_sha256=bought, binding_mode="CONTEMPORANEOUS", read_and_confirmed=True,
                confirmation_note="TEST_ONLY original rationale", entry_artifact_id=entry.artifact_id,
                consistency_artifact_id=consistency.artifact_id),
            repository_root=root, authenticated_subject="LOCAL_OPERATOR", now=opened)
        original_bindings[sleeve] = binding

    clock[0] = Clock.fromisoformat("2026-09-21T20:00:00+08:00")
    monkeypatch.setattr(thesis, "_application_repository", lambda *a, **k: repository)
    monkeypatch.setattr(projection, "_verified_attributes", lambda *a, **k: [_attributes(symbol).as_policy()])
    monkeypatch.setattr(projection, "_verified_prices", lambda *a, **k: {
        symbol: dict(price_cny="5", trade_date=clock[0].date().isoformat(), price_admitted=True,
            current_pit=True, scope="TEST_ONLY_SOURCE_ADAPTER", bundle_sha256="b"*64)})
    allocations = projection._allocations_payload
    monkeypatch.setattr(projection, "_allocations_payload", lambda replayed, day: [
        {**row, "committed_risk_cny": "100", "evidence_ref": "TEST_ONLY_EXPLICIT_RISK_NOT_REAL_ADMISSION"}
        for row in allocations(replayed, day)])

    def reconcile(key):
        service.reconcile(dict(idempotency_key=key, expected_revision=len(service.records()),
            reconciled_at=clock[0].isoformat(), confirmation_note="TEST_ONLY statement",
            account_evidence=dict(id=key, kind="broker_statement")))

    reconcile("TEST_ONLY-initial-reconcile")
    with _use_test_trust_registry(root / "TEST_ONLY-combined-trust-registry.json"):
        for index, (state, action, quantity) in enumerate((
                ("CONSISTENT", "HOLD", None), ("FULFILLED", "ADD", 100),
                ("WEAKENED", "REDUCE", 200), ("BROKEN", "EXIT", 200))):
            clock[0] += timedelta(seconds=1)
            save(replace(_consistency(state), symbol=symbol, as_of=clock[0].date(),
                entry_id="TEST_ONLY-entry-CORE_VALUE", review_id="TEST_ONLY-current-"+state))
            context = thesis.owned_entry_context(records=service.records(), symbol=symbol,
                sleeve="CORE_VALUE", authenticated_subject="LOCAL_OPERATOR", as_of=clock[0])
            extra = {}
            if action == "ADD":
                extra["core_request"] = dict(symbol=symbol, entry_price_cny="5", entry_slippage_cny="0",
                    buy_fee_fraction="0", minimum_buy_fee_cny="1", lot_size=100,
                    max_trade_notional_cny="501", quote_as_of=clock[0].date().isoformat(),
                    available_at=clock[0].isoformat(), valid_until=(clock[0]+timedelta(hours=1)).isoformat(),
                    liquidity_verified=True, limit_up=False, limit_down=False)
            risk = projection.review_private_risk_rehearsal(service.journal, repository_root=root,
                generated_at=clock[0], today=clock[0].date(), **extra)
            position = service._positions(service._replay(service.records()).state, clock[0].date())[0]
            sleeve_position = next(part for part in position["sleeves"] if part["sleeve"] == "CORE_VALUE")
            if index == 0:
                engine = risk["engine"]
                assert engine["aggregate"]["cash_cny"] == "7000"
                assert engine["sleeves"]["CORE_VALUE"]["cash_cny"] == "5000"
                assert engine["sleeves"]["HOTSPOT_SATELLITE"]["cash_cny"] == "1000"
                overlap = engine["aggregate"]["duplicated_security_exposure"][symbol]
                assert sum(Decimal(row["quantity"]) for row in overlap) == 600
                assert sum(Decimal(row["market_value_cny"]) for row in overlap) == 3000
            kwargs = {}
            if action in {"REDUCE", "EXIT"}:
                kwargs["sell_review_request"] = dict(schema_version=SELL_REVIEW_SCHEMA, action="no_order",
                    expected_revision=len(service.records()), account_scope=context["account_scope"],
                    symbol=symbol, exchange="SSE", sleeve="CORE_VALUE", requested_action=action,
                    requested_quantity=quantity, entry_thesis_record_sha256=original_bindings["CORE_VALUE"],
                    read_and_confirmed=True)
            plan = dict(symbol=symbol, strategy="CORE_VALUE", schema_version="value-action-plan-v1",
                action="no_order", action_intent="ADD", add_condition=dict(triggered=True), blockers=[])
            before = service.journal.path.read_bytes()
            result = owned_held_action(context=context, plan=plan, risk=risk, sleeve_position=sleeve_position,
                advisory_provider=lambda: evaluate_owned_held_advisory(root, context=context, plan=plan, now=clock[0]),
                **kwargs)
            assert service.journal.path.read_bytes() == before
            assert result["namespace"] == "TEST_ONLY" and result["action"] == "no_order"
            assert result["broker_execution_permission"] is result["trade_eligible"] is False
            assert result["entry_thesis_record_sha256"] == original_bindings["CORE_VALUE"]
            assert result["original_thesis"] == context["entry_thesis"].thesis
            if concentrated and action in {"HOLD", "ADD"}:
                assert result["decision_action"] == "UNASSESSABLE"
                assert result["review_quantity"] is None
                continue
            assert result["decision_action"] == action, result["blockers"]
            assert result["review_quantity"] == quantity
            assert result["decision_reason"] and result["advisory"]["current_consistency_status"] == state
            if concentrated:
                assert result["personal_risk_status"] == "REVIEW_REQUIRED" and result["risk_warnings"]
            if action in {"REDUCE", "EXIT"}:
                fill("SELL", "CORE_VALUE", quantity, "TEST_ONLY-"+action)
                reconcile("TEST_ONLY-reconcile-"+action)
                service = ledger.PrivatePortfolioService(ledger.PrivateJournal(service.journal.path), clock=lambda: clock[0])
                replayed = service._replay(service.records())
                assert sum(lot.quantity for lot in replayed.state.lots if lot.sleeve == "HOTSPOT_SATELLITE") == 200
                assert sum(lot.quantity for lot in replayed.state.lots if lot.sleeve == "CORE_VALUE") == (200 if action == "REDUCE" else 0)
        assert service._replay(service.records()).state.cash_cny == Decimal("9000")
        resolved = thesis.resolve_personal_entry_thesis(records=service.records(),
            account_scope="TEST_ONLY_TWO_SLEEVE_CONCENTRATION", expected_revision=len(service.records()),
            as_of=clock[0], authenticated_subject="LOCAL_OPERATOR")
        by_sleeve = {row["sleeve"]: row for row in resolved["items"]}
        assert by_sleeve["CORE_VALUE"]["remaining_quantity"] == "0"
        assert by_sleeve["HOTSPOT_SATELLITE"]["remaining_quantity"] == "200"
        assert {key: row["current_binding"]["record_sha256"] for key, row in by_sleeve.items()} == original_bindings

"""Retained public-case continuity with an explicitly hypothetical journal entry."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from .current_case_review import inspect_current_price_case
from .event_replay import _bound_bytes
from .lifecycle_review import build_hotspot_lifecycle_review
from .price_action_case import project_current_price_action_plan
from ..portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService
from ...domain.execution.exchange_calendar import next_exchange_session
from ...quote_sessions import CHINA


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def run_simulated_hotspot_lifecycle(*, source_root: Path, workspace_root: Path,
        symbol: str, entry_case_binding: dict, entry_at: datetime,
        followups: list[dict], generated_at: datetime,
        official_event_observation_binding: dict | None = None) -> dict:
    """Exercise real loaders and the existing ledger, not strategy admission.

    Entry is a discretionary 100-share close-mark scenario even if OPEN is false.
    It is recorded now, NOT as a historical executable fill, PIT, OOS or Shadow.
    Every subsequent action remains a review; this adapter never trades on it.
    Source bindings are relative to source_root; journal paths to workspace_root.
    """
    moments = [entry_at, generated_at, *(row["evaluated_at"] for row in followups)]
    if any(not isinstance(value, datetime) or value.utcoffset() is None for value in moments):
        raise ValueError("Simulation requires aware timestamps")
    if not followups or moments[2:] != sorted(moments[2:]) or any(
            value <= entry_at or value > generated_at for value in moments[2:]):
        raise ValueError("Followups must follow entry in chronological order, before generation")
    source_root = Path(source_root).resolve(strict=True)
    workspace_root = Path(workspace_root).resolve(strict=True)
    original = inspect_current_price_case(root=source_root, symbol=symbol,
        case_binding=entry_case_binding, now=entry_at)
    if original["data_status"] != "CURRENT":
        raise ValueError("Entry source not valid at assumed entry cutoff")
    case = original["case"]
    quote = case["current_reference_close"]
    bundle = json.loads(_bound_bytes(source_root,
        dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])))
    source_scope = ("TEST_ONLY" if bundle.get("test_only") or
        bundle.get("fixture_scope") == "TEST_ONLY" else
        "PUBLIC_PROVIDER_ARCHIVE_NOT_INDEPENDENT_MINUTE_VALIDATION")
    plan = project_current_price_action_plan(case)
    price = Decimal(case["current_reference_price"])
    if not price.is_finite() or price <= 0:
        raise ValueError("Positive finite entry close required")
    entry_review = build_hotspot_lifecycle_review(root=source_root, symbol=symbol,
        current_case_binding=entry_case_binding, now=entry_at,
        official_event_observation_binding=official_event_observation_binding)
    frozen = deepcopy(dict(namespace="SIMULATED", symbol=symbol,
        generated_at=generated_at.isoformat(), assumed_entry_at=entry_at.isoformat(),
        entry_case_binding=entry_case_binding, rule_version=plan["model_or_rule_version"],
        reference_close=str(price), original_protection_price=plan["invalidation_price"],
        candidate_review=entry_review, conditional_action_rules=plan["conditional_action_rules"],
        rationale="Exercise original-entry continuity with a discretionary close-mark assumption; "
            "the candidate review below remains authoritative about missing entry conditions",
        entry_review_basis=entry_review["decision_explanation"]["basis_code"],
        entry_origin="DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED",
        fill_scope="HYPOTHETICAL_CLOSE_MARK_NOT_EXECUTABLE_OR_CONFIRMED_MARKET_FILL"))
    frozen_hash = _digest(frozen)
    reviews = [build_hotspot_lifecycle_review(root=source_root, symbol=symbol,
        current_case_binding=row["case_binding"], now=row["evaluated_at"],
        entry_case_binding=entry_case_binding, entry_at=entry_at,
        official_event_observation_binding=official_event_observation_binding) for row in followups]

    # Only create a new isolated scenario ledger, never accept a caller's journal.
    parent = workspace_root
    for part in ("runtime", "swing-simulated-lifecycle"):
        parent = parent / part
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError("Simulation output cannot traverse a symlink or non-directory")
        if not parent.resolve().is_relative_to(workspace_root):
            raise ValueError("Simulation output must remain inside workspace")
        parent.mkdir(exist_ok=True)
    directory = parent / uuid4().hex
    directory.mkdir()
    journal_path = directory / "SIMULATED-journal.jsonl"
    service = PrivatePortfolioService(PrivateJournal(journal_path), clock=lambda: generated_at)
    entry_day = entry_at.astimezone(CHINA).date()
    exchange = "SSE" if symbol.startswith("6") else "SZSE"
    service.initialize(dict(idempotency_key="SIMULATED-init", expected_revision=0,
        account_scope="SIMULATED_HOTSPOT_LIFECYCLE", as_of=entry_day.isoformat(),
        cash_cny=str(price * 100 + Decimal("10000")), holdings=[], sleeve_allocations={},
        policy={}, confirmed_at=generated_at.isoformat(),
        confirmation_note="SIMULATED retrospective scenario, not user or broker confirmation"))
    _, digest = service.prepare_fill(dict(idempotency_key="SIMULATED-prepare-entry",
        expected_revision=len(service.records()), note="SIMULATED non-executable close mark",
        fill=dict(transaction_id="SIMULATED-ENTRY", side="BUY", sleeve="HOTSPOT_SATELLITE",
            symbol=symbol, exchange=exchange, quantity="100", trading_unit="100",
            price_cny=str(price), fees_cny="5", trade_date=entry_day.isoformat(),
            next_sell_session=next_exchange_session(exchange, entry_day).isoformat())))
    request = dict(idempotency_key="SIMULATED-confirm-entry",
        expected_revision=len(service.records()), prepared_record_sha256=digest,
        confirmed_at=generated_at.isoformat(),
        confirmation_note="SIMULATED scripted ledger confirmation only; not actual approval")
    confirmation = service.confirm_fill(request)
    before = journal_path.read_bytes()
    idempotent = service.confirm_fill(request) == confirmation and journal_path.read_bytes() == before
    steps = []
    for review in reviews:
        steps.append(dict(lifecycle_review=review, namespace="SIMULATED",
            intentions={intent: dict(status="REVIEW_ONLY_NO_SIMULATED_FOLLOWUP_FILL",
                observed=review["current_conditions"].get(intent, {}).get("observed"),
                blockers=list(dict.fromkeys([*review["blockers"],
                    "SIMULATED_ENTRY_IS_NOT_VERIFIED_OWNERSHIP",
                    "INDEPENDENT_STRATEGY_ADMISSION_NOT_PROVEN"])), action="no_order")
                for intent in ("ADD", "REDUCE", "EXIT")}, action="no_order"))
    restarted = PrivatePortfolioService(PrivateJournal(journal_path), clock=lambda: generated_at)
    replay = restarted._replay(restarted.records())
    if replay is None or _digest(frozen) != frozen_hash or journal_path.read_bytes() != before:
        raise ValueError("Simulation journal or frozen entry unexpectedly changed")
    relative = journal_path.relative_to(workspace_root).as_posix()
    return dict(schema_version="hotspot-simulated-lifecycle-v1", namespace="SIMULATED",
        symbol=symbol, generated_at=generated_at.isoformat(), action="no_order",
        scope="RETAINED_SOURCE_RETROSPECTIVE_NOT_PIT_OOS_OR_SHADOW",
        market_source_scope=source_scope,
        entry_reference=frozen, entry_freeze_sha256=frozen_hash, steps=steps,
        actual_account_used=False, actual_owned_entry_created=False,
        broker_execution_permission=False, formal_eligibility=False, trade_eligible=False,
        strategy_validation="NOT_PROVEN", position_guidance=None,
        simulated_fill_count=1, followup_fill_count=0,
        journal_receipt=dict(path=relative, sha256=sha256(before).hexdigest(),
            record_count=len(restarted.records()), retained=True,
            namespace="SIMULATED", confirmation_idempotent=idempotent,
            unchanged_by_followup=True, restart_verified=True),
        simulated_accounting=dict(cash_cny=str(replay.state.cash_cny),
            positions=restarted._positions(replay.state, generated_at.date())),
        assumptions=dict(quantity="100 hypothetical shares, NOT position guidance",
            fees="5 CNY synthetic journal fixture, NOT verified actual execution costs",
            entry="Discretionary hypothetical close mark, NOT evidence of a strategy-qualified entry",
            timing="Historical evaluation cutoffs; journal confirmation generated now, never backdated",
            event_coverage="SUPPLIED_OBSERVATION_REVERIFIED" if official_event_observation_binding
                else "OFFICIAL_EVENT_OBSERVATION_NOT_SUPPLIED"))

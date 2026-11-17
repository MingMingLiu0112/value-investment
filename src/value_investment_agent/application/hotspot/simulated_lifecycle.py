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


def _source_scope(root, binding, review):
    if review["source_integrity"] != "VERIFIED":
        return "UNVERIFIED"
    case = json.loads(_bound_bytes(root, binding))
    quote = case["current_reference_close"]
    bundle = json.loads(_bound_bytes(root,
        dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])))
    declarations = {str(item.get(key, "")).strip().upper() for item in (case, bundle)
        for key in ("namespace", "fixture_scope")}
    if any(item.get("test_only") for item in (case, bundle)) or "TEST_ONLY" in declarations:
        return "TEST_ONLY"
    if declarations & {"SIMULATED", "SYNTHETIC"}:
        return "SIMULATED"
    return "ORIGIN_NOT_ATTESTED"


def _event_scope(review, binding):
    coverage = (review.get("price_comparability") or {}).get("official_disclosure_coverage", {})
    return dict(evaluated_at=review["evaluated_at"], supplied_binding=deepcopy(binding),
        official_publication_coverage=coverage.get("official_publication_coverage",
            "NOT_EVALUATED" if binding is not None else "MISSING"),
        corporate_action_coverage=coverage.get("corporate_action_coverage", "UNKNOWN"))


def _entry_reference(symbol, binding, entry_at, generated_at, case, plan, review):
    return deepcopy(dict(namespace="SIMULATED", symbol=symbol,
        generated_at=generated_at.isoformat(), assumed_entry_at=entry_at.isoformat(),
        entry_case_binding=binding, rule_version=plan["model_or_rule_version"],
        reference_close=str(Decimal(case["current_reference_price"])),
        original_protection_price=plan["invalidation_price"], candidate_review=review,
        conditional_action_rules=plan["conditional_action_rules"],
        rationale="Exercise original-entry continuity with a discretionary close-mark assumption; "
            "the candidate review below remains authoritative about missing entry conditions",
        entry_review_basis=review["decision_explanation"]["basis_code"],
        entry_origin="DISCRETIONARY_SIMULATION_NOT_STRATEGY_TRIGGERED",
        fill_scope="HYPOTHETICAL_CLOSE_MARK_NOT_EXECUTABLE_OR_CONFIRMED_MARKET_FILL"))


def _step(review):
    return dict(lifecycle_review=review, namespace="SIMULATED",
        intentions={intent: dict(status="REVIEW_ONLY_NO_SIMULATED_FOLLOWUP_FILL",
            observed=review["current_conditions"].get(intent, {}).get("observed"),
            blockers=list(dict.fromkeys([*review["blockers"],
                "SIMULATED_ENTRY_IS_NOT_VERIFIED_OWNERSHIP",
                "INDEPENDENT_STRATEGY_ADMISSION_NOT_PROVEN"])), action="no_order")
            for intent in ("ADD", "REDUCE", "EXIT")}, action="no_order")


def _assumptions(official):
    return dict(quantity="100 hypothetical shares, NOT position guidance",
        fees="5 CNY synthetic journal fixture, NOT verified actual execution costs",
        entry="Discretionary hypothetical close mark, NOT evidence of a strategy-qualified entry",
        timing="Historical evaluation cutoffs; journal confirmation generated now, never backdated",
        event_coverage="SEE_PER_CUTOFF_NATIVE_REVIEWS" if official is not None
            else "OFFICIAL_EVENT_OBSERVATION_NOT_SUPPLIED")


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
    plan = project_current_price_action_plan(case)
    price = Decimal(case["current_reference_price"])
    if not price.is_finite() or price <= 0:
        raise ValueError("Positive finite entry close required")
    entry_review = build_hotspot_lifecycle_review(root=source_root, symbol=symbol,
        current_case_binding=entry_case_binding, now=entry_at,
        official_event_observation_binding=official_event_observation_binding)
    frozen = _entry_reference(symbol, entry_case_binding, entry_at, generated_at, case, plan, entry_review)
    frozen_hash = _digest(frozen)
    reviews = [build_hotspot_lifecycle_review(root=source_root, symbol=symbol,
        current_case_binding=row["case_binding"], now=row["evaluated_at"],
        entry_case_binding=entry_case_binding, entry_at=entry_at,
        official_event_observation_binding=official_event_observation_binding) for row in followups]
    evidence_scopes = [dict(case_binding=deepcopy(entry_case_binding),
        evaluated_at=entry_at.isoformat(), scope=_source_scope(source_root, entry_case_binding, original))]
    evidence_scopes.extend(dict(case_binding=deepcopy(row["case_binding"]),
        evaluated_at=review["evaluated_at"], scope=_source_scope(source_root, row["case_binding"], review))
        for row, review in zip(followups, reviews))
    scopes = {row["scope"] for row in evidence_scopes}
    source_scope = next(iter(scopes)) if len(scopes) == 1 else "MIXED_OR_UNVERIFIED_SOURCES"
    event_scopes = [_event_scope(review, official_event_observation_binding)
        for review in (entry_review, *reviews)]

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
    steps = [_step(review) for review in reviews]
    restarted = PrivatePortfolioService(PrivateJournal(journal_path), clock=lambda: generated_at)
    replay = restarted._replay(restarted.records())
    if replay is None or _digest(frozen) != frozen_hash or journal_path.read_bytes() != before:
        raise ValueError("Simulation journal or frozen entry unexpectedly changed")
    relative = journal_path.relative_to(workspace_root).as_posix()
    return dict(schema_version="hotspot-simulated-lifecycle-v1", namespace="SIMULATED",
        symbol=symbol, generated_at=generated_at.isoformat(), action="no_order",
        scope="RETAINED_SOURCE_RETROSPECTIVE_NOT_PIT_OOS_OR_SHADOW",
        market_source_scope=source_scope,
        market_evidence_scopes=evidence_scopes, official_event_reviews=event_scopes,
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
        assumptions=_assumptions(official_event_observation_binding))


def _runtime_bytes(root, binding):
    path = Path(binding["path"])
    if path.is_absolute() or not path.parts or path.parts[0] != "runtime" or ".." in path.parts:
        raise ValueError("Simulation bindings must stay under runtime")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root / "runtime"):
        raise ValueError("Resolved simulation binding escapes runtime")
    return _bound_bytes(root, dict(path=resolved.relative_to(root).as_posix(), sha256=binding["sha256"]))


def _cutoff(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Simulation cutoff is naive or in the future")
    return stamp


def _no_permissions(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"formal_eligibility", "trade_eligible", "risk_review_eligible",
                    "personal_permission", "broker_execution_permission", "actual_account_used",
                    "actual_owned_entry_created"} and item is not False:
                raise ValueError("Simulation cannot grant permissions")
            if key == "action" and item != "no_order":
                raise ValueError("Simulation action must remain no_order")
            _no_permissions(item)
    elif isinstance(value, list):
        for item in value:
            _no_permissions(item)


def load_simulated_hotspot_lifecycle(root: Path, receipt_binding: dict, now: datetime) -> dict:
    """Verify retained historical simulation; never transact or follow source_root.

    All source files must already exist under this root's runtime directory.
    Verification is hash/native-replay/accounting integrity, not strategy approval.
    """
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Simulation reader requires an aware verification clock")
    root = Path(root).resolve(strict=True)
    receipt_raw = _runtime_bytes(root, receipt_binding)
    receipt = json.loads(receipt_raw)
    _no_permissions(receipt)
    if (receipt["namespace"] != "SIMULATED" or receipt["action"] != "no_order"
            or receipt["strategy_validation"] != "NOT_PROVEN"
            or receipt["historical_pit_proven"] is not False
            or receipt["independent_oos_proven"] is not False
            or any(type(receipt[key]) is not int or receipt[key] != 0 for key in (
                "actual_owned_entries", "actual_accounts_used", "real_shadow_credit", "followup_fill_count"))):
        raise ValueError("Receipt cannot assert real ownership or validation")
    sealed_at = _cutoff(receipt["generated_at"], now)
    directory = Path(receipt_binding["path"]).parent
    result_binding = dict(path=(directory / "lifecycle-simulation.json").as_posix(),
        sha256=receipt["outputs"]["lifecycle-simulation.json"])
    report = json.loads(_runtime_bytes(root, result_binding))
    _no_permissions(report)
    expected_fields = {"schema_version", "namespace", "symbol", "generated_at", "action", "scope",
        "market_source_scope", "market_evidence_scopes", "official_event_reviews", "entry_reference",
        "entry_freeze_sha256", "steps", "actual_account_used", "actual_owned_entry_created",
        "broker_execution_permission", "formal_eligibility", "trade_eligible", "strategy_validation",
        "position_guidance", "simulated_fill_count", "followup_fill_count", "journal_receipt",
        "simulated_accounting", "assumptions"}
    if set(report) != expected_fields:
        raise ValueError("Simulation result fields differ from sealed contract")
    if (report["schema_version"] != "hotspot-simulated-lifecycle-v1"
            or report["namespace"] != "SIMULATED" or report["action"] != "no_order"
            or report["scope"] != "RETAINED_SOURCE_RETROSPECTIVE_NOT_PIT_OOS_OR_SHADOW"
            or report["strategy_validation"] != "NOT_PROVEN" or report["position_guidance"] is not None
            or type(report["simulated_fill_count"]) is not int or report["simulated_fill_count"] != 1
            or type(report["followup_fill_count"]) is not int or report["followup_fill_count"] != 0
            or any(report.get(key) is not False for key in ("actual_account_used",
                "actual_owned_entry_created", "broker_execution_permission", "formal_eligibility", "trade_eligible"))):
        raise ValueError("Result must remain a historical simulated review")
    generated = _cutoff(report["generated_at"], sealed_at)
    entry = report["entry_reference"]
    entry_at = _cutoff(entry["assumed_entry_at"], generated)
    symbol = report["symbol"]
    sources = {}
    for binding in receipt["source_bindings"]:
        _runtime_bytes(root, binding)
        if binding["path"] in sources:
            raise ValueError("Duplicate simulation source binding")
        sources[binding["path"]] = binding["sha256"]
    needed = {}

    def inspect(binding, at):
        case = json.loads(_runtime_bytes(root, binding))
        quote = case["current_reference_close"]
        for ref in (binding, *case["source_bindings"].values(),
                dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])):
            _runtime_bytes(root, ref)
            needed[ref["path"]] = ref["sha256"]
        result = inspect_current_price_case(root=root, symbol=symbol, case_binding=binding, now=at)
        if result["source_integrity"] != "VERIFIED":
            raise ValueError("Simulation price evidence failed native verification")
        return result

    original = inspect(entry["entry_case_binding"], entry_at)
    if original["data_status"] != "CURRENT":
        raise ValueError("Simulation entry not valid at its cutoff")
    official = report["official_event_reviews"][0]["supplied_binding"]
    if official is not None:
        raise ValueError("Official-event bundles are outside this retained price-only consumer contract")
    native_entry = build_hotspot_lifecycle_review(root=root, symbol=symbol,
        current_case_binding=entry["entry_case_binding"], now=entry_at,
        official_event_observation_binding=official)
    expected_entry = _entry_reference(symbol, entry["entry_case_binding"], entry_at, generated,
        original["case"], project_current_price_action_plan(original["case"]), native_entry)
    if entry != expected_entry or _digest(expected_entry) != report["entry_freeze_sha256"]:
        raise ValueError("Frozen simulated entry differs from native evidence")
    native_reviews, scopes = [], [dict(case_binding=deepcopy(entry["entry_case_binding"]),
        evaluated_at=entry_at.isoformat(), scope=_source_scope(root, entry["entry_case_binding"], original))]
    previous = entry_at
    for step in report["steps"]:
        retained = step["lifecycle_review"]
        at = _cutoff(retained["evaluated_at"], generated)
        if at <= entry_at or at < previous:
            raise ValueError("Simulation review cutoffs are out of order")
        previous = at
        binding = retained["current_case_binding"]
        inspected = inspect(binding, at)
        native = build_hotspot_lifecycle_review(root=root, symbol=symbol, current_case_binding=binding,
            now=at, entry_case_binding=entry["entry_case_binding"], entry_at=entry_at,
            official_event_observation_binding=official)
        if step != _step(native):
            raise ValueError("Retained simulated review differs from native replay")
        native_reviews.append(native)
        scopes.append(dict(case_binding=deepcopy(binding), evaluated_at=at.isoformat(),
            scope=_source_scope(root, binding, inspected)))
    if not native_reviews:
        raise ValueError("Simulation requires a subsequent review")
    for review in (native_entry, *native_reviews):
        coverage = (review.get("price_comparability") or {}).get("official_disclosure_coverage", {})
        for ref in coverage.get("evidence_bindings", []):
            _runtime_bytes(root, ref)
            needed[ref["path"]] = ref["sha256"]
    declared = {item["scope"] for item in scopes}
    scope = next(iter(declared)) if len(declared) == 1 else "MIXED_OR_UNVERIFIED_SOURCES"
    if (sources != needed or report["market_evidence_scopes"] != scopes
            or report["market_source_scope"] != scope
            or report["assumptions"] != _assumptions(official)
            or report["official_event_reviews"] != [_event_scope(r, official)
                for r in (native_entry, *native_reviews)]):
        raise ValueError("Simulation source or official-event scope mismatch")
    journal = report["journal_receipt"]
    journal_binding = dict(path=(directory / "SIMULATED-journal.jsonl").as_posix(),
        sha256=receipt["outputs"]["SIMULATED-journal.jsonl"])
    if journal["path"] != journal_binding["path"] or journal["sha256"] != journal_binding["sha256"]:
        raise ValueError("Simulation journal binding mismatch")
    journal_raw = _runtime_bytes(root, journal_binding)
    records = [json.loads(line) for line in journal_raw.decode("utf-8").splitlines() if line.strip()]
    previous_hash, previous_time = None, generated
    for index, record in enumerate(records, 1):
        PrivateJournal._validate_record(record, line_number=index, previous=previous_hash)
        recorded_at = _cutoff(record["recorded_at"], sealed_at)
        if recorded_at < previous_time:
            raise ValueError("Simulation journal time is backdated or out of order")
        previous_time = recorded_at
        _no_permissions(record)
        previous_hash = record["record_sha256"]
    if ([r["kind"] for r in records] != ["BASELINE_CONFIRMED", "FILL_PREPARED", "FILL_CONFIRMED"]
            or journal["namespace"] != "SIMULATED" or journal["record_count"] != len(records)):
        raise ValueError("Simulation journal must contain one hypothetical entry only")
    prepared_at = _cutoff(records[1]["body"]["prepared_at"], sealed_at)
    if not _cutoff(records[0]["recorded_at"], sealed_at) <= prepared_at <= _cutoff(
            records[1]["recorded_at"], sealed_at):
        raise ValueError("Simulation preparation time differs from recording order")
    price = Decimal(expected_entry["reference_close"])
    baseline = records[0]["body"]
    fill = records[-1]["body"]["fill"]
    expected_fill = dict(transaction_id="SIMULATED-ENTRY", side="BUY", sleeve="HOTSPOT_SATELLITE",
        symbol=symbol, exchange="SSE" if symbol.startswith("6") else "SZSE", quantity="100",
        price_cny=str(price), fees_cny="5", trade_date=entry_at.astimezone(CHINA).date().isoformat(),
        trading_unit="100", corporate_action=False, decision_id=None, research_version=None,
        judgment_snapshot=None)
    expected_fill["next_sell_session"] = next_exchange_session(expected_fill["exchange"],
        entry_at.astimezone(CHINA).date()).isoformat()
    if (baseline["account_scope"] != "SIMULATED_HOTSPOT_LIFECYCLE" or baseline["holdings"] != []
            or Decimal(baseline["cash_cny"]) != price * 100 + Decimal("10000")
            or baseline["as_of"] != expected_fill["trade_date"]
            or baseline["available_at"] != generated.isoformat()
            or baseline["confirmation"]["confirmed_at"] != generated.isoformat()
            or records[-1]["body"]["confirmation"]["confirmed_at"] != generated.isoformat()
            or baseline["policy"] != dict(action="no_order", restrictions=["no_order"])
            or baseline["sleeve_allocations"] != {}
            or fill != expected_fill or records[1]["body"]["fill"] != expected_fill):
        raise ValueError("Journal does not match hypothetical entry assumptions")
    # _replay consumes validated in-memory records; do not call records()/transaction().
    service = PrivatePortfolioService(PrivateJournal(root / journal_binding["path"]), clock=lambda: generated)
    replay = service._replay(records)
    if (replay is None or replay.pending is not None or len(replay.trades) != 1
            or report["simulated_accounting"] != dict(cash_cny=str(replay.state.cash_cny),
                positions=service._positions(replay.state, generated.date()))):
        raise ValueError("Retained simulated accounting differs from journal replay")
    if records[-1]["body"]["trade"] != {key: value for key, value in replay.trades[0].items()
            if key != "record_sha256"}:
        raise ValueError("Retained trade differs from native journal replay")
    for binding in (receipt_binding, result_binding, journal_binding, *receipt["source_bindings"]):
        _runtime_bytes(root, binding)
    return dict(schema_version="hotspot-simulated-lifecycle-read-v1", verified=True,
        status="VERIFIED_HISTORICAL_SIMULATION", verified_at=now.isoformat(),
        verification_scope="HASH_NATIVE_REPLAY_AND_SIMULATED_ACCOUNTING_ONLY",
        receipt_binding=deepcopy(receipt_binding), report=deepcopy(report), source_file_count=len(sources),
        historical_only=True, current_signal=False, current_pit=False, namespace="SIMULATED",
        actual_account_used=False, actual_owned_entry_created=False, formal_eligibility=False,
        broker_execution_permission=False, trade_eligible=False, position_guidance=None,
        strategy_validation="NOT_PROVEN", action="no_order")

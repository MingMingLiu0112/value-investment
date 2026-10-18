"""Private, read-only held-security review independent of candidate retention.

Call only behind the existing private authorization boundary. Never attach this
result to a public packet. Price providers must return existing engine plans,
not user-supplied price flags. No provider failure may remove a held security.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
from uuid import uuid4

from .private_portfolio_service import PrivatePortfolioService, JournalConflict, JournalValidationError
from .private_risk_projection import review_private_risk_rehearsal
from ..hotspot.price_action_case import project_current_price_action_plan
from ...infrastructure.hotspot.current_price_case import load_current_price_case, collect_current_price_case
from ...quote_session_collection import collect_session_bundle
from ...quote_sessions import parse_quote, evaluate_quote_session
from ..hotspot.current_registry import load_price_conditions
from ..decision.value_action_plan import load_registered_value_action_plans


def _plan_sleeve(plan: dict) -> str | None:
    sleeve = {
        "value-action-plan-v1": "CORE_VALUE",
        "price-action-plan-current-v1": "HOTSPOT_SATELLITE",
        "price-action-plan-independent-v2": "HOTSPOT_SATELLITE",
    }.get(plan.get("schema_version"))
    if (sleeve is None or plan.get("strategy", sleeve) != sleeve
            or plan.get("sleeve", sleeve) != sleeve):
        return None
    return sleeve


def _case_history(root: Path, symbol: str):
    """Existing immutable case history, not a second membership/quote registry."""
    history = root / "runtime/hotspot-current-price-cases"
    paths = list(history.glob(f"{symbol}-*/case.json"))
    return sorted(paths, key=lambda path: path.stat().st_mtime_ns, reverse=True)[:5]


def refresh_held_continuity(journal, *, repository_root: Path, payload: dict,
                             generated_at: datetime) -> dict:
    """Explicit private POST only; collect public evidence without publishing membership.

    No ledger append, candidate registry, current pointer or publication writes.
    Existing collectors keep their original source/session/size/retry gates.
    """
    if generated_at.utcoffset() is None:
        raise JournalValidationError("Timezone-aware refresh clock required")
    if set(payload) - {"expected_revision", "symbols"}:
        raise JournalValidationError("Unsupported held refresh fields")
    service = PrivatePortfolioService(journal)
    records = service.records()
    revision = len(records)
    if type(payload.get("expected_revision")) is not int or payload["expected_revision"] != revision:
        raise JournalConflict("REVISION_CONFLICT", "Refresh requires the current portfolio revision")
    replayed = service._replay(records)
    symbols = sorted({lot.symbol for lot in replayed.state.lots if lot.quantity > 0}) if replayed else []
    requested = payload.get("symbols", symbols[:5])
    if (not isinstance(requested, list) or len(requested) > 5
            or any(not isinstance(symbol, str) or symbol not in symbols for symbol in requested)
            or len(set(requested)) != len(requested)):
        raise JournalValidationError("Refresh accepts at most five unique actual held symbols")
    items, failures = [], []
    for symbol in requested:
        if not symbol.startswith(("0", "3", "6")):
            failures.append({"symbol": symbol, "reason": "EXISTING_CURRENT_CASE_COLLECTOR_UNSUPPORTED_SECURITY",
                "gap_category": "ENGINEERING", "gap_code": "HELD_SECURITY_COLLECTOR_UNSUPPORTED"})
            continue
        try:
            existing = None
            for path in _case_history(repository_root, symbol):
                try:
                    existing = load_held_price_plan(repository_root, symbol,
                        {"case_path": str(path), "case_sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                        now=generated_at)
                    break
                except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                    continue
            if existing is not None:
                items.append({"symbol": symbol, "case_path": existing["case_path"],
                    "case_sha256": existing["case_sha256"], "market_trade_date": existing["market_trade_date"],
                    "evidence_status": "REUSED_VERIFIED_LATEST_COMPLETED_CASE",
                    "observation_scope": existing.get("observation_scope", "SAME_SESSION_B1"),
                    "formal_eligibility": False})
                continue
            bundle = collect_session_bundle([symbol])
            # Generic existing public evidence storage; no held-membership report.
            archive = repository_root / "runtime/hotspot-current-refresh" / uuid4().hex
            archive.mkdir(parents=True)
            bundle_path = archive / "bundle.json"
            with bundle_path.open("x", encoding="utf-8") as stream:
                json.dump(bundle, stream, ensure_ascii=False, indent=2)
            digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            now = datetime.now(timezone.utc)
            ref = bundle["references"][symbol]
            quote = parse_quote(bundle["documents"][ref["document_refs"]["tencent"]], "tencent", symbol, now)
            checked = evaluate_quote_session(symbol, quote["price"], ref, now, documents=bundle["documents"])
            if not checked["passed"]:
                raise ValueError("B1 rejected: " + checked["status"])
            case = collect_current_price_case(root=repository_root, symbol=symbol,
                as_of=date.fromisoformat(checked["expected_session"]),
                quote_bundle_path=bundle_path, quote_bundle_sha256=digest,
                observation_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY")
            # Reverify the collector result; never promote its return flag alone.
            plan = load_held_price_plan(repository_root, symbol, case, now=datetime.now(timezone.utc))
            items.append({"symbol": symbol, "case_path": plan["case_path"],
                          "case_sha256": plan["case_sha256"], "market_trade_date": plan["market_trade_date"],
                          "evidence_status": "COLLECTED_AND_REVERIFIED_LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
                          "observation_scope": "LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
                          "current_pit": False, "price_admitted": False, "formal_eligibility": False})
        except Exception as error:
            # One source failure must not suppress the other held securities.
            timing_gap = "same-session post-close acquisition" in str(error)
            failures.append({"symbol": symbol, "reason": type(error).__name__ + ":" + str(error),
                "gap_category": "ENGINEERING" if timing_gap else "DATA",
                "gap_code": "HELD_NEXT_MORNING_CASE_COLLECTION_UNSUPPORTED" if timing_gap else
                            "HELD_CURRENT_EVIDENCE_UNAVAILABLE"})
    if len(service.records()) != revision:
        raise JournalConflict("REVISION_CONFLICT", "Portfolio changed during refresh; reread holdings")
    pending = [symbol for symbol in symbols if symbol not in requested]
    return {"schema_version": "private-held-continuity-refresh-v1", "action": "no_order",
        "sensitivity": "PRIVATE", "revision": revision, "items": items, "failures": failures,
        "unprocessed_symbols": pending, "status": "PARTIAL" if pending or failures else
        "REFRESHED" if items else "NO_HELD_SECURITIES", "ledger_written": False,
        "public_registry_written": False, "formal_eligibility": False}


def build_held_plan_provider(root: Path, replayed, *, now: datetime):
    """Resolve current evidence, then reverify confirmed recording-time bindings.

    Snapshot observations are never themselves treated as a current plan. Only
    their case path/hash can be reused by the existing current-case verifier.
    """
    try:
        current = load_price_conditions(root, now=now, research_version=None)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        current = {"items": []}
    plans = {row["symbol"]: row["price_action_plan"] for row in current["items"]}
    selected = {symbol for symbol, plan in plans.items()
                if plan.get("candidate_lifecycle") != "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"}
    # Actual ledger lots, not candidate membership or historical trades, decide
    # which strategy can still supply a held-security review after a full sale.
    state = getattr(replayed, "state", None)
    held_sleeves = None if state is None else {}
    if state is not None:
        for lot in state.lots:
            if lot.quantity > 0:
                held_sleeves.setdefault(lot.symbol, set()).add(lot.sleeve)
    retained = {}
    for trade in reversed(replayed.trades if replayed else []):
        snapshot = trade.get("judgment_snapshot")
        try:
            if not isinstance(snapshot, dict):
                continue
            unsigned = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
            digest = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            recorded = datetime.fromisoformat(snapshot["recorded_at"])
            plan = snapshot["plan"]
            symbol = trade["symbol"]
            if (snapshot.get("schema_version") != "private-recording-time-judgment-snapshot-v1"
                    or snapshot.get("action") != "no_order" or digest != snapshot.get("snapshot_sha256")
                    or recorded.utcoffset() is None or recorded > now
                    or snapshot.get("decision_id") != "hotspot-" + symbol
                    or plan.get("symbol") != symbol or plan.get("action") != "no_order"):
                continue
            if plan.get("case_path") and plan.get("case_sha256"):
                retained.setdefault(symbol, []).append(plan)
        except (ValueError, KeyError, TypeError):
            continue

    def strategy_plan(symbol):
        # Standalone source inspection may have no ledger; the final projection
        # below always enforces actual position sleeves before emitting reasons.
        allowed = held_sleeves.get(symbol, set()) if held_sleeves is not None else {"CORE_VALUE", "HOTSPOT_SATELLITE"}
        hotspot_held = "HOTSPOT_SATELLITE" in allowed
        current_plan = plans.get(symbol) if hotspot_held else None
        # The explicit private refresh writes ordinary immutable current cases.
        # Rediscover/reverify them after restart without publishing a held list.
        try:
            for path in _case_history(root, symbol) if hotspot_held else ():
                try:
                    return load_held_price_plan(root, symbol,
                        {"case_path": str(path), "case_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, now=now)
                except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                    continue
        except OSError:
            pass
        if (current_plan and current_plan.get("candidate_lifecycle") != "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
                and current_plan.get("signal_state") not in {"BLOCKED", "STALE", "EXPIRED"}):
            return current_plan
        # Value plans use a different contract: reconstruct with the existing
        # loader rather than requiring the hotspot data_available_at field.
        value = None
        try:
            result = (load_registered_value_action_plans(root, now=now, symbols=[symbol])
                      if "CORE_VALUE" in allowed else {"items": []})
            value = next((row for row in result["items"] if row["symbol"] == symbol), None)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            pass
        if value is not None and value.get("signal_state") not in {"BLOCKED", "STALE", "EXPIRED"}:
            return value
        for binding in retained.get(symbol, []) if hotspot_held else ():
            try:
                return load_held_price_plan(root, symbol, binding, now=now)
            except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
                continue
        if value is not None:
            return value
        return current_plan

    def provider(symbol):
        plan = strategy_plan(symbol)
        if plan is None:
            return None
        result = {**plan, "announcement_coverage_status": "UNKNOWN"}
        result.pop("announcement_coverage", None)
        result.pop("announcement_coverage_gap", None)
        try:
            from ..product.quote_bridge import POINTER_PATH
            from ..product.incremental_validity import (
                registered_package, read_bound_json, load_incremental_scan_binding,
            )
            from ..product.daily_event_observation import verify_retained_event_coverage

            if not isinstance(plan.get("market_trade_date"), str):
                raise ValueError("Plan has no verified completed-session date for announcement coverage")
            cutoff = date.fromisoformat(plan["market_trade_date"])
            package_ref, package = registered_package(root, symbol)
            pointer = json.loads((root / POINTER_PATH).read_bytes())
            binding_ref = pointer["quotes"][symbol]["incremental_validity_binding"]
            load_incremental_scan_binding(root=root, binding_ref=binding_ref, symbol=symbol,
                package_path=root / package_ref["path"], package_sha256=package_ref["sha256"],
                review_cutoff=cutoff, today=now)
            _, binding = read_bound_json(root, binding_ref, "held announcement binding")
            _, observation = read_bound_json(root, binding["observation_ref"], "held announcement observation")
            coverage = verify_retained_event_coverage(root, observation, symbol=symbol,
                required_from=date.fromisoformat(package["point_in_time"]["research_as_of"]),
                required_to=cutoff, now=now)
            result.update(announcement_coverage_status=coverage["coverage_status"],
                announcement_coverage={**coverage,
                    "scope": "RESEARCH_CUTOFF_TO_PLAN_COMPLETED_SESSION_ONLY",
                    "observation_binding": binding["observation_ref"],
                    "earlier_event_reviews_replaced": False})
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            result["announcement_coverage_gap"] = {
                "code": "RETAINED_COVERAGE_NOT_VERIFIED",
                "reason": str(error)[:300],
            }
        return result

    return selected, provider


def load_held_price_plan(root: Path, symbol: str, binding: dict, *, now: datetime) -> dict:
    """Revalidate a retained case directly, without a Top5/previous-items lookup."""
    case = load_current_price_case(root=root, symbol=symbol,
        case_path=root / binding["case_path"],
        expected_sha256=binding["case_sha256"], now=now)
    plan = project_current_price_action_plan(case)
    return {**plan, "case_path": case["case_path"], "case_sha256": case["case_sha256"]}


def project_held_continuity(positions: list[dict], risk: dict, *,
                            selected_symbols, plan_provider, generated_at: datetime) -> dict:
    """Join ALL existing ledger positions to existing plans and risk results.

    Ranking membership is descriptive only. Unknown thesis/event/budget facts
    remain explicit review gaps, independently of a known exit trigger.
    """
    if generated_at.utcoffset() is None:
        raise ValueError("Timezone-aware review clock required")
    selected = set(selected_symbols)
    rows = []
    for position in positions:
        if Decimal(position["quantity"]) <= 0:
            continue
        symbol = position["symbol"]
        gaps = list(risk.get("blockers") or [])
        reasons = []
        plan = None
        held_sleeves = {row["sleeve"] for row in position.get("sleeves", ())
                        if Decimal(row["quantity"]) > 0}
        try:
            plan = plan_provider(symbol)
            if plan is not None:
                if plan.get("symbol") != symbol or plan.get("action") != "no_order":
                    raise ValueError("Unbound or future held-security plan")
                if _plan_sleeve(plan) not in held_sleeves:
                    raise ValueError("Strategy plan does not match a positive held sleeve")
                stamp = plan.get("data_available_at")
                if stamp is not None:
                    available = datetime.fromisoformat(stamp)
                    if available.utcoffset() is None or available > generated_at:
                        raise ValueError("Future held-security plan")
                elif plan.get("schema_version") != "value-action-plan-v1":
                    raise ValueError("Missing plan availability")
                # Provider owns existing-engine freshness verification; retirement
                # must never turn stale observations into current exit evidence.
                if plan.get("signal_state") in {"BLOCKED", "STALE", "EXPIRED", "HISTORICAL_OBSERVATION_NOT_ADMITTED"}:
                    gaps.append("CURRENT_STRATEGY_PLAN_UNAVAILABLE")
                else:
                    behavior = plan.get("price_behavior") or {}
                    if (plan.get("action_intent") in {"EXIT", "REDUCE"}
                            or plan.get("signal_state") == "TRIGGER_REJECTED"
                            or behavior.get("structural_invalidation") is True):
                        reasons.append("INVALIDATION_OR_EXIT_REVIEW")
                    if behavior.get("daily_trend") == "DOWNTREND":
                        reasons.append("DAILY_DOWNTREND_REVIEW")
                gaps.extend(plan.get("blockers") or [])
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            plan = None
        if plan is None:
            gaps.append("CURRENT_STRATEGY_PLAN_UNAVAILABLE")
        announcement_coverage = (plan or {}).get("announcement_coverage_status", "UNKNOWN")
        gaps.append("ENTRY_THESIS_REVIEW_REQUIRED")
        if announcement_coverage != "COMPLETE":
            announcement_coverage = "UNKNOWN"
            gaps.append("ANNOUNCEMENT_COVERAGE_UNKNOWN")
        gaps.append("ANNOUNCEMENT_REVIEW_REQUIRED")
        if not risk.get("engine"):
            gaps.append("PORTFOLIO_RISK_REVIEW_UNAVAILABLE")
        valuation_blockers = (risk.get("facts") or {}).get("valuation_blockers") or []
        sleeves = deepcopy(position.get("sleeves") or [])
        sellable = (None if valuation_blockers else
                    str(sum((Decimal(row["sellable_quantity"]) for row in sleeves), Decimal(0))))
        if sellable is None:
            gaps.extend(valuation_blockers)
            for sleeve in sleeves:
                sleeve["sellable_quantity"] = None
        elif Decimal(sellable) < Decimal(position["quantity"]):
            reasons.append("T_PLUS_ONE_OR_SELLABLE_LIMIT")
        rows.append({"symbol": symbol, "exchange": position["exchange"],
            "quantity": position["quantity"], "sleeves": sleeves,
            "sellable_quantity": sellable, "selected_today": symbol in selected,
            "announcement_coverage_status": announcement_coverage,
            "tracking_basis": "ACTUAL_HELD_SECURITY_NOT_RANKING",
            "review_priority": 0 if "INVALIDATION_OR_EXIT_REVIEW" in reasons else 1,
            "review_reasons": reasons, "data_gaps": list(dict.fromkeys(gaps)),
            "strategy_plan": deepcopy(plan), "formal_eligibility": False,
            "personal_sell_permission": False, "position_guidance": None, "action": "no_order"})
    rows.sort(key=lambda row: (row["review_priority"], row["symbol"], row["exchange"]))
    return {"schema_version": "private-held-continuity-v1", "action": "no_order",
        "sensitivity": "PRIVATE", "generated_at": generated_at.isoformat(),
        "status": "REVIEW_REQUIRED" if rows else "NO_HELD_SECURITIES",
        "items": rows, "risk": deepcopy(risk), "position_guidance": None}


def review_held_continuity(journal, *, repository_root: Path, generated_at: datetime,
                           selected_symbols=(), plan_provider=None) -> dict:
    """Read confirmed lots, existing T+1 and the existing risk engine, never write.

    The default resolver uses current value/hotspot engines and confirmed
    judgment-history case bindings even after registry exit. An explicit
    provider remains available for isolated tests and existing consumers.
    """
    if generated_at.utcoffset() is None:
        raise ValueError("Timezone-aware review clock required")
    day = generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
    service = PrivatePortfolioService(journal)
    records = service.records()
    replayed = service._replay(records)
    if plan_provider is None:
        selected_symbols, plan_provider = build_held_plan_provider(repository_root, replayed, now=generated_at)
    risk = review_private_risk_rehearsal(journal, repository_root=repository_root,
        generated_at=generated_at, today=day)
    if replayed is None:
        result = project_held_continuity([], risk, selected_symbols=selected_symbols,
            plan_provider=plan_provider, generated_at=generated_at)
        result["status"] = "NOT_CONNECTED"
        result["revision"] = 0
        return result
    if (risk.get("facts") or {}).get("revision") != replayed.revision:
        raise ValueError("Private journal changed during held review; retry")
    positions = service._positions(replayed.state, day)
    result = project_held_continuity(positions, risk, selected_symbols=selected_symbols,
        plan_provider=plan_provider, generated_at=generated_at)
    result["revision"] = replayed.revision
    result["sellable_as_of"] = day.isoformat()
    return result

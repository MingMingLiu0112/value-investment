"""Bounded descriptive continuity over immutable current-refresh evidence.

This service does not publish, admit strategies, or monitor private holdings.
Callers supply the completed exchange session, never the machine's date.
"""

from copy import deepcopy
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path

from .daily_selection import verify_daily_selection
from .price_action_case import project_current_price_action_plan
from ...infrastructure.hotspot.current_price_case import load_current_price_case
from ...domain.execution.exchange_calendar import is_exchange_session, next_exchange_session
from ...quote_sessions import CHINA


def _bound(root, binding):
    path = (root / binding["path"]).resolve()
    if not path.is_relative_to(root / "runtime"):
        raise ValueError("Continuity evidence must remain under runtime")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Oversized continuity evidence")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("Continuity evidence hash mismatch")
    return json.loads(raw)


def _observations(root, binding, now):
    registry = _bound(root, binding)
    if (registry.get("schema_version") != "current-price-conditions-v1"
            or registry.get("action") != "no_order"
            or len(registry["items"]) > 10 or len(registry.get("previous_items", [])) > 10):
        raise ValueError("Invalid bounded observation registry")
    result, watches = {}, {}
    for retired, entries in ((False, registry["items"]), (True, registry.get("previous_items", []))):
        for item in entries:
            symbol = item["symbol"]
            if symbol in result:
                raise ValueError("Duplicate continuity symbol")
            watch_binding = item["watch_source_binding"] if retired else registry["watch_source_binding"]
            watch_key = (watch_binding["path"], watch_binding["sha256"])
            if watch_key not in watches:
                watch = _bound(root, watch_binding)
                if watch.get("schema_version") == "hotspot-daily-selection-v1":
                    verify_daily_selection(root, watch)
                elif (watch.get("schema_version") != "hotspot-observation-report-v1"
                      or watch.get("action") != "no_order"):
                    raise ValueError("Unsupported retained watch report")
                watches[watch_key] = watch
            watch = watches[watch_key]
            members = (watch.get("candidate_pool", []) + watch.get("observation_list", [])
                       + watch.get("dated_quote_observations", []))
            if symbol not in {row["symbol"] for row in members}:
                raise ValueError("Observation not bound to selection")
            case_binding = {"path": item["case_path"], "sha256": item["case_sha256"]}
            case = _bound(root, case_binding)
            bundle = _bound(root, {"path": case["current_reference_close"]["bundle_path"],
                                   "sha256": case["current_reference_close"]["bundle_sha256"]})
            # Rebuild at actual acquisition time, not a fabricated current date.
            acquired = max(datetime.fromisoformat(stamp) for stamp in [bundle["finished_at"],
                           *(source["fetched_at"] for source in case["source_bindings"].values())])
            if acquired.utcoffset() is None or acquired > now:
                raise ValueError("Observation unavailable at evaluation cutoff")
            verified = load_current_price_case(root=root, symbol=symbol,
                case_path=root / item["case_path"], expected_sha256=item["case_sha256"], now=acquired)
            plan = project_current_price_action_plan(verified)
            selection_day = watch.get("trade_date")
            if watch["schema_version"] == "hotspot-observation-report-v1":
                quotes = [row for row in watch.get("dated_quote_observations", [])
                          if row.get("symbol") == symbol
                          and row.get("status") == "DATED_DUAL_PROVIDER_OBSERVATION_NOT_PRICE_ADMISSION"]
                dated = [row["quote_date"] for row in quotes
                         if date.fromisoformat(row["quote_date"]) <= date.fromisoformat(plan["market_trade_date"])]
                if not dated:
                    raise ValueError("Legacy watch lacks prior dated observation")
                selection_day = max(dated)
            elif plan["market_trade_date"] != selection_day:
                raise ValueError("Observation and selection session conflict")
            result[symbol] = dict(symbol=symbol, selected=not retired, plan=plan,
                selection_trade_date=selection_day,
                registry_binding=deepcopy(binding), watch_source_binding=deepcopy(watch_binding),
                case_binding=case_binding)
    return result


def _compare(current, previous, *, completed_session, leave_symbols):
    symbols = sorted(current.keys() | previous.keys())
    if len(symbols) > 40:
        raise ValueError("Continuity union exceeds 40 symbols")
    if not set(leave_symbols) <= set(symbols):
        raise ValueError("Cannot leave an unknown observation")
    rows = []
    for symbol in symbols:
        old, fresh = previous.get(symbol), current.get(symbol)
        observation = fresh or old
        plan = observation["plan"]
        day = date.fromisoformat(plan["market_trade_date"])
        if day > completed_session:
            raise ValueError("Future observation session")
        if old and fresh and day < date.fromisoformat(old["plan"]["market_trade_date"]):
            raise ValueError("Observation session regressed")
        expiry_value = plan.get("expires_after_session")
        if expiry_value is None and plan.get("reference_price_scope") == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY":
            venue = "SSE" if symbol.startswith("6") else "SZSE"
            expiry = next_exchange_session(venue, day)
        elif expiry_value is None:
            raise ValueError("Observation plan expiry required")
        else:
            expiry = date.fromisoformat(expiry_value)
        state = plan["signal_state"]
        changed = old is not None and observation["case_binding"] != old["case_binding"]
        comparable = bool(old and old["plan"]["model_or_rule_version"] == plan["model_or_rule_version"])
        if symbol in leave_symbols:
            transition, reason = "left", "EXPLICIT_OBSERVATION_POOL_EXIT"
        elif completed_session >= expiry:
            transition, reason = "expired", "PLAN_SESSION_EXPIRED"
        elif state in {"TRIGGER_REJECTED", "BLOCKED"}:
            transition, reason = "invalid", state
        elif state == "STALE":
            transition, reason = "expired", state
        elif state == "TRIGGER_OBSERVED":
            transition, reason = "triggered", "COMPLETED_BAR_TRIGGER_OBSERVED_ONLY"
        elif state == "TRIGGER_PENDING":
            transition, reason = "approach", "PRICE_ABOVE_TRIGGER_VOLUME_PENDING"
        elif state == "WATCH":
            transition = "new" if old is None else "continue"
            reason = "CURRENT_OBSERVATION" if fresh and fresh["selected"] else "RETAINED_WITHOUT_FRESH_REASSESSMENT"
        else:
            raise ValueError("Unsupported observation signal")
        strengthened = bool(changed and comparable
            and old["plan"].get("price_behavior", {}).get("daily_trend") != "UPTREND"
            and plan.get("price_behavior", {}).get("daily_trend") == "UPTREND"
            and transition not in {"invalid", "expired", "left"})
        rows.append(dict(symbol=symbol, transition=transition, reason=reason,
            trend_strengthened=strengthened, rule_comparable=comparable,
            selected_today=bool(fresh and fresh["selected"]),
            fresh_evidence=bool(fresh and (old is None or changed)),
            observation=deepcopy(observation), previous_observation=deepcopy(old),
            price_admitted=False, current_price_admitted=False,
            formal_eligibility=False, action_eligibility=False, action="no_order"))
    return rows


def compare_observation_continuity(*, root: Path, current_binding: dict,
                                   previous_binding: dict | None, completed_session: date,
                                   now: datetime, leave_symbols=(), held_symbols=()) -> dict:
    """Verify two retained registries and return deterministic observation changes.

    Absence from today's shortlist does not imply an exit. Only explicit exits,
    existing signal invalidation, or the original plan expiry end observation.
    Source-bound plans and dates are returned verbatim, including retained rows.
    """
    if now.utcoffset() is None or type(completed_session) is not date:
        raise ValueError("Explicit session and timezone-aware cutoff required")
    local_now = now.astimezone(CHINA)
    if (not is_exchange_session("SSE", completed_session)
            or completed_session > local_now.date()
            or (completed_session == local_now.date() and local_now.time() < time(15))):
        raise ValueError("Invalid completed exchange session")
    held_symbols = tuple(held_symbols)
    if (len(held_symbols) > 20 or len(set(held_symbols)) != len(held_symbols)
            or any(not isinstance(symbol, str) or len(symbol) != 6
                   or not symbol.isascii() or not symbol.isdigit() for symbol in held_symbols)):
        raise ValueError("Bounded unique held security identities required")
    root = Path(root).resolve()
    current = _observations(root, current_binding, now)
    previous = _observations(root, previous_binding, now) if previous_binding else {}
    rows = _compare(current, previous, completed_session=completed_session, leave_symbols=leave_symbols)
    by_symbol = {row["symbol"]: row for row in rows}
    # Expiry or shortlist removal never disposes of a caller-supplied holding.
    monitoring = [dict(symbol=symbol, status="SEPARATE_HOLDING_REASSESSMENT_REQUIRED",
        observation_transition=by_symbol.get(symbol, {}).get("transition"),
        observation_binding=(by_symbol[symbol]["observation"]["case_binding"] if symbol in by_symbol else None),
        ownership_verified=False, action_eligibility=False, action="no_order")
        for symbol in sorted(held_symbols)]
    return dict(schema_version="hotspot-observation-continuity-v1", scope="OBSERVATION_ONLY",
        completed_session=completed_session.isoformat(), evaluated_at=now.isoformat(),
        items=rows, holding_monitoring_requests=monitoring,
        holdings_scope="NOT_EVALUATED_SEPARATE_MONITORING_REQUIRED",
        price_admitted=False, current_price_admitted=False,
        formal_eligibility=False, action_eligibility=False, action="no_order")

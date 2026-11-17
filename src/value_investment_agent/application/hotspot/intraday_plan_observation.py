"""Trusted-loader plan references compared with verified local Tencent quotes.

JSON digests detect accidental changes, not hostile replacement by an author.
The caller owns source verification and must obtain plans from the real loader.
No M5 event returned by the adapter is ingested or persisted here.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath

from .intraday_conditions import CHINA, evaluate_intraday_condition
from ...domain.execution.exchange_calendar import is_exchange_session, next_exchange_session
from ...domain.hotspot.price_action_plan import RULE_VERSION


BINDING_SCHEMA = "intraday-quote-plan-binding-v1"
RESULT_SCHEMA = "intraday-quote-plan-result-v1"
AGE = timedelta(seconds=120)
BOUNDARY = "QUOTE_REFERENCE_COMPARISON_NOT_COMPLETED_BAR_CONFIRMATION"
KINDS = (("ENTRY_REFERENCE_GT", "GT", "entry_trigger_price"),
         ("INVALIDATION_REFERENCE_LT", "LT", "invalidation_price"))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _clock(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Aware server clock required")
    return value.astimezone(timezone.utc)


def _stamp(value):
    return _clock(datetime.fromisoformat(value))


def _price(value):
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("Explicit finite positive price required")
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ValueError("Explicit finite positive price required")
        return number
    except InvalidOperation as error:
        raise ValueError("Explicit finite positive price required") from error


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_plan(plan, symbol, now):
    if (not isinstance(plan, dict) or not isinstance(symbol, str) or len(symbol) != 6
            or not symbol.isascii() or not symbol.isdigit() or not symbol.startswith(("0", "3", "6"))
            or plan.get("symbol") != symbol or plan.get("schema_version") != "price-action-plan-current-v1"
            or plan.get("strategy") != "HOTSPOT_SATELLITE" or plan.get("action") != "no_order"
            or plan.get("action_eligibility") is not False or plan.get("formal_eligibility") is not False
            or plan.get("model_or_rule_version") != RULE_VERSION
            or plan.get("signal_state") not in {"WATCH", "TRIGGER_PENDING", "TRIGGER_OBSERVED", "TRIGGER_REJECTED"}
            or (plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
                and plan.get("retained_observation_valid") is not True)):
        raise ValueError("Unsupported, missing, historical or stale reference plan")
    venue = "SSE" if symbol.startswith("6") else "SZSE"
    if any(plan[key] != venue for key in ("venue", "exchange") if key in plan):
        raise ValueError("Plan security venue mismatch")
    name = plan.get("case_path")
    if (not isinstance(name, str) or not name or "\\" in name
            or PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or not _sha(plan.get("case_sha256"))):
        raise ValueError("Exact repository-relative case path and SHA-256 required")
    blockers = plan.get("blockers")
    if not isinstance(blockers, list) or any(not isinstance(item, str) or not item for item in blockers):
        raise ValueError("Original plan blockers required")
    day = date.fromisoformat(plan["market_trade_date"])
    if day.isoformat() != plan["market_trade_date"] or not is_exchange_session(venue, day):
        raise ValueError("Invalid reference exchange date")
    available = _stamp(plan["data_available_at"])
    if not datetime.combine(day, time(15), CHINA) <= available <= now:
        raise ValueError("Future or inconsistent plan availability")
    ref = plan["current_reference_close"]
    display = plan["reference_price_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    if (plan["reference_price_scope"] not in {"LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
            "LATEST_COMPLETED_SESSION_DUAL_SOURCE_CLOSE"}
            or ref["status"] != ("VERIFIED_LAST_COMPLETED_CLOSE_DISPLAY_ONLY" if display else "VERIFIED_DUAL_SOURCE_CLOSE")
            or _price(ref["price"]) != _price(plan["current_reference_price"])
            or ("latest_completed_session" in ref and ref["latest_completed_session"] != day.isoformat())):
        raise ValueError("Reference close scope/date/price mismatch")
    if display and any(plan.get(key) is not False for key in ("current_pit", "price_admitted")):
        raise ValueError("Display-only reference cannot claim admission")
    for provider in ("tencent", "sina"):
        provider_at = _stamp(ref["provider_times"][provider])
        if provider_at.astimezone(CHINA).date() != day or provider_at > available:
            raise ValueError("Reference provider date mismatch")
    entry, invalidation = (_price(plan[key]) for key in ("entry_trigger_price", "invalidation_price"))
    if invalidation >= entry:
        raise ValueError("Inconsistent existing entry/invalidation levels")
    primary = plan["levels"]["60m"]
    if entry != _price(primary["prior_max_high"]) or invalidation != _price(primary["prior_min_low"]):
        raise ValueError("Plan thresholds differ from existing primary levels")
    expires = plan.get("expires_after_session")
    if expires is None:
        if not display:
            raise ValueError("Missing plan expiry")
        expiry_day = next_exchange_session(venue, day)
    else:
        expiry_day = date.fromisoformat(expires)
        if expiry_day.isoformat() != expires or expiry_day != next_exchange_session(venue, day):
            raise ValueError("Plan expiry is not the next covered session")
    deadline = datetime.combine(expiry_day, time(15), CHINA).astimezone(timezone.utc)
    return deadline


def bind_quote_plan(plan: dict, *, symbol: str, now: datetime) -> dict:
    """Snapshot an already loader-verified plan, retaining every original field."""
    now = _clock(now)
    plan = json.loads(json.dumps(plan, allow_nan=False))
    try:
        deadline = _validate_plan(plan, symbol, now)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Incomplete reference plan contract") from error
    if now >= deadline:
        raise ValueError("Plan reference expired after next completed session")
    binding = {"schema_version": BINDING_SCHEMA, "symbol": symbol, "plan": plan,
        "plan_sha256": _digest(plan), "bound_at": now.isoformat(), "valid_until": deadline.isoformat(),
        "source_id": "tencent", "source_url": "https://qt.gtimg.cn/q=" +
            ("sh" if symbol.startswith("6") else "sz") + symbol,
        "namespace": "ACTUAL", "scope": BOUNDARY, "action": "no_order",
        "eligibility": False, "m5_admitted": False}
    binding["binding_sha256"] = _digest(binding)
    return binding


def _binding(binding, now):
    if not isinstance(binding, dict):
        raise ValueError("Explicit plan binding required; quote-only observation remains separate")
    bound_at = _stamp(binding["bound_at"])
    expected = bind_quote_plan(binding["plan"], symbol=binding["symbol"], now=bound_at)
    if binding != expected or bound_at > now:
        raise ValueError("Plan binding changed or is from the future")
    return expected


def _conditions(binding):
    plan = binding["plan"]
    return [{"strategy": plan["strategy"], "symbol": binding["symbol"],
        "venue": "SSE" if binding["symbol"].startswith("6") else "SZSE", "condition_id": kind,
        "rule_version": plan["model_or_rule_version"] + ":" + binding["binding_sha256"],
        "source_id": "tencent", "source_url": binding["source_url"], "input_kind": "QUOTE",
        "period": "quote", "operator": operator, "threshold": str(plan[field]), "action": "no_order"}
        for kind, operator, field in KINDS]


def _previous(previous, binding, conditions, now):
    if previous is None:
        return [None, None]
    if not isinstance(previous, dict):
        raise ValueError("Invalid prior plan observation")
    fields = {"schema_version", "symbol", "binding_sha256", "namespace", "scope", "checked_at",
              "states", "transitions", "blockers", "plan_status", "action", "eligibility",
              "m5_admitted", "result_sha256"}
    body = {key: value for key, value in previous.items() if key != "result_sha256"}
    if (set(previous) != fields or previous.get("symbol") != binding["symbol"]
            or previous.get("result_sha256") != _digest(body) or previous.get("binding_sha256") != binding["binding_sha256"]
            or previous.get("schema_version") != RESULT_SCHEMA or previous.get("action") != "no_order"
            or previous.get("eligibility") is not False or previous.get("m5_admitted") is not False
            or previous.get("namespace") != "ACTUAL" or previous.get("scope") != BOUNDARY
            or len(previous.get("states", [])) != 2 or not isinstance(previous.get("transitions"), list)):
        raise ValueError("Foreign, changed or permission-bearing prior result")
    states = []
    for row, condition in zip(previous["states"], conditions):
        if (set(row) != {"kind", "condition", "state", "status", "reason", "next_step", "blockers"}
                or row["kind"] != condition["condition_id"] or row["condition"] != condition):
            raise ValueError("Prior condition changed")
        state = row["state"]
        checked = _stamp(state["checked_at"])
        if checked > now or state["checked_at"] != previous["checked_at"]:
            raise ValueError("Prior cursor clock conflict")
        validated = evaluate_intraday_condition(condition, None, previous=state, now=checked,
            max_age=AGE, namespace="ACTUAL")
        if (set(state) != set(validated.state) or state["cycle"] < 1
                or any(state[key] != validated.state[key] for key in (
                    "binding", "symbol", "strategy", "condition_id", "rule_version", "namespace"))
                or state["session_date"] != checked.astimezone(CHINA).date().isoformat()
                or state["last_bar_end"] is not None or state["last_bar_price"] is not None):
            raise ValueError("Prior cursor fields changed")
        presented = "RISK_REVIEW" if row["kind"] == "INVALIDATION_REFERENCE_LT" and state["status"] == "STRUCTURE_OBSERVATION" else state["status"]
        if row["status"] != presented:
            raise ValueError("Prior presentation differs from native cursor")
        source, received, fingerprint = (state[key] for key in (
            "last_source_at", "last_received_at", "last_fingerprint"))
        if source is None:
            if received is not None or fingerprint is not None:
                raise ValueError("Partial prior source cursor")
        elif not (_stamp(source) <= _stamp(received) <= checked and _sha(fingerprint)):
            raise ValueError("Prior source cursor conflicts with check clock")
        states.append(state)
    return states


def evaluate_quote_plan(binding: dict, observation: dict | None, *, previous: dict | None,
        now: datetime) -> dict:
    """Two reference comparisons, native adapter cursors and local transitions only.

    states[].state retains native adapter status for replay; states[].status
    labels invalidation matches RISK_REVIEW. No confirmed exit or entry exists.
    """
    now = _clock(now)
    binding = _binding(binding, now)
    conditions = _conditions(binding)
    old = _previous(previous, binding, conditions, now)
    plan = binding["plan"]
    blockers = [*plan["blockers"], BOUNDARY, "COMPLETED_BAR_STRATEGY_AND_PRIVATE_GATES_REQUIRED"]
    expired = now >= _stamp(binding["valid_until"])
    if expired:
        blockers.append("PLAN_REFERENCE_EXPIRED")
    unavailable_reason = "PLAN_REFERENCE_EXPIRED" if expired else None
    if observation is not None and not unavailable_reason:
        if (not isinstance(observation, dict) or observation.get("input_kind") != "QUOTE" or observation.get("period") != "quote"
                or observation.get("completed") is not False
                or any(observation.get(key) is not False for key in ("eligibility", "admitted", "b1_eligible"))):
            unavailable_reason = "INVALID_QUOTE_OBSERVATION_CONTRACT"
        else:
            try:
                if _stamp(observation["source_at"]) < _stamp(plan["data_available_at"]):
                    unavailable_reason = "QUOTE_PRECEDES_PLAN_AVAILABILITY"
            except (KeyError, ValueError, TypeError):
                unavailable_reason = "INVALID_QUOTE_CLOCK"
    states, transitions = [], []
    for (kind, _, _), condition, prior in zip(KINDS, conditions, old):
        result = evaluate_intraday_condition(condition, None if unavailable_reason else observation,
            previous=prior, now=now, max_age=AGE, namespace="ACTUAL")
        native = result.state
        status = ("RISK_REVIEW" if kind == "INVALIDATION_REFERENCE_LT"
            and native["status"] == "STRUCTURE_OBSERVATION" else native["status"])
        reason = unavailable_reason or native["reason"]
        next_step = ("REVIEW_EXISTING_INVALIDATION_WITH_COMPLETED_BAR_STRATEGY_AND_PRIVATE_GATES"
            if status == "RISK_REVIEW" else "AWAIT_COMPLETED_BAR_AND_EXISTING_STRATEGY_CONFIRMATION"
            if status == "STRUCTURE_OBSERVATION" else "RESTORE_VERIFIED_PLAN_AND_FRESH_QUOTE"
            if status == "STALE_OR_UNAVAILABLE" else "CONTINUE_REFERENCE_OBSERVATION")
        states.append({"kind": kind, "condition": condition, "state": native, "status": status,
            "reason": reason, "next_step": next_step, "blockers": list(blockers)})
        changed = (prior is None and native["status"] != "NOT_TRIGGERED") or (
            prior is not None and native["status"] != prior["status"])
        if changed:
            transition = {"binding_sha256": binding["binding_sha256"], "kind": kind,
                "status": status, "previous_status": None if prior is None else prior["status"],
                "checked_at": now.isoformat(), "price": None if native["status"] == "STALE_OR_UNAVAILABLE"
                    else str(observation["price"]), "threshold": condition["threshold"],
                "reason": reason, "source_refs": [] if native["status"] == "STALE_OR_UNAVAILABLE"
                    else deepcopy(observation["evidence_refs"]), "next_step": next_step,
                "blockers": list(blockers), "action": "no_order", "eligibility": False, "m5_admitted": False}
            transition["transition_id"] = "local-plan-" + _digest([binding["binding_sha256"], kind,
                native["cycle"], native["status"], native["session_date"]])
            transitions.append(transition)
    output = {"schema_version": RESULT_SCHEMA, "symbol": binding["symbol"],
        "binding_sha256": binding["binding_sha256"], "namespace": "ACTUAL", "scope": BOUNDARY,
        "checked_at": now.isoformat(), "states": states, "transitions": transitions,
        "blockers": blockers, "plan_status": "STALE_OR_UNAVAILABLE" if expired else "REFERENCE_ONLY",
        "action": "no_order", "eligibility": False, "m5_admitted": False}
    output["result_sha256"] = _digest(output)
    return output

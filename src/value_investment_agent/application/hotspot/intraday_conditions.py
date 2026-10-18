"""Pure observation adapter. Callers verify evidence and authorize/persist M5 runs.

    This compares an explicit price condition, not a complete trading strategy.
    It never admits B1 data, recalculates levels, or grants execution permission.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ...domain.execution.exchange_calendar import is_exchange_session
from ...domain.hotspot.current_price import SESSION_TIMES
from ...m5_event_core import (
    ChangeEventInput, EVENT_NAMESPACES, EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED,
    EVENT_TYPE_SOURCE_SCAN_FAILED, EVENT_TYPE_SOURCE_SCAN_RECOVERED,
)


SCHEMA = "intraday-condition-state-v1"
CHINA = ZoneInfo("Asia/Shanghai")
STATUSES = {"NOT_TRIGGERED", "STRUCTURE_OBSERVATION", "CONDITION_REVIEW", "STALE_OR_UNAVAILABLE"}


@dataclass(frozen=True)
class IntradayConditionResult:
    state: dict
    events: tuple[ChangeEventInput, ...]
    action: str = "no_order"
    eligibility: bool = False
    admitted: bool = False
    b1_eligible: bool = False


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
    except (ValueError, TypeError) as error:
        raise ValueError("Aware ISO timestamp required") from error
    if stamp.utcoffset() is None:
        raise ValueError("Aware ISO timestamp required")
    return stamp.astimezone(timezone.utc)


def _positive(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Positive finite price required") from error
    if not number.is_finite() or number <= 0:
        raise ValueError("Positive finite price required")
    return number


def _session(venue, stamp):
    local = stamp.astimezone(CHINA)
    clock = local.time()
    return is_exchange_session(venue, local.date()) and (
        time(9, 30) <= clock <= time(11, 30) or time(13) <= clock <= time(15))


def evaluate_intraday_condition(condition: dict, observation: dict | None, *,
        previous: dict | None, now: datetime, max_age: timedelta, namespace: str) -> IntradayConditionResult:
    """Return caller-persistable state plus unadmitted M5 input events.

    condition: strategy, symbol, venue, condition_id, rule_version, source_id,
      source_url, input_kind (QUOTE/COMPLETED_BAR), period (quote/15m/60m),
      operator (GT/LT), threshold, action=no_order.
    observation: symbol, source_id, source_url, source_at, received_at, price,
      quality=VERIFIED, suspended=False, evidence_refs; completed bars also
      require period, bar_end, completed=True. The upstream caller must verify
      retained source bytes. VERIFIED is an input assertion, not authorization.
    previous is this adapter's exact last state; persist atomically with events.
    max_age is a caller-selected data freshness policy, never a price threshold.
    """
    if (not isinstance(now, datetime) or now.utcoffset() is None
            or not isinstance(max_age, timedelta) or max_age <= timedelta(0)
            or namespace not in EVENT_NAMESPACES):
        raise ValueError("Aware clock, positive freshness policy and explicit namespace required")
    now = now.astimezone(timezone.utc)
    required = {"strategy", "symbol", "venue", "condition_id", "rule_version", "source_id",
                "source_url", "input_kind", "period", "operator", "threshold", "action"}
    if not isinstance(condition, dict) or set(condition) != required:
        raise ValueError("Exact explicit condition contract required")
    c = deepcopy(condition)
    if any(not isinstance(value, str) or not value.strip() for value in c.values()):
        raise ValueError("Condition values must be nonempty strings")
    if (c["strategy"] not in {"CORE_VALUE", "HOTSPOT_SATELLITE"} or c["action"] != "no_order"
            or len(c["symbol"]) != 6 or not c["symbol"].isascii() or not c["symbol"].isdigit()
            or c["operator"] not in {"GT", "LT"}
            or c["input_kind"] not in {"QUOTE", "COMPLETED_BAR"}
            or (c["input_kind"] == "QUOTE" and c["period"] != "quote")
            or (c["input_kind"] == "COMPLETED_BAR" and c["period"] not in SESSION_TIMES)):
        raise ValueError("Unsupported condition identity or semantics")
    expected_venue = "SSE" if c["symbol"].startswith("6") else "SZSE" if c["symbol"].startswith(("0", "3")) else None
    url = urlparse(c["source_url"])
    if (c["venue"] != expected_venue or url.scheme != "https" or not url.hostname
            or url.username or url.password or url.fragment):
        raise ValueError("Unsupported security venue or source URL")
    c["threshold"] = str(_positive(c["threshold"]).normalize())
    binding = _digest({"condition": c, "namespace": namespace, "max_age_seconds": max_age.total_seconds()})
    old = deepcopy(previous)
    if old is not None:
        if (not isinstance(old, dict) or not {"checked_at", "last_source_at", "last_received_at",
                "last_fingerprint", "last_bar_end", "last_bar_price", "session_date"} <= set(old)
                or old.get("schema_version") != SCHEMA or old.get("binding") != binding
                or old.get("status") not in STATUSES or type(old.get("cycle")) is not int
                or old["cycle"] < 0 or old.get("action") != "no_order"
                or old.get("eligibility") is not False or old.get("admitted") is not False
                or _stamp(old["checked_at"]) > now):
            raise ValueError("Prior state is foreign, malformed or from the future")
    status, reason, received, source, fingerprint, refs = "STALE_OR_UNAVAILABLE", "DATA_UNAVAILABLE", None, None, None, ()
    end, price = None, None
    try:
        if not isinstance(observation, dict):
            raise ValueError("DATA_UNAVAILABLE")
        o = deepcopy(observation)
        if (o["symbol"] != c["symbol"] or o["source_id"] != c["source_id"]
                or o["source_url"] != c["source_url"] or o["quality"] != "VERIFIED"
                or o.get("action", "no_order") != "no_order"
                or o["suspended"] is not False):
            raise ValueError("SOURCE_OR_SECURITY_UNAVAILABLE")
        source, received = _stamp(o["source_at"]), _stamp(o["received_at"])
        if not source <= received <= now or now - source > max_age or now - received > max_age:
            raise ValueError("STALE_OR_CONFLICTING_CLOCK")
        if (source.astimezone(CHINA).date() != now.astimezone(CHINA).date()
                or not _session(c["venue"], now) or not _session(c["venue"], source)
                or not _session(c["venue"], received)):
            raise ValueError("OUTSIDE_EXCHANGE_SESSION")
        price = _positive(o["price"])
        refs = tuple(deepcopy(o["evidence_refs"]))
        if not refs or any(not isinstance(ref, dict) or not ref.get("id")
                or ref.get("source_url") != c["source_url"]
                or not isinstance(ref.get("sha256"), str) or len(ref["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in ref["sha256"]) for ref in refs):
            raise ValueError("SOURCE_EVIDENCE_MISSING")
        if c["input_kind"] == "COMPLETED_BAR":
            end = _stamp(o["bar_end"])
            if (o["completed"] is not True or o["period"] != c["period"] or end > source
                    or end.astimezone(CHINA).date() != source.astimezone(CHINA).date()
                    or end.astimezone(CHINA).strftime("%H:%M:%S") not in SESSION_TIMES[c["period"]]
                    or end.microsecond or now - end > max_age):
                raise ValueError("INCOMPLETE_OR_STALE_BAR")
        fingerprint = _digest({"symbol": c["symbol"], "source_id": c["source_id"],
            "source_url": c["source_url"], "source_at": source.isoformat(),
            "price": str(price.normalize()), "period": c["period"],
            "bar_end": end.isoformat() if end else None})
        if old and old.get("last_source_at"):
            if source < _stamp(old["last_source_at"]) or received < _stamp(old["last_received_at"]):
                raise ValueError("OBSERVATION_TIME_REGRESSION")
            if source == _stamp(old["last_source_at"]) and fingerprint != old["last_fingerprint"]:
                raise ValueError("CONFLICTING_REPEATED_OBSERVATION")
            if old["status"] == "STALE_OR_UNAVAILABLE" and source <= _stamp(old["last_source_at"]):
                raise ValueError("RECOVERY_REQUIRES_NEW_OBSERVATION")
        if end and old and old.get("last_bar_end"):
            prior_end = _stamp(old["last_bar_end"])
            if end < prior_end or (end == prior_end and price != _positive(old["last_bar_price"])):
                raise ValueError("CONFLICTING_OR_REGRESSED_COMPLETED_BAR")
        matched = price > _positive(c["threshold"]) if c["operator"] == "GT" else price < _positive(c["threshold"])
        status = ("CONDITION_REVIEW" if c["input_kind"] == "COMPLETED_BAR" else "STRUCTURE_OBSERVATION") if matched else "NOT_TRIGGERED"
        reason = "EXPLICIT_PRICE_CONDITION_MATCHED" if matched else "EXPLICIT_PRICE_CONDITION_NOT_MATCHED"
    except (ValueError, KeyError, TypeError, InvalidOperation, OverflowError) as error:
        # Invalid input can create a quality transition, never a valid trigger.
        message = str(error)
        reason = message if message.isascii() and message.replace("_", "").isupper() else "INVALID_OBSERVATION"
        source, received, fingerprint, refs = None, None, None, ()
        end, price = None, None
    session_date = now.astimezone(CHINA).date().isoformat()
    changed = old is None or old["status"] != status or old.get("session_date") != session_date
    cycle = (old["cycle"] if old else 0) + int(changed)
    state = {"schema_version": SCHEMA, "binding": binding, "strategy": c["strategy"],
        "symbol": c["symbol"], "condition_id": c["condition_id"], "rule_version": c["rule_version"],
        "namespace": namespace, "session_date": session_date, "status": status, "cycle": cycle, "reason": reason,
        "checked_at": now.isoformat(), "last_source_at": source.isoformat() if source else (old or {}).get("last_source_at"),
        "last_received_at": received.isoformat() if received else (old or {}).get("last_received_at"),
        "last_fingerprint": fingerprint if fingerprint else (old or {}).get("last_fingerprint"),
        "last_bar_end": end.isoformat() if end else (old or {}).get("last_bar_end"),
        "last_bar_price": str(price.normalize()) if end else (old or {}).get("last_bar_price"),
        "action": "no_order", "eligibility": False, "admitted": False}
    events = []
    if changed and not (old is None and status == "NOT_TRIGGERED"):
        failed = status == "STALE_OR_UNAVAILABLE"
        recovered = old is not None and old["status"] == "STALE_OR_UNAVAILABLE" and not failed
        types = ([EVENT_TYPE_SOURCE_SCAN_FAILED] if failed else
                 ([EVENT_TYPE_SOURCE_SCAN_RECOVERED] if recovered else []) + [EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED])
        if failed:
            refs = ({"id": "intraday-diagnostic-" + _digest([binding, cycle, reason]),
                     "type": "adapter_quality_diagnostic", "condition_binding": binding,
                     "reason": reason},)
        for event_type in types:
            health = event_type in {EVENT_TYPE_SOURCE_SCAN_FAILED, EVENT_TYPE_SOURCE_SCAN_RECOVERED}
            event_state = {key: state[key] for key in ("binding", "strategy", "symbol", "condition_id",
                "rule_version", "namespace", "status", "cycle", "action", "eligibility", "admitted")}
            events.append(ChangeEventInput(
                source_event_id="intraday-" + _digest([binding, cycle, status, event_type]),
                source_id="intraday-condition-adapter-v1", symbol="SYSTEM" if health else c["symbol"],
                event_type=event_type, detected_at=now, available_at=now,
                effective_at=source, previous_state={} if old is None else
                    {"status": old["status"], "cycle": old["cycle"], "binding": binding},
                current_state=event_state, severity="MEDIUM" if health else "LOW", reason=reason,
                evidence_refs=refs, confidence="LOW", requires_human_review=True, namespace=namespace))
    return IntradayConditionResult(state=state, events=tuple(events))

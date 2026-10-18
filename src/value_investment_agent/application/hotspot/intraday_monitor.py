"""Local TEST_ONLY condition ticks; cursor and M5 state commit as one snapshot.

Internal callers own condition configuration and verify public observations.
Neither function is a Web input boundary. Snapshot hashes detect corruption,
not malicious replacement or rollback by a filesystem owner.
"""
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .intraday_conditions import CHINA, evaluate_intraday_condition
from ..portfolio.private_journal_lock import InterProcessLock
from ...m5_event_dependencies import (
    DependencyGraph, DependencyNode, KIND_PRICE_ATTRACTIVENESS, KIND_SOURCE_HEALTH,
)
from ...m5_event_run import run_event_batch
from ...m5_event_outbox import (
    ALERT_PENDING, ALERT_SENT, ALERT_DELIVERED, ALERT_ACKNOWLEDGED,
    ALERT_FAILED_RETRYABLE, ALERT_CANCELLED, ALERT_EXPIRED,
)
from ...m5_event_outbox_state import apply_outbox_transition
from ...m5_event_run_state import M5EventRunState, m5_event_run_state_from_payload
from ...m5_event_watermark import ScanWatermark, SOURCE_DEGRADED, WATERMARK_COVERAGE_INCOMPLETE


SCHEMA = "intraday-monitor-v1"
SCOPE = "EXPLICIT_OBSERVED_CONDITION_ONLY"
EXPIRY_POLICY = "intraday-alert-session-expiry-v1"
OPERATIONS = {"ACKNOWLEDGE": ALERT_ACKNOWLEDGED, "CANCEL": ALERT_CANCELLED, "EXPIRE": ALERT_EXPIRED}


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def _load(path):
    if not path.exists():
        return None, None
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {"schema_version", "namespace", "scope", "condition", "max_age_seconds",
              "cursor", "m5_state", "snapshot_sha256"}
    if (not isinstance(raw, dict) or set(raw) not in (fields, fields | {"alert_action_receipts"})):
        raise ValueError("Malformed intraday monitor snapshot")
    unsigned = {key: value for key, value in raw.items() if key != "snapshot_sha256"}
    if (raw["schema_version"] != SCHEMA or raw["namespace"] != "SIMULATED"
            or raw["scope"] != SCOPE or raw["snapshot_sha256"] != _digest(unsigned)
            or type(raw["max_age_seconds"]) not in {int, float}):
        raise ValueError("Corrupt or unsupported intraday monitor snapshot")
    cursor = raw["cursor"]
    checked = datetime.fromisoformat(cursor["checked_at"])
    validated = evaluate_intraday_condition(raw["condition"], None, previous=cursor,
        now=checked, max_age=timedelta(seconds=raw["max_age_seconds"]), namespace="SIMULATED")
    if set(cursor) != set(validated.state) or any(cursor[key] != validated.state[key]
            for key in ("binding", "strategy", "symbol", "condition_id", "rule_version", "namespace")):
        raise ValueError("Foreign intraday cursor")
    state = m5_event_run_state_from_payload(raw["m5_state"])
    binding = cursor["binding"]
    if state.namespace != "SIMULATED" or state.state_key != "intraday-condition-" + binding:
        raise ValueError("Foreign M5 state")
    events = state.event_ledger.events()
    for event in events:
        if event.current_state.get("binding") != binding:
            raise ValueError("Cross-condition M5 history")
    if events:
        latest = events[-1]
        if (any(latest.current_state.get(key) != cursor[key]
                for key in ("binding", "strategy", "symbol", "condition_id", "rule_version",
                            "namespace", "status", "cycle", "action", "eligibility", "admitted"))
                or latest.detected_at > checked
                or latest.detected_at.astimezone(CHINA).date().isoformat() != cursor["session_date"]):
            raise ValueError("Cursor disagrees with latest M5 condition event")
    elif cursor["status"] != "NOT_TRIGGERED" or cursor["cycle"] != 1:
        raise ValueError("Only initial untriggered cursor may have no M5 event")
    for watermark in state.watermarks.watermarks():
        if (watermark.scope != SCOPE + ":" + binding
                or watermark.source != "intraday-condition-adapter-v1"
                or watermark.coverage_status != WATERMARK_COVERAGE_INCOMPLETE):
            raise ValueError("Unexpected source coverage claim")
    receipts = raw.get("alert_action_receipts", [])
    if not isinstance(receipts, list):
        raise ValueError("Invalid alert action receipts")
    seen = set()
    for receipt in receipts:
        if (not isinstance(receipt, dict) or set(receipt) != {
                "alert_id", "operation", "expected_snapshot_sha256", "occurred_at", "outbox_revision"}
                or receipt["operation"] not in OPERATIONS or receipt["alert_id"] in seen
                or not _sha256(receipt["expected_snapshot_sha256"])
                or type(receipt["outbox_revision"]) is not int):
            raise ValueError("Invalid alert action receipt")
        seen.add(receipt["alert_id"])
        matching = [record for record in state.outbox_transitions
            if record.outbox_revision == receipt["outbox_revision"]
            and record.alert_id == receipt["alert_id"] and record.to_status == OPERATIONS[receipt["operation"]]
            and record.occurred_at.isoformat() == receipt["occurred_at"]]
        if len(matching) != 1:
            raise ValueError("Alert action receipt disagrees with M5 transition")
    return raw, state


def _sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _scoped_alert_id(path, alert_id):
    return "intraday-alert-" + _digest([os.path.normcase(str(Path(path).resolve())), alert_id])


def _expiry_deadline(state, alert):
    event = next(event for event in state.event_ledger.events() if event.event_id == alert.event_id)
    # Source-health alerts retain their review requirement; only a day's price
    # observation notification can expire under this versioned display policy.
    if event.event_type != "PRICE_ATTRACTIVENESS_CHANGED":
        return None
    day = event.detected_at.astimezone(CHINA).date()
    from ...domain.execution.exchange_calendar import is_exchange_session
    venue = "SSE" if event.symbol.startswith("6") else "SZSE"
    return datetime.combine(day, time(15), CHINA) if is_exchange_session(venue, day) else None


def _projection(raw, state, *, path):
    alerts = []
    for alert in (() if state is None else state.outbox.alerts()):
        mutable = alert.status in {ALERT_PENDING, ALERT_SENT, ALERT_DELIVERED, ALERT_FAILED_RETRYABLE}
        deadline = _expiry_deadline(state, alert)
        operations = (["ACKNOWLEDGE"] if alert.status in {ALERT_PENDING, ALERT_SENT, ALERT_DELIVERED} else [])
        if mutable:
            operations.append("CANCEL")
            if deadline is not None and datetime.now(timezone.utc) >= deadline:
                operations.append("EXPIRE")
        alerts.append({**alert.as_policy(), "alert_id": _scoped_alert_id(path, alert.alert_id),
            "user_status": alert.status, "delivery_channel": "LOCAL_TEST_ONLY",
            "expiry_at": None if deadline is None else deadline.isoformat(),
            "expiry_policy": None if deadline is None else EXPIRY_POLICY,
            "available_operations": operations})
    return {"schema_version": SCHEMA, "namespace": "SIMULATED", "test_only": True,
        "scope": SCOPE, "action": "no_order", "eligibility": False, "admitted": False,
        "snapshot_sha256": None if raw is None else raw["snapshot_sha256"],
        "condition": None if raw is None else deepcopy(raw["condition"]),
        "supported_operations": list(OPERATIONS),
        "unsupported_operations": ["RESET"],
        "status": "NOT_INITIALIZED" if raw is None else raw["cursor"]["status"],
        "cursor": None if raw is None else deepcopy(raw["cursor"]),
        "engine": {"namespace": "SIMULATED", "status": "NOT_INITIALIZED" if state is None
            else "CONDITION_ONLY_INCOMPLETE_COVERAGE", "revision": 0 if state is None else state.revision,
            "outbox_revision": 0 if state is None else state.outbox_revision,
            "whole_source_coverage": False, "acceptance_authority": "NONE", "action": "no_order"},
        "alerts": alerts,
        "alert_transitions": [] if state is None else [record.as_policy() for record in state.outbox_transitions],
        "history": [] if state is None else [event.as_policy() for event in state.event_ledger.events()]}


def read_intraday_monitor(path) -> dict:
    """Read a committed snapshot without creating files, locks or directories."""
    return _projection(*_load(Path(path)), path=path)


def _require_clock(now, raw, state):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Aware server clock required")
    if now < datetime.fromisoformat(raw["cursor"]["checked_at"]) or any(
            now < record.occurred_at for record in state.outbox_transitions):
        raise ValueError("Prior state: server clock precedes committed monitor state")


def transition_intraday_alert(path, *, alert_id: str, operation: str,
        expected_snapshot_sha256: str, now: datetime) -> dict:
    """Record an actual local-page acknowledgement using the server's clock.

    The authenticated caller must invoke ACKNOWLEDGE only after the user has
    actually seen the alert. SENT/DELIVERED then record that local presentation,
    never external transport. CANCEL stops this notification; EXPIRE uses the
    explicit session-end notification policy. Neither resolves a risk review,
    changes the original condition, nor grants investment permission.
    """
    if operation not in OPERATIONS:
        raise ValueError("Unsupported operation")
    if not isinstance(alert_id, str) or not _sha256(expected_snapshot_sha256):
        raise ValueError("Scoped alert id and snapshot SHA-256 required")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Aware server clock required")
    path = Path(path)
    if not path.exists():
        raise ValueError("Monitor does not exist")
    with InterProcessLock(path.with_name(path.name + ".lock")):
        raw, state = _load(path)
        if raw is None:
            raise ValueError("Monitor does not exist")
        _require_clock(now, raw, state)
        alert = next((item for item in state.outbox.alerts()
            if _scoped_alert_id(path, item.alert_id) == alert_id), None)
        if alert is None:
            raise ValueError("Alert does not belong to this monitor file")
        receipts = raw.get("alert_action_receipts", [])
        if any(receipt["alert_id"] == alert.alert_id and receipt["operation"] == operation
                and receipt["expected_snapshot_sha256"] == expected_snapshot_sha256 for receipt in receipts):
            return _projection(raw, state, path=path)
        if raw["snapshot_sha256"] != expected_snapshot_sha256:
            raise ValueError("Stale monitor snapshot")
        if alert.status == OPERATIONS[operation]:
            return _projection(raw, state, path=path)
        mutable = {ALERT_PENDING, ALERT_SENT, ALERT_DELIVERED}
        if operation != "ACKNOWLEDGE":
            mutable.add(ALERT_FAILED_RETRYABLE)
        if alert.status not in mutable:
            raise ValueError("Alert status does not permit this operation")
        status = alert.status
        targets = ([ALERT_SENT, ALERT_DELIVERED, ALERT_ACKNOWLEDGED] if status == ALERT_PENDING else
            [ALERT_DELIVERED, ALERT_ACKNOWLEDGED] if status == ALERT_SENT else [ALERT_ACKNOWLEDGED]) if operation == "ACKNOWLEDGE" else [OPERATIONS[operation]]
        extra = {}
        if operation != "ACKNOWLEDGE":
            deadline = _expiry_deadline(state, alert) if operation == "EXPIRE" else None
            if operation == "EXPIRE" and (deadline is None or now < deadline):
                raise ValueError("Price observation notification has not expired")
            extra = dict(reason="USER_CANCELLED_LOCAL_REMINDER" if operation == "CANCEL" else EXPIRY_POLICY,
                expires_at=deadline, evidence_refs=("snapshot:" + expected_snapshot_sha256,
                    "condition:" + raw["cursor"]["binding"],
                    "policy:" + (EXPIRY_POLICY if operation == "EXPIRE" else "user-local-cancel-v1")))
        for target in targets:
            state = apply_outbox_transition(state=state, alert_id=alert.alert_id,
                from_status=status, to_status=target, occurred_at=now, **extra)
            status = target
        payload = deepcopy(raw)
        payload["m5_state"] = json.loads(state.to_json())
        m5_event_run_state_from_payload(payload["m5_state"])
        payload["alert_action_receipts"] = [*receipts, {"alert_id": alert.alert_id,
            "operation": operation, "expected_snapshot_sha256": expected_snapshot_sha256,
            "occurred_at": now.isoformat(), "outbox_revision": state.outbox_revision}]
        payload.pop("snapshot_sha256")
        payload["snapshot_sha256"] = _digest(payload)
        _atomic_write(path, payload)
        return _projection(payload, state, path=path)


def _atomic_write(path, payload):
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def tick_intraday_monitor(path, *, condition: dict, observation: dict | None,
        now: datetime, max_age: timedelta, namespace: str = "SIMULATED") -> dict:
    """One manual public-data tick, using server-owned inputs and persisted cursor.

    ACTUAL is deliberately unsupported in this initial TEST_ONLY orchestrator;
    this function cannot mint or accept substitute authorization assertions.
    """
    if namespace != "SIMULATED":
        raise ValueError("TEST_ONLY monitor requires SIMULATED; ACTUAL authorization is not supported")
    # Validate configuration and clock before any filesystem mutation.
    initial = evaluate_intraday_condition(condition, observation, previous=None,
        now=now, max_age=max_age, namespace=namespace)
    condition = deepcopy(condition)
    path = Path(path)
    with InterProcessLock(path.with_name(path.name + ".lock")):
        old, state = _load(path)
        if old is not None:
            _require_clock(now, old, state)
        if old is not None and old["cursor"]["binding"] != initial.state["binding"]:
            raise ValueError("Monitor is bound to a different condition or freshness policy")
        result = evaluate_intraday_condition(condition, observation,
            previous=None if old is None else old["cursor"], now=now, max_age=max_age, namespace=namespace)
        binding = result.state["binding"]
        run_id = "intraday-condition-" + binding
        state = state or M5EventRunState.empty(state_key=run_id, namespace=namespace)
        if result.events:
            batch_id = "intraday-tick-" + _digest(result.state)
            refs = ({"id": binding, "scope": SCOPE},)
            graph = DependencyGraph(tuple(DependencyNode(node_id=binding + ":" + kind,
                kind=kind, symbol=condition["symbol"] if kind == KIND_PRICE_ATTRACTIVENESS else "SYSTEM",
                inputs=(), version=SCHEMA, evidence_refs=refs)
                for kind in (KIND_PRICE_ATTRACTIVENESS, KIND_SOURCE_HEALTH)))
            watermark = ScanWatermark(watermark_id=batch_id, scope=SCOPE + ":" + binding,
                source="intraday-condition-adapter-v1", coverage_through=now, retrieved_at=now,
                parser_version=SCHEMA, coverage_status=WATERMARK_COVERAGE_INCOMPLETE,
                source_health=SOURCE_DEGRADED, evidence_refs=refs)
            receipt = run_event_batch(events=result.events, observed_times=(now,) * len(result.events),
                watermark=watermark, graph=graph, run_id=run_id, generated_at=now,
                namespace=namespace, state=state, batch_id=batch_id, expected_revision=state.revision)
            if any(item.event is None for item in receipt.ingest_results):
                raise ValueError("M5 rejected condition events; cursor not committed")
            state = receipt.state
        # Round-trip through the existing aggregate validator before committing.
        m5_payload = json.loads(state.to_json())
        m5_event_run_state_from_payload(m5_payload)
        payload = {"schema_version": SCHEMA, "namespace": namespace, "scope": SCOPE,
            "condition": condition, "max_age_seconds": max_age.total_seconds(),
            "cursor": result.state, "m5_state": m5_payload}
        if old is not None and "alert_action_receipts" in old:
            payload["alert_action_receipts"] = deepcopy(old["alert_action_receipts"])
        payload["snapshot_sha256"] = _digest(payload)
        if old != payload:
            _atomic_write(path, payload)
        return _projection(payload, state, path=path)

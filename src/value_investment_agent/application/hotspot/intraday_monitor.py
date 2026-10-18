"""Local TEST_ONLY condition ticks; cursor and M5 state commit as one snapshot.

Internal callers own condition configuration and verify public observations.
Neither function is a Web input boundary. Snapshot hashes detect corruption,
not malicious replacement or rollback by a filesystem owner.
"""
from copy import deepcopy
from datetime import datetime, timedelta
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
from ...m5_event_run_state import M5EventRunState, m5_event_run_state_from_payload
from ...m5_event_watermark import ScanWatermark, SOURCE_DEGRADED, WATERMARK_COVERAGE_INCOMPLETE


SCHEMA = "intraday-monitor-v1"
SCOPE = "EXPLICIT_OBSERVED_CONDITION_ONLY"


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def _load(path):
    if not path.exists():
        return None, None
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {"schema_version", "namespace", "scope", "condition", "max_age_seconds",
              "cursor", "m5_state", "snapshot_sha256"}
    if not isinstance(raw, dict) or set(raw) != fields:
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
    return raw, state


def _projection(raw, state):
    return {"schema_version": SCHEMA, "namespace": "SIMULATED", "test_only": True,
        "scope": SCOPE, "action": "no_order", "eligibility": False, "admitted": False,
        "status": "NOT_INITIALIZED" if raw is None else raw["cursor"]["status"],
        "cursor": None if raw is None else deepcopy(raw["cursor"]),
        "engine": {"namespace": "SIMULATED", "status": "NOT_INITIALIZED" if state is None
            else "CONDITION_ONLY_INCOMPLETE_COVERAGE", "revision": 0 if state is None else state.revision,
            "whole_source_coverage": False, "acceptance_authority": "NONE", "action": "no_order"},
        "alerts": [] if state is None else [alert.as_policy() for alert in state.outbox.alerts()],
        "history": [] if state is None else [event.as_policy() for event in state.event_ledger.events()]}


def read_intraday_monitor(path) -> dict:
    """Read a committed snapshot without creating files, locks or directories."""
    return _projection(*_load(Path(path)))


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
        payload["snapshot_sha256"] = _digest(payload)
        if old != payload:
            _atomic_write(path, payload)
        return _projection(payload, state)

"""Observation inbox projection over replay-verified collection reports.

This adds local reading state to the existing public observation store. It
does not ingest ACTUAL M5 events or change an investment plan's eligibility.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json


OPERATIONS = {"ACKNOWLEDGE": "ACKNOWLEDGED", "CANCEL": "CANCELLED", "EXPIRE": "EXPIRED"}


def _id(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _completed_transition(report, result):
    observations = {}
    refs = []
    for period, item in result["periods"].items():
        observation = (item.get("source_result") or {}).get("observation") or {}
        observations[period] = {
            "status": item["status"],
            "reason": item["reason"],
            "bar_end": observation.get("bar_end"),
            "completed": observation.get("completed") is True,
            "price": observation.get("close"),
        }
        refs.extend(deepcopy(observation.get("evidence_refs", [])))
    dated = [(row["bar_end"], row) for row in observations.values() if row["bar_end"]]
    effective_at, latest = max(dated, key=lambda pair: pair[0]) if dated else (None, None)
    plan = report["plan_binding"]["plan"]
    status = result["status"]
    threshold = (str(plan["invalidation_price"]) if status == "RISK_REVIEW"
                 else str(plan["entry_trigger_price"]))
    return dict(kind="COMPLETED_STRUCTURE", status=status, checked_at=result["checked_at"],
        reason="; ".join(f"{period}:{item['reason']}" for period, item in observations.items()),
        threshold=threshold, price=None if latest is None else latest["price"],
        source_refs=refs, input_kind="COMPLETED_BAR",
        completed_bar=bool(observations) and all(row["completed"] for row in observations.values()),
        period="60m+15m", bar_end=effective_at,
        completed_periods=observations,
        transition_id="completed-" + _id([report["plan_binding"]["plan_sha256"],
            result["result_sha256"], result["checked_at"]]))


def project_notification_inbox(reports, *, now, snapshot_sha256):
    events, actions, changes, streams = {}, [], [], {}
    for report in reports:
        binding = report.get("plan_binding")
        for sample in report["samples"]:
            result = sample.get("condition_result") or {}
            for row in result.get("states", []):
                native = row["state"]
                transition = next((item for item in result["transitions"] if item["kind"] == row["kind"]), None)
                if transition is None:
                    transition = dict(kind=row["kind"], status=row["status"], checked_at=result["checked_at"],
                        reason=row["reason"], threshold=row["condition"]["threshold"],
                        price=None if row["status"] == "STALE_OR_UNAVAILABLE" else (sample.get("observation") or {}).get("price"),
                        source_refs=deepcopy((sample.get("observation") or {}).get("evidence_refs", [])),
                        transition_id="local-cursor-" + _id([binding["plan_sha256"], row["kind"], result["checked_at"]]))
                transition = {**transition, "input_kind": "QUOTE", "completed_bar": False,
                    "period": "QUOTE", "bar_end": None, "completed_periods": None}
                changes.append((binding, report, transition, native))
            completed = sample.get("completed_plan_result")
            if completed is not None:
                if (not isinstance(completed, dict) or completed.get("action") != "no_order"
                        or completed.get("formal_eligibility") is not False
                        or completed.get("m5_admitted") is not False
                        or completed.get("binding_sha256") != binding["binding_sha256"]):
                    raise ValueError("Invalid completed-bar observation result")
                native = {"session_date": datetime.fromisoformat(completed["checked_at"]).date().isoformat(),
                          "last_source_at": None}
                changes.append((binding, report, _completed_transition(report, completed), native))
        receipts = report.get("notification_actions", [])
        if not isinstance(receipts, list):
            raise ValueError("Invalid observation notification actions")
        actions.extend(receipts)
    for binding, report, transition, native in sorted(changes, key=lambda row: row[2]["checked_at"]):
        key = (binding["plan_sha256"], transition["input_kind"], transition["kind"], native["session_date"])
        old_status, cycle = streams.get(key, (None, 0))
        if old_status is None and transition["status"] == "NOT_TRIGGERED":
            streams[key] = (transition["status"], 0)
            continue
        if transition["status"] != old_status:
            cycle += 1
        streams[key] = (transition["status"], cycle)
        if cycle == 0 and transition["status"] == "NOT_TRIGGERED":
            continue
        level = {"STRUCTURE_OBSERVATION": "BAR_CONFIRMATION_PENDING",
                 "RISK_REVIEW": "STRUCTURE_INVALIDATED",
                 "STALE_OR_UNAVAILABLE": "DATA_STALE",
                 "NOT_TRIGGERED": "PRICE_CONDITION_CLEARED",
                 "INSUFFICIENT_DATA": "DATA_STALE",
                 "WAITING_CONFIRMATION": "BAR_CONFIRMATION_PENDING",
                 "STRUCTURE_CONFIRMED_OBSERVATION": "STRUCTURE_CONFIRMED_OBSERVATION"}[transition["status"]]
        identity = "observation-" + _id([binding["plan_sha256"], transition["kind"],
            native["session_date"], cycle, transition["status"]])
        event = dict(event_id=identity, source_event_id=transition["transition_id"],
            symbol=report["symbol"], event_type=level, detected_at=transition["checked_at"],
            last_seen_at=transition["checked_at"], reason=transition["reason"],
            effective_at=native.get("last_source_at"),
            evidence_refs=deepcopy(transition["source_refs"]),
            price=transition["price"], threshold=transition["threshold"],
            plan_sha256=binding["plan_sha256"], condition_kind=transition["kind"],
            expiry_at=binding["valid_until"], completed_bar=transition["completed_bar"],
            input_kind=transition["input_kind"], period=transition["period"], bar_end=transition["bar_end"],
            completed_periods=deepcopy(transition.get("completed_periods")),
            scope="PUBLIC_SOURCE_OBSERVATION_ONLY", action="no_order", eligibility=False)
        if identity in events:
            event["detected_at"] = min(events[identity]["detected_at"], event["detected_at"])
        events[identity] = event
    states = {identity: "PENDING" for identity in events}
    seen = set()
    for receipt in sorted(actions, key=lambda row: row["occurred_at"]):
        if (set(receipt) != {"alert_id", "operation", "occurred_at", "expected_snapshot_sha256"}
                or receipt["operation"] not in OPERATIONS or receipt["alert_id"] not in events
                or not isinstance(receipt["expected_snapshot_sha256"], str)
                or len(receipt["expected_snapshot_sha256"]) != 64):
            raise ValueError("Unbound observation notification action")
        identity = receipt["alert_id"]
        moment = datetime.fromisoformat(receipt["occurred_at"])
        event = events[identity]
        if moment.utcoffset() is None or not datetime.fromisoformat(event["detected_at"]) <= moment <= now:
            raise ValueError("Observation action clock mismatch")
        key = (identity, receipt["operation"], receipt["expected_snapshot_sha256"])
        if key in seen:
            raise ValueError("Duplicate observation action receipt")
        seen.add(key)
        if states[identity] != "PENDING":
            raise ValueError("Observation notification already terminal")
        if receipt["operation"] == "EXPIRE" and moment < datetime.fromisoformat(event["expiry_at"]):
            raise ValueError("Observation notification has not expired")
        states[identity] = OPERATIONS[receipt["operation"]]
    history = sorted(events.values(), key=lambda row: (row["detected_at"], row["event_id"]), reverse=True)
    alerts = []
    for event in history:
        identity = event["event_id"]
        state = states[identity]
        operations = ["ACKNOWLEDGE", "CANCEL"] if state == "PENDING" else []
        if state == "PENDING" and now >= datetime.fromisoformat(event["expiry_at"]):
            operations.append("EXPIRE")
        alerts.append(dict(alert_id=identity, event_id=identity, status=state,
            expiry_at=event["expiry_at"], available_operations=operations,
            action="no_order", eligibility=False, delivery_channel="LOCAL_OBSERVATION"))
    return dict(schema_version="public-condition-observation-inbox-v1", action="no_order",
        snapshot_sha256=snapshot_sha256, alerts=alerts, history=history,
        formal_eligibility=False, m5_admitted=False)

"""Capture public judgment at recording time, never reconstruct trade-time knowledge."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from ..product.public_snapshot import load_current_packet

RISK_SCOPE = "RECORDING_TIME_RISK_NOT_PROVEN_PRETRADE"


def recording_risk_request(fill, option):
    """Only assumptions are selectable; identity always comes from the fill."""
    if (not isinstance(option, dict) or set(option) != {"assumptions"}
            or not isinstance(option["assumptions"], dict)):
        raise ValueError("RISK_CAPTURE_ASSUMPTIONS_REQUIRED")
    if fill.get("side") != "BUY":
        raise ValueError("BUY_ADD_RISK_NOT_APPLICABLE_TO_SELL")
    payload = dict(symbol=fill["symbol"], assumptions=deepcopy(option["assumptions"]))
    if fill["sleeve"] == "CORE_VALUE":
        payload["sleeve"] = "CORE_VALUE"
    elif fill["sleeve"] != "HOTSPOT_SATELLITE":
        raise ValueError("RISK_CAPTURE_STRATEGY_MISMATCH")
    return payload


def attach_recording_time_risk(root, snapshot, *, fill, records, capture, now):
    """Bind a trusted server calculation; failure never certifies a risk result."""
    outcome = dict(status="UNAVAILABLE", scope=RISK_SCOPE, action="no_order",
        trade_time_availability_proven=False, formal_eligibility=False)
    try:
        if snapshot is None:
            raise ValueError("MATCHING_PUBLIC_JUDGMENT_UNAVAILABLE")
        if capture.get("error"):
            raise ValueError(capture["error"])
        if (not records or capture["journal_revision"] != len(records)
                or capture["journal_tip_sha256"] != records[-1]["record_sha256"]):
            raise ValueError("RISK_CAPTURE_JOURNAL_CHANGED")
        result = capture["result"]
        facts = result.get("facts") or {}
        engine = result.get("engine") or {}
        sizing = result.get("sizing_preview") or {}
        decision = result.get("actionable_decision") or {}
        binding = sizing.get("plan_binding") or {}
        plan = binding.get("plan") or {}
        if (result.get("action") != "no_order" or engine.get("namespace") != "ACTUAL"
                or facts.get("account_scope") != records[0]["body"]["account_scope"]
                or facts.get("revision") != len(records)
                or sizing.get("symbol") != fill["symbol"]
                or decision.get("symbol") != fill["symbol"]
                or decision.get("strategy") != fill["sleeve"]
                or plan.get("symbol") != fill["symbol"]
                or plan.get("research_version") != fill["research_version"]
                or binding.get("publication_id") != snapshot["publication_id"]
                or decision.get("action") != "no_order"
                or decision.get("trade_eligible") is not False
                or decision.get("broker_execution_permission") is not False):
            raise ValueError("RISK_CAPTURE_IDENTITY_OR_NAMESPACE_MISMATCH")
        generated = datetime.fromisoformat(decision["generated_at"])
        if (generated.utcoffset() is None or not capture["started_at"] <= generated
                <= capture["completed_at"] <= now):
            raise ValueError("RISK_CAPTURE_TIME_MISMATCH")
        # Reuse the current source/signature verifiers, not saved eligibility flags.
        from .private_risk_preview import _current_plan, _current_value_plan
        if fill["sleeve"] == "CORE_VALUE":
            current, error = _current_value_plan(root, fill["symbol"], now)
        else:
            current, error = _current_plan(root, fill["symbol"], now,
                plan.get("risk_review_action", "OPEN"))
        if error or current != binding:
            raise ValueError("RISK_CAPTURE_CURRENT_SOURCE_CHANGED")
        from .decision_logic import project_decision_logic
        logic = project_decision_logic(plan, outcome=decision.get("decision_action"),
            blockers=decision.get("blockers") or [])
        if decision.get('logic_card') is not None:
            # This is the trusted server risk result, never the fill request.
            # Preserve its verified owned-entry context rather than rebuilding
            # a context-free card at recording time.
            logic = deepcopy(decision['logic_card'])
            digest = hashlib.sha256(json.dumps(
                {key: value for key, value in logic.items() if key != 'content_sha256'},
                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
            if (logic.get('content_sha256') != digest or logic.get('symbol') != fill['symbol']
                    or logic.get('decision_action') != decision.get('decision_action')
                    or logic.get('action') != 'no_order' or logic.get('broker_execution_permission') is not False
                    or (logic.get('source_bindings') and logic['source_bindings'] != plan.get('source_bindings'))):
                raise ValueError('RISK_CAPTURE_LOGIC_CARD_CHANGED')
        outcome.update(status="SERVER_VERIFIED_RECORDING_TIME_RISK", generated_at=generated.isoformat(),
            verified_at=now.isoformat(), account_scope=facts["account_scope"],
            journal_revision=len(records), journal_tip_sha256=records[-1]["record_sha256"],
            symbol=fill["symbol"], strategy=fill["sleeve"], research_version=fill["research_version"],
            publication_id=binding["publication_id"], risk_status=result.get("status"),
            blockers=deepcopy(list(dict.fromkeys([*result.get("blockers", []),
                *sizing.get("blockers", []), *decision.get("blockers", [])]))),
            decision_action=decision.get("decision_action"),
            logic_card=logic,
            review_quantity=decision.get("review_quantity"),
            risk_sizing=deepcopy(sizing.get("sizing_details")),
            assumptions=deepcopy(sizing.get("effective_sizing_inputs")),
            plan_binding=deepcopy(binding), trade_eligible=False, broker_execution_permission=False)
    except Exception as error:
        # This optional attachment must not turn a verifier/provider outage into
        # refusal to record an otherwise lawful fill. No exception text is saved.
        known = {"MATCHING_PUBLIC_JUDGMENT_UNAVAILABLE", "RISK_CAPTURE_JOURNAL_CHANGED",
            "RISK_CAPTURE_IDENTITY_OR_NAMESPACE_MISMATCH", "RISK_CAPTURE_TIME_MISMATCH",
            "RISK_CAPTURE_CURRENT_SOURCE_CHANGED", "RISK_CAPTURE_LOGIC_CARD_CHANGED"}
        outcome["reason"] = (capture.get("error") or
            (str(error) if isinstance(error, ValueError) and str(error) in known
             else "RISK_CAPTURE_BINDING_UNVERIFIED"))
    if snapshot is not None:
        snapshot = deepcopy(snapshot)
        snapshot["recorded_at"] = now.isoformat()
        snapshot["personal_risk_capture"] = deepcopy(outcome)
        if outcome["status"] == "SERVER_VERIFIED_RECORDING_TIME_RISK":
            snapshot["personal_risk_at_trade"] = deepcopy(outcome)
        snapshot["snapshot_sha256"] = hashlib.sha256(json.dumps(
            {key: value for key, value in snapshot.items() if key != "snapshot_sha256"},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return snapshot, outcome


def capture_judgment_snapshot(root, fill):
    packet, error = load_current_packet(root)
    identifier = fill.get("decision_id")
    if packet is None or not identifier:
        return None
    symbol = fill["symbol"]
    if identifier == "hotspot-" + symbol and fill.get("sleeve") == "HOTSPOT_SATELLITE":
        plan = next((row["price_action_plan"] for row in packet.get("price_conditions", {}).get("items", [])
                     if row["symbol"] == symbol), None)
    elif identifier == symbol and fill.get("sleeve") == "CORE_VALUE":
        plan = packet.get("value_price_conditions", {}).get(symbol)
    else:
        plan = None
    if plan is None or not plan.get("research_version") or fill.get("research_version") != plan["research_version"]:
        return None
    payload = dict(schema_version="private-recording-time-judgment-snapshot-v1", action="no_order",
        decision_id=identifier, publication_id=packet["publication_id"],
        public_packet_content_sha256=packet["content_sha256"],
        research_version=plan["research_version"], recorded_at=datetime.now(timezone.utc).isoformat(),
        scope="IMMUTABLE_PUBLICATION_AT_RECORDING_TIME_NOT_PROVEN_PRETRADE_KNOWLEDGE",
        trade_time_availability_proven=False, current_source_reverified=False,
        plan=deepcopy(plan), personal_risk_at_trade=None)
    payload["snapshot_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload

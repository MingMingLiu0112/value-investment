"""Capture public judgment at recording time, never reconstruct trade-time knowledge."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from ..product.public_snapshot import load_current_packet


def capture_judgment_snapshot(root, fill):
    packet, error = load_current_packet(root)
    identifier = fill.get("decision_id")
    if packet is None or not identifier:
        return None
    symbol = fill["symbol"]
    if identifier == "hotspot-" + symbol:
        plan = next((row["price_action_plan"] for row in packet.get("price_conditions", {}).get("items", [])
                     if row["symbol"] == symbol), None)
    elif identifier == symbol:
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

"""Versioned hotspot review gates, independent of value valuation and G3."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

RULE_VERSION = "independent-hotspot-admission-v1"
GATES = (
    "security_identity", "security_risk", "event_risk", "data_quality",
    "completed_bars", "trend", "price_structure", "risk_reward",
    "strategy_validation", "execution_constraints",
)


@dataclass(frozen=True)
class HotspotGateEvidence:
    gate: str
    status: str
    available_at: datetime
    expires_at: datetime
    evidence_sha256: str

    def __post_init__(self):
        if self.gate not in GATES or self.status not in {"PASS", "FAIL", "UNKNOWN"}:
            raise ValueError("Unknown independent hotspot gate or status")
        if (not isinstance(self.available_at, datetime) or self.available_at.utcoffset() is None
                or not isinstance(self.expires_at, datetime) or self.expires_at.utcoffset() is None
                or self.expires_at <= self.available_at):
            raise ValueError("Gate evidence requires an explicit availability interval")
        if not isinstance(self.evidence_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_sha256):
            raise ValueError("Gate evidence requires exact SHA256")


def evaluate_independent_hotspot(*, symbol: str, strategy_rule_version: str,
        evidence: tuple[HotspotGateEvidence, ...], now: datetime,
        authorization_status: str, namespace: str = "ACTUAL") -> dict:
    """Evaluate verified application inputs; this pure result is not an authority.

    The application must verify signed release provenance and current evidence
    before using this projection. No value valuation or value approval is an
    input. Portfolio limits and personal execution permission remain external.
    """
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("Independent hotspot requires security identity")
    if not isinstance(strategy_rule_version, str) or not strategy_rule_version.strip():
        raise ValueError("Independent hotspot requires a strategy rule version")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Independent hotspot requires a timezone-aware clock")
    if namespace not in {"ACTUAL", "TEST_ONLY"}:
        raise ValueError("Unknown independent hotspot namespace")
    if authorization_status not in {"VERIFIED", "MISSING", "REJECTED", "EXPIRED"}:
        raise ValueError("Unknown independent strategy authorization status")
    if not isinstance(evidence, tuple) or any(not isinstance(row, HotspotGateEvidence) for row in evidence):
        raise ValueError("Independent hotspot requires typed gate evidence")
    indexed = {row.gate: row for row in evidence}
    if len(indexed) != len(evidence):
        raise ValueError("Duplicate independent hotspot evidence")
    blockers = []
    for name in GATES:
        row = indexed.get(name)
        if row is None:
            blockers.append(name + ":MISSING")
        elif row.available_at > now:
            blockers.append(name + ":NOT_YET_AVAILABLE")
        elif now >= row.expires_at:
            blockers.append(name + ":EXPIRED")
        elif row.status != "PASS":
            blockers.append(name + ":" + row.status)
    if authorization_status != "VERIFIED":
        blockers.append("independent_strategy_authorization:" + authorization_status)
    return {
        "schema_version": RULE_VERSION,
        "strategy": "HOTSPOT_SATELLITE", "symbol": symbol,
        "rule_version": strategy_rule_version, "admission_rule_version": RULE_VERSION,
        "namespace": namespace, "as_of": now.isoformat(),
        "data_available_at": max((row.available_at for row in evidence), default=now).isoformat(),
        "status": "RISK_REVIEW_ELIGIBLE" if not blockers else "OBSERVATION_ONLY",
        "risk_review_eligible": not blockers,
        "formal_eligibility": False, "personal_risk_status": "NOT_EVALUATED",
        "trade_eligible": False, "position_guidance": None,
        "blockers": blockers, "review_status": authorization_status,
        "evidence_refs": list(dict.fromkeys(row.evidence_sha256 for row in evidence)),
        "action": "no_order",
    }

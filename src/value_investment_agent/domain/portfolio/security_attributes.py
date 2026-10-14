"""Field-level official observations, separate from economic risk certification."""
from dataclasses import dataclass
from datetime import datetime
import re

SCHEMA = "field-verified-security-risk-attributes-v1"
UNKNOWN = "UNKNOWN"


def moment(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("Attribute timestamp must include timezone")
    return result


@dataclass(frozen=True)
class ObservedSecurityAttributes:
    symbol: str
    industry: str
    cyclical: None
    liquidity_profile: str
    common_factors: tuple
    evidence_refs: tuple
    gaps: tuple


def parse_observed_attributes(payload, *, now):
    if payload.get("schema_version") != SCHEMA or payload.get("action") != "no_order":
        raise ValueError("Unknown field-level attribute contract")
    if not re.fullmatch(r"[0-9]{6}", payload["symbol"]):
        raise ValueError("Invalid security identity")
    available, expiry = moment(payload["known_at"]), moment(payload["valid_until"])
    if available > now or expiry < now or expiry < available:
        raise ValueError("Security attributes unavailable or expired")
    if payload["classification_effective_date"] is not None or payload["historical_pit"] is not False:
        raise ValueError("Current exchange list cannot certify historical industry membership")
    if any(payload[key] != UNKNOWN for key in ("cyclical", "common_factors", "liquidity_profile")):
        raise ValueError("Exchange list does not certify economic factors or liquidity")
    if payload["security_type"] not in ("A_SHARE", "DEPOSITARY_RECEIPT"):
        raise ValueError("Unsupported security type")
    if payload["exchange"] not in ("SZSE", "SSE") or not payload["company_name"].strip():
        raise ValueError("Incomplete official identity")
    refs = payload["evidence_refs"]
    if not refs or any(not r.get("id") or not r.get("path") or not re.fullmatch(r"[0-9a-f]{64}", r.get("sha256", "")) for r in refs):
        raise ValueError("Missing original field evidence")
    industry = payload["industry"]
    if industry != UNKNOWN and not re.fullmatch(r"CSRC_SECTION:[A-S]", industry):
        raise ValueError("Unknown concentration taxonomy")
    gaps = ["cyclical", "common_factors", "liquidity_profile"]
    if industry == UNKNOWN:
        gaps.append("industry")
    return ObservedSecurityAttributes(payload["symbol"], industry, None, UNKNOWN, (), tuple(refs), tuple(gaps))


def official_observation(row, *, industry_code, known_at, valid_until, evidence_refs):
    if row["security_type"] not in ("A\u80a1", "\u5883\u5185\u5b58\u6258\u51ed\u8bc1"):
        raise ValueError("Official security type is unsupported")
    payload = {"schema_version": SCHEMA, "action": "no_order", "symbol": row["symbol"],
        "company_name": row["name"], "exchange": row["exchange"], "board": row["board"],
        "security_type": "A_SHARE" if row["security_type"] == "A\u80a1" else "DEPOSITARY_RECEIPT",
        "listed_on": row["listed_on"], "industry": "CSRC_SECTION:" + industry_code if industry_code else UNKNOWN,
        "industry_description": row.get("official_industry"), "classification_standard": "EXCHANGE_REPORTED_CSRC_SECTION",
        "classification_effective_date": None, "historical_pit": False,
        "classification_scope": "CURRENT_OBSERVATION_KNOWN_AFTER_CAPTURE_ONLY",
        "cyclical": UNKNOWN, "common_factors": UNKNOWN, "liquidity_profile": UNKNOWN,
        "published_at": None, "known_at": known_at.isoformat(), "valid_until": valid_until.isoformat(),
        "validity_basis": "SOURCE_CAPTURE_PLUS_7_CALENDAR_DAYS_REQUIRES_REFRESH",
        "field_evidence": {key: list(evidence_refs) for key in ("symbol", "company_name", "exchange", "security_type", "industry")},
        "field_status": {"symbol": "VERIFIED_OFFICIAL_OBSERVATION", "company_name": "VERIFIED_OFFICIAL_OBSERVATION",
            "exchange": "VERIFIED_OFFICIAL_OBSERVATION", "security_type": "VERIFIED_OFFICIAL_OBSERVATION",
            "industry": "VERIFIED_OFFICIAL_OBSERVATION" if industry_code else UNKNOWN,
            "cyclical": UNKNOWN, "common_factors": UNKNOWN, "liquidity_profile": UNKNOWN,
            "classification_effective_date": UNKNOWN, "published_at": UNKNOWN},
        "evidence_refs": list(evidence_refs)}
    parse_observed_attributes(payload, now=known_at)
    return payload

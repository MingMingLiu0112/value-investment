"""Typed M1 fixed-sample preregistration contract.

This is the W1 research-design ledger, not the frozen C3 admission manifest and
not an execution or production-data instruction. It registers the 20-company
sample, why each company is present, and which known gaps must stay visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .research_profile import PROFILES
from .valuation_router import VALUATION_MODEL_REGISTRY


M1_SAMPLE_PREREGISTRATION_SCHEMA = "m1-fixed-sample-preregistration-v1"
DEFAULT_PREREGISTRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "m1-fixed-sample-preregistration-v1.json"
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_BUCKETS = {
    "ORIGINAL_CASE",
    "PROFILE_REPLICATION",
    "PROFILE_DIVERSIFICATION",
    "UNSUPPORTED_MODEL",
    "DATA_INSUFFICIENT",
    "RISK_COUNTEREXAMPLE",
}
_FORBIDDEN_KEYS = {
    "action",
    "trade_approved",
    "target_weight",
    "position_size",
    "order_quantity",
    "proposed_entry",
    "buy",
    "sell",
    "live_eligible",
}
_REQUIRED_METHODOLOGY_KEYS = {
    "data_sources",
    "field_requirements",
    "research_depth",
    "budget",
    "stop_rules",
    "acceptance_criteria",
}


@dataclass(frozen=True)
class M1SamplePreregistrationEntry:
    """One preregistered company with an explicit research bucket and blockers."""

    symbol: str
    name: str
    exchange: str
    industry: str
    profile_id: str
    primary_model: str | None
    selection_bucket: str
    initial_research_depth: str
    selection_reason: str
    evidence_basis: str
    known_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Preregistration symbol must contain six digits")
        for field in ("name", "exchange", "industry", "selection_reason", "evidence_basis"):
            if not getattr(self, field).strip():
                raise ValueError(f"Preregistration {field} is required")
        if self.exchange not in {"SSE", "SZSE"}:
            raise ValueError("Preregistration exchange must be SSE or SZSE")
        if self.selection_bucket not in _BUCKETS:
            raise ValueError(f"Unknown preregistration bucket: {self.selection_bucket}")
        if self.initial_research_depth not in {
            "FROZEN_PLATFORM_CASE",
            "DEEP_CANDIDATE",
            "GAP_TRIAGE",
        }:
            raise ValueError(
                f"Unknown preregistration depth: {self.initial_research_depth}"
            )
        if self.profile_id == "unsupported_profile":
            if self.primary_model is not None:
                raise ValueError("Unsupported profiles cannot register a primary model")
        else:
            profile = PROFILES.get(self.profile_id)
            if profile is None:
                raise ValueError(f"Unknown preregistration profile: {self.profile_id}")
            if self.primary_model != profile.primary_valuation_model:
                raise ValueError(
                    "Preregistration primary model must match the profile"
                )
            if VALUATION_MODEL_REGISTRY.get(self.primary_model) is None:
                raise ValueError(
                    f"Unregistered preregistration model: {self.primary_model}"
                )
        object.__setattr__(self, "known_blockers", tuple(self.known_blockers))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "exchange": self.exchange,
            "industry": self.industry,
            "profile_id": self.profile_id,
            "primary_model": self.primary_model,
            "selection_bucket": self.selection_bucket,
            "initial_research_depth": self.initial_research_depth,
            "selection_reason": self.selection_reason,
            "evidence_basis": self.evidence_basis,
            "known_blockers": list(self.known_blockers),
        }


@dataclass(frozen=True)
class M1SamplePreregistration:
    """Validated W1 ledger; it never chooses a company by price or yield."""

    schema_version: str
    preregistration_version: str
    as_of: date
    methodology: Mapping[str, Any]
    companies: tuple[M1SamplePreregistrationEntry, ...]

    def __post_init__(self) -> None:
        if self.schema_version != M1_SAMPLE_PREREGISTRATION_SCHEMA:
            raise ValueError("Unknown M1 sample preregistration schema")
        if not self.preregistration_version.strip():
            raise ValueError("Preregistration version is required")
        symbols = [entry.symbol for entry in self.companies]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Preregistration company symbols must be unique")
        if len(self.companies) != 20:
            raise ValueError("M1 sample preregistration requires exactly 20 companies")
        if symbols[:3] != ["600519", "000333", "601088"]:
            raise ValueError("Preregistration must retain the frozen three-company order")
        profile_counts: dict[str, int] = {}
        buckets = {entry.selection_bucket for entry in self.companies}
        for entry in self.companies:
            profile_counts[entry.profile_id] = (
                profile_counts.get(entry.profile_id, 0) + 1
            )
        for profile_id in PROFILES:
            if profile_counts.get(profile_id, 0) < 2:
                raise ValueError(
                    f"Preregistration requires at least two {profile_id} entries"
                )
        if not {"UNSUPPORTED_MODEL", "DATA_INSUFFICIENT", "RISK_COUNTEREXAMPLE"} <= buckets:
            raise ValueError("Preregistration must include unsupported, insufficient and risk cases")
        object.__setattr__(self, "companies", tuple(self.companies))
        object.__setattr__(self, "methodology", dict(self.methodology))


def _reject_forbidden_keys(
    value: object,
    *,
    allow_root_action: bool = False,
) -> None:
    if isinstance(value, dict):
        forbidden = _FORBIDDEN_KEYS & set(value)
        if allow_root_action:
            forbidden -= {"action"}
        if forbidden:
            raise ValueError(f"Preregistration contains execution keys: {sorted(forbidden)}")
        for child in value.values():
            _reject_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child)


def load_m1_sample_preregistration(
    path: Path | str = DEFAULT_PREREGISTRATION_PATH,
) -> M1SamplePreregistration:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M1 sample preregistration must be a JSON object")
    _reject_forbidden_keys(payload, allow_root_action=True)
    if payload.get("action") != "no_order":
        raise ValueError("Preregistration action must remain no_order")
    methodology = payload.get("methodology")
    if not isinstance(methodology, Mapping) or not (
        _REQUIRED_METHODOLOGY_KEYS <= set(methodology)
    ):
        raise ValueError("Preregistration methodology is incomplete")
    return M1SamplePreregistration(
        schema_version=str(payload["schema_version"]),
        preregistration_version=str(payload["preregistration_version"]),
        as_of=date.fromisoformat(str(payload["as_of"])),
        methodology=dict(methodology),
        companies=tuple(
            M1SamplePreregistrationEntry(
                symbol=str(item["symbol"]),
                name=str(item["name"]),
                exchange=str(item["exchange"]),
                industry=str(item["industry"]),
                profile_id=str(item["profile_id"]),
                primary_model=item.get("primary_model"),
                selection_bucket=str(item["selection_bucket"]),
                initial_research_depth=str(item["initial_research_depth"]),
                selection_reason=str(item["selection_reason"]),
                evidence_basis=str(item["evidence_basis"]),
                known_blockers=tuple(
                    str(blocker) for blocker in item.get("known_blockers") or []
                ),
            )
            for item in payload["companies"]
        ),
    )

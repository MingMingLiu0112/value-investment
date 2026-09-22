"""Versioned fixed-sample admission manifest and typed policy loader.

The manifest is the only source of company admission policy. Scripts and the
application layer may read it, but they must not encode symbol-specific
decisions or execution state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .fixed_sample_admission import (
    CASH_RETURN_STATUSES,
    DECISIONS,
    RESEARCH_SAMPLE_STATUSES,
    FixedSampleAdmissionPolicy,
)
from .research_profile import PROFILES
from .valuation_router import VALUATION_MODEL_REGISTRY


FIXED_SAMPLE_MANIFEST_SCHEMA = "fixed-sample-manifest-v1"
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "fixed-sample-manifest.json"
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_FORBIDDEN_MANIFEST_KEYS = {
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


@dataclass(frozen=True)
class FixedSampleManifestEntry:
    """Explicit, versioned admission policy for one fixed-sample security."""

    symbol: str
    name: str
    profile_id: str
    primary_model: str
    distribution_profile: str
    distribution_status: str
    admission_state: str
    admission_evidence: tuple[str, ...]
    required_evidence: tuple[str, ...]
    decision: str
    decision_reason: str
    cash_return_status: str
    cash_return_explanation: str

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Manifest symbol must contain six digits")
        if not self.name.strip():
            raise ValueError("Manifest company name is required")
        profile = PROFILES.get(self.profile_id)
        if profile is None:
            raise ValueError(f"Unknown manifest profile: {self.profile_id}")
        if self.primary_model != profile.primary_valuation_model:
            raise ValueError("Manifest primary model must match the profile")
        if VALUATION_MODEL_REGISTRY.get(self.primary_model) is None:
            raise ValueError(f"Unregistered manifest model: {self.primary_model}")
        if self.distribution_profile != self.profile_id:
            raise ValueError("Manifest distribution profile must match the profile")
        if self.distribution_status not in CASH_RETURN_STATUSES:
            raise ValueError("Unknown manifest distribution status")
        if self.admission_state not in RESEARCH_SAMPLE_STATUSES:
            raise ValueError("Unknown manifest admission state")
        if self.decision not in DECISIONS:
            raise ValueError(f"Unknown manifest decision: {self.decision}")
        if not self.decision_reason.strip():
            raise ValueError("Manifest decision requires a reason")
        if self.cash_return_status not in CASH_RETURN_STATUSES:
            raise ValueError("Unknown manifest cash-return status")
        if not self.cash_return_explanation.strip():
            raise ValueError("Manifest cash-return explanation is required")
        if not self.admission_evidence or any(
            not item.strip() for item in self.admission_evidence
        ):
            raise ValueError("Manifest admission evidence is required")
        if not self.required_evidence or any(
            not item.strip() for item in self.required_evidence
        ):
            raise ValueError("Manifest required evidence is required")
        object.__setattr__(self, "admission_evidence", tuple(self.admission_evidence))
        object.__setattr__(self, "required_evidence", tuple(self.required_evidence))

    def as_policy(self) -> FixedSampleAdmissionPolicy:
        return FixedSampleAdmissionPolicy(
            profile_id=self.profile_id,
            decision=self.decision,
            decision_reason=self.decision_reason,
            cash_return_status=self.cash_return_status,
            cash_return_explanation=self.cash_return_explanation,
            admission_evidence=self.admission_evidence,
            required_evidence=self.required_evidence,
        )

    def as_policy_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "profile_id": self.profile_id,
            "primary_model": self.primary_model,
            "distribution_profile": self.distribution_profile,
            "distribution_status": self.distribution_status,
            "admission_state": self.admission_state,
            "admission_evidence": list(self.admission_evidence),
            "required_evidence": list(self.required_evidence),
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "cash_return_status": self.cash_return_status,
            "cash_return_explanation": self.cash_return_explanation,
        }


@dataclass(frozen=True)
class FixedSampleManifest:
    """Validated collection of fixed-sample entries with no execution state."""

    schema_version: str
    manifest_version: str
    protocol_version: str
    as_of: date
    companies: tuple[FixedSampleManifestEntry, ...]

    def __post_init__(self) -> None:
        if self.schema_version != FIXED_SAMPLE_MANIFEST_SCHEMA:
            raise ValueError("Unknown fixed-sample manifest schema")
        if not self.manifest_version.strip():
            raise ValueError("Fixed-sample manifest version is required")
        if not self.protocol_version.strip():
            raise ValueError("Fixed-sample protocol version is required")
        if not self.companies:
            raise ValueError("Fixed-sample manifest requires at least one company")
        symbols = [entry.symbol for entry in self.companies]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Fixed-sample manifest symbols must be unique")
        object.__setattr__(self, "companies", tuple(self.companies))

    @property
    def policies(self) -> dict[str, FixedSampleAdmissionPolicy]:
        return {entry.symbol: entry.as_policy() for entry in self.companies}

    def entry(self, symbol: str) -> FixedSampleManifestEntry:
        for entry in self.companies:
            if entry.symbol == symbol:
                return entry
        raise KeyError(f"Unknown fixed-sample manifest symbol: {symbol}")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_version": self.manifest_version,
            "protocol_version": self.protocol_version,
            "as_of": self.as_of.isoformat(),
            "companies": [entry.as_policy_dict() for entry in self.companies],
        }


def _reject_execution_keys(value: Mapping[str, Any], path: str) -> None:
    forbidden = sorted(set(value) & _FORBIDDEN_MANIFEST_KEYS)
    if forbidden:
        separator = ":"
        raise ValueError(
            f"Manifest contains execution keys at {path}: {separator.join(forbidden)}"
        )


def _parse_company(raw: Mapping[str, Any]) -> FixedSampleManifestEntry:
    _reject_execution_keys(raw, "$.companies[]")
    required = {
        "symbol",
        "name",
        "profile_id",
        "primary_model",
        "distribution_profile",
        "distribution_status",
        "admission_state",
        "admission_evidence",
        "required_evidence",
        "decision",
        "decision_reason",
        "cash_return_status",
        "cash_return_explanation",
    }
    missing = sorted(required - set(raw))
    if missing:
        separator = ","
        raise ValueError(
            f"Manifest company is missing fields: {separator.join(missing)}"
        )
    return FixedSampleManifestEntry(
        symbol=str(raw["symbol"]),
        name=str(raw["name"]),
        profile_id=str(raw["profile_id"]),
        primary_model=str(raw["primary_model"]),
        distribution_profile=str(raw["distribution_profile"]),
        distribution_status=str(raw["distribution_status"]),
        admission_state=str(raw["admission_state"]),
        admission_evidence=tuple(str(item) for item in raw["admission_evidence"]),
        required_evidence=tuple(str(item) for item in raw["required_evidence"]),
        decision=str(raw["decision"]),
        decision_reason=str(raw["decision_reason"]),
        cash_return_status=str(raw["cash_return_status"]),
        cash_return_explanation=str(raw["cash_return_explanation"]),
    )


def load_fixed_sample_manifest(
    path: Path | str | None = None,
) -> FixedSampleManifest:
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Fixed-sample manifest must be an object")
    _reject_execution_keys(raw, "$")
    schema_version = str(raw.get("schema_version", ""))
    if schema_version != FIXED_SAMPLE_MANIFEST_SCHEMA:
        raise ValueError("Unknown fixed-sample manifest schema")
    companies_raw = raw.get("companies")
    if not isinstance(companies_raw, list) or not companies_raw:
        raise ValueError("Fixed-sample manifest requires companies")
    companies = tuple(
        _parse_company(item)
        for item in companies_raw
        if isinstance(item, dict)
    )
    if len(companies) != len(companies_raw):
        raise ValueError("Every fixed-sample manifest company must be an object")
    return FixedSampleManifest(
        schema_version=schema_version,
        manifest_version=str(raw.get("manifest_version", "")),
        protocol_version=str(raw.get("protocol_version", "")),
        as_of=date.fromisoformat(str(raw.get("as_of", ""))),
        companies=companies,
    )

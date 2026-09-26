"""Fail-closed contracts for prospective public research observation.

Registration records what will be observed before later evidence or market
outcomes arrive.  It is deliberately not a valuation, screening result,
decision signal, portfolio instruction, or order interface.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse


ACTION_NO_ORDER = "no_order"
SCHEMA_VERSION = "prospective-research-registration-v1"
_SYMBOL = re.compile(r"^[0-9]{6}$")


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _https_url(value: Any, field: str) -> str:
    text = _text(value, field)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be an HTTPS URL")
    return text


@dataclass(frozen=True)
class ProspectiveResearchCase:
    """One bounded public company observation contract."""

    case_id: str
    symbol: str
    name: str
    profile_id: str
    valuation_model: str
    observation_start_at: datetime
    baseline_cutoff_at: datetime
    required_sources: tuple[dict[str, str], ...]
    required_assumptions: tuple[str, ...]
    pit_rules: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("case_id", "name", "profile_id", "valuation_model"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("symbol must contain exactly six digits")
        if self.observation_start_at.tzinfo is None or self.baseline_cutoff_at.tzinfo is None:
            raise ValueError("prospective timestamps must include a timezone")
        if self.baseline_cutoff_at > self.observation_start_at:
            raise ValueError("baseline_cutoff_at cannot follow observation_start_at")
        if not self.required_sources:
            raise ValueError("prospective case requires at least one source")
        ids: list[str] = []
        normalized_sources: list[dict[str, str]] = []
        for index, source in enumerate(self.required_sources):
            if not isinstance(source, Mapping):
                raise ValueError("required_sources entries must be objects")
            source_id = _text(source.get("id"), f"required_sources[{index}].id")
            ids.append(source_id)
            normalized_sources.append({
                "id": source_id,
                "role": _text(source.get("role"), f"required_sources[{index}].role"),
                "source_url": _https_url(source.get("source_url"), f"required_sources[{index}].source_url"),
            })
        if len(ids) != len(set(ids)):
            raise ValueError("required_sources ids must be unique")
        object.__setattr__(self, "required_sources", tuple(normalized_sources))
        assumptions = tuple(_text(item, "required_assumptions entry") for item in self.required_assumptions)
        if not assumptions or len(assumptions) != len(set(assumptions)):
            raise ValueError("required_assumptions must be nonempty and unique")
        object.__setattr__(self, "required_assumptions", assumptions)
        rules = tuple(_text(item, "pit_rules entry") for item in self.pit_rules)
        if len(rules) < 2:
            raise ValueError("prospective case requires at least two PIT rules")
        object.__setattr__(self, "pit_rules", rules)


@dataclass(frozen=True)
class ProspectiveResearchRegistration:
    """A preregistered bounded observation set with no execution semantics."""

    registration_id: str
    registered_at: datetime
    action: str
    cases: tuple[ProspectiveResearchCase, ...]
    exclusions: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "registration_id", _text(self.registration_id, "registration_id"))
        if self.registered_at.tzinfo is None:
            raise ValueError("registered_at must include a timezone")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("prospective research registration must remain action=no_order")
        if not 2 <= len(self.cases) <= 5:
            raise ValueError("prospective registration must contain between 2 and 5 cases")
        case_ids = [case.case_id for case in self.cases]
        symbols = [case.symbol for case in self.cases]
        if len(case_ids) != len(set(case_ids)) or len(symbols) != len(set(symbols)):
            raise ValueError("prospective case ids and symbols must be unique")
        if any(case.observation_start_at < self.registered_at for case in self.cases):
            raise ValueError("observation_start_at cannot precede registered_at")
        exclusions = tuple(_text(item, "exclusions entry") for item in self.exclusions)
        object.__setattr__(self, "exclusions", exclusions)

    def as_policy(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["registered_at"] = self.registered_at.isoformat()
        for case in payload["cases"]:
            case["observation_start_at"] = case["observation_start_at"].isoformat()
            case["baseline_cutoff_at"] = case["baseline_cutoff_at"].isoformat()
            case["required_sources"] = list(case["required_sources"])
            case["required_assumptions"] = list(case["required_assumptions"])
            case["pit_rules"] = list(case["pit_rules"])
        payload["cases"] = payload["cases"]
        payload["exclusions"] = list(self.exclusions)
        return payload


def prospective_registration_from_payload(payload: Mapping[str, Any]) -> ProspectiveResearchRegistration:
    if not isinstance(payload, Mapping):
        raise ValueError("prospective registration must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported prospective registration schema")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("prospective registration cases must be a list")
    cases: list[ProspectiveResearchCase] = []
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            raise ValueError("prospective case must be an object")
        sources = raw.get("required_sources")
        assumptions = raw.get("required_assumptions")
        rules = raw.get("pit_rules")
        if not isinstance(sources, list) or not isinstance(assumptions, list) or not isinstance(rules, list):
            raise ValueError("prospective case sources, assumptions and PIT rules must be lists")
        cases.append(ProspectiveResearchCase(
            case_id=raw.get("case_id"),
            symbol=raw.get("symbol"),
            name=raw.get("name"),
            profile_id=raw.get("profile_id"),
            valuation_model=raw.get("valuation_model"),
            observation_start_at=_timestamp(raw.get("observation_start_at"), "observation_start_at"),
            baseline_cutoff_at=_timestamp(raw.get("baseline_cutoff_at"), "baseline_cutoff_at"),
            required_sources=tuple(sources),
            required_assumptions=tuple(assumptions),
            pit_rules=tuple(rules),
        ))
    exclusions = payload.get("exclusions", [])
    if not isinstance(exclusions, list):
        raise ValueError("prospective registration exclusions must be a list")
    return ProspectiveResearchRegistration(
        registration_id=payload.get("registration_id"),
        registered_at=_timestamp(payload.get("registered_at"), "registered_at"),
        action=payload.get("action"),
        cases=tuple(cases),
        exclusions=tuple(exclusions),
    )


def canonical_registration_payload(registration: ProspectiveResearchRegistration) -> str:
    return json.dumps(registration.as_policy(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "ACTION_NO_ORDER",
    "SCHEMA_VERSION",
    "ProspectiveResearchCase",
    "ProspectiveResearchRegistration",
    "canonical_registration_payload",
    "prospective_registration_from_payload",
]

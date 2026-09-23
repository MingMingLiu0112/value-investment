"""Shared fail-closed builder for provider research dossiers.

Company-specific scripts should own only source extraction and interpretation.
This module owns the common schema conversion, evidence-reference validation,
source-file hash pinning and runtime artifact publication.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .research_read_model import (
    ACTION_NO_ORDER,
    BUSINESS_DIMENSION_CAPITAL_INTENSITY,
    BUSINESS_DIMENSION_CASH_CONVERSION,
    BUSINESS_DIMENSION_DURATION,
    BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
    BUSINESS_DIMENSION_MOAT,
    BUSINESS_DIMENSION_PRICING_CUSTOMERS,
    BUSINESS_DIMENSION_REINVESTMENT,
    BUSINESS_DIMENSION_ROIC,
    CONFIDENCE_UNKNOWN,
    DOSSIER_SCHEMA_VERSION,
    REQUIRED_BUSINESS_DIMENSIONS,
    REQUIRED_SECTION_KEYS,
    ResearchDimension,
    ResearchDossier,
    ResearchSection,
    ResearchStatement,
    SECTION_BUSINESS_QUALITY,
    SECTION_CAPITAL_ALLOCATION,
    SECTION_COMPLETE,
    SECTION_COUNTER_EVIDENCE,
    SECTION_FINANCIAL_QUALITY,
    SECTION_NEXT_EVENTS,
    SECTION_RESEARCH_GAPS,
    SECTION_STATUSES,
    SECTION_THESIS,
    SECTION_THESIS_BREAKERS,
    STATEMENT_KINDS,
    dossier_from_payload,
    section,
    statement,
)


ROOT = Path(__file__).resolve().parents[2]
_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_SECTION_TITLES = {
    SECTION_BUSINESS_QUALITY: "Business Quality",
    SECTION_FINANCIAL_QUALITY: "Financial Quality",
    SECTION_CAPITAL_ALLOCATION: "Capital Allocation",
    SECTION_THESIS: "Thesis",
    SECTION_COUNTER_EVIDENCE: "Counter Evidence",
    SECTION_THESIS_BREAKERS: "Thesis Breakers",
    SECTION_NEXT_EVENTS: "Next Events",
    SECTION_RESEARCH_GAPS: "Research Gaps",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _date(value: object, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date string") from error


def _evidence_refs(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("provider dossier evidence_refs must be a list")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("provider dossier evidence reference must be an object")
        ref = deepcopy(dict(raw))
        ref_id = _required_text(ref.get("id"), "evidence reference id")
        if ref_id in seen:
            raise ValueError("provider dossier evidence reference ids must be unique")
        seen.add(ref_id)
        path = _required_text(ref.get("path"), f"{ref_id} path")
        digest = _required_text(ref.get("sha256"), f"{ref_id} sha256").lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError(f"{ref_id} sha256 must be a hexadecimal SHA-256")
        ref["sha256"] = digest
        if "source_url" in ref:
            _required_text(ref.get("source_url"), f"{ref_id} source_url")
        if "published_date" in ref:
            _date(ref.get("published_date"), f"{ref_id} published_date")
        if "period_end" in ref:
            _date(ref.get("period_end"), f"{ref_id} period_end")
        result.append({"path": path, **ref})
    return tuple(result)


def _statement_from_spec(item: Mapping[str, Any], field: str) -> ResearchStatement:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object")
    kind = _required_text(item.get("kind"), f"{field}.kind")
    if kind not in STATEMENT_KINDS:
        raise ValueError(f"{field}.kind is not a research statement kind")
    text = _required_text(item.get("text"), f"{field}.text")
    confidence = str(item.get("confidence") or CONFIDENCE_UNKNOWN).upper()
    status = str(item.get("status") or SECTION_COMPLETE).upper()
    if status not in SECTION_STATUSES:
        raise ValueError(f"{field}.status is unknown")
    evidence_refs = tuple(
        _required_text(ref, f"{field}.evidence_refs")
        for ref in (item.get("evidence_refs") or [])
    )
    return statement(
        kind=kind,
        text=text,
        confidence=confidence,
        status=status,
        evidence_refs=evidence_refs,
    )


def _dimension_from_spec(item: Mapping[str, Any], field: str) -> ResearchDimension:
    if not isinstance(item, Mapping):
        raise ValueError(f"{field} must be an object")
    key = _required_text(item.get("key"), f"{field}.key")
    status = _required_text(item.get("status"), f"{field}.status")
    observation = _required_text(item.get("observation"), f"{field}.observation")
    evidence_refs = tuple(
        _required_text(ref, f"{field}.evidence_refs")
        for ref in (item.get("evidence_refs") or [])
    )
    return ResearchDimension(
        key=key,
        status=status,
        observation=observation,
        evidence_refs=evidence_refs,
    )


def _section_from_spec(key: str, item: Mapping[str, Any]) -> ResearchSection:
    if not isinstance(item, Mapping):
        raise ValueError(f"sections.{key} must be an object")
    status = _required_text(item.get("status"), f"sections.{key}.status")
    findings = tuple(
        _statement_from_spec(raw, f"sections.{key}.findings[{index}]")
        for index, raw in enumerate(item.get("findings") or [])
    )
    dimensions = tuple(
        _dimension_from_spec(raw, f"sections.{key}.dimensions[{index}]")
        for index, raw in enumerate(item.get("dimensions") or [])
    )
    blockers = tuple(
        _required_text(raw, f"sections.{key}.blockers[{index}]")
        for index, raw in enumerate(item.get("blockers") or [])
    )
    return section(
        key=key,
        title=_SECTION_TITLES[key],
        status=status,
        findings=findings,
        dimensions=dimensions,
        blockers=blockers,
        explanation=str(item.get("explanation") or ""),
    )


def _check_references(dossier: ResearchDossier) -> None:
    known = {ref["id"] for ref in dossier.evidence_refs}
    unknown: list[str] = []
    for current in (
        dossier.business_quality,
        dossier.financial_quality,
        dossier.capital_allocation,
        dossier.thesis,
        dossier.counter_evidence,
        dossier.thesis_breakers,
        dossier.next_events,
        dossier.research_gaps,
    ):
        for finding in current.findings:
            if finding.kind in {"fact", "interpretation"} and not finding.evidence_refs:
                raise ValueError(
                    f"{current.key} fact/interpretation must reference evidence"
                )
            unknown.extend(
                ref for ref in finding.evidence_refs if ref not in known
            )
        for dimension in current.dimensions:
            if dimension.status not in {
                "UNKNOWN",
                "NOT_APPLICABLE",
                "MISSING",
                "NOT_STARTED",
            } and not dimension.evidence_refs:
                raise ValueError(
                    f"{current.key}.{dimension.key} must reference evidence"
                )
            unknown.extend(
                ref for ref in dimension.evidence_refs if ref not in known
            )
    if unknown:
        raise ValueError(
            "Provider dossier references unknown evidence ids: "
            + ", ".join(sorted(set(unknown)))
        )


def build_provider_dossier(
    spec: Mapping[str, Any],
    *,
    generated_at: datetime | None = None,
) -> ResearchDossier:
    """Convert a validated provider spec into a no-order ResearchDossier."""

    if not isinstance(spec, Mapping):
        raise ValueError("provider dossier spec must be an object")
    data = deepcopy(dict(spec))
    if data.get("action") not in (None, ACTION_NO_ORDER):
        raise ValueError("provider dossier action must remain no_order")

    symbol = _required_text(data.get("symbol"), "provider dossier symbol")
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("provider dossier symbol must contain six digits")
    name = _required_text(data.get("name"), "provider dossier name")
    as_of = _date(data.get("as_of"), "provider dossier as_of")
    run_id = _required_text(data.get("run_id"), "provider dossier run_id")
    research_version = _required_text(
        data.get("research_version"), "provider dossier research_version"
    )
    profile_id = _required_text(data.get("profile_id"), "provider dossier profile_id")
    primary_model = data.get("primary_model")
    if primary_model is not None:
        primary_model = _required_text(primary_model, "provider dossier primary_model")
    financial_period = (
        _date(data.get("financial_period"), "provider dossier financial_period")
        if data.get("financial_period") is not None
        else None
    )
    valuation_status = _required_text(
        data.get("valuation_status"), "provider dossier valuation_status"
    )
    research_status = _required_text(
        data.get("research_status"), "provider dossier research_status"
    )
    evidence_refs = _evidence_refs(data.get("evidence_refs"))

    raw_sections = data.get("sections")
    if not isinstance(raw_sections, Mapping):
        raise ValueError("provider dossier sections must be an object")
    section_keys = {str(key) for key in raw_sections}
    if section_keys != set(REQUIRED_SECTION_KEYS):
        raise ValueError("provider dossier sections must contain every required key")
    sections = {
        key: _section_from_spec(key, raw_sections[key])
        for key in _SECTION_TITLES
    }
    business_dimensions = {
        dimension.key for dimension in sections[SECTION_BUSINESS_QUALITY].dimensions
    }
    if business_dimensions != REQUIRED_BUSINESS_DIMENSIONS:
        raise ValueError(
            "provider dossier business_quality must register every required dimension"
        )
    for key in (SECTION_COUNTER_EVIDENCE, SECTION_THESIS_BREAKERS, SECTION_NEXT_EVENTS):
        if not sections[key].findings:
            raise ValueError(f"provider dossier {key} must contain findings")

    draft = ResearchDossier(
        schema_version=DOSSIER_SCHEMA_VERSION,
        symbol=symbol,
        name=name,
        as_of=as_of,
        run_id=run_id,
        generated_at=generated_at or datetime.now(timezone.utc),
        research_version=research_version,
        profile_id=profile_id,
        primary_model=primary_model,
        action=ACTION_NO_ORDER,
        business_quality=sections[SECTION_BUSINESS_QUALITY],
        financial_quality=sections[SECTION_FINANCIAL_QUALITY],
        capital_allocation=sections[SECTION_CAPITAL_ALLOCATION],
        thesis=sections[SECTION_THESIS],
        counter_evidence=sections[SECTION_COUNTER_EVIDENCE],
        thesis_breakers=sections[SECTION_THESIS_BREAKERS],
        next_events=sections[SECTION_NEXT_EVENTS],
        research_gaps=sections[SECTION_RESEARCH_GAPS],
        evidence_refs=evidence_refs,
        financial_period=financial_period,
        valuation_status=valuation_status,
        research_status=research_status,
    )
    _check_references(draft)
    # Decode the round trip so the same execution-key and schema rules apply
    # to provider-built dossiers as to manually written runtime artifacts.
    return dossier_from_payload(draft.as_policy())


def _verify_evidence_files(
    dossier: ResearchDossier, *, root: Path
) -> None:
    for ref in dossier.evidence_refs:
        path = (root / ref["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"Evidence path escapes project root: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Evidence source file is missing: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != ref["sha256"]:
            raise ValueError(
                f"Evidence source hash changed for {ref['id']}: "
                f"expected {ref['sha256']}, got {actual}"
            )


def write_provider_dossier(
    spec: Mapping[str, Any],
    *,
    generated_at: datetime | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Write one provider dossier with a hash-pinned source and latest pointer."""

    dossier = build_provider_dossier(spec, generated_at=generated_at)
    _verify_evidence_files(dossier, root=root)
    timestamp = dossier.generated_at.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    target = (
        root
        / "runtime"
        / "company-research"
        / f"{dossier.symbol}-m1-dossier-{timestamp}"
    )
    target.mkdir(parents=True, exist_ok=True)
    evidence = target / "evidence.json"
    evidence.write_text(
        json.dumps(dossier.as_policy(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pointer = {
        "path": str(target.relative_to(root)),
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    pointer_path = (
        root
        / "runtime"
        / "company-research"
        / f"{dossier.symbol}-m1-dossier-latest.json"
    )
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "symbol": dossier.symbol,
        "readiness": dossier.readiness,
        "action": dossier.action,
        "evidence_path": str(evidence.relative_to(root)),
        "pointer_path": str(pointer_path.relative_to(root)),
        "sha256": pointer["sha256"],
        "source_hashes": [ref["sha256"] for ref in dossier.evidence_refs],
    }

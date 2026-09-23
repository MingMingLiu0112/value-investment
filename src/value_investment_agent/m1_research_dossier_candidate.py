"""Build the W3 dossier candidate from W1 and retained frozen evidence.

The three frozen cases become honest PARTIAL/BLOCKED dossier views.  Every
other preregistered company starts as NOT_STARTED with its known blockers
visible.  This module never writes the production workbook and never changes
the no_order contract.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .m1_sample_preregistration import (
    M1SamplePreregistration,
    M1SamplePreregistrationEntry,
    load_m1_sample_preregistration,
)
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
    ResearchDimension,
    ResearchDossier,
    ResearchDossierCollection,
    ResearchSection,
    ResearchStatement,
    SECTION_BLOCKED,
    SECTION_COMPLETE,
    SECTION_NOT_STARTED,
    SECTION_PARTIAL,
    SECTION_UNKNOWN,
    dossier_collection_from_payload,
    dossier_from_payload,
    not_started_dossier,
    section,
    statement,
)


ROOT = Path(__file__).resolve().parents[2]
FROZEN_RESEARCH_CASES = ROOT / "runtime" / "excel-mvp-research-cases" / "evidence.json"
RUNTIME_ROOT = ROOT / "runtime"
CANDIDATE_POINTER = RUNTIME_ROOT / "m1-research-dossier-candidate-latest.json"
CANDIDATE_RUN_ID = "m1-w3-dossier-candidate"

_BUSINESS_DIMENSIONS = (
    BUSINESS_DIMENSION_MOAT,
    BUSINESS_DIMENSION_PRICING_CUSTOMERS,
    BUSINESS_DIMENSION_INDUSTRY_STRUCTURE,
    BUSINESS_DIMENSION_ROIC,
    BUSINESS_DIMENSION_REINVESTMENT,
    BUSINESS_DIMENSION_CAPITAL_INTENSITY,
    BUSINESS_DIMENSION_CASH_CONVERSION,
    BUSINESS_DIMENSION_DURATION,
)


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    return date.fromisoformat(value)


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _statement_from_legacy(item: Mapping[str, Any]) -> ResearchStatement:
    kind = str(item.get("kind") or "")
    text = str(item.get("text") or "")
    refs = tuple(str(ref) for ref in (item.get("evidence_refs") or []))
    if kind == "gap":
        status = SECTION_UNKNOWN
    elif kind == "hypothesis":
        status = SECTION_UNKNOWN
    else:
        status = SECTION_COMPLETE
    return statement(
        kind=kind,
        text=text,
        confidence=CONFIDENCE_UNKNOWN,
        status=status,
        evidence_refs=refs,
    )


def _section_from_legacy_items(
    key: str,
    title: str,
    items: Sequence[Mapping[str, Any]],
    *,
    status_override: str | None = None,
) -> ResearchSection:
    findings = tuple(_statement_from_legacy(item) for item in items)
    status = status_override or (
        SECTION_COMPLETE if findings else SECTION_UNKNOWN
    )
    return section(key, title, status, findings=findings)


def build_frozen_case_dossier(
    record: Mapping[str, Any],
    entry: M1SamplePreregistrationEntry,
    *,
    generated_at: datetime,
    run_id: str,
) -> ResearchDossier:
    """Convert one retained legacy case without inventing a section taxonomy."""

    case = dict(record.get("case") or {})
    if case.get("symbol") != entry.symbol:
        raise ValueError("Frozen research record and preregistration symbol differ")
    evidence_refs = tuple(
        dict(ref) for ref in (case.get("evidence_refs") or [])
    )
    unknown_dimensions = tuple(
        ResearchDimension(
            key=key,
            status=SECTION_UNKNOWN,
            observation=(
                "Legacy ResearchCase did not separate this business-quality "
                "dimension from its combined evidence list."
            ),
        )
        for key in _BUSINESS_DIMENSIONS
    )
    thesis_text = str(case.get("thesis") or "")
    return_driver_text = str(case.get("return_driver") or "")
    mispricing_text = str(case.get("mispricing_hypothesis") or "")
    thesis_items = [
        statement("gap", f"Legacy thesis text retained: {thesis_text}"),
        statement("gap", f"Legacy return driver retained: {return_driver_text}"),
        statement("gap", f"Legacy mispricing text retained: {mispricing_text}"),
    ]
    blockers = tuple(str(item) for item in (case.get("blockers") or []))
    research_gaps = section(
        "research_gaps",
        "Research Gaps",
        SECTION_BLOCKED if blockers else SECTION_COMPLETE,
        findings=tuple(
            statement("gap", blocker, status=SECTION_BLOCKED)
            for blocker in blockers
        ),
        blockers=blockers,
    )
    business_quality = section(
        "business_quality",
        "Business Quality",
        SECTION_UNKNOWN,
        dimensions=unknown_dimensions,
        explanation=(
            "Legacy positives/counter-evidence were retained, but moat, pricing, "
            "industry structure, reinvestment and duration were not yet split into "
            "evidence-bound dimensions."
        ),
    )
    financial_quality = section(
        "financial_quality",
        "Financial Quality",
        SECTION_UNKNOWN,
        findings=(
            statement(
                "gap",
                "Legacy financial_summary is retained but not yet bound field by field.",
            ),
        ),
        explanation="The legacy financial summary is a research boundary, not a verified read-model section.",
    )
    capital_allocation = section(
        "capital_allocation",
        "Capital Allocation",
        SECTION_UNKNOWN,
        explanation=(
            "Cash return and capital actions appear in the legacy evidence, but a "
            "dedicated allocation assessment has not been registered."
        ),
    )
    counter_evidence = _section_from_legacy_items(
        "counter_evidence",
        "Counter Evidence",
        case.get("counter_evidence") or [],
    )
    thesis_breakers = _section_from_legacy_items(
        "thesis_breakers",
        "Thesis Breakers",
        case.get("thesis_breakers") or [],
    )
    next_events = _section_from_legacy_items(
        "next_events",
        "Next Events",
        case.get("next_events") or [],
    )
    return ResearchDossier(
        schema_version=DOSSIER_SCHEMA_VERSION,
        symbol=entry.symbol,
        name=str(case.get("name") or entry.name),
        as_of=_date(case.get("as_of"), "frozen case as_of"),
        run_id=run_id,
        generated_at=generated_at,
        research_version=str(case.get("research_version") or "legacy-v1"),
        profile_id=entry.profile_id,
        primary_model=entry.primary_model,
        action=ACTION_NO_ORDER,
        business_quality=business_quality,
        financial_quality=financial_quality,
        capital_allocation=capital_allocation,
        thesis=section(
            "thesis",
            "Thesis",
            SECTION_UNKNOWN,
            findings=tuple(thesis_items),
            explanation="Legacy thesis fields were not bound to specific evidence references.",
        ),
        counter_evidence=counter_evidence,
        thesis_breakers=thesis_breakers,
        next_events=next_events,
        research_gaps=research_gaps,
        evidence_refs=evidence_refs,
        financial_period=(
            _date(case["financial_period"], "frozen financial period")
            if case.get("financial_period")
            else None
        ),
        valuation_status=str(case.get("valuation_status") or "NOT_READY"),
        research_status=str(case.get("research_status") or "NOT_STARTED"),
    )


def _not_started_from_entry(
    entry: M1SamplePreregistrationEntry,
    *,
    as_of: date,
    generated_at: datetime,
    run_id: str,
) -> ResearchDossier:
    return not_started_dossier(
        symbol=entry.symbol,
        name=entry.name,
        as_of=as_of,
        run_id=run_id,
        generated_at=generated_at,
        research_version="m1-w3-candidate-v1",
        profile_id=entry.profile_id,
        primary_model=entry.primary_model,
        known_blockers=entry.known_blockers,
    )


def build_candidate_collection(
    preregistration: M1SamplePreregistration,
    frozen_payload: Mapping[str, Any],
    *,
    generated_at: datetime,
    run_id: str = CANDIDATE_RUN_ID,
    real_dossiers: Mapping[str, ResearchDossier] | None = None,
) -> ResearchDossierCollection:
    """Build 20 dossiers; only the retained three may carry legacy findings."""

    if frozen_payload.get("formal_trade_instructions") is not False:
        raise ValueError("Frozen research payload must not contain trade instructions")
    records = frozen_payload.get("records")
    if not isinstance(records, list) or len(records) != 3:
        raise ValueError("Frozen research payload must contain three legacy records")
    frozen_by_symbol = {
        str(record.get("case", {}).get("symbol")): dict(record)
        for record in records
    }
    if set(frozen_by_symbol) != {"600519", "000333", "601088"}:
        raise ValueError("Frozen research payload identity changed")
    entries = {entry.symbol: entry for entry in preregistration.companies}
    real_by_symbol = dict(real_dossiers or {})
    if any(symbol not in entries for symbol in real_by_symbol):
        raise ValueError("Real dossier symbol is not in the preregistered sample")
    if any(
        entries[symbol].initial_research_depth == "FROZEN_PLATFORM_CASE"
        for symbol in real_by_symbol
    ):
        raise ValueError("A frozen platform case cannot be replaced by a provider dossier")
    dossiers = tuple(
        real_by_symbol[entry.symbol]
        if entry.symbol in real_by_symbol
        else build_frozen_case_dossier(
            frozen_by_symbol[entry.symbol],
            entry,
            generated_at=generated_at,
            run_id=f"{run_id}:{entry.symbol}",
        )
        if entry.symbol in frozen_by_symbol
        else _not_started_from_entry(
            entry,
            as_of=preregistration.as_of,
            generated_at=generated_at,
            run_id=f"{run_id}:{entry.symbol}",
        )
        for entry in preregistration.companies
    )
    return ResearchDossierCollection(
        schema_version=DOSSIER_SCHEMA_VERSION,
        generated_at=generated_at,
        action=ACTION_NO_ORDER,
        dossiers=dossiers,
    )


def load_frozen_candidates(path: Path = FROZEN_RESEARCH_CASES) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Frozen research candidate file is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Frozen research candidate must be a JSON object")
    return payload


def write_candidate(
    collection: ResearchDossierCollection,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    runtime_root = root / "runtime"
    timestamp = collection.generated_at.astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    target_dir = runtime_root / f"m1-research-dossier-candidate-{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = collection.as_policy()
    evidence_path = target_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "run_id": CANDIDATE_RUN_ID,
        "generated_at": collection.generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "company_count": len(collection.dossiers),
        "input_failure_count": len(collection.input_failures),
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pointer = {
        "path": str(target_dir.relative_to(root)),
        "sha256": manifest["evidence_sha256"],
    }
    (runtime_root / "m1-research-dossier-candidate-latest.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "evidence_path": str(evidence_path.relative_to(root)),
        "manifest_path": str((target_dir / "manifest.json").relative_to(root)),
        "pointer_path": str(
            (runtime_root / "m1-research-dossier-candidate-latest.json").relative_to(
                root
            )
        ),
        **manifest,
    }


def load_provider_dossiers(
    root: Path = ROOT,
) -> dict[str, ResearchDossier]:
    """Load every symbol-keyed provider dossier pointer in local runtime."""

    runtime = root / "runtime" / "company-research"
    dossiers: dict[str, ResearchDossier] = {}
    for pointer_path in sorted(runtime.glob("??????-m1-dossier-latest.json")):
        symbol = pointer_path.name[:6]
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if not isinstance(pointer, Mapping):
            raise ValueError(f"Provider dossier pointer must be an object: {symbol}")
        evidence = (root / pointer["path"] / "evidence.json").resolve()
        if (
            not evidence.is_relative_to(root.resolve())
            or hashlib.sha256(evidence.read_bytes()).hexdigest()
            != str(pointer["sha256"]).lower()
        ):
            raise ValueError(f"Provider dossier pointer is invalid: {symbol}")
        dossier = dossier_from_payload(
            json.loads(evidence.read_text(encoding="utf-8"))
        )
        if dossier.symbol != symbol:
            raise ValueError(f"Provider dossier pointer symbol mismatch: {symbol}")
        dossiers[symbol] = dossier
    return dossiers


def build_default_candidate(
    *,
    generated_at: datetime | None = None,
    root: Path = ROOT,
) -> ResearchDossierCollection:
    preregistration = load_m1_sample_preregistration()
    real_dossiers = load_provider_dossiers(root=root)
    return build_candidate_collection(
        preregistration,
        load_frozen_candidates(root / "runtime" / "excel-mvp-research-cases" / "evidence.json"),
        generated_at=generated_at or datetime.now(timezone.utc),
        real_dossiers=real_dossiers,
    )


def load_candidate_pointer(root: Path = ROOT) -> ResearchDossierCollection:
    pointer = json.loads(CANDIDATE_POINTER.read_text(encoding="utf-8"))
    path = (root / pointer["path"] / "evidence.json").resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Candidate evidence pointer escapes project root")
    expected = str(pointer.get("sha256") or "").lower()
    if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Candidate evidence hash changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dossier_collection_from_payload(payload)

"""Controlled importer and parity report for frozen three-company runtime JSON.

The runtime files remain the source snapshots. This module copies their
canonical payloads into an append-only repository and verifies semantic parity
without deleting or overwriting the JSON pointers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .current_research_status import current_research_status_from_payloads
from .research_artifact_codecs import (
    ARTIFACT_SCHEMA_VERSION,
    artifact_payload,
    decode_artifact,
)
from .research_artifact_repository import ResearchArtifactRepository
from .research_artifacts import (
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_FIXED_SAMPLE_ADMISSION,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_RESULT,
    SCOPE_REVIEW,
    SCOPE_SECURITY,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
    canonicalize_artifact_payload,
)


SYMBOLS = ("600519", "000333", "601088")

RESEARCH_POINTER = "runtime/excel-mvp-research-cases-latest.json"
VALUATION_POINTERS = {
    "600519": "runtime/valuation-results/600519-current-equity-stage-b-latest.json",
    "000333": "runtime/valuation-results/000333-fcff-stage-b-latest.json",
    "601088": "runtime/valuation-results/601088-cyclical-stage-b-latest.json",
}
REVIEW_POINTER = "runtime/fixed-sample-admission-review-latest.json"


@dataclass(frozen=True)
class PinnedEvidence:
    pointer: Path
    evidence: Path
    sha256: str

    def as_ref(self, root: Path) -> dict[str, Any]:
        resolved_root = root.resolve()
        return {
            "id": f"runtime-source:{self.pointer.as_posix()}",
            "path": self.evidence.relative_to(resolved_root).as_posix(),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RuntimeArtifactCandidate:
    symbol: str
    artifact_type: str
    identity: ResearchArtifactIdentity
    payload: dict[str, Any]
    evidence_refs: tuple[dict[str, Any], ...]
    run_id: str
    source_path: Path
    source_sha256: str
    dependencies: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RuntimeImportResult:
    run_id: str
    symbols: tuple[str, ...]
    candidates: tuple[RuntimeArtifactCandidate, ...]
    stored: tuple[StoredResearchArtifact, ...]
    missing: tuple[tuple[str, str], ...]
    parity_rows: tuple[dict[str, Any], ...]

    @property
    def all_hashes_matched(self) -> bool:
        return bool(self.parity_rows) and all(
            row["hash_matched"] for row in self.parity_rows
        )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_refs(*groups: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Runtime evidence references require ids")
            if ref_id in merged and merged[ref_id] != ref:
                raise ValueError(f"Runtime evidence id conflict: {ref_id}")
            merged[ref_id] = ref
    return tuple(merged.values())


def resolve_pinned(root: Path, pointer_name: str) -> tuple[Any, PinnedEvidence]:
    pointer_path = root / pointer_name
    if not pointer_path.is_file():
        raise FileNotFoundError(f"Missing runtime pointer: {pointer_path}")
    pin = _read_json(pointer_path)
    evidence_relative = str(pin["path"]).replace("\\", "/")
    evidence_path = (root / evidence_relative / "evidence.json").resolve()
    if not evidence_path.is_relative_to(root.resolve()):
        raise ValueError(f"Pinned runtime evidence escapes the repository: {pointer_name}")
    actual = sha256_file(evidence_path)
    expected = str(pin["sha256"]).lower()
    if actual != expected:
        raise ValueError(f"Pinned runtime evidence hash changed: {pointer_name}")
    return (
        _read_json(evidence_path),
        PinnedEvidence(pointer=pointer_path.relative_to(root), evidence=evidence_path, sha256=actual),
    )


def _datetime_from_iso(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _date_at_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    return datetime.combine(date.fromisoformat(value), time.min, tzinfo=timezone.utc)


def _refs(value: object) -> tuple[dict[str, Any], ...]:
    return tuple(dict(item) for item in (value or []))


def build_runtime_candidates(
    root: Path,
    *,
    run_id: str,
    symbols: Sequence[str] = SYMBOLS,
) -> tuple[tuple[RuntimeArtifactCandidate, ...], tuple[tuple[str, str], ...]]:
    """Read pinned runtime payloads and produce append-only artifact candidates."""
    selected = tuple(str(symbol) for symbol in symbols)
    research, research_pin = resolve_pinned(root, RESEARCH_POINTER)
    review, review_pin = resolve_pinned(root, REVIEW_POINTER)
    records = {
        str(record["case"]["symbol"]): record
        for record in research["records"]
        if str(record["case"]["symbol"]) in selected
    }
    companies = {
        str(company["symbol"]): company
        for company in review.get("companies", [])
        if str(company["symbol"]) in selected
    }
    if set(records) != set(selected) or set(companies) != set(selected):
        raise ValueError("Research and admission payloads must cover the selected symbols")

    candidates: list[RuntimeArtifactCandidate] = []
    missing: list[tuple[str, str]] = []
    valuation_payloads: dict[str, dict[str, Any]] = {}
    valuation_pins: dict[str, PinnedEvidence] = {}
    research_refs: dict[str, dict[str, Any]] = {}

    for symbol in selected:
        research_refs[symbol] = research_pin.as_ref(root)
        case = dict(records[symbol]["case"])
        available_at = _datetime_from_iso(case["generated_at"], "generated_at")
        case_identity = ResearchArtifactIdentity(
            SCOPE_SECURITY,
            symbol,
            ARTIFACT_RESEARCH_CASE,
            ARTIFACT_SCHEMA_VERSION,
            date.fromisoformat(str(case["as_of"])),
            available_at,
        )
        case_refs = _merge_refs(
            _refs(case.get("evidence_refs")),
            (research_pin.as_ref(root),),
        )
        candidates.append(
            RuntimeArtifactCandidate(
                symbol,
                ARTIFACT_RESEARCH_CASE,
                case_identity,
                case,
                case_refs,
                run_id,
                research_pin.evidence,
                research_pin.sha256,
            )
        )

        gate = dict(records[symbol]["gate"])
        candidates.append(
            RuntimeArtifactCandidate(
                symbol,
                ARTIFACT_RESEARCH_GATE,
                ResearchArtifactIdentity(
                    SCOPE_SECURITY,
                    symbol,
                    ARTIFACT_RESEARCH_GATE,
                    ARTIFACT_SCHEMA_VERSION,
                    date.fromisoformat(str(case["as_of"])),
                    available_at,
                ),
                gate,
                (research_pin.as_ref(root),),
                run_id,
                research_pin.evidence,
                research_pin.sha256,
            )
        )

        payload, valuation_pin = resolve_pinned(
            root, VALUATION_POINTERS[symbol]
        )
        valuation_payloads[symbol] = payload
        valuation_pins[symbol] = valuation_pin
        result = dict(payload["result"])
        valuation_available_at = _date_at_utc(
            result["valuation_date"], "valuation_date"
        )
        common_refs = _merge_refs(
            _refs(result.get("evidence_refs")),
            (valuation_pin.as_ref(root),),
        )
        candidates.append(
            RuntimeArtifactCandidate(
                symbol,
                ARTIFACT_VALUATION_RESULT,
                ResearchArtifactIdentity(
                    SCOPE_SECURITY,
                    symbol,
                    ARTIFACT_VALUATION_RESULT,
                    ARTIFACT_SCHEMA_VERSION,
                    date.fromisoformat(str(result["valuation_date"])),
                    valuation_available_at,
                ),
                result,
                common_refs,
                run_id,
                valuation_pin.evidence,
                valuation_pin.sha256,
            )
        )

        model_validity = payload.get("model_validity")
        if model_validity is not None:
            validity_refs = _merge_refs(
                _refs(model_validity.get("evidence_refs")),
                (valuation_pin.as_ref(root),),
            )
            candidates.append(
                RuntimeArtifactCandidate(
                    symbol,
                    ARTIFACT_MODEL_VALIDITY,
                    ResearchArtifactIdentity(
                        SCOPE_SECURITY,
                        symbol,
                        ARTIFACT_MODEL_VALIDITY,
                        ARTIFACT_SCHEMA_VERSION,
                        date.fromisoformat(str(model_validity["model_as_of"])),
                        _date_at_utc(model_validity["model_as_of"], "model_as_of"),
                    ),
                    dict(model_validity),
                    validity_refs,
                    run_id,
                    valuation_pin.evidence,
                    valuation_pin.sha256,
                )
            )
        else:
            missing.append((symbol, ARTIFACT_MODEL_VALIDITY))

        bridge = payload.get("price_bridge")
        if bridge is not None:
            bridge_refs = _merge_refs(
                _refs(bridge.get("evidence_refs")),
                (valuation_pin.as_ref(root),),
            )
            candidates.append(
                RuntimeArtifactCandidate(
                    symbol,
                    ARTIFACT_PRICE_BRIDGE,
                    ResearchArtifactIdentity(
                        SCOPE_SECURITY,
                        symbol,
                        ARTIFACT_PRICE_BRIDGE,
                        ARTIFACT_SCHEMA_VERSION,
                        date.fromisoformat(str(bridge["valuation_date"])),
                        _date_at_utc(bridge["valuation_date"], "valuation_date"),
                    ),
                    dict(bridge),
                    bridge_refs,
                    run_id,
                    valuation_pin.evidence,
                    valuation_pin.sha256,
                )
            )
        else:
            missing.append((symbol, ARTIFACT_PRICE_BRIDGE))

        quote = payload.get("quote_snapshot")
        if quote is not None:
            quote_refs = _merge_refs(
                _refs(quote.get("evidence_refs")),
                (valuation_pin.as_ref(root),),
            )
            quote_date = quote.get("quote_date")
            candidates.append(
                RuntimeArtifactCandidate(
                    symbol,
                    ARTIFACT_QUOTE_SNAPSHOT,
                    ResearchArtifactIdentity(
                        SCOPE_SECURITY,
                        symbol,
                        ARTIFACT_QUOTE_SNAPSHOT,
                        ARTIFACT_SCHEMA_VERSION,
                        date.fromisoformat(str(quote_date)) if quote_date else None,
                        (
                            _date_at_utc(quote_date, "quote_date")
                            if quote_date
                            else valuation_available_at
                        ),
                    ),
                    dict(quote),
                    quote_refs,
                    run_id,
                    valuation_pin.evidence,
                    valuation_pin.sha256,
                )
            )

    for symbol in selected:
        company = dict(companies[symbol])
        cash_return = company.get("cash_return_research")
        if cash_return is not None:
            cash_refs = _merge_refs(
                _refs(cash_return.get("evidence_refs")),
                (review_pin.as_ref(root),),
            )
            candidates.append(
                RuntimeArtifactCandidate(
                    symbol,
                    ARTIFACT_DIVIDEND_RESEARCH,
                    ResearchArtifactIdentity(
                        SCOPE_SECURITY,
                        symbol,
                        ARTIFACT_DIVIDEND_RESEARCH,
                        ARTIFACT_SCHEMA_VERSION,
                        date.fromisoformat(str(cash_return["as_of"])),
                        _date_at_utc(cash_return["as_of"], "as_of"),
                    ),
                    dict(cash_return),
                    cash_refs,
                    run_id,
                    review_pin.evidence,
                    review_pin.sha256,
                )
            )
        else:
            missing.append((symbol, ARTIFACT_DIVIDEND_RESEARCH))

        record = records[symbol]
        payload = valuation_payloads[symbol]
        profile_id = str(company["profile_id"])
        status = current_research_status_from_payloads(
            dict(record["gate"]),
            dict(payload["result"]),
            dict(payload["price_bridge"]),
            model_validity_payload=(
                dict(payload["model_validity"])
                if payload.get("model_validity") is not None
                else None
            ),
            profile_id=profile_id,
        )
        status_refs = _merge_refs(
            status.evidence_refs,
            (review_pin.as_ref(root),),
        )
        candidates.append(
            RuntimeArtifactCandidate(
                symbol,
                ARTIFACT_CURRENT_RESEARCH_STATUS,
                ResearchArtifactIdentity(
                    SCOPE_SECURITY,
                    symbol,
                    ARTIFACT_CURRENT_RESEARCH_STATUS,
                    ARTIFACT_SCHEMA_VERSION,
                    date.fromisoformat(str(review["as_of"])),
                    _datetime_from_iso(review["generated_at"], "generated_at"),
                ),
                artifact_payload(status)[1],
                status_refs,
                run_id,
                review_pin.evidence,
                review_pin.sha256,
            )
        )

    review_payload = {
        key: value
        for key, value in review.items()
        if key not in {"version", "generated_at", "input_refs"}
    }
    review_available_at = _datetime_from_iso(
        review["generated_at"], "generated_at"
    )
    candidates.append(
        RuntimeArtifactCandidate(
            "review",
            ARTIFACT_FIXED_SAMPLE_ADMISSION,
            ResearchArtifactIdentity(
                SCOPE_REVIEW,
                "fixed-sample-v1",
                ARTIFACT_FIXED_SAMPLE_ADMISSION,
                ARTIFACT_SCHEMA_VERSION,
                date.fromisoformat(str(review["as_of"])),
                review_available_at,
            ),
            review_payload,
            _merge_refs(
                _refs(review.get("evidence_refs")),
                (review_pin.as_ref(root),),
            ),
            run_id,
            review_pin.evidence,
            review_pin.sha256,
        )
    )
    return tuple(candidates), tuple(missing)


def import_runtime_artifacts(
    repository: ResearchArtifactRepository,
    root: Path,
    *,
    run_id: str,
    symbols: Sequence[str] = SYMBOLS,
) -> RuntimeImportResult:
    candidates, missing = build_runtime_candidates(
        root, run_id=run_id, symbols=symbols
    )
    stored: list[StoredResearchArtifact] = []
    for candidate in candidates:
        envelope = ResearchArtifactEnvelope.build(
            identity=candidate.identity,
            payload=candidate.payload,
            evidence_refs=candidate.evidence_refs,
            run_id=candidate.run_id,
        )
        stored.append(repository.save(envelope))

    resolved_root = root.resolve()
    by_key = {
        (
            item.envelope.identity.scope_type,
            item.envelope.identity.scope_key,
            item.envelope.identity.artifact_type,
        ): item
        for item in stored
    }
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (
            candidate.identity.scope_type,
            candidate.identity.scope_key,
            candidate.identity.artifact_type,
        )
        db = by_key[key]
        rows.append(
            {
                "symbol": candidate.symbol,
                "artifact_type": candidate.artifact_type,
                "source_path": candidate.source_path.relative_to(resolved_root).as_posix(),
                "source_sha256": candidate.source_sha256,
                "database_artifact_id": db.artifact_id,
                "database_payload_sha256": db.envelope.payload_sha256,
                "hash_matched": (
                    canonicalize_artifact_payload(candidate.payload)
                    == db.envelope.canonical_payload
                ),
                "restored_semantic_status": "NOT_VERIFIED",
            }
        )
    return RuntimeImportResult(
        run_id=run_id,
        symbols=tuple(str(symbol) for symbol in symbols),
        candidates=candidates,
        stored=tuple(stored),
        missing=missing,
        parity_rows=tuple(rows),
    )


def semantic_parity_report(
    result: RuntimeImportResult,
    *,
    root: Path,
    valuations: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Restore typed objects and replace parity-row status placeholders."""
    valuation_objects = {
        symbol: decode_artifact(ARTIFACT_VALUATION_RESULT, dict(payload["result"]))
        for symbol, payload in valuations.items()
    }
    rows: list[dict[str, Any]] = []
    for row in result.parity_rows:
        artifact_type = str(row["artifact_type"])
        if artifact_type == ARTIFACT_PRICE_BRIDGE:
            stored = next(
                item
                for item in result.stored
                if item.artifact_id == row["database_artifact_id"]
            )
            symbol = str(row["symbol"])
            restored = decode_artifact(
                artifact_type,
                stored.envelope.payload_object(),
                dependencies={"valuation": valuation_objects[symbol]},
            )
            status = f"bridge={restored.bridge_status}"
        elif artifact_type == ARTIFACT_VALUATION_RESULT:
            stored = next(
                item
                for item in result.stored
                if item.artifact_id == row["database_artifact_id"]
            )
            restored = decode_artifact(artifact_type, stored.envelope.payload_object())
            status = f"valuation={restored.status}/confidence={restored.confidence}"
        elif artifact_type == ARTIFACT_DIVIDEND_RESEARCH:
            stored = next(
                item
                for item in result.stored
                if item.artifact_id == row["database_artifact_id"]
            )
            restored = decode_artifact(artifact_type, stored.envelope.payload_object())
            status = f"cash_return={restored.cash_return_status}/action={restored.action}"
        elif artifact_type == ARTIFACT_FIXED_SAMPLE_ADMISSION:
            stored = next(
                item
                for item in result.stored
                if item.artifact_id == row["database_artifact_id"]
            )
            restored = decode_artifact(artifact_type, stored.envelope.payload_object())
            status = (
                f"orchestration={restored.engineering_orchestration_status}/"
                f"production_available={restored.production_valuation_available}/"
                f"action={restored.action}"
            )
        else:
            status = "payload_verified"
        rows.append({**row, "restored_semantic_status": status})
    return tuple(rows)

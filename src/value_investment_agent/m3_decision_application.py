"""Application orchestration that builds fail-closed M3 decision cards.

The only source accepted here is an already-frozen point-in-time M1 application
payload.  Missing portfolio data is never replaced with a synthetic capacity;
no Entry, Journal or Consistency record is invented; every card remains
``action=no_order`` and requires human review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .decision_read_model import (
    DECISION_CARD_SCHEMA,
    DecisionCard,
    DecisionCardCollection,
    DecisionCardSourceHash,
    decision_card_from_review,
)
from .investment_decision import (
    ACTION_NO_ORDER,
    DecisionArtifactReference,
    DecisionEvidenceBundle,
    MinimalPortfolioPreconditions,
    evaluate_investment_decision,
)
from .pre_decision_eligibility import pre_decision_eligibility_from_payload
from .research_artifacts import (
    canonicalize_artifact_payload,
    sha256_text,
)


RULE_VERSION = "m3-decision-v1"
INTEGRATED_RUN_ARTIFACT_TYPE = "m1_integrated_run"

# Integrated-run sections that can be hash-bound as decision evidence.
SUPPORTED_ARTIFACT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("research_gate", "gate"),
    ("human_research_approval", "human_approval"),
    ("valuation_result", "valuation"),
    ("model_validity", "model_validity"),
    ("price_bridge", "price_bridge"),
    ("price_attractiveness", "price_attractiveness"),
    ("current_research_status", "current_research_status"),
)


def _merge_refs(groups: Sequence[Sequence[Mapping[str, Any]]]) -> tuple[dict[str, Any], ...]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not isinstance(ref_id, str) or not ref_id.strip():
                raise ValueError("Decision evidence references require ids")
            current = merged.get(ref_id)
            if current is None:
                merged[ref_id] = ref
                continue
            for key, value in ref.items():
                if key in current and current[key] != value:
                    raise ValueError(f"Decision evidence id conflict: {ref_id}")
                current[key] = value
    return tuple(merged.values())


def _source_hash(
    source_key: str,
    artifact_type: str,
    artifact_id: str | None,
    payload: Mapping[str, Any],
    available_at: date | None,
) -> DecisionCardSourceHash:
    return DecisionCardSourceHash(
        source_key=source_key,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        sha256=sha256_text(canonicalize_artifact_payload(payload)),
        available_at=available_at,
    )


def _artifact_refs(
    entry: Mapping[str, Any],
    *,
    run_id: str,
    symbol: str,
    decision_as_of: date,
) -> tuple[DecisionArtifactReference, ...]:
    refs: list[DecisionArtifactReference] = []
    for artifact_type, section_key in SUPPORTED_ARTIFACT_SECTIONS:
        raw = entry.get(section_key)
        if not isinstance(raw, Mapping) or not raw:
            continue
        payload = dict(raw)
        refs.append(
            DecisionArtifactReference(
                artifact_type=artifact_type,
                artifact_id=f"{symbol}-{section_key}-{run_id}",
                sha256=sha256_text(canonicalize_artifact_payload(payload)),
                schema_version=str(payload.get("schema_version") or "m1-integrated-run-v1"),
                available_at=decision_as_of,
            )
        )
    if not refs:
        raise ValueError("Integrated run has no supported decision artifact sections")
    return tuple(refs)


@dataclass(frozen=True)
class DecisionApplicationInputFailure:
    run_id: str | None
    symbol: str | None
    error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", self.run_id)
        object.__setattr__(self, "symbol", self.symbol)
        if not self.error.strip():
            raise ValueError("Decision input failure requires an error")

    def as_policy(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "symbol": self.symbol,
            "error": self.error,
        }


def _build_card(
    entry: Mapping[str, Any],
    *,
    generated_at: datetime,
    rule_version: str,
) -> DecisionCard:
    if entry.get("action") != ACTION_NO_ORDER:
        raise ValueError("Integrated run must remain no_order")
    run_id = str(entry.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Integrated run id is required")
    predecision_raw = entry.get("pre_decision_eligibility")
    if not isinstance(predecision_raw, Mapping):
        raise ValueError("Integrated run is missing pre_decision_eligibility")
    predecision = pre_decision_eligibility_from_payload(dict(predecision_raw))
    symbol = predecision.symbol
    decision_as_of = predecision.decision_as_of
    if decision_as_of > generated_at.date():
        raise ValueError("Integrated decision date is later than the application generation date")

    bundle = DecisionEvidenceBundle(
        bundle_id=f"{symbol}-decision-bundle-{decision_as_of.isoformat()}-{rule_version}",
        symbol=symbol,
        decision_as_of=decision_as_of,
        rule_version=rule_version,
        artifact_refs=_artifact_refs(
            entry,
            run_id=run_id,
            symbol=symbol,
            decision_as_of=decision_as_of,
        ),
        evidence_refs=_merge_refs((predecision.evidence_refs,)),
    )
    review = evaluate_investment_decision(
        predecision=predecision,
        bundle=bundle,
        decision_as_of=decision_as_of,
        decision_intent=None,
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
        rule_version=rule_version,
        created_at=generated_at,
    )
    source_hashes = (
        _source_hash(
            "m1_integrated_run",
            INTEGRATED_RUN_ARTIFACT_TYPE,
            run_id,
            entry,
            decision_as_of,
        ),
        _source_hash(
            "investment_decision_review",
            "investment_decision_review",
            review.review_id,
            review.as_policy(),
            decision_as_of,
        ),
        _source_hash(
            "decision_evidence_bundle",
            "decision_evidence_bundle",
            bundle.bundle_id,
            bundle.as_policy(),
            decision_as_of,
        ),
    )
    return decision_card_from_review(
        review,
        decision_intent=None,
        source_hashes=source_hashes,
    )


def build_nonpersonal_decision_card_collection(
    integrated_runs: Sequence[Mapping[str, Any]],
    *,
    generated_at: datetime,
    source_run_id: str,
    rule_version: str = RULE_VERSION,
) -> DecisionCardCollection:
    """Build only public, negative-capable cards from frozen M1 inputs."""
    if isinstance(integrated_runs, (str, bytes)) or not isinstance(integrated_runs, Sequence):
        raise ValueError("Integrated runs must be a sequence of JSON objects")
    cards: list[DecisionCard] = []
    failures: list[DecisionApplicationInputFailure] = []
    for index, raw in enumerate(integrated_runs):
        if not isinstance(raw, Mapping):
            failures.append(
                DecisionApplicationInputFailure(
                    run_id=None,
                    symbol=None,
                    error=f"Integrated run {index} is not an object",
                )
            )
            continue
        entry = dict(raw)
        run_id = str(entry.get("run_id") or "") or None
        symbol = str(entry.get("symbol") or "") or None
        try:
            cards.append(
                _build_card(
                    entry,
                    generated_at=generated_at,
                    rule_version=rule_version,
                )
            )
        except (TypeError, ValueError) as error:
            failures.append(
                DecisionApplicationInputFailure(
                    run_id=run_id,
                    symbol=symbol,
                    error=str(error),
                )
            )
    return DecisionCardCollection(
        schema_version=DECISION_CARD_SCHEMA,
        generated_at=generated_at,
        source_run_id=source_run_id,
        cards=tuple(cards),
        input_failures=tuple(failures),
    )


def load_integrated_runs(
    root: Path,
    input_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a JSON run file without following an escaping project path."""
    root = root.resolve()
    target = input_path.resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Integrated runs path escapes project root: {input_path}")
    if not target.is_file():
        raise ValueError(f"Integrated runs path is not a file: {input_path}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError("Integrated runs file must contain a JSON array of objects")
    return payload, {
        "path": str(input_path),
        "sha256": sha256_text(target.read_bytes()),
    }

"""Pre-registered stratified coverage audit for an M2 discovery receipt.

This module is a W3 audit tool. It does not score companies, choose a sample by
outcome, or produce valuation, order, position or BUY semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CANDIDATE_CLASS_LEAD,
    CHANNELS,
    CHANNEL_QUALITY,
    DATA_PARTIAL,
    EVALUATION_BUDGET_EXCLUDED,
    _EVALUATION_STATUSES,
    DiscoveryRunReceipt,
    discovery_receipt_from_payload,
)


M2_COVERAGE_SAMPLING_SCHEMA = "m2-coverage-sampling-v1"
M2_COVERAGE_AUDIT_SCHEMA = "m2-coverage-audit-v1"
DEFAULT_SAMPLING_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "m2-coverage-sampling-v1.json"
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STRATUM_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SOURCES = {"candidate", "evaluation", "excluded_security", "legacy_set"}
_FORBIDDEN_KEYS = {
    "trade_approved",
    "target_weight",
    "position_size",
    "order_quantity",
    "proposed_entry",
    "buy",
    "sell",
    "live_eligible",
    "return_threshold",
    "backtest_return",
}


@dataclass(frozen=True)
class M2SamplingStratum:
    """One pre-registered stratum with a deterministic selection budget."""

    id: str
    source: str
    statuses: tuple[str, ...]
    channels: tuple[str, ...]
    target_per_channel: int
    minimum_population: int
    purpose: str

    def __post_init__(self) -> None:
        if not _STRATUM_ID.fullmatch(self.id):
            raise ValueError("Sampling stratum id must be a lowercase snake_case id")
        if self.source not in _SOURCES:
            raise ValueError(f"Unknown sampling source: {self.source}")
        if self.source == "evaluation" and set(self.statuses) - _EVALUATION_STATUSES:
            raise ValueError("Evaluation stratum contains an unknown status")
        if self.source != "evaluation" and self.statuses:
            raise ValueError("Only evaluation strata may register statuses")
        if self.source == "legacy_set" and self.channels:
            raise ValueError("Legacy strata cannot be channel-scoped")
        if set(self.channels) - set(CHANNELS):
            raise ValueError("Sampling stratum contains an unknown channel")
        if self.target_per_channel <= 0:
            raise ValueError("Sampling target must be positive")
        if self.minimum_population <= 0:
            raise ValueError("Sampling minimum population must be positive")
        if not self.purpose.strip():
            raise ValueError("Sampling stratum purpose is required")
        object.__setattr__(self, "statuses", tuple(self.statuses))
        object.__setattr__(self, "channels", tuple(self.channels))

    def channels_for(self) -> tuple[str, ...]:
        return self.channels if self.channels else CHANNELS

    def as_policy(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "statuses": list(self.statuses),
            "channels": list(self.channels),
            "target_per_channel": self.target_per_channel,
            "minimum_population": self.minimum_population,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class M2CoverageSamplingPolicy:
    """Versioned AC9 sampling plan pinned to one immutable receipt."""

    schema_version: str
    sampling_version: str
    as_of: date
    receipt_path: str
    receipt_sha256: str
    run_id: str
    coverage_signature: str
    candidate_signature: str
    quote_date: date
    seed: str
    methodology: Mapping[str, Any]
    strata: tuple[M2SamplingStratum, ...]

    def __post_init__(self) -> None:
        if self.schema_version != M2_COVERAGE_SAMPLING_SCHEMA:
            raise ValueError("Unknown M2 coverage sampling schema")
        if not self.sampling_version.strip():
            raise ValueError("Sampling version is required")
        if not _SHA256.fullmatch(self.receipt_sha256):
            raise ValueError("Receipt SHA-256 is invalid")
        if not _SHA256.fullmatch(self.coverage_signature):
            raise ValueError("Coverage signature is invalid")
        if not _SHA256.fullmatch(self.candidate_signature):
            raise ValueError("Candidate signature is invalid")
        if not self.run_id.strip():
            raise ValueError("Receipt run id is required")
        if not self.seed.strip():
            raise ValueError("Sampling seed is required")
        if self.quote_date > self.as_of:
            raise ValueError("Sampling quote date cannot be after sampling as_of")
        ids = [stratum.id for stratum in self.strata]
        if len(ids) != len(set(ids)):
            raise ValueError("Sampling stratum ids must be unique")
        object.__setattr__(self, "strata", tuple(self.strata))
        object.__setattr__(self, "methodology", dict(self.methodology))

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sampling_version": self.sampling_version,
            "as_of": self.as_of.isoformat(),
            "receipt": {
                "path": self.receipt_path,
                "sha256": self.receipt_sha256,
                "run_id": self.run_id,
                "coverage_signature": self.coverage_signature,
                "candidate_signature": self.candidate_signature,
                "quote_date": self.quote_date.isoformat(),
            },
            "action": ACTION_NO_ORDER,
            "seed": self.seed,
            "methodology": self.methodology,
            "strata": [stratum.as_policy() for stratum in self.strata],
        }


@dataclass(frozen=True)
class SampledEvaluation:
    stratum_id: str
    channel: str
    symbol: str
    name: str
    status: str
    reason: str
    profile_status: str
    evidence_date: str
    selection_rank: int

    def as_policy(self) -> dict[str, Any]:
        return {
            "stratum_id": self.stratum_id,
            "channel": self.channel,
            "symbol": self.symbol,
            "name": self.name,
            "status": self.status,
            "reason": self.reason,
            "profile_status": self.profile_status,
            "evidence_date": self.evidence_date,
            "selection_rank": self.selection_rank,
        }


@dataclass(frozen=True)
class SampledCandidate:
    stratum_id: str
    channel: str
    symbol: str
    name: str
    priority_tier: str
    profile_status: str
    data_status: str
    candidate_class: str
    evidence_date: str
    reasons: tuple[str, ...]
    metrics: Mapping[str, Any]
    evidence_ids: tuple[str, ...]
    selection_rank: int

    def as_policy(self) -> dict[str, Any]:
        return {
            "stratum_id": self.stratum_id,
            "channel": self.channel,
            "symbol": self.symbol,
            "name": self.name,
            "priority_tier": self.priority_tier,
            "profile_status": self.profile_status,
            "data_status": self.data_status,
            "candidate_class": self.candidate_class,
            "evidence_date": self.evidence_date,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
            "evidence_ids": list(self.evidence_ids),
            "selection_rank": self.selection_rank,
        }


@dataclass(frozen=True)
class SampledExcluded:
    stratum_id: str
    channel: str
    symbol: str
    name: str
    reason: str
    profile_status: str
    evidence_date: str
    source_list: str
    selection_rank: int

    def as_policy(self) -> dict[str, Any]:
        return {
            "stratum_id": self.stratum_id,
            "channel": self.channel,
            "symbol": self.symbol,
            "name": self.name,
            "reason": self.reason,
            "profile_status": self.profile_status,
            "evidence_date": self.evidence_date,
            "source_list": self.source_list,
            "selection_rank": self.selection_rank,
        }


@dataclass(frozen=True)
class SampledLegacy:
    stratum_id: str
    bucket: str
    symbol: str
    name: str
    channel_statuses: Mapping[str, str]
    channel_reasons: Mapping[str, str]
    selection_rank: int

    def as_policy(self) -> dict[str, Any]:
        return {
            "stratum_id": self.stratum_id,
            "bucket": self.bucket,
            "symbol": self.symbol,
            "name": self.name,
            "channel_statuses": dict(self.channel_statuses),
            "channel_reasons": dict(self.channel_reasons),
            "selection_rank": self.selection_rank,
        }


@dataclass(frozen=True)
class StratumAudit:
    stratum_id: str
    source: str
    population_count: int
    population_by_channel: Mapping[str, int]
    selected_count: int
    samples: tuple[Any, ...]

    def as_policy(self) -> dict[str, Any]:
        return {
            "stratum_id": self.stratum_id,
            "source": self.source,
            "population_count": self.population_count,
            "population_by_channel": dict(self.population_by_channel),
            "selected_count": self.selected_count,
            "samples": [sample.as_policy() for sample in self.samples],
        }


@dataclass(frozen=True)
class StructuralCheck:
    id: str
    status: str
    detail: str

    def as_policy(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class M2CoverageAudit:
    schema_version: str
    sampling_version: str
    receipt_identity: Mapping[str, Any]
    population: Mapping[str, Any]
    strata: tuple[StratumAudit, ...]
    legacy_samples: tuple[SampledLegacy, ...]
    structural_checks: tuple[StructuralCheck, ...]
    quality_empty_explanation: Mapping[str, Any]
    audit_status: str
    acceptance_status: str

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sampling_version": self.sampling_version,
            "action": ACTION_NO_ORDER,
            "receipt_identity": dict(self.receipt_identity),
            "population": dict(self.population),
            "strata": [stratum.as_policy() for stratum in self.strata],
            "legacy_samples": [sample.as_policy() for sample in self.legacy_samples],
            "structural_checks": [check.as_policy() for check in self.structural_checks],
            "quality_empty_explanation": dict(self.quality_empty_explanation),
            "audit_status": self.audit_status,
            "acceptance_status": self.acceptance_status,
        }


def _reject_execution_keys(value: object) -> None:
    if isinstance(value, dict):
        if _FORBIDDEN_KEYS & set(value):
            raise ValueError(f"Sampling policy contains execution keys: {sorted(_FORBIDDEN_KEYS & set(value))}")
        for child in value.values():
            _reject_execution_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_execution_keys(child)


def load_m2_coverage_sampling(path: Path | str = DEFAULT_SAMPLING_PATH) -> M2CoverageSamplingPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M2 coverage sampling policy must be a JSON object")
    _reject_execution_keys(payload)
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("M2 coverage sampling action must remain no_order")
    methodology = payload.get("methodology")
    if not isinstance(methodology, Mapping):
        raise ValueError("M2 coverage sampling methodology is required")
    required_methodology = {
        "selection_rule",
        "sampling_frame",
        "no_post_hoc_tuning",
        "review_scope",
    }
    if not required_methodology <= set(methodology):
        raise ValueError("M2 coverage sampling methodology is incomplete")
    receipt = payload.get("receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("M2 coverage sampling receipt binding is required")
    return M2CoverageSamplingPolicy(
        schema_version=str(payload["schema_version"]),
        sampling_version=str(payload["sampling_version"]),
        as_of=date.fromisoformat(str(payload["as_of"])),
        receipt_path=str(receipt["path"]),
        receipt_sha256=str(receipt["sha256"]),
        run_id=str(receipt["run_id"]),
        coverage_signature=str(receipt["coverage_signature"]),
        candidate_signature=str(receipt["candidate_signature"]),
        quote_date=date.fromisoformat(str(receipt["quote_date"])),
        seed=str(payload["seed"]),
        methodology=dict(methodology),
        strata=tuple(
            M2SamplingStratum(
                id=str(item["id"]),
                source=str(item["source"]),
                statuses=tuple(str(status) for status in item.get("statuses") or []),
                channels=tuple(str(channel) for channel in item.get("channels") or []),
                target_per_channel=int(item["target_per_channel"]),
                minimum_population=int(item["minimum_population"]),
                purpose=str(item["purpose"]),
            )
            for item in payload.get("strata") or []
        ),
    )


def load_pinned_receipt(
    policy: M2CoverageSamplingPolicy,
    *,
    root: Path,
) -> DiscoveryRunReceipt:
    receipt_path = (root / policy.receipt_path).resolve()
    if not receipt_path.is_relative_to(root.resolve()):
        raise ValueError("M2 receipt path escapes project root")
    data = receipt_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != policy.receipt_sha256:
        raise ValueError("M2 receipt SHA-256 does not match the pre-registered policy")
    receipt = discovery_receipt_from_payload(json.loads(data.decode("utf-8")))
    if receipt.run_id != policy.run_id:
        raise ValueError("M2 receipt run id does not match the pre-registered policy")
    if receipt.coverage_signature != policy.coverage_signature:
        raise ValueError("M2 coverage signature does not match the pre-registered policy")
    if receipt.candidate_signature != policy.candidate_signature:
        raise ValueError("M2 candidate signature does not match the pre-registered policy")
    if receipt.quote_date is None:
        raise ValueError("M2 receipt is missing quote_date")
    receipt_quote_date = date.fromisoformat(receipt.quote_date)
    if receipt.as_of != policy.as_of or receipt_quote_date != policy.quote_date:
        raise ValueError("M2 receipt date does not match the pre-registered policy")
    if receipt.action != ACTION_NO_ORDER:
        raise ValueError("M2 coverage audit cannot consume a non-no_order receipt")
    return receipt


def _selection_rank(policy: M2CoverageSamplingPolicy, *parts: object) -> str:
    text = "|".join(str(part) for part in (policy.seed, *parts))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _select(
    entries: Sequence[Any],
    *,
    count: int,
    rank: Any,
    symbol: Any | None = None,
) -> list[tuple[int, Any]]:
    symbol_key = symbol or (lambda item: item.symbol)
    ordered = sorted(entries, key=lambda item: (rank(item), symbol_key(item)))
    return [(index + 1, item) for index, item in enumerate(ordered[:count])]


def _status_counts(receipt: DiscoveryRunReceipt) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for channel, channel_result in receipt.channel_results.items():
        counts = {status: 0 for status in sorted(_EVALUATION_STATUSES)}
        for evaluation in channel_result.evaluations:
            counts[evaluation.status] = counts.get(evaluation.status, 0) + 1
        result[channel] = counts
    return result


def _evaluation_samples(
    policy: M2CoverageSamplingPolicy,
    stratum: M2SamplingStratum,
    receipt: DiscoveryRunReceipt,
) -> tuple[int, dict[str, int], tuple[SampledEvaluation, ...]]:
    selected: list[SampledEvaluation] = []
    populations: dict[str, int] = {}
    for channel in stratum.channels_for():
        entries = [
            evaluation
            for evaluation in receipt.channel_results[channel].evaluations
            if evaluation.status in stratum.statuses
        ]
        populations[channel] = len(entries)
        rank = lambda item, channel=channel: _selection_rank(
            policy, stratum.id, channel, item.symbol
        )
        selected.extend(
            SampledEvaluation(
                stratum_id=stratum.id,
                channel=channel,
                symbol=item.symbol,
                name=item.name,
                status=item.status,
                reason=item.reason,
                profile_status=item.profile_status,
                evidence_date=item.evidence_date,
                selection_rank=position,
            )
            for position, item in _select(entries, count=stratum.target_per_channel, rank=rank)
        )
    return sum(populations.values()), populations, tuple(selected)


def _candidate_samples(
    policy: M2CoverageSamplingPolicy,
    stratum: M2SamplingStratum,
    receipt: DiscoveryRunReceipt,
) -> tuple[int, dict[str, int], tuple[SampledCandidate, ...]]:
    selected: list[SampledCandidate] = []
    populations: dict[str, int] = {}
    for channel in stratum.channels_for():
        entries = list(receipt.channel_results[channel].candidates)
        populations[channel] = len(entries)
        rank = lambda item, channel=channel: _selection_rank(
            policy, stratum.id, channel, item.symbol
        )
        selected.extend(
            SampledCandidate(
                stratum_id=stratum.id,
                channel=channel,
                symbol=item.symbol,
                name=item.name,
                priority_tier=item.priority_tier,
                profile_status=item.profile_status,
                data_status=item.data_status,
                candidate_class=item.candidate_class,
                evidence_date=item.evidence_date,
                reasons=item.reasons,
                metrics=item.metrics,
                evidence_ids=tuple(ref.id for ref in item.evidence_refs),
                selection_rank=position,
            )
            for position, item in _select(entries, count=stratum.target_per_channel, rank=rank)
        )
    return sum(populations.values()), populations, tuple(selected)


def _excluded_samples(
    policy: M2CoverageSamplingPolicy,
    stratum: M2SamplingStratum,
    receipt: DiscoveryRunReceipt,
) -> tuple[int, dict[str, int], tuple[SampledExcluded, ...]]:
    selected: list[SampledExcluded] = []
    populations: dict[str, int] = {}
    for channel in stratum.channels_for():
        result = receipt.channel_results[channel]
        entries = [
            (item, "excluded") for item in result.excluded
        ] + [(item, "missing") for item in result.missing]
        populations[channel] = len(entries)
        rank = lambda pair, channel=channel: _selection_rank(
            policy, stratum.id, channel, pair[0].symbol
        )
        selected.extend(
            SampledExcluded(
                stratum_id=stratum.id,
                channel=channel,
                symbol=item.symbol,
                name=item.name,
                reason=item.reason,
                profile_status=item.profile_status,
                evidence_date=item.evidence_date,
                source_list=source_list,
                selection_rank=position,
            )
            for position, (item, source_list) in _select(
                entries,
                count=stratum.target_per_channel,
                rank=rank,
                symbol=lambda pair: pair[0].symbol,
            )
        )
    return sum(populations.values()), populations, tuple(selected)


def _legacy_samples(
    policy: M2CoverageSamplingPolicy,
    stratum: M2SamplingStratum,
    receipt: DiscoveryRunReceipt,
) -> tuple[SampledLegacy, ...]:
    legacy = set(receipt.legacy_comparison.legacy_candidates)
    new = {
        candidate.symbol
        for result in receipt.channel_results.values()
        for candidate in result.candidates
    }
    by_symbol: dict[str, list[Any]] = {}
    names: dict[str, str] = {}
    for channel in CHANNELS:
        for evaluation in receipt.channel_results[channel].evaluations:
            by_symbol.setdefault(evaluation.symbol, []).append(evaluation)
            names[evaluation.symbol] = evaluation.name
    selected: list[SampledLegacy] = []
    for bucket, symbols in (
        ("overlap", legacy & new),
        ("new_only", new - legacy),
        ("legacy_only", legacy - new),
    ):
        rank = lambda symbol, bucket=bucket: _selection_rank(
            policy, stratum.id, bucket, symbol
        )
        for position, symbol in _select(
            tuple(sorted(symbols)),
            count=stratum.target_per_channel,
            rank=rank,
            symbol=str,
        ):
            evaluations = by_symbol.get(symbol, [])
            selected.append(
                SampledLegacy(
                    stratum_id=stratum.id,
                    bucket=bucket,
                    symbol=symbol,
                    name=names.get(symbol, symbol),
                    channel_statuses={
                        evaluation.channel: evaluation.status for evaluation in evaluations
                    },
                    channel_reasons={
                        evaluation.channel: evaluation.reason for evaluation in evaluations
                    },
                    selection_rank=position,
                )
            )
    return tuple(selected)


def _check(checks: list[StructuralCheck], id_: str, passed: bool, detail: str) -> None:
    checks.append(
        StructuralCheck(id=id_, status="PASS" if passed else "FAIL", detail=detail)
    )


def _population(receipt: DiscoveryRunReceipt, status_counts: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    return {
        "universe_count": len(receipt.universe.records),
        "evaluation_count_by_channel": {
            channel: len(result.evaluations)
            for channel, result in receipt.channel_results.items()
        },
        "status_counts_by_channel": {
            channel: dict(counts) for channel, counts in status_counts.items()
        },
        "candidate_counts_by_channel": {
            channel: len(result.candidates)
            for channel, result in receipt.channel_results.items()
        },
        "verified_candidate_count": len(receipt.verified_candidate_pool()),
        "legacy": {
            "legacy_count": receipt.legacy_comparison.legacy_candidate_count,
            "new_unique_count": len({
                candidate.symbol
                for result in receipt.channel_results.values()
                for candidate in result.candidates
            }),
            "overlap_count": receipt.legacy_comparison.overlap_count,
        },
    }


def run_m2_coverage_audit(
    policy: M2CoverageSamplingPolicy,
    receipt: DiscoveryRunReceipt,
) -> M2CoverageAudit:
    status_counts = _status_counts(receipt)
    strata: list[StratumAudit] = []
    all_population_counts: dict[str, int] = {}
    checks: list[StructuralCheck] = []

    for stratum in policy.strata:
        if stratum.source == "candidate":
            population_count, populations, samples = _candidate_samples(policy, stratum, receipt)
        elif stratum.source == "evaluation":
            population_count, populations, samples = _evaluation_samples(policy, stratum, receipt)
        elif stratum.source == "excluded_security":
            population_count, populations, samples = _excluded_samples(policy, stratum, receipt)
        else:
            continue
        all_population_counts[stratum.id] = population_count
        strata.append(
            StratumAudit(
                stratum_id=stratum.id,
                source=stratum.source,
                population_count=population_count,
                population_by_channel=populations,
                selected_count=len(samples),
                samples=samples,
            )
        )

    legacy_strata = [stratum for stratum in policy.strata if stratum.source == "legacy_set"]
    legacy_samples = tuple(
        sample
        for stratum in legacy_strata
        for sample in _legacy_samples(policy, stratum, receipt)
    )
    for stratum in legacy_strata:
        legacy_sets = (
            set(receipt.legacy_comparison.legacy_candidates),
            {
                candidate.symbol
                for result in receipt.channel_results.values()
                for candidate in result.candidates
            },
        )
        population_count = sum(
            len(values)
            for values in (
                legacy_sets[0] & legacy_sets[1],
                legacy_sets[1] - legacy_sets[0],
                legacy_sets[0] - legacy_sets[1],
            )
        )
        all_population_counts[stratum.id] = population_count
        strata.append(
            StratumAudit(
                stratum_id=stratum.id,
                source=stratum.source,
                population_count=population_count,
                population_by_channel={},
                selected_count=sum(1 for item in legacy_samples if item.stratum_id == stratum.id),
                samples=tuple(item for item in legacy_samples if item.stratum_id == stratum.id),
            )
        )

    for stratum in policy.strata:
        _check(
            checks,
            f"stratum_population_{stratum.id}",
            all_population_counts.get(stratum.id, 0) >= stratum.minimum_population,
            f"{stratum.id} population={all_population_counts.get(stratum.id, 0)} "
            f"minimum={stratum.minimum_population}",
        )

    universe_count = len(receipt.universe.records)
    for channel in CHANNELS:
        result = receipt.channel_results[channel]
        _check(
            checks,
            f"universe_alignment_{channel}",
            len(result.evaluations) == universe_count,
            f"{channel} evaluations={len(result.evaluations)} universe={universe_count}",
        )
        pass_symbols = {
            evaluation.symbol
            for evaluation in result.evaluations
            if evaluation.status == "PASS"
        }
        candidate_symbols = {candidate.symbol for candidate in result.candidates}
        _check(
            checks,
            f"pass_candidate_equivalence_{channel}",
            pass_symbols == candidate_symbols,
            f"{channel} PASS={len(pass_symbols)} displayed_candidates={len(candidate_symbols)}",
        )
        budget_symbols = {
            evaluation.symbol
            for evaluation in result.evaluations
            if evaluation.status == EVALUATION_BUDGET_EXCLUDED
        }
        budget_reasons_valid = all(
            "展示预算" in evaluation.reason
            for evaluation in result.evaluations
            if evaluation.status == EVALUATION_BUDGET_EXCLUDED
        )
        _check(
            checks,
            f"budget_bookkeeping_{channel}",
            budget_reasons_valid and not (candidate_symbols & budget_symbols),
            f"{channel} displayed={len(candidate_symbols)} budget_excluded={len(budget_symbols)}",
        )

    all_candidates = [
        candidate
        for result in receipt.channel_results.values()
        for candidate in result.candidates
    ]
    _check(
        checks,
        "no_verified_candidate",
        not receipt.verified_candidate_pool()
        and all(candidate.candidate_class == CANDIDATE_CLASS_LEAD for candidate in all_candidates),
        f"displayed={len(all_candidates)} verified={len(receipt.verified_candidate_pool())}",
    )
    _check(
        checks,
        "cheap_screen_partial_semantics",
        all(
            candidate.data_status == DATA_PARTIAL
            for candidate in all_candidates
            if candidate.channel != CHANNEL_QUALITY
        ),
        "All non-Quality displayed leads must remain DATA_PARTIAL",
    )
    all_evaluations = [
        evaluation
        for result in receipt.channel_results.values()
        for evaluation in result.evaluations
    ]
    _check(
        checks,
        "evidence_date_alignment",
        all(evaluation.evidence_date == policy.quote_date.isoformat() for evaluation in all_evaluations),
        f"expected evidence_date={policy.quote_date.isoformat()}",
    )
    _check(
        checks,
        "legacy_bookkeeping",
        len(receipt.legacy_comparison.legacy_candidates)
        == receipt.legacy_comparison.legacy_candidate_count,
        "Legacy symbol list matches declared count",
    )

    quality_result = receipt.channel_results[CHANNEL_QUALITY]
    quality_explanation = {
        "displayed_candidates": len(quality_result.candidates),
        "financial_evidence_count": receipt.data_health.financial_evidence_count,
        "status_counts": dict(status_counts[CHANNEL_QUALITY]),
        "finding": (
            "Quality zero does not prove the market has no quality companies. "
            "The current snapshot has financial evidence for only "
            f"{receipt.data_health.financial_evidence_count} of "
            f"{receipt.data_health.universe_count} official securities; the remaining "
            "denominator is DATA_GAP. Zero displayed leads must therefore be read as "
            "an unresolved coverage limitation, not as an investment conclusion."
        ),
    }
    _check(
        checks,
        "quality_empty_explained",
        len(quality_result.candidates) == 0
        and status_counts[CHANNEL_QUALITY].get("DATA_GAP", 0) > 0,
        quality_explanation["finding"],
    )

    machine_passed = all(check.status == "PASS" for check in checks)
    return M2CoverageAudit(
        schema_version=M2_COVERAGE_AUDIT_SCHEMA,
        sampling_version=policy.sampling_version,
        receipt_identity={
            "run_id": receipt.run_id,
            "generated_at": receipt.generated_at.isoformat(),
            "as_of": receipt.as_of.isoformat(),
            "quote_date": receipt.quote_date,
            "coverage_signature": receipt.coverage_signature,
            "candidate_signature": receipt.candidate_signature,
            "action": receipt.action,
        },
        population=_population(receipt, status_counts),
        strata=tuple(strata),
        legacy_samples=legacy_samples,
        structural_checks=tuple(checks),
        quality_empty_explanation=quality_explanation,
        audit_status="MACHINE_CHECKS_PASS" if machine_passed else "MACHINE_CHECKS_FAILED",
        acceptance_status="AC9_REVIEW_PENDING",
    )

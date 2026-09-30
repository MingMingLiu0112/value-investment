"""Failure-isolated batch orchestration over the shared company runner.

One company cannot break the batch. Missing data becomes an explicit gap;
unsupported profiles remain unsupported; changed input fingerprints or
dependency versions are the only reasons a previous company result is rerun.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .gap_classification import (
    GapClassification,
    classify_blockers,
)
from .research_application import (
    RUN_COMPLETED,
    RUN_COMPLETED_WITH_BLOCKERS,
    RUN_UNSUPPORTED,
    CompanyResearchRunOutcome,
    ResearchApplicationService,
    ResearchRunSpec,
)
from .research_artifact_repository import (
    InMemoryResearchArtifactRepository,
    ResearchArtifactRepository,
)
from .research_artifact_codecs import ARTIFACT_SCHEMA_VERSION
from .research_artifacts import (
    ARTIFACT_BATCH_RUN_RESULT,
    SCOPE_BATCH,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
)
from .research_input import (
    build_research_run_spec,
    descriptor_from_payload,
)
from .domain.research.evidence_stop import (
    EvidenceStop,
    ResearchScheduleRequest,
    evaluate_research_schedule,
)
from .infrastructure.evidence.evidence_stop_schedule import (
    claim_research_schedule_once,
    verified_official_package_source_ids,
)
from .research_run_contract import canonical_contract_payload


BATCH_COMPLETED = "COMPLETED"
BATCH_COMPLETED_WITH_BLOCKERS = "COMPLETED_WITH_BLOCKERS"
BATCH_UNCHANGED = "UNCHANGED"
BATCH_UNSUPPORTED = "UNSUPPORTED"
BATCH_GAP = "GAP"
BATCH_FAILED = "FAILED"
BATCH_STOPPED = "BLOCKED_BY_RESEARCH_SCHEDULER"
BATCH_PARTIAL = "PARTIAL"
BATCH_STATUSES = {
    BATCH_COMPLETED,
    BATCH_COMPLETED_WITH_BLOCKERS,
    BATCH_UNCHANGED,
    BATCH_UNSUPPORTED,
    BATCH_GAP,
    BATCH_FAILED,
    BATCH_STOPPED,
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[0-9]{6}$")


def _dependency_sha256(spec: ResearchRunSpec) -> str:
    """Hash only the dependency versions that must invalidate a prior run."""

    payload = {
        "profile_id": spec.profile_id,
        "requested_model": spec.requested_model,
        "rule_version": spec.rule_version,
        "model_version": spec.model_version,
        "parser_version": spec.parser_version,
        "scan_watermark": spec.scan_watermark,
    }
    return hashlib.sha256(
        canonical_contract_payload(payload).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ResearchBatchCompanySpec:
    """One company input plus a stable fingerprint for change detection."""

    research_spec: ResearchRunSpec
    input_sha256: str | None = None
    dependency_sha256: str | None = None
    schedule_request: ResearchScheduleRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.research_spec, ResearchRunSpec):
            raise TypeError("Batch company requires a typed ResearchRunSpec")
        if self.schedule_request is not None and not isinstance(
            self.schedule_request, ResearchScheduleRequest
        ):
            raise TypeError("Batch schedule request must use the shared contract")
        if not _SYMBOL.fullmatch(self.research_spec.symbol):
            raise ValueError("Batch company symbol must contain six digits")
        if self.input_sha256 is not None and not _SHA256.fullmatch(self.input_sha256):
            raise ValueError("Batch input fingerprint must be SHA-256 hex")
        if self.schedule_request is not None and self.input_sha256 is not None:
            request_payload = {
                "symbol": self.schedule_request.symbol,
                "source_id": self.schedule_request.source_id,
                "period": self.schedule_request.period,
                "research_question_id": self.schedule_request.research_question_id,
                "blocker_id": self.schedule_request.blocker_id,
                "reopen_condition_met": self.schedule_request.reopen_condition_met,
                "new_evidence_ids": sorted(self.schedule_request.new_evidence_ids),
            }
            request_sha256 = hashlib.sha256(
                canonical_contract_payload(request_payload).encode("utf-8")
            ).hexdigest()
            combined_sha256 = hashlib.sha256(canonical_contract_payload({
                "input_sha256": self.input_sha256,
                "schedule_request_sha256": request_sha256,
            }).encode("utf-8")).hexdigest()
            object.__setattr__(self, "input_sha256", combined_sha256)
        expected_dependency_sha256 = _dependency_sha256(self.research_spec)
        if self.dependency_sha256 is None:
            object.__setattr__(self, "dependency_sha256", expected_dependency_sha256)
        elif self.dependency_sha256 != expected_dependency_sha256:
            raise ValueError(
                "Batch dependency fingerprint does not match the run spec"
            )


@dataclass(frozen=True)
class ResearchBatchInputFailure:
    """One descriptor that could not be admitted, isolated from valid inputs."""

    input_id: str
    symbol: str | None
    input_sha256: str | None
    error: str

    def __post_init__(self) -> None:
        if not self.input_id.strip():
            raise ValueError("Batch input failure id is required")
        if self.symbol is not None and not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Batch input failure symbol must contain six digits")
        if self.input_sha256 is not None and not _SHA256.fullmatch(
            self.input_sha256
        ):
            raise ValueError("Batch input failure hash must be SHA-256 hex")
        if not self.error.strip():
            raise ValueError("Batch input failure error is required")

    def as_policy(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "symbol": self.symbol,
            "input_sha256": self.input_sha256,
            "error": self.error,
            "action": "no_order",
        }


@dataclass(frozen=True)
class ResearchBatchSpec:
    """Explicit batch contract; no symbol-based policy lives here."""

    run_id: str
    rule_version: str
    companies: tuple[ResearchBatchCompanySpec, ...]
    started_at: datetime | None = None
    previous_run_id: str | None = None
    input_failures: tuple[ResearchBatchInputFailure, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("Batch run id is required")
        if not self.rule_version.strip():
            raise ValueError("Batch rule version is required")
        if not self.companies and not self.input_failures:
            raise ValueError("Batch requires at least one company or input failure")
        symbols = [item.research_spec.symbol for item in self.companies]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Batch company symbols must be unique")
        if self.started_at is not None and self.started_at.tzinfo is None:
            raise ValueError("Batch started_at must include timezone")
        if self.previous_run_id is not None:
            if not self.previous_run_id.strip():
                raise ValueError("Previous batch run id cannot be empty")
            missing = [
                item.research_spec.symbol
                for item in self.companies
                if item.input_sha256 is None
            ]
            if missing:
                raise ValueError(
                    "Incremental batch requires input fingerprints for all companies"
                )
        object.__setattr__(self, "companies", tuple(self.companies))
        object.__setattr__(self, "input_failures", tuple(self.input_failures))


@dataclass(frozen=True)
class BatchCompanyResult:
    """Isolated result for one symbol; never carries execution instructions."""

    symbol: str
    status: str
    run_id: str
    input_sha256: str | None
    blockers: tuple[str, ...]
    gaps: tuple[GapClassification, ...]
    artifact_ids: Mapping[str, str]
    dependency_sha256: str | None = None
    outcome: CompanyResearchRunOutcome | None = None
    error: str | None = None
    unchanged_from_run_id: str | None = None
    schedule_gate: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Batch result symbol must contain six digits")
        if self.status not in BATCH_STATUSES:
            raise ValueError(f"Unknown batch company status: {self.status}")
        if not self.run_id.strip():
            raise ValueError("Batch company run id is required")
        if self.input_sha256 is not None and not _SHA256.fullmatch(self.input_sha256):
            raise ValueError("Batch input fingerprint must be SHA-256 hex")
        if self.dependency_sha256 is not None and not _SHA256.fullmatch(
            self.dependency_sha256
        ):
            raise ValueError("Batch dependency fingerprint must be SHA-256 hex")
        if self.status == BATCH_UNCHANGED and not self.unchanged_from_run_id:
            raise ValueError("An unchanged result requires its source run id")
        if self.status == BATCH_FAILED and not self.error:
            raise ValueError("A failed result requires an error")
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "gaps", tuple(self.gaps))
        object.__setattr__(self, "artifact_ids", dict(self.artifact_ids))
        object.__setattr__(self, "schedule_gate", dict(self.schedule_gate))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "run_id": self.run_id,
            "input_sha256": self.input_sha256,
            "dependency_sha256": self.dependency_sha256,
            "blockers": list(self.blockers),
            "gaps": [gap.as_policy() for gap in self.gaps],
            "artifact_ids": dict(self.artifact_ids),
            "error": self.error,
            "unchanged_from_run_id": self.unchanged_from_run_id,
            "schedule_gate": dict(self.schedule_gate),
            "action": "no_order",
        }


@dataclass(frozen=True)
class ResearchBatchResult:
    """Auditable batch receipt with explicit start/end and per-company isolation."""

    run_id: str
    rule_version: str
    started_at: datetime
    finished_at: datetime
    results: tuple[BatchCompanyResult, ...]
    input_failures: tuple[ResearchBatchInputFailure, ...] = ()
    stored_artifact: StoredResearchArtifact | None = None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("Batch times must include timezone")
        if self.finished_at < self.started_at:
            raise ValueError("Batch finished_at cannot precede started_at")
        symbols = [result.symbol for result in self.results]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Batch result symbols must be unique")
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "input_failures", tuple(self.input_failures))

    @property
    def results_by_symbol(self) -> dict[str, BatchCompanyResult]:
        return {result.symbol: result for result in self.results}

    @property
    def status(self) -> str:
        if self.input_failures:
            return BATCH_PARTIAL
        if not self.results:
            return BATCH_PARTIAL
        if all(result.status == BATCH_COMPLETED for result in self.results):
            return BATCH_COMPLETED
        if all(
            result.status
            in {
                BATCH_COMPLETED,
                BATCH_COMPLETED_WITH_BLOCKERS,
                BATCH_UNCHANGED,
            }
            for result in self.results
        ):
            return BATCH_COMPLETED_WITH_BLOCKERS
        return BATCH_PARTIAL

    @property
    def evidence_refs(self) -> tuple[dict[str, Any], ...]:
        refs: list[dict[str, Any]] = []
        for result in self.results:
            for artifact_type, artifact_id in result.artifact_ids.items():
                refs.append(
                    {
                        "id": f"artifact:{result.symbol}:{artifact_type}",
                        "artifact_id": artifact_id,
                        "kind": "research_artifact",
                    }
                )
        return tuple(refs)

    def as_policy(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "rule_version": self.rule_version,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "status": self.status,
            "results": [result.as_policy() for result in self.results],
            "input_failures": [
                failure.as_policy() for failure in self.input_failures
            ],
            "action": "no_order",
        }

    @classmethod
    def from_policy(cls, payload: Mapping[str, Any]) -> ResearchBatchResult:
        started_at = _datetime(payload.get("started_at"), "started_at")
        finished_at = _datetime(payload.get("finished_at"), "finished_at")
        results = tuple(
            _company_result_from_policy(item)
            for item in payload.get("results") or []
        )
        input_failures = tuple(
            ResearchBatchInputFailure(
                input_id=str(item["input_id"]),
                symbol=item.get("symbol"),
                input_sha256=item.get("input_sha256"),
                error=str(item["error"]),
            )
            for item in payload.get("input_failures") or []
        )
        return cls(
            run_id=str(payload["run_id"]),
            rule_version=str(payload["rule_version"]),
            started_at=started_at,
            finished_at=finished_at,
            results=results,
            input_failures=input_failures,
        )


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _company_result_from_policy(payload: Mapping[str, Any]) -> BatchCompanyResult:
    gaps = tuple(
        GapClassification(
            symbol=str(payload["symbol"]),
            blocker=str(item["blocker"]),
            gap_type=str(item["type"]),
            field=item.get("field"),
            reason=str(item["reason"]),
        )
        for item in payload.get("gaps") or []
    )
    return BatchCompanyResult(
        symbol=str(payload["symbol"]),
        status=str(payload["status"]),
        run_id=str(payload["run_id"]),
        input_sha256=payload.get("input_sha256"),
        dependency_sha256=payload.get("dependency_sha256"),
        blockers=tuple(str(item) for item in payload.get("blockers") or []),
        gaps=gaps,
        artifact_ids=dict(payload.get("artifact_ids") or {}),
        error=payload.get("error"),
        unchanged_from_run_id=payload.get("unchanged_from_run_id"),
        schedule_gate=dict(payload.get("schedule_gate") or {}),
    )


def company_spec_from_descriptor_payload(
    payload: Mapping[str, Any],
    *,
    run_id: str,
) -> tuple[ResearchBatchCompanySpec | None, ResearchBatchInputFailure | None]:
    """Admit one descriptor or return an isolated failure; never raise to caller."""

    try:
        descriptor = descriptor_from_payload(payload)
        spec = build_research_run_spec(descriptor, run_id=run_id)
    except Exception as error:
        raw_symbol = payload.get("symbol") if isinstance(payload, Mapping) else None
        symbol = (
            str(raw_symbol)
            if isinstance(raw_symbol, str) and _SYMBOL.fullmatch(raw_symbol)
            else None
        )
        raw_hash = payload.get("input_sha256") if isinstance(payload, Mapping) else None
        input_sha256 = (
            str(raw_hash)
            if isinstance(raw_hash, str) and _SHA256.fullmatch(raw_hash)
            else None
        )
        raw_id = (
            payload.get("descriptor_version")
            if isinstance(payload, Mapping)
            else None
        )
        input_id = str(raw_id or symbol or "unnamed-descriptor").strip()
        return None, ResearchBatchInputFailure(
            input_id=input_id,
            symbol=symbol,
            input_sha256=input_sha256,
            error=f"{type(error).__name__}: {error}",
        )
    return (
        ResearchBatchCompanySpec(
            spec,
            descriptor.input_sha256,
        ),
        None,
    )


def build_batch_spec_from_descriptor_payloads(
    payloads: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    rule_version: str,
) -> ResearchBatchSpec:
    if not payloads:
        raise ValueError("Descriptor batch requires at least one input")
    companies: list[ResearchBatchCompanySpec] = []
    failures: list[ResearchBatchInputFailure] = []
    for payload in payloads:
        company, failure = company_spec_from_descriptor_payload(
            payload,
            run_id=run_id,
        )
        if company is not None:
            companies.append(company)
        if failure is not None:
            failures.append(failure)
    return ResearchBatchSpec(
        run_id=run_id,
        rule_version=rule_version,
        companies=tuple(companies),
        input_failures=tuple(failures),
    )


class ResearchBatchService:
    """Runs a batch through one application service and persists its receipt."""

    def __init__(
        self,
        repository: ResearchArtifactRepository | None = None,
        *,
        evidence_stops: tuple[EvidenceStop, ...] | None = None,
        evidence_root: Path | None = None,
        frozen_replay_mode: bool = False,
        application_service: ResearchApplicationService | None = None,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        if evidence_stops is None:
            raise ValueError("ResearchBatchService requires an explicit Evidence Stop policy")
        if not evidence_stops and not frozen_replay_mode:
            raise ValueError("An empty Evidence Stop policy is restricted to frozen replay")
        if frozen_replay_mode and evidence_stops:
            raise ValueError("Frozen replay cannot carry an active Evidence Stop policy")
        if any(not isinstance(stop, EvidenceStop) for stop in evidence_stops):
            raise TypeError("Evidence Stop policy must use shared EvidenceStop records")
        self.repository = repository or InMemoryResearchArtifactRepository()
        self.evidence_stops = tuple(evidence_stops)
        self.evidence_root = evidence_root
        self.frozen_replay_mode = frozen_replay_mode
        policy_payload = [asdict(stop) for stop in sorted(
            self.evidence_stops, key=lambda item: item.stop_id,
        )]
        self.evidence_stop_policy_sha256 = hashlib.sha256(
            canonical_contract_payload({"stops": policy_payload}).encode("utf-8")
        ).hexdigest()
        self.application = application_service or ResearchApplicationService(
            self.repository
        )
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def run(self, spec: ResearchBatchSpec) -> ResearchBatchResult:
        if not isinstance(spec, ResearchBatchSpec):
            raise TypeError("Batch run requires a ResearchBatchSpec")
        started_at = spec.started_at or self.now_utc()
        previous = (
            self._load_previous(spec.previous_run_id)
            if spec.previous_run_id is not None
            else None
        )
        results: list[BatchCompanyResult] = []
        for company in spec.companies:
            active_stops = tuple(
                stop for stop in self.evidence_stops
                if stop.symbol == company.research_spec.symbol
            )
            if self.frozen_replay_mode:
                schedule_gate = {
                    "allowed": True,
                    "status": "FROZEN_REPLAY_ONLY",
                    "matched_stop_ids": [],
                }
            else:
                verified_ids = frozenset()
                if (
                    company.schedule_request is not None
                    and active_stops
                    and self.evidence_root is not None
                ):
                    verified_ids = verified_official_package_source_ids(
                        self.evidence_root,
                        [asdict(source) for source in company.research_spec.input_sources],
                        company.schedule_request.new_evidence_ids,
                        symbol=company.schedule_request.symbol,
                    )
                schedule_gate = evaluate_research_schedule(
                    symbol=company.research_spec.symbol,
                    stops=self.evidence_stops,
                    request=company.schedule_request,
                    verified_evidence_ids=verified_ids,
                )
            schedule_gate["policy_sha256"] = self.evidence_stop_policy_sha256
            if not schedule_gate["allowed"]:
                results.append(BatchCompanyResult(
                    symbol=company.research_spec.symbol,
                    status=BATCH_STOPPED,
                    run_id=f"{spec.run_id}:{company.research_spec.symbol}",
                    input_sha256=company.input_sha256,
                    dependency_sha256=company.dependency_sha256,
                    blockers=(f"EVIDENCE_STOP:{schedule_gate['status']}",),
                    gaps=(),
                    artifact_ids={},
                    schedule_gate=schedule_gate,
                ))
                continue
            previous_result = (
                previous.results_by_symbol.get(company.research_spec.symbol)
                if previous is not None
                else None
            )
            if (
                previous_result is not None
                and previous.rule_version == spec.rule_version
                and previous_result.input_sha256 == company.input_sha256
                and previous_result.dependency_sha256 == company.dependency_sha256
                and previous_result.status not in {BATCH_FAILED, BATCH_STOPPED}
            ):
                results.append(
                    BatchCompanyResult(
                        symbol=company.research_spec.symbol,
                        status=BATCH_UNCHANGED,
                        run_id=previous_result.run_id,
                        input_sha256=company.input_sha256,
                        dependency_sha256=company.dependency_sha256,
                        blockers=previous_result.blockers,
                        gaps=previous_result.gaps,
                        artifact_ids=previous_result.artifact_ids,
                        unchanged_from_run_id=previous_result.run_id,
                        schedule_gate=schedule_gate,
                    )
                )
                continue
            if (
                company.schedule_request is not None
                and active_stops
                and schedule_gate.get("new_evidence_ids")
            ):
                if self.evidence_root is None:
                    schedule_gate = {
                        **schedule_gate,
                        "allowed": False,
                        "status": "BLOCKED_SCHEDULER_STORE_UNAVAILABLE",
                    }
                else:
                    request_payload = {
                        "symbol": company.schedule_request.symbol,
                        "scope_key": list(company.schedule_request.key),
                        "reopen_condition_met": company.schedule_request.reopen_condition_met,
                        "new_evidence_ids": sorted(company.schedule_request.new_evidence_ids),
                    }
                    consumption = claim_research_schedule_once(
                        root=self.evidence_root,
                        request=company.schedule_request,
                        decision=schedule_gate,
                        ledger_sha256=self.evidence_stop_policy_sha256,
                        request_sha256=hashlib.sha256(
                            canonical_contract_payload(request_payload).encode("utf-8")
                        ).hexdigest(),
                    )
                    schedule_gate["consumption"] = consumption
                    if not consumption["created"]:
                        schedule_gate = {
                            **schedule_gate,
                            "allowed": False,
                            "status": "BLOCKED_EVIDENCE_ALREADY_CONSUMED",
                        }
                if not schedule_gate["allowed"]:
                    results.append(BatchCompanyResult(
                        symbol=company.research_spec.symbol,
                        status=BATCH_STOPPED,
                        run_id=f"{spec.run_id}:{company.research_spec.symbol}",
                        input_sha256=company.input_sha256,
                        dependency_sha256=company.dependency_sha256,
                        blockers=(f"EVIDENCE_STOP:{schedule_gate['status']}",),
                        gaps=(),
                        artifact_ids={},
                        schedule_gate=schedule_gate,
                    ))
                    continue
            results.append(self._run_company(spec.run_id, company, schedule_gate))

        finished_at = self.now_utc()
        batch_result = ResearchBatchResult(
            run_id=spec.run_id,
            rule_version=spec.rule_version,
            started_at=started_at,
            finished_at=finished_at,
            results=tuple(results),
            input_failures=tuple(spec.input_failures),
        )
        stored = self._persist(batch_result)
        object.__setattr__(batch_result, "stored_artifact", stored)
        return batch_result

    def _run_company(
        self,
        batch_run_id: str,
        company: ResearchBatchCompanySpec,
        schedule_gate: Mapping[str, Any],
    ) -> BatchCompanyResult:
        symbol = company.research_spec.symbol
        company_run_id = f"{batch_run_id}:{symbol}"
        run_spec = replace(company.research_spec, run_id=company_run_id)
        try:
            outcome = self.application.run_company_research(run_spec)
        except Exception as error:
            return BatchCompanyResult(
                symbol=symbol,
                status=BATCH_FAILED,
                run_id=company_run_id,
                input_sha256=company.input_sha256,
                dependency_sha256=company.dependency_sha256,
                blockers=(f"{type(error).__name__}:{error}",),
                gaps=(),
                artifact_ids={},
                error=f"{type(error).__name__}: {error}",
                schedule_gate=schedule_gate,
            )
        return self._map_outcome(company, company_run_id, outcome, schedule_gate)

    @staticmethod
    def _map_outcome(
        company: ResearchBatchCompanySpec,
        company_run_id: str,
        outcome: CompanyResearchRunOutcome,
        schedule_gate: Mapping[str, Any],
    ) -> BatchCompanyResult:
        gaps = classify_blockers(outcome.symbol, list(outcome.blockers))
        if outcome.status == RUN_UNSUPPORTED:
            status = BATCH_UNSUPPORTED
        elif outcome.valuation is not None and outcome.valuation.status == "not_ready":
            status = BATCH_GAP
        elif outcome.status == RUN_COMPLETED:
            status = BATCH_COMPLETED
        else:
            status = BATCH_COMPLETED_WITH_BLOCKERS
        artifact_ids = {
            stored.envelope.identity.artifact_type: stored.artifact_id
            for stored in outcome.stored_artifacts
        }
        return BatchCompanyResult(
            symbol=outcome.symbol,
            status=status,
            run_id=company_run_id,
            input_sha256=company.input_sha256,
            dependency_sha256=company.dependency_sha256,
            blockers=outcome.blockers,
            gaps=tuple(gaps),
            artifact_ids=artifact_ids,
            outcome=outcome,
            schedule_gate=schedule_gate,
        )

    def _load_previous(self, run_id: str) -> ResearchBatchResult | None:
        try:
            stored = self.repository.load_latest(
                SCOPE_BATCH,
                run_id,
                ARTIFACT_BATCH_RUN_RESULT,
            )
        except KeyError:
            return None
        payload = stored.envelope.payload_object()
        result = ResearchBatchResult.from_policy(payload)
        object.__setattr__(result, "stored_artifact", stored)
        return result

    def _persist(
        self,
        result: ResearchBatchResult,
    ) -> StoredResearchArtifact:
        identity = ResearchArtifactIdentity(
            scope_type=SCOPE_BATCH,
            scope_key=result.run_id,
            artifact_type=ARTIFACT_BATCH_RUN_RESULT,
            schema_version=ARTIFACT_SCHEMA_VERSION,
            as_of=None,
            available_at=result.finished_at,
        )
        envelope = ResearchArtifactEnvelope.build(
            identity=identity,
            payload=result.as_policy(),
            evidence_refs=result.evidence_refs,
            run_id=result.run_id,
        )
        return self.repository.save(envelope)

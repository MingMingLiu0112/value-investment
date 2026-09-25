"""Validate external evidence for strict contemporaneous-rule PIT.

The audit never proves a historical rule by itself. It only converts an
explicit user-provided evidence packet into a validated
``CONTEMPORANEOUS_RULE`` binding when the evidence is dated before the replay
date and its local artifact hash matches. Missing evidence remains
``NOT_PROVEN``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .m3_historical_research_replay import (
    ACTION_NO_ORDER,
    RULE_REGISTRATION_CONTEMPORANEOUS,
    RULE_REGISTRATION_EVIDENCE_KINDS,
    HistoricalEvidenceReference,
    HistoricalRuleBinding,
)
from .application.historical_validation import (
    StrictPitConsumerBlocked,
    enforce_strict_pit_consumption,
)


SCHEMA_VERSION = "m3-strict-pit-evidence-audit-v1"
CANDIDATE_SCHEMA_VERSION = "m3-strict-pit-evidence-candidate-v1"

NOT_PROVEN = "NOT_PROVEN"
EVIDENCE_VALID = "EVIDENCE_VALID"
FAILED = "FAILED"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return text


def _datetime(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _date(value: object, field: str) -> date:
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field} must be an ISO-8601 date") from error
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


@dataclass(frozen=True)
class StrictPitEvidenceCandidate:
    """One independently dated rule-registration artifact."""

    evidence_id: str
    evidence_kind: str
    path: str
    sha256: str
    source_url: str
    available_at: datetime
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _required_text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "evidence_kind", _required_text(self.evidence_kind, "evidence_kind"))
        if self.evidence_kind not in RULE_REGISTRATION_EVIDENCE_KINDS:
            raise ValueError("Unsupported rule registration evidence kind")
        object.__setattr__(self, "path", _required_text(self.path, "path"))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))
        object.__setattr__(self, "source_url", _required_text(self.source_url, "source_url"))
        object.__setattr__(self, "available_at", _datetime(self.available_at, "available_at"))
        object.__setattr__(self, "notes", str(self.notes).strip())

    def as_policy(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_kind": self.evidence_kind,
            "path": self.path,
            "sha256": self.sha256,
            "source_url": self.source_url,
            "available_at": self.available_at.isoformat(),
            "notes": self.notes,
        }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _load_replay(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_version") != "m3-historical-research-replay-v1":
        raise ValueError("Unsupported historical replay schema")
    if payload.get("namespace") != "HISTORICAL_RESEARCH_REPLAY":
        raise ValueError("Historical replay namespace is required")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("Historical replay must remain no_order")
    return payload


def load_candidate(path: Path) -> tuple[StrictPitEvidenceCandidate, ...]:
    payload = _load_json(path)
    if payload.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise ValueError("Unsupported strict PIT evidence candidate schema")
    rule_version = _required_text(payload.get("rule_version"), "rule_version")
    replay_id = _required_text(payload.get("replay_id"), "replay_id")
    replay_date = _date(payload.get("replay_date"), "replay_date")
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("evidence must contain at least one artifact")
    evidence: list[StrictPitEvidenceCandidate] = []
    seen: set[str] = set()
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            raise ValueError("evidence entries must be JSON objects")
        item = StrictPitEvidenceCandidate(
            evidence_id=str(raw.get("evidence_id") or raw.get("id") or ""),
            evidence_kind=str(raw.get("evidence_kind") or raw.get("kind") or ""),
            path=str(raw.get("path") or ""),
            sha256=str(raw.get("sha256") or ""),
            source_url=str(raw.get("source_url") or ""),
            available_at=raw.get("available_at") or "",
            notes=str(raw.get("notes") or ""),
        )
        if item.evidence_id in seen:
            raise ValueError(f"Duplicate evidence id: {item.evidence_id}")
        seen.add(item.evidence_id)
        evidence.append(item)
    return tuple(evidence)


def _inside(root: Path, relative: str, field: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"{field} escapes the project root")
    return target


def _binding_from_replay(
    replay: Mapping[str, Any],
    evidence: Sequence[StrictPitEvidenceCandidate],
    root: Path,
) -> HistoricalRuleBinding:
    rule = replay.get("rule")
    if not isinstance(rule, Mapping):
        raise ValueError("Historical replay is missing its rule binding")
    rule_version = _required_text(rule.get("rule_version"), "rule.rule_version")
    refs: list[HistoricalEvidenceReference] = []
    for item in evidence:
        local_path = _inside(root, item.path, "evidence.path")
        if not local_path.is_file():
            raise ValueError(f"Rule evidence file does not exist: {item.path}")
        actual = _digest(local_path)
        if actual != item.sha256:
            raise ValueError(f"Rule evidence hash mismatch: {item.evidence_id}")
        refs.append(
            HistoricalEvidenceReference(
                ref_id=item.evidence_id,
                kind=item.evidence_kind,
                path=item.path,
                sha256=item.sha256,
                source_url=item.source_url,
                available_at=item.available_at,
                role="contemporaneous rule registration evidence",
                notes=item.notes,
            )
        )
    registered_at = max(item.available_at for item in evidence)
    return HistoricalRuleBinding(
        rule_version=rule_version,
        model_scope=_required_text(rule.get("model_scope"), "rule.model_scope"),
        registered_at=registered_at,
        rule_registration_status=RULE_REGISTRATION_CONTEMPORANEOUS,
        entry_margin=Decimal(str(rule.get("entry_margin"))),
        research_quantity=int(rule.get("research_quantity")),
        exit_rule=_required_text(rule.get("exit_rule"), "rule.exit_rule"),
        registration_evidence=tuple(refs),
    )


def audit(
    root: Path,
    replay_path: Path,
    candidate_path: Path | None = None,
    *,
    pit_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Audit a strict-PIT evidence packet against a frozen replay."""
    root = root.resolve()
    replay_path = replay_path.resolve()
    if not replay_path.is_file():
        raise ValueError(f"Historical replay does not exist: {replay_path}")
    replay_input_sha256 = _digest(replay_path)
    replay = _load_replay(replay_path)
    replay_meta = {
        "replay_id": replay.get("replay_id"),
        "replay_date": replay.get("replay_date"),
        "symbol": replay.get("symbol"),
        "rule_version": (replay.get("rule") or {}).get("rule_version"),
        "rule_registration_status": (replay.get("rule") or {}).get("rule_registration_status"),
        "future_rule_version_used": replay.get("future_rule_version_used"),
    }
    if candidate_path is None or not candidate_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "action": ACTION_NO_ORDER,
            "status": NOT_PROVEN,
            "strict_contemporaneous_rule_pit": NOT_PROVEN,
            "replay": replay_meta,
            "candidate": None,
            "checks": [],
            "required_input": {
                "rule_version": replay_meta["rule_version"],
                "replay_id": replay_meta["replay_id"],
                "replay_date": replay_meta["replay_date"],
                "evidence_kinds": sorted(RULE_REGISTRATION_EVIDENCE_KINDS),
            },
            "next_action": "提供早于 replay_date 且带可核验时间、URL 和 SHA-256 的规则登记证据",
        }

    candidate_path = candidate_path.resolve()
    try:
        evidence = load_candidate(candidate_path)
        replay_date = _date(replay_meta["replay_date"], "replay_date")
        candidate_policy = _load_json(candidate_path)
        candidate_rule_version = _required_text(
            candidate_policy.get("rule_version"),
            "rule_version",
        )
        candidate_replay_id = _required_text(
            candidate_policy.get("replay_id"),
            "replay_id",
        )
        if candidate_rule_version != replay_meta["rule_version"]:
            raise ValueError("Candidate rule version does not match the replay")
        if candidate_replay_id != replay_meta["replay_id"]:
            raise ValueError("Candidate replay id does not match the replay")
        if any(item.available_at.date() > replay_date for item in evidence):
            raise ValueError("Rule evidence cannot postdate the replay date")
        binding = _binding_from_replay(replay, evidence, root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "action": ACTION_NO_ORDER,
            "status": FAILED,
            "strict_contemporaneous_rule_pit": NOT_PROVEN,
            "replay": replay_meta,
            "candidate": None,
            "checks": [
                {
                    "check": "candidate_evidence_validation",
                    "status": FAILED,
                    "detail": str(error),
                }
            ],
            "required_input": {
                "rule_version": replay_meta["rule_version"],
                "replay_id": replay_meta["replay_id"],
                "replay_date": replay_meta["replay_date"],
                "evidence_kinds": sorted(RULE_REGISTRATION_EVIDENCE_KINDS),
            },
            "next_action": "修正候选证据中的规则身份、时间、路径或 SHA-256 后重新审计",
        }
    checks = [
        {
            "check": "rule_version_matches_replay",
            "status": "PASS",
            "detail": candidate_rule_version,
        },
        {
            "check": "replay_id_matches_replay",
            "status": "PASS",
            "detail": candidate_replay_id,
        },
        {
            "check": "evidence_precedes_replay_date",
            "status": "PASS",
            "detail": [item.available_at.isoformat() for item in evidence],
        },
        {
            "check": "local_artifact_hashes_match",
            "status": "PASS",
            "detail": [item.sha256 for item in evidence],
        },
        {
            "check": "contemporaneous_binding_constructs",
            "status": "PASS",
            "detail": binding.as_policy(),
        },
    ]
    try:
        verified = enforce_strict_pit_consumption(
            root,
            subject_path=replay_path,
            manifest_path=pit_manifest_path,
        )
        if verified.subject_sha256 != replay_input_sha256:
            raise StrictPitConsumerBlocked(
                "replay bytes changed between evidence binding and consumer enforcement"
            )
    except StrictPitConsumerBlocked as error:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "action": ACTION_NO_ORDER,
            "status": NOT_PROVEN,
            "strict_contemporaneous_rule_pit": NOT_PROVEN,
            "replay": replay_meta,
            "candidate": [item.as_policy() for item in evidence],
            "checks": checks
            + [
                {
                    "check": "strict_pit_consumer_enforcement",
                    "status": NOT_PROVEN,
                    "detail": str(error),
                }
            ],
            "required_input": {
                "verifier": "pit-conformance-verifier-v2",
                "subject": str(replay_path),
                "manifest": str(pit_manifest_path) if pit_manifest_path else None,
            },
            "next_action": (
                "先让 replay 和独立 v2 manifest 通过 pit-conformance-verifier-v2；"
                "未通过前不得把候选证据升级为 strict contemporaneous binding"
            ),
            "consumer_enforcement": {
                "status": "BLOCKED",
                "strict_pit_admitted": False,
                "verifier_result": error.verifier_result,
            },
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": ACTION_NO_ORDER,
        "status": EVIDENCE_VALID,
        "strict_contemporaneous_rule_pit": "EVIDENCE_VALID_FOR_CONTEMPORANEOUS_BINDING",
        "replay": replay_meta,
        "candidate": [item.as_policy() for item in evidence],
        "checks": checks,
        "required_input": {},
        "consumer_enforcement": verified.as_receipt(),
        "next_action": "以该绑定重建 HistoricalResearchReplay，并把 future_rule_version_used 设为 false",
    }

"""Typed, non-admitted outputs from bounded research assistants."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import re
from zoneinfo import ZoneInfo


class AgentRole(str, Enum):
    FUNDAMENTAL = "FUNDAMENTAL"
    COUNTER_EVIDENCE = "COUNTER_EVIDENCE"
    EVENT = "EVENT"


class FindingStatus(str, Enum):
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class AgentFinding:
    finding_id: str
    symbol: str
    research_as_of: date
    agent_role: AgentRole
    claim: str
    finding_type: str
    supporting_evidence_refs: tuple[str, ...]
    counter_evidence_refs: tuple[str, ...]
    source_available_at: datetime
    research_input_fingerprint: str
    model_id: str
    prompt_version: str
    confidence: str
    verification_status: FindingStatus
    affected_research_dimensions: tuple[str, ...]
    proposed_follow_up: str
    created_at: datetime
    action: str = "no_order"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Finding requires a six-digit symbol")
        if not re.fullmatch(r"[0-9a-f]{64}", self.research_input_fingerprint):
            raise ValueError("Finding requires a bound input fingerprint")
        if self.source_available_at.utcoffset() is None or self.created_at.utcoffset() is None:
            raise ValueError("Finding timestamps require explicit timezone")
        if self.source_available_at.astimezone(ZoneInfo("Asia/Shanghai")).date() > self.research_as_of:
            raise ValueError("Finding cannot use future evidence")
        if self.created_at < self.source_available_at:
            raise ValueError("Finding cannot predate its evidence")
        if self.finding_type not in {"FACT_CANDIDATE", "INTERPRETATION", "RESEARCH_QUESTION"}:
            raise ValueError("Unknown finding type")
        if self.confidence not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("Unknown finding confidence")
        if self.verification_status != FindingStatus.PENDING_HUMAN_REVIEW:
            raise ValueError("An agent cannot approve or reject its own finding")
        if not self.supporting_evidence_refs or len(set(self.supporting_evidence_refs)) != len(self.supporting_evidence_refs):
            raise ValueError("Finding requires distinct source references")
        if not all((self.finding_id, self.claim.strip(), self.model_id.strip(),
                    self.prompt_version.strip(), self.proposed_follow_up.strip(),
                    self.affected_research_dimensions)):
            raise ValueError("Finding explanation and provenance are required")
        if len(self.claim) > 1200 or self.action != "no_order":
            raise ValueError("Finding exceeds scope or attempts an order")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "agent-finding-v1",
            "finding_id": self.finding_id,
            "symbol": self.symbol,
            "research_as_of": self.research_as_of.isoformat(),
            "agent_role": self.agent_role.value,
            "claim": self.claim,
            "finding_type": self.finding_type,
            "supporting_evidence_refs": list(self.supporting_evidence_refs),
            "counter_evidence_refs": list(self.counter_evidence_refs),
            "source_available_at": self.source_available_at.isoformat(),
            "research_input_fingerprint": self.research_input_fingerprint,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "confidence": self.confidence,
            "verification_status": self.verification_status.value,
            "affected_research_dimensions": list(self.affected_research_dimensions),
            "proposed_follow_up": self.proposed_follow_up,
            "created_at": self.created_at.isoformat(),
            "action": self.action,
        }

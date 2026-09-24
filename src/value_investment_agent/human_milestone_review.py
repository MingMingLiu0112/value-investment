"""Versioned append-only human milestone review receipts.

Machine audits cannot sign product checkpoints. These receipts record exactly
the narrow conclusions a human reviewer supplied, keep them hash-bound, and
never turn a sub-item approval into an overall milestone approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER


HUMAN_MILESTONE_RECEIPT_SCHEMA = "human-milestone-review-receipt-v1"
M2_CHECKPOINT_A_V2_PACKET_SCHEMA = "m2-checkpoint-a-human-resubmission-v2"

_SYMBOL = re.compile(r"^[0-9]{6}$")
_ANNOUNCEMENT_ID = re.compile(r"^[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

M5_MATERIALITY_DECISIONS = frozenset(
    {
        "NOT_MATERIAL",
        "MATERIAL_SUPPORTING_EVIDENCE",
        "MATERIAL_ALREADY_INCORPORATED",
        "MATERIAL_REQUIRES_RECALCULATION",
        "MATERIAL_RISK_MONITOR",
        "DUPLICATE_OR_DERIVED",
        "REQUIRES_DECOMPOSITION",
    }
)

REQUIRED_DECISION_KEYS = (
    "M2_CHECKPOINT_A",
    "M3_NEGATIVE_CARDS",
    "M3_CHECKPOINT_B",
    "M5_1225578520",
    "M7_SEMANTIC_STRUCTURE",
    "M4_PRIVATE_INPUT",
    "M6_AUTHORIZATION",
    "M7_FINAL_UX",
)

DECISION_VALUES = {
    "M2_CHECKPOINT_A": {
        "NOT_APPROVED_PENDING_VERIFICATION_V2",
        "HUMAN_PASS",
    },
    "M3_NEGATIVE_CARDS": {"PASS"},
    "M3_CHECKPOINT_B": {"PARTIAL_NOT_APPROVED", "PARTIAL"},
    "M5_1225578520": M5_MATERIALITY_DECISIONS,
    "M7_SEMANTIC_STRUCTURE": {"PASS"},
    "M4_PRIVATE_INPUT": {"PENDING", "PENDING_USER_PRIVATE_INPUT"},
    "M6_AUTHORIZATION": {"PENDING", "NOT_YET"},
    "M7_FINAL_UX": {"PENDING"},
}

SUPPLEMENTAL_DECISION_VALUES = {
    "M3_NEGATIVE_CARD_HUMAN_REVIEW": {"PASS"},
    "M3_HUMAN_UNDERSTANDABILITY": {"PASS"},
    "M3_NO_FALSE_BUY_ADD": {"PASS"},
    "M3_BLOCKER": {"STRICT_CONTEMPORANEOUS_RULE_PIT_NOT_PROVEN"},
    "M4_PERSONALIZED_ACCEPTANCE": {"PENDING_USER_PRIVATE_INPUT"},
    "M6_PRODUCTION_AUTHORIZATION": {"NOT_YET"},
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return text


def canonical_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class M5HumanMaterialityBinding:
    symbol: str
    announcement_id: str
    human_decision: str
    pdf_path: str
    pdf_sha256: str
    reviewed_at: date

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("M5 binding symbol must contain six digits")
        if not _ANNOUNCEMENT_ID.fullmatch(self.announcement_id):
            raise ValueError("M5 binding announcement id must contain digits only")
        object.__setattr__(
            self,
            "human_decision",
            _required_text(self.human_decision, "human_decision"),
        )
        if self.human_decision not in M5_MATERIALITY_DECISIONS:
            raise ValueError("M5 binding has an unknown materiality decision")
        object.__setattr__(self, "pdf_path", _required_text(self.pdf_path, "pdf_path"))
        object.__setattr__(self, "pdf_sha256", _sha256(self.pdf_sha256, "pdf_sha256"))
        if not isinstance(self.reviewed_at, date):
            raise ValueError("M5 binding reviewed_at must be a date")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "announcement_id": self.announcement_id,
            "human_decision": self.human_decision,
            "pdf_path": self.pdf_path,
            "pdf_sha256": self.pdf_sha256,
            "reviewed_at": self.reviewed_at.isoformat(),
        }


@dataclass(frozen=True)
class HumanMilestoneReviewReceipt:
    receipt_id: str
    sequence: int
    reviewed_at: date
    review_scope: str
    decisions: Mapping[str, str]
    m5_bindings: Sequence[M5HumanMaterialityBinding] = ()
    supplemental_decisions: Mapping[str, str] = field(default_factory=dict)
    previous_receipt_sha256: str | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", _required_text(self.receipt_id, "receipt_id"))
        if self.sequence < 1:
            raise ValueError("Human milestone receipt sequence must be positive")
        if not isinstance(self.reviewed_at, date):
            raise ValueError("Human milestone receipt reviewed_at must be a date")
        object.__setattr__(self, "review_scope", _required_text(self.review_scope, "review_scope"))
        if set(self.decisions) != set(REQUIRED_DECISION_KEYS):
            raise ValueError(
                "Human milestone receipt decisions must contain exactly "
                + ", ".join(REQUIRED_DECISION_KEYS)
            )
        normalized_decisions: dict[str, str] = {}
        for key, allowed in DECISION_VALUES.items():
            value = _required_text(self.decisions.get(key), key)
            if value not in allowed:
                raise ValueError(f"Unknown human milestone decision for {key}: {value}")
            normalized_decisions[key] = value
        object.__setattr__(self, "decisions", normalized_decisions)

        supplemental = dict(self.supplemental_decisions)
        unknown_supplemental = set(supplemental) - set(SUPPLEMENTAL_DECISION_VALUES)
        if unknown_supplemental:
            raise ValueError(
                "Unknown supplemental human milestone decisions: "
                + ", ".join(sorted(unknown_supplemental))
            )
        normalized_supplemental: dict[str, str] = {}
        for key, allowed in SUPPLEMENTAL_DECISION_VALUES.items():
            if key not in supplemental:
                continue
            value = _required_text(supplemental[key], key)
            if value not in allowed:
                raise ValueError(
                    f"Unknown supplemental human milestone decision for {key}: {value}"
                )
            normalized_supplemental[key] = value
        object.__setattr__(self, "supplemental_decisions", normalized_supplemental)

        bindings = tuple(self.m5_bindings)
        if len({item.announcement_id for item in bindings}) != len(bindings):
            raise ValueError("Human milestone receipt has duplicate M5 bindings")
        object.__setattr__(self, "m5_bindings", bindings)
        if self.previous_receipt_sha256 is not None:
            object.__setattr__(
                self,
                "previous_receipt_sha256",
                _sha256(self.previous_receipt_sha256, "previous_receipt_sha256"),
            )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Human milestone receipt must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "schema_version": HUMAN_MILESTONE_RECEIPT_SCHEMA,
            "receipt_id": self.receipt_id,
            "sequence": self.sequence,
            "reviewed_at": self.reviewed_at.isoformat(),
            "review_scope": self.review_scope,
            "decisions": dict(self.decisions),
            "m5_bindings": [item.as_policy() for item in self.m5_bindings],
            "previous_receipt_sha256": self.previous_receipt_sha256,
            "action": self.action,
        }
        if self.supplemental_decisions:
            payload["supplemental_decisions"] = dict(self.supplemental_decisions)
        return payload

    def sha256(self) -> str:
        return canonical_digest(self.as_policy())

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_human_milestone_receipt(path: Path) -> HumanMilestoneReviewReceipt:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Human milestone receipt must be a JSON object")
    if payload.get("schema_version") != HUMAN_MILESTONE_RECEIPT_SCHEMA:
        raise ValueError("Unsupported human milestone receipt schema")
    bindings = tuple(
        M5HumanMaterialityBinding(
            symbol=item["symbol"],
            announcement_id=item["announcement_id"],
            human_decision=item["human_decision"],
            pdf_path=item["pdf_path"],
            pdf_sha256=item["pdf_sha256"],
            reviewed_at=date.fromisoformat(item["reviewed_at"]),
        )
        for item in payload.get("m5_bindings") or []
    )
    return HumanMilestoneReviewReceipt(
        receipt_id=payload["receipt_id"],
        sequence=int(payload["sequence"]),
        reviewed_at=date.fromisoformat(payload["reviewed_at"]),
        review_scope=payload["review_scope"],
        decisions=payload["decisions"],
        m5_bindings=bindings,
        supplemental_decisions=payload.get("supplemental_decisions") or {},
        previous_receipt_sha256=payload.get("previous_receipt_sha256"),
        action=payload.get("action", ACTION_NO_ORDER),
    )


def write_human_milestone_receipt(
    receipt: HumanMilestoneReviewReceipt,
    output_dir: Path,
    previous_receipt: Path | None = None,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "receipt.json"
    if target.exists():
        raise ValueError(f"Human milestone receipt already exists: {target}")
    if previous_receipt is not None:
        previous_digest = hashlib.sha256(previous_receipt.read_bytes()).hexdigest()
        if receipt.previous_receipt_sha256 != previous_digest:
            raise ValueError("Human milestone receipt does not bind its predecessor")
        previous = load_human_milestone_receipt(previous_receipt)
        if previous.sequence + 1 != receipt.sequence:
            raise ValueError("Human milestone receipt sequence is not append-only")
    target.write_text(receipt.to_json(), encoding="utf-8")
    return {
        "path": str(target.resolve()),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }

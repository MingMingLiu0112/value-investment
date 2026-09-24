"""Point-in-time M3 research replay from a frozen historical experiment.

This namespace is deliberately distinct from ACTUAL and SIMULATED. It re-runs
one historical research signal through the current fail-closed decision
vocabulary without claiming the source was a valuation, a trade, or a
contemporaneously registered rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER


REPLAY_SCHEMA = "m3-historical-research-replay-v1"
REPLAY_NAMESPACE = "HISTORICAL_RESEARCH_REPLAY"
CN_TZ = timezone(timedelta(hours=8))

RULE_REGISTRATION_CONTEMPORANEOUS = "CONTEMPORANEOUS_RULE"
RULE_REGISTRATION_RETROSPECTIVE = "RETROSPECTIVE_RESEARCH_EXTENSION"
RULE_REGISTRATION_STATUSES = frozenset(
    {
        RULE_REGISTRATION_CONTEMPORANEOUS,
        RULE_REGISTRATION_RETROSPECTIVE,
    }
)

RULE_REGISTRATION_EVIDENCE_KINDS = frozenset(
    {
        "archived_document",
        "publication",
        "source_commit",
        "versioned_file",
    }
)

OUTCOME_WAIT = "WAIT"
OUTCOMES = frozenset(
    {
        "BUY_REVIEW",
        OUTCOME_WAIT,
        "HOLD",
        "REDUCE",
        "EXIT",
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return parsed


def _normalize_refs(refs: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Historical replay evidence requires named references")
    return normalized


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HistoricalEvidenceReference:
    ref_id: str
    kind: str
    path: str
    sha256: str
    source_url: str
    available_at: datetime
    role: str
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", _required_text(self.ref_id, "ref_id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "path", _required_text(self.path, "path"))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "sha256"))
        object.__setattr__(
            self, "source_url", _required_text(self.source_url, "source_url")
        )
        object.__setattr__(
            self, "available_at", _datetime(self.available_at, "available_at")
        )
        object.__setattr__(self, "role", _required_text(self.role, "role"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "id": self.ref_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "source_url": self.source_url,
            "available_at": self.available_at.isoformat(),
            "role": self.role,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ThenKnownFinancialFacts:
    symbol: str
    period_label: str
    source_id: str
    published_at: datetime
    parent_profit_cny: Decimal
    ending_issued_shares: Decimal
    reported_basic_eps: Decimal
    source_ref: HistoricalEvidenceReference

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Historical facts symbol must contain six digits")
        object.__setattr__(
            self, "period_label", _required_text(self.period_label, "period_label")
        )
        object.__setattr__(self, "source_id", _required_text(self.source_id, "source_id"))
        object.__setattr__(
            self, "published_at", _datetime(self.published_at, "published_at")
        )
        object.__setattr__(
            self, "parent_profit_cny", _decimal(self.parent_profit_cny, "parent_profit_cny")
        )
        object.__setattr__(
            self,
            "ending_issued_shares",
            _decimal(self.ending_issued_shares, "ending_issued_shares"),
        )
        object.__setattr__(
            self, "reported_basic_eps", _decimal(self.reported_basic_eps, "reported_basic_eps")
        )
        if self.source_ref.kind != "annual_filing":
            raise ValueError("Financial facts must reference an annual filing")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "period_label": self.period_label,
            "source_id": self.source_id,
            "published_at": self.published_at.isoformat(),
            "parent_profit_cny": str(self.parent_profit_cny),
            "ending_issued_shares": str(self.ending_issued_shares),
            "reported_basic_eps": str(self.reported_basic_eps),
            "source_ref": self.source_ref.as_policy(),
        }


@dataclass(frozen=True)
class ThenKnownQuote:
    symbol: str
    quote_date: date
    close_cny: Decimal
    source_ref: HistoricalEvidenceReference

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Historical quote symbol must contain six digits")
        object.__setattr__(self, "quote_date", _date(self.quote_date, "quote_date"))
        object.__setattr__(self, "close_cny", _decimal(self.close_cny, "close_cny"))
        if self.source_ref.kind != "prices":
            raise ValueError("Historical quote must reference a price file")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quote_date": self.quote_date.isoformat(),
            "close_cny": str(self.close_cny),
            "source_ref": self.source_ref.as_policy(),
        }


@dataclass(frozen=True)
class HistoricalRuleBinding:
    rule_version: str
    model_scope: str
    registered_at: datetime
    rule_registration_status: str
    entry_margin: Decimal
    research_quantity: int
    exit_rule: str
    registration_evidence: tuple[HistoricalEvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "rule_version", _required_text(self.rule_version, "rule_version")
        )
        object.__setattr__(
            self, "model_scope", _required_text(self.model_scope, "model_scope")
        )
        object.__setattr__(
            self, "registered_at", _datetime(self.registered_at, "registered_at")
        )
        object.__setattr__(
            self,
            "rule_registration_status",
            _required_text(
                self.rule_registration_status,
                "rule_registration_status",
            ),
        )
        if self.rule_registration_status not in RULE_REGISTRATION_STATUSES:
            raise ValueError("Unknown historical rule registration status")
        object.__setattr__(
            self, "entry_margin", _decimal(self.entry_margin, "entry_margin")
        )
        if not Decimal("0") <= self.entry_margin < Decimal("1"):
            raise ValueError("entry_margin must be in [0, 1)")
        if self.research_quantity <= 0:
            raise ValueError("research_quantity must be positive")
        object.__setattr__(self, "exit_rule", _required_text(self.exit_rule, "exit_rule"))
        object.__setattr__(
            self,
            "registration_evidence",
            tuple(dict.fromkeys(self.registration_evidence)),
        )
        for evidence in self.registration_evidence:
            if evidence.kind not in RULE_REGISTRATION_EVIDENCE_KINDS:
                raise ValueError(
                    "Contemporaneous rule evidence kind must be an independently dated source"
                )
            if evidence.available_at > self.registered_at:
                raise ValueError(
                    "Contemporaneous rule evidence cannot postdate the registered_at timestamp"
                )
        if (
            self.rule_registration_status == RULE_REGISTRATION_CONTEMPORANEOUS
            and not self.registration_evidence
        ):
            raise ValueError(
                "Contemporaneous rule registration requires dated source evidence"
            )

    @property
    def is_retrospective_rule(self) -> bool:
        return self.rule_registration_status == RULE_REGISTRATION_RETROSPECTIVE

    def as_policy(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "model_scope": self.model_scope,
            "registered_at": self.registered_at.isoformat(),
            "rule_registration_status": self.rule_registration_status,
            "entry_margin": str(self.entry_margin),
            "research_quantity": self.research_quantity,
            "exit_rule": self.exit_rule,
            "registration_evidence": [
                evidence.as_policy() for evidence in self.registration_evidence
            ],
        }


@dataclass(frozen=True)
class HistoricalResearchReplay:
    replay_id: str
    schema_version: str
    namespace: str
    symbol: str
    replay_date: date
    generated_at: datetime
    source_receipt: dict[str, Any]
    then_known_facts: ThenKnownFinancialFacts
    then_known_filings: tuple[HistoricalEvidenceReference, ...]
    then_known_quote: ThenKnownQuote
    rule: HistoricalRuleBinding
    source_decision_state: str
    source_decision_action: str
    final_decision: str
    blockers: tuple[str, ...] = ()
    valuation_approved: bool = False
    trade_approved: bool = False
    positive_price_review_eligible: bool = False
    future_facts_used: bool = False
    future_rule_version_used: bool = False
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != REPLAY_SCHEMA:
            raise ValueError("Unknown historical replay schema")
        if self.namespace != REPLAY_NAMESPACE:
            raise ValueError("Historical replay requires its dedicated namespace")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Historical replay symbol must contain six digits")
        object.__setattr__(self, "replay_id", _required_text(self.replay_id, "replay_id"))
        object.__setattr__(self, "replay_date", _date(self.replay_date, "replay_date"))
        object.__setattr__(
            self, "generated_at", _datetime(self.generated_at, "generated_at")
        )
        if self.final_decision not in OUTCOMES:
            raise ValueError("Unknown historical replay final decision")
        if self.source_decision_state != "proposed_entry":
            raise ValueError("Historical replay source must be a proposed entry")
        if self.source_decision_action != "propose_entry_review":
            raise ValueError("Historical replay source must remain a review proposal")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Historical replay must remain no_order")
        if self.valuation_approved or self.trade_approved:
            raise ValueError("Historical replay cannot approve valuation or trade")
        if self.final_decision in {"BUY_REVIEW"}:
            raise ValueError("Historical replay cannot produce a positive BUY_REVIEW")
        if self.positive_price_review_eligible:
            raise ValueError("Relative-PE research replay is not price-review eligible")
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))
        object.__setattr__(
            self,
            "then_known_filings",
            tuple(self.then_known_filings),
        )
        if self.future_facts_used:
            raise ValueError("Historical replay cannot use future facts")
        rule_as_of = self.rule.registered_at.astimezone(CN_TZ).date()
        if self.rule.is_retrospective_rule:
            if not self.future_rule_version_used:
                raise ValueError(
                    "Retrospective rule replay must mark future_rule_version_used"
                )
        else:
            if self.future_rule_version_used:
                raise ValueError(
                    "Contemporaneous rule replay cannot use a future rule version"
                )
            if rule_as_of > self.replay_date:
                raise ValueError(
                    "Contemporaneous rule registration cannot postdate the replay date"
                )

    @property
    def replay_sha256(self) -> str:
        return _canonical_digest(self.as_policy())

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "replay_id": self.replay_id,
            "namespace": self.namespace,
            "symbol": self.symbol,
            "replay_date": self.replay_date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "source_receipt": dict(self.source_receipt),
            "then_known_facts": self.then_known_facts.as_policy(),
            "then_known_filings": [
                ref.as_policy() for ref in self.then_known_filings
            ],
            "then_known_quote": self.then_known_quote.as_policy(),
            "rule": self.rule.as_policy(),
            "source_decision_state": self.source_decision_state,
            "source_decision_action": self.source_decision_action,
            "final_decision": self.final_decision,
            "blockers": list(self.blockers),
            "valuation_approved": self.valuation_approved,
            "trade_approved": self.trade_approved,
            "positive_price_review_eligible": self.positive_price_review_eligible,
            "future_facts_used": self.future_facts_used,
            "future_rule_version_used": self.future_rule_version_used,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )

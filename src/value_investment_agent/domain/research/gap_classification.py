"""Classify valuation and research blockers instead of calling every gap 'more data'."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


GAP_FACT_MISSING = "FACT_MISSING"
GAP_FACT_CONFLICT = "FACT_CONFLICT"
GAP_ASSUMPTION_MISSING = "ASSUMPTION_MISSING"
GAP_ASSUMPTION_LOW_CONFIDENCE = "ASSUMPTION_LOW_CONFIDENCE"
GAP_MATERIALITY_UNKNOWN = "MATERIALITY_UNKNOWN"
GAP_MODEL_NOT_APPLICABLE = "MODEL_NOT_APPLICABLE"
GAP_MODEL_NOT_REGISTERED = "MODEL_NOT_REGISTERED"
GAP_PRICE_DATA_PENDING = "PRICE_DATA_PENDING"
GAP_MODEL_STALE = "MODEL_STALE"
GAP_THESIS_INCOMPLETE = "THESIS_INCOMPLETE"
GAP_UNCLASSIFIED = "UNCLASSIFIED"

GAP_TYPES = {
    GAP_FACT_MISSING,
    GAP_FACT_CONFLICT,
    GAP_ASSUMPTION_MISSING,
    GAP_ASSUMPTION_LOW_CONFIDENCE,
    GAP_MATERIALITY_UNKNOWN,
    GAP_MODEL_NOT_APPLICABLE,
    GAP_MODEL_NOT_REGISTERED,
    GAP_PRICE_DATA_PENDING,
    GAP_MODEL_STALE,
    GAP_THESIS_INCOMPLETE,
    GAP_UNCLASSIFIED,
}


@dataclass(frozen=True)
class GapClassification:
    symbol: str
    blocker: str
    gap_type: str
    field: str | None
    reason: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Gap symbol must contain six digits")
        if not self.blocker.strip():
            raise ValueError("Gap blocker is required")
        if self.gap_type not in GAP_TYPES:
            raise ValueError("Unknown gap type")
        object.__setattr__(self, "blocker", self.blocker.strip())

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "blocker": self.blocker,
            "type": self.gap_type,
            "field": self.field,
            "reason": self.reason,
        }


_PREFIX_RULES = (
    (GAP_FACT_MISSING, "FACT_MISSING:"),
    (GAP_FACT_CONFLICT, "FACT_CONFLICT:"),
    (GAP_ASSUMPTION_MISSING, "ASSUMPTION_MISSING:"),
    (GAP_ASSUMPTION_LOW_CONFIDENCE, "ASSUMPTION_LOW_CONFIDENCE:"),
    (GAP_MATERIALITY_UNKNOWN, "MATERIALITY_UNKNOWN:"),
    (GAP_MODEL_NOT_APPLICABLE, "MODEL_NOT_APPLICABLE:"),
    (GAP_MODEL_NOT_REGISTERED, "MODEL_NOT_REGISTERED:"),
    (GAP_PRICE_DATA_PENDING, "PRICE_DATA_PENDING:"),
    (GAP_MODEL_STALE, "MODEL_STALE:"),
    (GAP_THESIS_INCOMPLETE, "THESIS_INCOMPLETE:"),
)

_PATTERN_RULES = (
    (GAP_FACT_MISSING, re.compile(r"(not_disclosed|not_allocated|not_full_standalone|missing|scope_not_available|split_not|尚未披露|未披露|尚无披露)", re.I)),
    (GAP_FACT_CONFLICT, re.compile(r"(conflict|不一致|来源冲突|contradicts)", re.I)),
    (GAP_ASSUMPTION_MISSING, re.compile(r"(assumption.*missing|discount_rate.*basis|no_reviewed_basis|no_company_specific|尚未形成假设)", re.I)),
    (GAP_ASSUMPTION_LOW_CONFIDENCE, re.compile(r"(low_confidence|估值置信度为低|assumption.*low|低置信度|有界研究区间|有界假设.*尚未|尚未经验证实|不是未来实际资本成本)", re.I)),
    (GAP_MODEL_NOT_APPLICABLE, re.compile(r"(model_not_applicable|carve.?out|cannot.*pair|scope.*applicable)", re.I)),
    (GAP_MODEL_NOT_REGISTERED, re.compile(r"(not_registered|model_not_registered)", re.I)),
    (GAP_PRICE_DATA_PENDING, re.compile(r"(pending_external_data|等待已验证收盘行情|price_bridge_)", re.I)),
    (GAP_MODEL_STALE, re.compile(r"(stale_model|重大事项后的模型重估|model.*stale)", re.I)),
    (GAP_THESIS_INCOMPLETE, re.compile(r"(thesis|论点)", re.I)),
)


def classify_gap(symbol: str, blocker: str) -> GapClassification:
    for gap_type, prefix in _PREFIX_RULES:
        if blocker.startswith(prefix):
            return GapClassification(
                symbol=symbol,
                blocker=blocker,
                gap_type=gap_type,
                field=blocker[len(prefix):] or None,
                reason=blocker,
            )
    for gap_type, pattern in _PATTERN_RULES:
        if pattern.search(blocker):
            return GapClassification(
                symbol=symbol,
                blocker=blocker,
                gap_type=gap_type,
                field=None,
                reason=blocker,
            )
    return GapClassification(
        symbol=symbol,
        blocker=blocker,
        gap_type=GAP_UNCLASSIFIED,
        field=None,
        reason="No explicit gap category is embedded in this blocker",
    )


def classify_blockers(symbol: str, blockers: list[str]) -> list[GapClassification]:
    return [classify_gap(symbol, blocker) for blocker in blockers]


def gap_classifications_to_json(items: list[GapClassification]) -> str:
    return json.dumps(
        [item.as_policy() for item in items],
        ensure_ascii=False,
        indent=2,
    )


__all__ = [
    "GAP_FACT_MISSING",
    "GAP_FACT_CONFLICT",
    "GAP_ASSUMPTION_MISSING",
    "GAP_ASSUMPTION_LOW_CONFIDENCE",
    "GAP_MATERIALITY_UNKNOWN",
    "GAP_MODEL_NOT_APPLICABLE",
    "GAP_MODEL_NOT_REGISTERED",
    "GAP_PRICE_DATA_PENDING",
    "GAP_MODEL_STALE",
    "GAP_THESIS_INCOMPLETE",
    "GAP_UNCLASSIFIED",
    "GAP_TYPES",
    "GapClassification",
    "classify_gap",
    "classify_blockers",
    "gap_classifications_to_json",
]

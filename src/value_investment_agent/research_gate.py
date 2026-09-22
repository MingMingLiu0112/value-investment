"""Research gates for evidence-backed analysis; never create orders or positions."""
from __future__ import annotations

from dataclasses import dataclass

from .research_case import ResearchCase


GATE_EVIDENCE = "G0_证据门"
GATE_FINANCIAL = "G1_财务门"
GATE_BUSINESS = "G2_商业论点门"
GATE_VALUATION = "G3_估值门"


@dataclass(frozen=True)
class ResearchGate:
    symbol: str
    results: dict[str, bool]
    blockers: list[str]

    conclusion: str

    @property
    def valuation_ready(self) -> bool:
        """A valuation can be reviewed only after the four substantive gates pass."""
        return all(self.results[gate] for gate in (
            GATE_EVIDENCE, GATE_FINANCIAL, GATE_BUSINESS, GATE_VALUATION,
        ))


def _has_complete_business_case(case: ResearchCase) -> bool:
    """The MVP requires evidence-linked arguments, not merely populated sections."""
    groups = (case.positives, case.counter_evidence, case.thesis_breakers)
    if not all(
        len(items) >= 3
        and all(item.get("evidence_refs") for item in items)
        for items in groups
    ):
        return False
    if not case.next_events or not all(item.get("text", "").strip() for item in case.next_events):
        return False
    return bool(case.thesis.strip() and case.return_driver.strip() and case.mispricing_hypothesis.strip())


def _conclusion(results: dict[str, bool], case: ResearchCase) -> str:
    if not results[GATE_EVIDENCE]:
        return "数据不足"
    if not results[GATE_FINANCIAL] or not results[GATE_BUSINESS]:
        return "研究未完成"
    if not results[GATE_VALUATION]:
        return "估值未就绪"
    if case.valuation_status == "approved_low_confidence":
        return "等待更有吸引力的价格"
    return "估值具备研究吸引力"


def evaluate(case: ResearchCase) -> ResearchGate:
    """Preserve evidence, financial, business, and valuation failures separately."""
    results = {
        GATE_EVIDENCE: case.evidence_status == "verified" and bool(case.evidence_refs),
        GATE_FINANCIAL: case.research_status == "financial_scope_approved",
        GATE_BUSINESS: _has_complete_business_case(case),
        GATE_VALUATION: case.valuation_status in {"approved", "approved_low_confidence"},
    }
    conclusion = _conclusion(results, case)
    blockers = list(case.blockers)
    for gate, passed in results.items():
        if not passed:
            blockers.append(gate)
    return ResearchGate(case.symbol, results, list(dict.fromkeys(blockers)), conclusion)

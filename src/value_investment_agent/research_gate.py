"""Research gates for evidence-backed analysis; never create orders or positions."""
from __future__ import annotations

from dataclasses import dataclass

from .research_case import ResearchCase


GATE_EVIDENCE = "G0_证据门"
GATE_FINANCIAL = "G1_财务门"
GATE_BUSINESS = "G2_商业论点门"
GATE_VALUATION = "G3_估值门"

CONCLUSION_DATA_INSUFFICIENT = "数据不足"
CONCLUSION_RESEARCH_INCOMPLETE = "研究未完成"
CONCLUSION_VALUATION_NOT_READY = "估值未就绪"
CONCLUSION_RESEARCH_NOT_PASSED = "研究不通过"
CONCLUSION_RESEARCH_READY = "研究与估值已就绪"
RESEARCH_READY_FOR_PRICE_ASSESSMENT = "RESEARCH_READY_FOR_PRICE_ASSESSMENT"
RESEARCH_NOT_READY_FOR_PRICE_ASSESSMENT = "RESEARCH_NOT_READY_FOR_PRICE_ASSESSMENT"


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

    @property
    def ready_for_price_assessment(self) -> bool:
        """ResearchGate may state that research is ready, never whether price is attractive."""
        return self.conclusion == CONCLUSION_RESEARCH_READY

    @property
    def internal_status(self) -> str:
        return (
            RESEARCH_READY_FOR_PRICE_ASSESSMENT
            if self.ready_for_price_assessment
            else RESEARCH_NOT_READY_FOR_PRICE_ASSESSMENT
        )


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


def _conclusion(results: dict[str, bool]) -> str:
    if not results[GATE_EVIDENCE]:
        return CONCLUSION_DATA_INSUFFICIENT
    if not results[GATE_FINANCIAL] or not results[GATE_BUSINESS]:
        return CONCLUSION_RESEARCH_INCOMPLETE
    if not results[GATE_VALUATION]:
        return CONCLUSION_VALUATION_NOT_READY
    return CONCLUSION_RESEARCH_READY


def evaluate(case: ResearchCase) -> ResearchGate:
    """Preserve evidence, financial, business, and valuation failures separately."""
    results = {
        GATE_EVIDENCE: case.evidence_status == "verified" and bool(case.evidence_refs),
        GATE_FINANCIAL: case.research_status == "financial_scope_approved",
        GATE_BUSINESS: _has_complete_business_case(case),
        GATE_VALUATION: case.valuation_status in {"approved", "approved_low_confidence"},
    }
    conclusion = _conclusion(results)
    blockers = list(case.blockers)
    for gate, passed in results.items():
        if not passed:
            blockers.append(gate)
    return ResearchGate(case.symbol, results, list(dict.fromkeys(blockers)), conclusion)

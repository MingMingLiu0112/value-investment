"""Gate results for a research case; never creates an order or a target price."""
from __future__ import annotations

from dataclasses import dataclass

from .research_case import ResearchCase


@dataclass(frozen=True)
class ResearchGate:
    symbol: str
    results: dict[str, bool]
    blockers: list[str]

    @property
    def valuation_ready(self) -> bool:
        return all(self.results.values())

    @property
    def conclusion(self) -> str:
        return "估值未就绪" if not self.valuation_ready else "估值研究可进入人工复核"


def evaluate(case: ResearchCase) -> ResearchGate:
    """Keep evidence, financial scope and valuation approval independently visible."""
    results = {
        "G0_时点完整": case.quote_date is not None and case.financial_period is not None,
        "G1_证据可追溯": case.evidence_status == "verified",
        "G2_财务口径通过": case.research_status == "financial_scope_approved",
        "G3_估值模型通过": case.valuation_status == "approved",
    }
    blockers = list(case.blockers)
    for gate, passed in results.items():
        if not passed:
            blockers.append(gate)
    return ResearchGate(case.symbol, results, list(dict.fromkeys(blockers)))

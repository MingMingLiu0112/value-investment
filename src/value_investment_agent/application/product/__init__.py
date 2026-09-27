"""Generic product command entrypoints."""

from .company_research import run_company_research_for_symbol
from .event_review import review_event_for_symbol
from .research_case import build_research_case_for_symbol
from .prospective_registration import register_prospective_research_plan
from .prospective_baseline import build_prospective_baselines
from .valuation import build_company_valuation_for_symbol
from .workbench import build_current_workbench_for_symbol

__all__ = [
    "build_company_valuation_for_symbol",
    "build_current_workbench_for_symbol",
    "build_research_case_for_symbol",
    "review_event_for_symbol",
    "register_prospective_research_plan",
    "build_prospective_baselines",
    "run_company_research_for_symbol",
]

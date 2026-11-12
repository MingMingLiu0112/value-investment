"""Reject a source-bound payout target when its profit denominator drifts.

This is a read-time economic review. It never rewrites a sealed model response.
"""
from copy import deepcopy
import re

PLAN_EVIDENCE = "cninfo:1224808850:conditional-return-plan"
WRONG_DENOMINATOR = re.compile(
    r"\bparent\s+(?:company\s+)?(?:net\s+)?(?:profit|earnings)\b|母公司(?:净)?利润",
    flags=re.IGNORECASE,
)
NEGATED_WRONG_DENOMINATOR = re.compile(
    r"(?:\bnot\b|\bnever\b|不是|并非|而非)(?:[\s-]|standalone){0,24}$",
    flags=re.IGNORECASE,
)


def _affirmative_wrong_denominator(rationale):
    for match in WRONG_DENOMINATOR.finditer(rationale):
        before = rationale[max(0, match.start() - 35):match.start()]
        if not NEGATED_WRONG_DENOMINATOR.search(before):
            return True
    return False


def review_task_view(task):
    value = deepcopy(task)
    paths_by_year = (value.get("research_result") or {}).get("years") or {}
    conflicts = []
    for year, row in paths_by_year.items():
        paths = row.get("shareholder_cash_paths") if isinstance(row, dict) else None
        if not isinstance(paths, dict):
            continue
        for scenario, path in paths.items():
            term = (path.get("terms") or {}).get("target_payout_ratio") if isinstance(path, dict) else None
            if (isinstance(term, dict) and term.get("classification") == "FORECAST_ASSUMPTION"
                    and PLAN_EVIDENCE in term.get("evidence_ids", [])
                    and _affirmative_wrong_denominator(term.get("rationale") or "")):
                conflicts.append({"year": year, "scenario": scenario,
                                  "term": "target_payout_ratio", "source_id": PLAN_EVIDENCE})
    value["economic_validation"] = {
        "status": "REJECTED" if conflicts else "NO_DETECTED_DENOMINATOR_CONFLICT",
        "reason": "SOURCE_PAYOUT_PROFIT_DENOMINATOR_CONFLICT" if conflicts else None,
        "conflicts": conflicts,
        "actual_plan_denominator": "consolidated_profit_attributable_to_parent_shareholders",
        "action": "no_order",
    }
    return value

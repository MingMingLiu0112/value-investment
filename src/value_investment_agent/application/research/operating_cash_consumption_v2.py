"""Compile actual D2 periods for E2 without rewriting the historical v1 adapter.

This consumer preserves each complete operating witness. It never chooses a
central point, repeats a year, or supplies a missing cash/terminal policy.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path

from . import operating_cash_consumption_v1 as previous
from ...domain.research import period_earnings_assembly_v1 as periods

VERSION = "operating-cash-consumption-v2"


def compile_verified_annual_candidates(*, consumed, opening_date, asof):
    """Adapt a verified earnings result to the existing annual input contract.

    Authentication is performed by read_operating_cash_consumption below. This
    pure adapter is not an alternative evidence or valuation admission boundary.
    Each returned witness is an alternative, not a selected annual forecast.
    """
    opening = date.fromisoformat(opening_date)
    if opening.isoformat() != opening_date or (opening.month, opening.day) != (12, 31):
        raise ValueError("ANNUAL_OPENING_BASIS_REQUIRED")
    if consumed.get("action") != "no_order" or consumed.get("formal_eligibility") is not False:
        raise ValueError("UNAPPROVED_EARNINGS_REQUIRED")
    scenarios = consumed.get("scenarios", {})
    if set(scenarios) != {"bear", "base", "bull"}:
        raise ValueError("THREE_EARNINGS_SCENARIOS_REQUIRED")
    cutoff = datetime.fromisoformat(asof)
    if cutoff.utcoffset() is None:
        raise ValueError("AWARE_RESEARCH_CUTOFF_REQUIRED")
    outputs = {}
    for name, path in scenarios.items():
        start, end = (date.fromisoformat(path[k]) for k in ("period_start", "period_end"))
        refs = deepcopy(path["anchor_evidence"])
        if not refs:
            raise ValueError("EARNINGS_ANCHOR_EVIDENCE_REQUIRED")
        for ref in refs:
            available = datetime.fromisoformat(ref["available_at"])
            if available.utcoffset() is None or available > cutoff:
                raise ValueError("EARNINGS_SOURCE_AFTER_RESEARCH_CUTOFF")
        index = start.year - opening.year
        if start <= opening or not 1 <= index <= 10:
            raise ValueError("EARNINGS_OUTSIDE_TEN_YEAR_OPENING_HORIZON")
        complete = (path["period_basis"] == "FY" and start == date(start.year, 1, 1)
                    and end == date(start.year, 12, 31))
        if path["period_basis"] == "FY" and not complete:
            raise ValueError("FY_LABEL_WITH_INCOMPLETE_CALENDAR_COVERAGE")
        candidates = {}
        if complete:
            for witness, point in path["witnesses"].items():
                # Keep all terms from one recomputed witness, never splice extrema.
                with localcontext() as arithmetic:
                    arithmetic.prec = 48
                    parent = (Decimal(point["group_pbt_cny"]) - Decimal(point["income_tax_cny"])
                              - Decimal(point["signed_nci_cny"]))
                    if parent != Decimal(point["parent_profit_cny"]):
                        raise ValueError("D2_PARENT_PROFIT_RECONCILIATION_MISMATCH")
                    amounts = {k: format(Decimal(point[k]).quantize(Decimal("0.01"),
                        rounding=ROUND_HALF_EVEN), "f") for k in periods.AMOUNTS}
                segment = dict(period_start=start.isoformat(), period_end=end.isoformat(),
                    kind="FORECAST_ASSUMPTION", currency="CNY", scope="consolidated",
                    **amounts,
                    source_refs=refs,
                    assumption_refs=[dict(task_id=consumed["task_id"], scenario=name,
                                          witness=witness, research_as_of=asof)])
                candidates[witness] = periods.assemble_annual_earnings(year=index,
                    period_start=start.isoformat(), period_end=end.isoformat(),
                    segments=[segment], asof=asof)
                with localcontext() as arithmetic:
                    arithmetic.prec = 48
                    candidates[witness]["input_rounding"] = dict(
                        basis="CNY_CENTS_ROUND_HALF_EVEN_NOT_ORIGINAL_FACTS",
                        original_amounts={k: point[k] for k in periods.AMOUNTS},
                        parent_profit_delta_cny=str(Decimal(candidates[witness]["parent_bridge"][
                            "parent_profit_cny"]) - parent))
        covered = {start.year} if candidates else set()
        outputs[name] = dict(period_start=start.isoformat(), period_end=end.isoformat(),
            period_basis=path["period_basis"], model_year=index,
            status="ANNUAL_EARNINGS_CANDIDATES_COMPILED" if candidates else "PARTIAL_YEAR_REQUIRES_OTHER_SEGMENTS",
            candidates=candidates, selected_witness=None,
            missing_calendar_years=[year for year in range(opening.year + 1, opening.year + 11)
                                    if year not in covered])
    return dict(schema_version=VERSION, action="no_order", formal_eligibility=False,
        symbol=consumed["symbol"], task_id=consumed["task_id"], opening_date=opening_date,
        scenarios=outputs, cash_model_ready=False, selected_annual_rows=None,
        reason="EXPLICIT_COMPLETE_HORIZON_WITNESS_SELECTION_AND_CASH_POLICY_REQUIRED")


def read_operating_cash_consumption(*, root, task, now):
    """Cold-source v1 replay plus annual compilation; no network or writes."""
    result = previous.read_operating_cash_consumption(root=root, task=task, now=now)
    if not result.get("scenarios"):
        return result
    # v1 already authenticates the exact task source/context and recomputes every
    # witness. The opening date is the registered financial basis, not today.
    context = previous.build_operating_source_context(root=root, symbol=task["symbol"],
        now=datetime.fromisoformat(task["research_as_of"]), binding=task["source_binding"])
    if context["snapshot_fingerprint"] != task["context_fingerprint"]:
        raise ValueError("OPERATING_CONTEXT_CHANGED_DURING_ANNUAL_COMPILATION")
    try:
        if all(row["period_basis"] == "H1" for row in result["scenarios"].values()):
            compiled = dict(schema_version=VERSION,
                status="DELEGATED_TO_EXISTING_PERIOD_ADAPTER",
                reason="半年研究继续使用既有滚动全年适配；本次全年适配不改变旧路径。",
                action="no_order", formal_eligibility=False, cash_model_ready=False)
        else:
            compiled = compile_verified_annual_candidates(consumed=result,
                opening_date=context["financial_basis"], asof=task["research_as_of"])
    except (ValueError, KeyError, TypeError) as error:
        compiled = dict(schema_version=VERSION, status="UNASSESSABLE", reason=str(error),
                        action="no_order", formal_eligibility=False, cash_model_ready=False)
        result["current_blockers"] = [row for row in result.get("current_blockers", [])
            if row["code"] != "COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED"] + [
            dict(code="ANNUAL_INPUT_COMPILATION_REJECTED", stage="valuation", explanation=str(error))]
    result["earnings_input_compilation"] = compiled
    if compiled.get("scenarios"):
        annual = all(r["candidates"] for r in compiled["scenarios"].values())
        for blocker in result.get("current_blockers", []):
            if blocker["code"] == "COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED":
                blocker.update(code="COMPLETE_TEN_YEAR_OPERATING_PATH_REQUIRED" if annual
                               else "COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED",
                    explanation=("已有完整年度经营输入；仍缺逐年连续预测、明确角点选择与现金政策，不能复制一年为十年。"
                                 if annual else "已有期间不是完整年度；需补齐同一年其他期间，不能乘二年化。"))
    hashes = {VERSION: hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              periods.VERSION: hashlib.sha256(Path(periods.__file__).read_bytes()).hexdigest()}
    identity = dict(previous_fingerprint=result.get("consumption_fingerprint"),
                    compilation=compiled, implementations=hashes)
    result["previous_consumption_fingerprint"] = result.get("consumption_fingerprint")
    result["consumption_fingerprint"] = hashlib.sha256(json.dumps(identity, sort_keys=True,
        ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    result["annual_compilation_implementations"] = hashes
    return result

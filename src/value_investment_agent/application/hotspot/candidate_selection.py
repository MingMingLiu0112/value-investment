"""Replay the retained activity pool through existing completed-bar rules.

This is research selection, not strategy admission or portfolio permission.
No collection, registry mutation or order is performed here.
"""
from __future__ import annotations

from datetime import datetime, time
import hashlib
import json
from pathlib import Path

from .current_case_review import inspect_current_price_case
from .current_refresh import final_observation_key, structure_selection_evidence
from .current_registry import REGISTRY
from .daily_selection import verify_daily_selection
from .price_action_case import project_current_price_action_plan
from ...domain.hotspot.opportunity_quality import RULE_VERSION as STRUCTURE_RULE
from ...quote_sessions import CHINA, evaluate_quote_session, parse_quote

RULE_VERSION = "hotspot-watch-pool-completed-structure-selection-v1"


def _read(root: Path, binding: dict) -> dict:
    name = Path(binding["path"])
    path = (root / name).resolve()
    if name.is_absolute() or not path.is_relative_to((root / "runtime").resolve()):
        raise ValueError("Candidate evidence must remain under runtime")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("Candidate source hash mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Candidate source must be an object")
    return value


def _stamp(value: str, now: datetime) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("Candidate source unavailable at cutoff")
    return stamp


def _watch_status(root: Path, report: dict, now: datetime) -> str:
    verify_daily_selection(root, report)
    day = datetime.fromisoformat(report["trade_date"]).date()
    close = datetime.combine(day, time(15), CHINA)
    stamps = [_stamp(report["available_at"], now)]
    for binding in report["source_bindings"]:
        stamps.append(_stamp(binding["available_at"], now))
    for row in report["rows"]:
        quote_at = _stamp(row["available_at"], now)
        if quote_at < close:
            raise ValueError("Watch quote acquired before completed session")
        stamps.append(quote_at)
        stamps.append(_stamp(row["classification_available_at"], now))
    if now < close or stamps[0] < close or max(stamps) > stamps[0]:
        raise ValueError("Watch pool is not a completed, available session")
    calendar = _read(root, report["source_bindings"][1])
    if _stamp(calendar["finished_at"], now) > stamps[0]:
        raise ValueError("Watch calendar acquired after report availability")
    references = calendar["references"]
    if not references:
        raise ValueError("Watch pool has no calendar anchor")
    statuses = []
    for symbol, reference in references.items():
        quote = parse_quote(calendar["documents"][reference["document_refs"]["tencent"]],
                            "tencent", symbol, now)
        checked = evaluate_quote_session(symbol, quote["price"], reference, now,
                                          documents=calendar["documents"])
        if checked["passed"] and checked["expected_session"] == report["trade_date"]:
            statuses.append("CURRENT")
        elif checked["status"] == "stale_quote":
            statuses.append("STALE")
        else:
            raise ValueError("Watch calendar/session anchor rejected")
    # Any venue already past this report's session makes the shared pool old.
    return "STALE" if "STALE" in statuses else "CURRENT"


def select_current_hotspot_candidates(*, root: Path, now: datetime,
                                      limit: int = 30,
                                      watch_binding: dict | None = None,
                                      case_bindings: dict[str, dict] | None = None) -> dict:
    """Select from the whole retained pool, not the five displayed representatives.

    Explicit bindings support immutable replay without changing current pointers.
    Cases are mapped by symbol to ``{path, sha256}``. Missing/invalid/stale cases
    are UNKNOWN, never negative structural evidence. ``limit`` bounds displayed
    pool members; coverage includes the untruncated pool and reports omissions.
    """
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware cutoff required")
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("Candidate limit must be 1..30")
    root = Path(root).resolve()
    result = dict(schema_version=RULE_VERSION, rule_version=RULE_VERSION,
        evaluated_at=now.isoformat(), action="no_order", items=[], shortlist=[],
        coverage={}, source_bindings=[], blockers=[], data_status="UNKNOWN",
        formal_eligibility=False, portfolio_eligibility=False,
        personal_risk_evaluated=False,
        strategy_validation="NOT_EVALUATED", current_pit=False,
        ranking_scope="RESEARCH_OBSERVATION_NOT_STRATEGY_ADMISSION")
    try:
        registry = None
        if watch_binding is None or case_bindings is None:
            raw = (root / REGISTRY).read_bytes()
            registry = json.loads(raw)
            if (registry.get("schema_version") != "current-price-conditions-v1"
                    or registry.get("action") != "no_order"):
                raise ValueError("Invalid current price registry")
            result["registry_binding"] = dict(path=REGISTRY,
                sha256=hashlib.sha256(raw).hexdigest())
        watch_binding = watch_binding if watch_binding is not None else registry["watch_source_binding"]
        report = _read(root, watch_binding)
        watch_status = _watch_status(root, report, now)
        pool = report.get("candidate_pool", report["observation_list"])
        if not isinstance(pool, list) or len(pool) > 30:
            raise ValueError("Invalid bounded watch pool")
        if case_bindings is None:
            case_bindings = {}
            # Do not import previous_items: those belong to a different watch pool.
            for item in registry.get("assessed_candidates", []) + registry["items"]:
                binding = dict(path=item["case_path"], sha256=item["case_sha256"])
                if item["symbol"] in case_bindings and case_bindings[item["symbol"]] != binding:
                    raise ValueError("Conflicting case bindings for security")
                case_bindings[item["symbol"]] = binding
        members = {row["symbol"] for row in pool}
        if len(members) != len(pool) or (case_bindings.keys() - members):
            raise ValueError("Duplicate or mixed-watch-pool security")
        result["source_bindings"] = [dict(watch_binding), *report["source_bindings"]]
        result.update(trade_date=report["trade_date"], data_status=watch_status,
            activity_rule_version=report["ranking"]["rule_version"],
            structure_rule_version=STRUCTURE_RULE,
            candidate_pool_rule=report["ranking"].get("candidate_pool_rule"),
            ranking=report["ranking"]["ranking"],
            market_environment=report["ranking"]["market"],
            activity_exclusions=report["ranking"]["excluded"],
            data_failures=report.get("failures", []),
            classification_effective_date=None)
        for candidate in pool[:limit]:
            symbol = candidate["symbol"]
            item = dict(candidate, activity_status="ACTIVE_OBSERVATION",
                selection_status="UNKNOWN", structure_status="UNKNOWN",
                structure_tier="UNKNOWN", data_status="MISSING", missing_periods=["daily", "60m", "15m"],
                reasons=["COMPLETED_MULTIPERIOD_CASE_MISSING"],
                entry_condition=None, invalidation_condition=None,
                formal_eligibility=False, action_eligibility=False, current_pit=False,
                action="no_order", evidence_refs=[watch_binding["sha256"]])
            binding = case_bindings.get(symbol)
            if binding:
                result["source_bindings"].append(dict(binding))
                review = inspect_current_price_case(root=root, symbol=symbol,
                                                    case_binding=binding, now=now)
                item.update(case_binding=dict(binding), data_status=review["data_status"],
                    source_integrity=review["source_integrity"],
                    diagnostic=review.get("diagnostic"),
                    reasons=[review.get("reason") or "STRUCTURE_NOT_EVALUATED"])
                case = review.get("case")
                if case and case["market_trade_date"] != report["trade_date"]:
                    item.update(data_status="INVALID", reasons=["WATCH_CASE_DATE_MISMATCH"])
                elif case and review["data_status"] == "CURRENT" and watch_status == "CURRENT":
                    plan = project_current_price_action_plan(case)
                    quality = plan["opportunity_quality"]
                    tier = quality["structure_tier"]
                    status = {"STRUCTURE_QUALIFIED_OBSERVATION": "SELECTED",
                              "CONFLICT_OR_REJECTED": "EXCLUDED",
                              "ACTIVE_ONLY": "PENDING_CONFIRMATION"}[tier]
                    item.update(selection_status=status,
                        structure_status="PASS" if status == "SELECTED" else "FAIL" if status == "EXCLUDED" else "PENDING",
                        structure_tier=tier, missing_periods=[], reasons=quality["structure_reasons"],
                        signal_state=plan["signal_state"], period_structure=plan["period_structure"],
                        activity_rank=candidate.get("rank"),
                        structure_selection_evidence=structure_selection_evidence(plan),
                        entry_condition=plan["entry_condition"],
                        invalidation_condition=plan["invalidation_condition"],
                        price_behavior=plan["price_behavior"],
                        source_available_at=plan["data_available_at"],
                        structure_source_bindings=case["source_bindings"],
                        valid_from_session=plan["valid_from_session"],
                        expires_after_session=plan["expires_after_session"],
                        evidence_refs=list(dict.fromkeys([watch_binding["sha256"], *plan["evidence_refs"]])),
                        strategy_blockers=plan["blockers"])
                elif watch_status == "STALE":
                    item.update(data_status="STALE", reasons=["WATCH_POOL_STALE"])
            if watch_status == "STALE":
                item.update(data_status="STALE", reasons=["WATCH_POOL_STALE"])
            result["items"].append(item)
        qualified = [row for row in result["items"] if row["selection_status"] == "SELECTED"]
        result["shortlist"] = sorted(qualified, key=final_observation_key)
        items = result["items"]
        result["coverage"] = dict(market_securities=len(report["rows"]),
            candidate_pool=len(pool), evaluated=len(items), omitted_by_limit=len(pool)-len(items),
            industries=len({row["industry"] for row in pool}),
            bound_cases=sum(row["symbol"] in case_bindings for row in items),
            structure_verified=sum(row["structure_status"] != "UNKNOWN" for row in items),
            selected=len(qualified), excluded=sum(row["selection_status"] == "EXCLUDED" for row in items),
            pending_confirmation=sum(row["selection_status"] == "PENDING_CONFIRMATION" for row in items),
            unknown=sum(row["selection_status"] == "UNKNOWN" for row in items))
        if any(row["selection_status"] == "UNKNOWN" for row in items):
            result["blockers"].append("CANDIDATE_STRUCTURE_COVERAGE_INCOMPLETE")
        if watch_status == "STALE":
            result["blockers"].append("WATCH_POOL_STALE")
        result["blockers"].append("STRATEGY_PIT_OOS_COST_SHADOW_AND_APPROVAL_SEPARATE")
        result["watch_data_status"] = watch_status
        if watch_status == "CURRENT" and any(row["data_status"] != "CURRENT" for row in items):
            result["data_status"] = "PARTIAL"
        result["status"] = "RESEARCH_SELECTION_REPLAYED"
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError, AttributeError) as error:
        result.update(status="UNASSESSABLE", data_status="INVALID", items=[], shortlist=[],
                      blockers=["HOTSPOT_SELECTION_SOURCE_INVALID"], diagnostic=str(error))
    return result

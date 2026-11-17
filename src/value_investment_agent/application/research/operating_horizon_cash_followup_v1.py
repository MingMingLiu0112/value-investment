"""Prepare a source-bound D2-to-E2 handoff without inventing shareholder cash.

The horizon D2 task has annual operating scenarios; the selected official
reports separately contain parent-only cash observations.  This module records
their exact shared input boundary so a later E2 policy compiler can consume
both.  It deliberately does not select a payout, maintenance, remittance or
valuation assumption.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from . import operating_cash_consumption_v5 as annual
from .agent_review.operating_horizon_sources_v1 import (
    CONFIG as HORIZON_CONFIG,
    VERSION as HORIZON_VERSION,
    build_operating_horizon_source_context,
)
from .parent_cash_research import replay_bound_parent_cash_observations


SCHEMA = "operating-horizon-cash-followup-v1"


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def prepare_operating_horizon_cash_followup(*, root: Path, symbol: str, now: datetime) -> dict:
    """Join one successful annual D2 supplement to replayed parent cash facts.

    The returned artifact is only a source-bound E2 *input manifest*.  A
    current cash policy remains a distinct economic-research input and every
    result stays unapproved/no-order.
    """
    base = dict(schema_version=SCHEMA, action="no_order", formal_eligibility=False,
        main_range_adopted=False, valuation=None, condition_price=None,
        cash_model_ready=False)
    if now.utcoffset() is None:
        raise ValueError("AWARE_HORIZON_CASH_FOLLOWUP_CLOCK_REQUIRED")
    supplement = annual.read_annual_supplement(root=root, symbol=symbol, now=now)
    if supplement.get("status") != "ANNUAL_SUPPLEMENT_COMPILED_NOT_CASH_POLICY":
        return dict(base, symbol=symbol, status="NOT_READY",
            reason="SOURCE_BOUND_ANNUAL_D2_SUPPLEMENT_REQUIRED",
            annual_supplement_status=supplement.get("status"),
            annual_supplement_reason=supplement.get("reason"),
            annual_supplement=deepcopy(supplement))
    scope_status = supplement.get("scope_decomposition_status")
    if scope_status not in {"STABLE_SCOPE_VERIFIED", "SCOPE_CHANGE_VERIFIED"}:
        return dict(base, symbol=symbol, status="NOT_READY",
            reason="SOURCE_BOUND_SCOPE_APPLICABILITY_REQUIRED",
            scope_decomposition_status=scope_status,
            annual_supplement=deepcopy(supplement))
    context = build_operating_horizon_source_context(
        root=root, symbol=symbol,
        now=datetime.fromisoformat(supplement["research_as_of"]),
        binding=supplement["source_binding"],
    )
    if context["snapshot_fingerprint"] != supplement["context_fingerprint"]:
        raise ValueError("HORIZON_CASH_FOLLOWUP_SOURCE_CONTEXT_CHANGED")
    receipts = context.get("parent_cash_observation_receipts")
    if not isinstance(receipts, list) or not receipts:
        raise ValueError("HORIZON_PARENT_CASH_RECEIPTS_REQUIRED")
    observations = replay_bound_parent_cash_observations(
        root=Path(root), symbol=symbol, issuer_name=context["issuer_name"],
        receipt_bindings=receipts, now=now,
    )
    inputs = dict(
        schema_version=SCHEMA, symbol=symbol, issuer_name=context["issuer_name"],
        financial_basis=context["financial_basis"], research_as_of=supplement["research_as_of"],
        annual_task_id=supplement["task_id"], annual_source_binding=deepcopy(supplement["source_binding"]),
        annual_context_fingerprint=supplement["context_fingerprint"],
        annual_supplement_fingerprint=_fingerprint(supplement),
        scope_decomposition_status=scope_status,
        parent_cash_observation_receipts=deepcopy(receipts),
        parent_cash_source_bindings=deepcopy(observations["source_bindings"]),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    return dict(base, status="SOURCE_BOUND_ANNUAL_AND_PARENT_CASH_READY_FOR_POLICY",
        symbol=symbol, issuer_name=context["issuer_name"],
        annual_supplement=deepcopy(supplement), parent_cash_observations=observations,
        input_manifest=inputs, input_fingerprint=_fingerprint(inputs),
        scope_decomposition_status=scope_status,
        current_blockers=[
            dict(code="EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED", stage="shareholder_cash",
                explanation="已绑定经营情景和母公司现金原件，但维持投入、营运资本、资金上划、派息与现金底线仍须单独形成可追溯政策。"),
            dict(code="MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED", stage="economic_research",
                explanation="D2 年度情景仍是未批准研究输入，不能自动选为主估值区间。"),
            dict(code="CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED", stage="condition_price",
                explanation="财务期股本、分配、重大事件和合格报价尚未对齐，不能生成当前条件价格。"),
        ],
        limitation="该交接件不把历史母公司现金观察转化为FCFE、可分配现金、分红率、估值或交易资格。")


def scan_operating_horizon_cash_followups(*, root: Path, now: datetime) -> dict:
    """Read every explicitly registered horizon D2 case independently.

    This is a read-only health projection, not a scanner, queue creator or
    retry mechanism.  One issuer's stale task or missing evidence never hides
    another issuer's independently verifiable result.
    """
    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("AWARE_HORIZON_CASH_FOLLOWUP_CLOCK_REQUIRED")
    path = root / HORIZON_CONFIG
    try:
        registry = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HORIZON_SOURCE_REGISTRY_UNAVAILABLE") from error
    cases = registry.get("cases") if isinstance(registry, dict) else None
    if (registry.get("schema_version") != HORIZON_VERSION
            or registry.get("action") != "no_order"
            or not isinstance(cases, dict)):
        raise ValueError("HORIZON_SOURCE_REGISTRY_INVALID")
    if any(not isinstance(symbol, str) or re.fullmatch(r"[0-9]{6}", symbol) is None
           for symbol in cases):
        raise ValueError("HORIZON_SOURCE_REGISTRY_SYMBOL_INVALID")
    results = {}
    for symbol in sorted(cases):
        try:
            results[symbol] = prepare_operating_horizon_cash_followup(
                root=root, symbol=symbol, now=now)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            results[symbol] = dict(schema_version=SCHEMA, symbol=symbol,
                status="UNASSESSABLE", reason=str(error), action="no_order",
                formal_eligibility=False, cash_model_ready=False,
                condition_price=None, valuation=None)
    ready = [symbol for symbol, item in results.items()
             if item["status"] == "SOURCE_BOUND_ANNUAL_AND_PARENT_CASH_READY_FOR_POLICY"]
    return dict(schema_version=SCHEMA, action="no_order", status=(
            "READY_FOR_POLICY" if ready and len(ready) == len(results)
            else "PARTIAL" if ready else "NOT_READY"),
        registered_symbols=sorted(cases), ready_symbols=ready, results=results,
        limitation="只读取已登记来源；不发现新公司、不重试研究、不写任务或研究结果。")

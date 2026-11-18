"""Strict F2 projection for a paid owner-distribution successor receipt.

The adapter proves only that one exact, source-bound implemented distribution
is consumed by every valuation scenario.  It delegates the five existing F2
gates to the shared alignment service and never promotes period completeness,
capital continuity, materiality, financial updates, eligibility, or an order.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from .direct_owner_cash_alignment_v1 import _capital_anchor, _official_catalog
from .direct_owner_cash_research_v1 import _read
from .parent_owner_distribution_successor_v2 import (
    RECEIPT_SCHEMA,
    replay_parent_owner_distribution_successor,
)
from .parent_remaining_year_successor import replay_parent_remaining_year_successor
from .parent_direct_cash_research import _bound
from .pending_candidate_alignment import _load_bound_alignment
from ...research_artifact_codecs import ValuationResultCodec


INPUT_SCHEMA = "parent-owner-distribution-alignment-input-v2"
SCHEMA = "parent-owner-distribution-alignment-v2"
KIND = "PARENT_OWNER_DISTRIBUTION_SUCCESSOR_RECEIPT"
PASS = "IMPLEMENTED_DISTRIBUTION_INCLUDED_IN_MODEL"
FINANCIAL_UPDATE_RECOMPUTED = "EXACT_FINANCIAL_UPDATE_COLD_RECOMPUTED_IN_CANDIDATE"


def _decimal(value: Any, error: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(error)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(error) from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(error)
    return number


def _binding(value: Any, error: str) -> dict[str, str]:
    if (not isinstance(value, Mapping) or set(value) != {"path", "sha256"}
            or not all(isinstance(value.get(key), str) and value[key]
                       for key in ("path", "sha256"))):
        raise ValueError(error)
    return dict(value)


def _implemented_distribution(result: Mapping[str, Any], spec: Mapping[str, Any],
                              receipt: Mapping[str, Any], root: Path) -> dict[str, Any]:
    if (receipt.get("spec_binding") != result.get("spec_binding")
            or receipt.get("result_binding") is None
            or result.get("distribution") != spec.get("distribution")
            or result.get("distribution_evidence") != spec.get("distribution_evidence")
            or result.get("input_descriptor_sha256") != receipt.get("input_descriptor_sha256")):
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_RECEIPT_RESULT_SPEC_IDENTITY_MISMATCH")
    distribution = result["distribution"]
    if (distribution.get("currency") != "CNY"
            or distribution.get("classification") != "FACT"
            or distribution.get("scope") != "PARENT_STANDALONE_OWNER_DISTRIBUTION"):
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_FACT_IDENTITY_INVALID")
    amount = _decimal(distribution.get("total_cny"),
                      "OWNER_DISTRIBUTION_ALIGNMENT_AMOUNT_INVALID")
    per_share = _decimal(distribution.get("per_share_cny"),
                         "OWNER_DISTRIBUTION_ALIGNMENT_PER_SHARE_INVALID")
    evidence = spec.get("distribution_evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != {"original", "reconciliation"}:
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_EVIDENCE_PAIR_REQUIRED")
    original_ref = _binding(evidence["original"],
                            "OWNER_DISTRIBUTION_ALIGNMENT_ORIGINAL_BINDING_INVALID")
    reconciliation_ref = _binding(
        evidence["reconciliation"],
        "OWNER_DISTRIBUTION_ALIGNMENT_RECONCILIATION_BINDING_INVALID",
    )
    source_bindings = result.get("source_bindings")
    if (not isinstance(source_bindings, list) or original_ref not in source_bindings
            or reconciliation_ref not in source_bindings):
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_EVIDENCE_OUTSIDE_SOURCE_CLOSURE")
    _bound(root, original_ref)
    reconciliation = _read(root, reconciliation_ref)
    rows = reconciliation.get("distributions") if isinstance(reconciliation, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_RECONCILIATION_INVALID")
    matches = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        refs = [entry.get("binding") for entry in row.get("evidence", [])
                if isinstance(entry, Mapping)]
        if (row.get("cash_per_share") == distribution.get("per_share_cny")
                and row.get("cash_payment_date") == distribution.get("paid_date")
                and original_ref in refs):
            matches.append(row)
    if len(matches) != 1:
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_RECONCILIATION_TERMS_MISMATCH")
    if _decimal(matches[0].get("cash_amount"),
                "OWNER_DISTRIBUTION_ALIGNMENT_RECONCILIATION_AMOUNT_INVALID") != per_share:
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_RECONCILIATION_PER_SHARE_MISMATCH")

    calculations = result.get("valuation", {}).get("assumptions", {}).get(
        "scenario_calculations")
    if not isinstance(calculations, Mapping) or set(calculations) != {"bear", "base", "bull"}:
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_THREE_SCENARIOS_REQUIRED")
    for name in ("bear", "base", "bull"):
        rows = calculations[name].get("annual_rows")
        if not isinstance(rows, list) or not rows:
            raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_ANNUAL_ROWS_REQUIRED")
        if Decimal(rows[0].get("scheduled_owner_distribution_cny", "NaN")) != amount:
            raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_FIRST_YEAR_AMOUNT_MISMATCH")
        if any(Decimal(row.get("scheduled_owner_distribution_cny", "NaN")) != 0
               for row in rows[1:]):
            raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_LATER_YEAR_SCHEDULE_NOT_ZERO")
    return {
        "status": "PASS",
        "reason_code": PASS,
        "scope": "EXACT_IMPLEMENTED_DISTRIBUTION_ONLY_NOT_PERIOD_COMPLETENESS",
        "period_year": distribution["period_year"],
        "paid_date": distribution["paid_date"],
        "per_share_cny": str(per_share),
        "total_cny": str(amount),
        "original_binding": original_ref,
        "reconciliation_binding": reconciliation_ref,
        "period_cash_coverage_complete": False,
        "capital_structure_aligned": False,
        "materiality_approved": False,
        "financial_updates_reconciled": False,
        "formal_eligibility": False,
        "action": "no_order",
    }


def _consumed_financial_update_closure(*, result: Mapping[str, Any],
                                       receipt: Mapping[str, Any], root: Path,
                                       now: datetime,
                                       candidate_binding: Mapping[str, str]) -> list[dict[str, Any]]:
    """Prove a quarterly original was consumed by a cold-recomputed predecessor."""
    predecessor_binding = receipt.get("predecessor_binding")
    if (not isinstance(predecessor_binding, Mapping)
            or result.get("predecessor_binding") != predecessor_binding):
        raise ValueError("FINANCIAL_UPDATE_PREDECESSOR_BINDING_MISMATCH")
    predecessor = replay_parent_remaining_year_successor(
        root=root, receipt_binding=dict(predecessor_binding), now=now,
    )
    predecessor_receipt = _read(root, predecessor_binding)
    predecessor_spec = _read(root, predecessor_receipt["spec_binding"])
    source = predecessor_spec.get("quarterly_source")
    if (predecessor.get("quarterly_source") != source
            or predecessor.get("spec_binding") != predecessor_receipt.get("spec_binding")
            or predecessor.get("input_descriptor_sha256")
            != predecessor_receipt.get("input_descriptor_sha256")):
        raise ValueError("FINANCIAL_UPDATE_PREDECESSOR_COLD_RESULT_IDENTITY_MISMATCH")
    if (not isinstance(source, Mapping)
            or not isinstance(source.get("path"), str)
            or not isinstance(source.get("sha256"), str)
            or not isinstance(predecessor_spec.get("period_end"), str)):
        raise ValueError("FINANCIAL_UPDATE_PREDECESSOR_SOURCE_INVALID")
    source_binding = {"path": source["path"], "sha256": source["sha256"]}
    if (source_binding not in predecessor.get("source_bindings", [])
            or source_binding not in result.get("source_bindings", [])):
        raise ValueError("FINANCIAL_UPDATE_SOURCE_OUTSIDE_RECOMPUTED_CLOSURE")
    _bound(root, source_binding)
    return [{
        "status": FINANCIAL_UPDATE_RECOMPUTED,
        "period_end": predecessor_spec["period_end"],
        "source_binding": source_binding,
        "predecessor_receipt_binding": dict(predecessor_binding),
        "predecessor_input_descriptor_sha256": predecessor["input_descriptor_sha256"],
        "candidate_binding": dict(candidate_binding),
        "input_descriptor_sha256": result["input_descriptor_sha256"],
        "valuation_date_preserved": result["compiled"]["valuation_date"],
        "action": "no_order",
    }]


def read_parent_owner_distribution_alignment(*, root: Path, receipt_binding: dict,
                                             now: datetime) -> dict[str, Any]:
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_AWARE_CLOCK_REQUIRED")
    receipt = _read(root, receipt_binding)
    if (receipt.get("schema_version") != RECEIPT_SCHEMA
            or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False):
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_EXACT_V2_RECEIPT_REQUIRED")
    result = replay_parent_owner_distribution_successor(
        root=root, receipt_binding=receipt_binding, now=now,
    )
    spec = _read(root, receipt["spec_binding"])
    valuation = ValuationResultCodec().from_payload(result["valuation"])
    valuation_date = result["compiled"]["valuation_date"]
    if (result.get("symbol") != receipt.get("symbol")
            or valuation.symbol != result.get("symbol")
            or valuation.valuation_date.isoformat() != valuation_date
            or result.get("action") != "no_order"
            or result.get("formal_eligibility") is not False
            or result.get("successor_adopted") is not False
            or result.get("main_range_adopted") is not False):
        raise ValueError("OWNER_DISTRIBUTION_ALIGNMENT_COLD_RESULT_IDENTITY_CHANGED")
    inclusion = _implemented_distribution(result, spec, receipt, root)
    financial_update_closure = _consumed_financial_update_closure(
        result=result, receipt=receipt, root=root, now=now,
        candidate_binding=receipt_binding,
    )
    source_bindings = [dict(row) for row in result["source_bindings"]]
    for ref in (receipt_binding, receipt["spec_binding"], receipt["result_binding"]):
        if ref not in source_bindings:
            source_bindings.append(dict(ref))
    catalog = _official_catalog(result["package"], result["source_bindings"], result["symbol"])
    anchors = _capital_anchor(result["compiled"], catalog, result["symbol"])
    analysis = {
        "status": "CONDITIONAL_ANALYSIS_VERIFIED",
        "action": "no_order",
        "event_pdf_byte_limit": 128 * 1024 * 1024,
        "arithmetic_complete": True,
        "symbol": result["symbol"],
        "valuation_date": valuation_date,
        "research_as_of": spec["research_as_of"],
        "input_descriptor_sha256": result["input_descriptor_sha256"],
        "review_binding": {"candidate_binding": dict(receipt_binding)},
        "valuation": result["valuation"],
        "source_bindings": source_bindings,
        "source_catalog": catalog,
        "official_fact_anchors": anchors,
        "consumed_operating_inputs": {
            "ordinary_shares": result["compiled"]["ordinary_shares"],
        },
        "joint_capital_review": {"economic_path": {"currency": "CNY"}},
        "consumed_financial_updates": financial_update_closure,
    }
    aligned = _load_bound_alignment(
        root=root, analysis=analysis, now=now, input_schema=INPUT_SCHEMA,
    )
    return dict(
        aligned,
        schema_version=SCHEMA,
        research_artifact_kind=KIND,
        receipt_binding=dict(receipt_binding),
        implemented_distribution_model_inclusion=deepcopy(inclusion),
        formal_eligibility=False,
        action="no_order",
    )

"""Source-bound successor for an implemented finite-year owner distribution.

This application cold-replays a ``parent-remaining-year-successor-receipt-v1``
and injects one verified, already-paid parent-only owner distribution into the
first finite year of every scenario.  All cash, book, capacity, PV and residual
income arithmetic is delegated to the versioned v2 domain/model and the shared
``ResearchApplicationService``.  It never adopts a main range or grants an
order/approval state.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .direct_owner_cash_input_adapter_v2 import (
    DESCRIPTOR_VERSION,
    run_direct_owner_cash_research,
)
from .direct_owner_cash_research_v1 import _bytes, _read, _write
from .parent_direct_cash_research import _bound
from .parent_remaining_year_successor import (
    RECEIPT_SCHEMA as PREDECESSOR_RECEIPT_SCHEMA,
    replay_parent_remaining_year_successor,
)
from ...domain.valuation.direct_parent_owner_cash_v2 import compile_direct_owner_cash_path
from ...valuation_models.direct_owner_cash_v2 import (
    MODEL_VERSION,
    SCENARIO_CONTRACT,
)
from ..product.company_research import _serialize_outcome
from ..product.common import require_inside

SCHEMA = "parent-owner-distribution-successor-spec-v2"
RECEIPT_SCHEMA = "parent-owner-distribution-successor-receipt-v2"
SCOPE = "PARENT_STANDALONE_OWNER_DISTRIBUTION"
CLASSIFICATION = "FACT"
CURRENCY = "CNY"
IMPLEMENTATIONS = (
    "application/research/parent_owner_distribution_successor_v2.py",
    "application/research/parent_remaining_year_successor.py",
    "application/research/direct_owner_cash_input_adapter_v2.py",
    "domain/valuation/direct_parent_owner_cash_v2.py",
    "valuation_models/direct_owner_cash_v2.py",
)


def _implementations() -> dict[str, str]:
    source = Path(__file__).resolve().parents[2]
    return {name: sha256((source / name).read_bytes()).hexdigest() for name in IMPLEMENTATIONS}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any, error: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(error)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(error) from exc
    if not result.is_finite():
        raise ValueError(error)
    return result


def _binding(binding: Any, error: str) -> dict[str, str]:
    if (not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}
            or not all(_text(binding.get(key)) for key in ("path", "sha256"))):
        raise ValueError(error)
    return dict(binding)


def _validate_spec(spec: Any, *, now: datetime) -> tuple[datetime, date, dict[str, Any]]:
    expected = {
        "schema_version", "action", "predecessor_binding", "distribution_evidence",
        "distribution", "computed_at", "research_as_of", "run_id",
        "research_version", "reasons",
    }
    if (not isinstance(spec, Mapping) or set(spec) != expected
            or spec.get("schema_version") != SCHEMA or spec.get("action") != "no_order"):
        raise ValueError("OWNER_DISTRIBUTION_SUCCESSOR_SPEC_INVALID")
    if now.utcoffset() is None:
        raise ValueError("OWNER_DISTRIBUTION_SUCCESSOR_AWARE_CLOCK_REQUIRED")
    try:
        computed = datetime.fromisoformat(spec["computed_at"])
        research_day = date.fromisoformat(spec["research_as_of"])
    except (TypeError, ValueError) as exc:
        raise ValueError("OWNER_DISTRIBUTION_SUCCESSOR_TIME_INVALID") from exc
    if (computed.utcoffset() is None or computed > now or research_day > computed.date()
            or any(not _text(spec.get(key)) for key in ("run_id", "research_version", "reasons"))):
        raise ValueError("OWNER_DISTRIBUTION_SUCCESSOR_TIME_OR_REASON_INVALID")
    _binding(spec["predecessor_binding"], "OWNER_DISTRIBUTION_PREDECESSOR_BINDING_INVALID")
    evidence = spec["distribution_evidence"]
    if (not isinstance(evidence, Mapping) or set(evidence) != {"original", "reconciliation"}
            or evidence["original"] == evidence["reconciliation"]):
        raise ValueError("OWNER_DISTRIBUTION_ORIGINAL_AND_RECONCILIATION_EVIDENCE_REQUIRED")
    for row in evidence.values():
        _binding(row, "OWNER_DISTRIBUTION_EVIDENCE_BINDING_INVALID")
    distribution = spec["distribution"]
    fields = {"period_year", "paid_date", "per_share_cny", "eligible_shares", "total_cny",
              "scope", "currency", "classification"}
    if not isinstance(distribution, Mapping) or set(distribution) != fields:
        raise ValueError("OWNER_DISTRIBUTION_FACT_CONTRACT_INVALID")
    try:
        paid = date.fromisoformat(distribution["paid_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("OWNER_DISTRIBUTION_PAID_DATE_INVALID") from exc
    if (type(distribution["period_year"]) is not int
            or distribution["scope"] != SCOPE or distribution["currency"] != CURRENCY
            or distribution["classification"] != CLASSIFICATION):
        raise ValueError("OWNER_DISTRIBUTION_SCOPE_CURRENCY_OR_CLASSIFICATION_INVALID")
    per_share = _number(distribution["per_share_cny"], "OWNER_DISTRIBUTION_AMOUNT_INVALID")
    shares = _number(distribution["eligible_shares"], "OWNER_DISTRIBUTION_AMOUNT_INVALID")
    total = _number(distribution["total_cny"], "OWNER_DISTRIBUTION_AMOUNT_INVALID")
    if min(per_share, shares, total) <= 0 or total != per_share * shares:
        raise ValueError("OWNER_DISTRIBUTION_TOTAL_RECONCILIATION_FAILED")
    if paid > research_day:
        raise ValueError("OWNER_DISTRIBUTION_AFTER_RESEARCH_AS_OF")
    return computed, research_day, dict(distribution)


def _append_unique(rows: list[Any], additions: list[Any]) -> list[Any]:
    result = deepcopy(rows)
    for row in additions:
        if row not in result:
            result.append(deepcopy(row))
    return result


def _stable(value: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(value)
    for artifact in value["research_result"]["artifact_bundle"]["artifacts"]:
        artifact.pop("created_at", None)
    return value


def _recalculate(*, root: Path, spec_binding: Mapping[str, str], now: datetime) -> dict[str, Any]:
    root = Path(root).resolve()
    spec_binding = _binding(spec_binding, "OWNER_DISTRIBUTION_SPEC_BINDING_INVALID")
    spec = _read(root, spec_binding)
    computed, _, distribution = _validate_spec(spec, now=now)
    predecessor_receipt = _read(root, spec["predecessor_binding"])
    if predecessor_receipt.get("schema_version") != PREDECESSOR_RECEIPT_SCHEMA:
        raise ValueError("OWNER_DISTRIBUTION_EXACT_PREDECESSOR_REQUIRED")
    predecessor = replay_parent_remaining_year_successor(
        root=root, receipt_binding=spec["predecessor_binding"], now=computed,
    )
    if (predecessor.get("action") != "no_order"
            or predecessor.get("successor_adopted") is not False
            or predecessor.get("main_range_adopted") is not False):
        raise ValueError("OWNER_DISTRIBUTION_PREDECESSOR_BOUNDARY_CHANGED")
    for binding in spec["distribution_evidence"].values():
        _bound(root, binding)

    package = deepcopy(predecessor["package"])
    compiled = deepcopy(predecessor["compiled"])
    first_years = {
        name: row["years"][0]["year"] for name, row in compiled["scenarios"].items()
    }
    if (set(first_years) != {"bear", "base", "bull"}
            or len(set(first_years.values())) != 1
            or distribution["period_year"] != next(iter(first_years.values()))):
        raise ValueError("OWNER_DISTRIBUTION_FIRST_YEAR_MISMATCH")
    scheduled = distribution["total_cny"]
    calculations: dict[str, Any] = {}
    for name in ("bear", "base", "bull"):
        scenario = compiled["scenarios"][name]
        years = deepcopy(scenario["years"])
        for index, year in enumerate(years):
            year["scheduled_owner_distribution_cny"] = scheduled if index == 0 else "0"
        calculation = compile_direct_owner_cash_path(
            opening=deepcopy(scenario["opening"]), years=years,
            terminal=deepcopy(scenario["terminal"]),
            ordinary_shares=Decimal(scenario["ordinary_shares"]),
            cost_of_equity=Decimal(scenario["cost_of_equity"]),
            scope=package["facts"]["scenario_inputs"][name]["scope"], currency=CURRENCY,
        )
        scenario.update(
            years=years, calculation=calculation,
            forecast_roes=[row["roe_assumption"] for row in calculation["annual_rows"]],
            forecast_retentions=[row["retention_assumption"] for row in calculation["annual_rows"]],
        )
        payload = package["facts"]["scenario_inputs"][name]
        payload.update(
            scenario_contract=SCENARIO_CONTRACT, years=deepcopy(years),
            forecast_roes=deepcopy(scenario["forecast_roes"]),
            forecast_retentions=deepcopy(scenario["forecast_retentions"]),
        )
        calculations[name] = calculation

    package["descriptor_version"] = DESCRIPTOR_VERSION
    package["run_id"] = spec["run_id"]
    package["dependencies"]["model_version"] = MODEL_VERSION
    package["dependencies"]["rule_version"] = RECEIPT_SCHEMA
    package["facts"]["direct_owner_cash_contract"] = MODEL_VERSION
    package["point_in_time"].update(
        research_as_of=spec["research_as_of"], computed_at=spec["computed_at"],
        available_at=spec["computed_at"],
    )
    package["research_case"].update(
        run_id=spec["run_id"], research_version=spec["research_version"],
        generated_at=spec["computed_at"],
    )
    source_bindings = _append_unique(
        predecessor["source_bindings"], [spec["predecessor_binding"],
                                         *spec["distribution_evidence"].values(), spec_binding],
    )
    package["source_contract"] = deepcopy(package["source_contract"])
    package["source_contract"].update(
        schema_version=RECEIPT_SCHEMA, spec_sha256=spec_binding["sha256"],
        raw_source_bindings=source_bindings,
        implemented_distribution=deepcopy(distribution),
    )
    outcome, descriptor = run_direct_owner_cash_research(package, computed, root=root)
    if outcome.valuation is None or outcome.valuation.status != "conditional_research_only":
        raise ValueError("OWNER_DISTRIBUTION_SHARED_MODEL_NOT_CONSUMED:" + str(outcome.blockers))
    valuation = json.loads(outcome.valuation.to_json())
    actual = valuation["assumptions"]["scenario_calculations"]
    if actual != calculations:
        raise ValueError("OWNER_DISTRIBUTION_SHARED_MODEL_CALCULATION_CHANGED")
    for name in ("bear", "base", "bull"):
        rows = actual[name]["annual_rows"]
        if (rows[0]["scheduled_owner_distribution_cny"] != scheduled
                or any(row["scheduled_owner_distribution_cny"] != "0" for row in rows[1:])):
            raise ValueError("OWNER_DISTRIBUTION_CROSS_SCENARIO_FACT_CHANGED")
    serialized = _serialize_outcome(outcome)
    return {
        "schema_version": RECEIPT_SCHEMA, "symbol": predecessor["symbol"],
        "action": "no_order", "formal_eligibility": False,
        "successor_adopted": False, "main_range_adopted": False,
        "predecessor_binding": spec["predecessor_binding"], "spec_binding": spec_binding,
        "distribution": distribution, "distribution_evidence": spec["distribution_evidence"],
        "input_descriptor_sha256": descriptor.input_sha256,
        "valuation": valuation, "compiled": compiled,
        "research_case": package["research_case"], "package": package,
        "research_result": serialized, "source_bindings": source_bindings,
    }


def build_parent_owner_distribution_successor(
    *, root: Path, spec_binding: Mapping[str, str], output_dir: Path, now: datetime,
) -> dict[str, Any]:
    root = Path(root).resolve()
    output = require_inside(root / "runtime", Path(output_dir).resolve(), "owner distribution output")
    if output.exists():
        raise FileExistsError("OWNER_DISTRIBUTION_NEW_OUTPUT_REQUIRED")
    result = _recalculate(root=root, spec_binding=spec_binding, now=now)
    result_binding = _write(root, output / "result.json", result)
    receipt = {
        "schema_version": RECEIPT_SCHEMA, "symbol": result["symbol"], "action": "no_order",
        "formal_eligibility": False, "successor_adopted": False,
        "main_range_adopted": False, "predecessor_binding": result["predecessor_binding"],
        "spec_binding": dict(spec_binding), "result_binding": result_binding,
        "input_descriptor_sha256": result["input_descriptor_sha256"],
        "source_bindings": result["source_bindings"],
        "implementation_sha256": _implementations(),
    }
    receipt_binding = _write(root, output / "receipt.json", receipt)
    replay_parent_owner_distribution_successor(root=root, receipt_binding=receipt_binding, now=now)
    return {"receipt_binding": receipt_binding, "result": result}


def replay_parent_owner_distribution_successor(
    *, root: Path, receipt_binding: Mapping[str, str], now: datetime,
) -> dict[str, Any]:
    root = Path(root).resolve()
    receipt = _read(root, receipt_binding)
    if (receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False
            or receipt.get("successor_adopted") is not False
            or receipt.get("main_range_adopted") is not False
            or receipt.get("implementation_sha256") != _implementations()):
        raise ValueError("OWNER_DISTRIBUTION_RECEIPT_VERSION_INVALID")
    expected = _recalculate(root=root, spec_binding=receipt["spec_binding"], now=now)
    stored = _read(root, receipt["result_binding"])
    if (_bytes(_stable(stored)) != _bytes(_stable(expected))
            or receipt["symbol"] != expected["symbol"]
            or receipt["predecessor_binding"] != expected["predecessor_binding"]
            or receipt["source_bindings"] != expected["source_bindings"]
            or receipt["input_descriptor_sha256"] != expected["input_descriptor_sha256"]):
        raise ValueError("OWNER_DISTRIBUTION_COLD_REPLAY_CHANGED")
    return stored

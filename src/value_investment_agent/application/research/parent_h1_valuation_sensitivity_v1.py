"""Recompute an E1 H1 research sensitivity from an exact predecessor."""

from datetime import date
from pathlib import Path

from .direct_owner_cash_research_v1 import _read
from .first_research_input_v1 import replay_first_research_input
from .parent_h1_successor_basis_v1 import prepare_parent_h1_successor
from ...domain.valuation.direct_parent_half_year_cash_v1 import value_parent_half_year_cash
from ...domain.valuation.parent_cash_policy import _number


def replay_parent_h1_valuation_sensitivity(*, root: Path, predecessor_binding: dict,
                                           assumptions_binding: dict, now, share_evidence_binding: dict | None = None) -> dict:
    root = Path(root).resolve()
    assumptions = _read(root, assumptions_binding)
    if (assumptions.get("schema_version") != "parent-h1-sensitivity-input-v1"
            or assumptions.get("action") != "no_order"
            or assumptions.get("predecessor_binding") != predecessor_binding
            or set(assumptions.get("scenarios", {})) != {"bear", "base", "bull"}):
        raise ValueError("PARENT_H1_SENSITIVITY_INPUT_INVALID")
    basis = prepare_parent_h1_successor(
        root=root, predecessor_binding=predecessor_binding,
        period_end=assumptions["period_end"], now=now)
    if (assumptions.get("symbol") != basis["symbol"]
            or assumptions.get("input_descriptor_sha256") != basis["predecessor_input_descriptor_sha256"]):
        raise ValueError("PARENT_H1_SENSITIVITY_BASIS_MISMATCH")
    opening = basis["opening_cash"]
    book_fact = opening["book_equity_fact"]
    if not book_fact or not book_fact.get("source_refs"):
        raise ValueError("PARENT_H1_SENSITIVITY_CAPITAL_FACTS_MISSING")
    share_fact = opening["ordinary_shares_fact"]
    if share_fact is None and share_evidence_binding is not None:
        replay = replay_first_research_input(root=root, receipt_binding=share_evidence_binding, now=now)
        package = _read(root, replay["package_binding"])
        receipt = _read(root, share_evidence_binding)
        original_spec = _read(root, receipt["spec_binding"])
        native_binding = original_spec["native_facts_binding"]
        if native_binding not in replay["source_bindings"]:
            raise ValueError("PARENT_H1_SHARE_EVIDENCE_BASIS_MISMATCH")
        native = _read(root, native_binding)
        verified_source_ids = {ref["id"] for ref in native["sources"]
                               if ref["sha256"] == book_fact["source_refs"]["sha256"]}
        verified_shares = [row for row in native["facts"] if row["field"] == "ordinary_shares"
                           and row["scope"] == "issued_ordinary_shares" and row["unit"] == "shares"
                           and row["period_end"] == basis["period_end"]
                           and row["source_id"] in verified_source_ids]
        if (package["symbol"] != basis["symbol"]
                or package["point_in_time"]["valuation_date"] != basis["period_end"]
                or len(verified_shares) != 1
                or verified_shares[0]["value"] != package["facts"]["operating_inputs"]["ordinary_shares"]):
            raise ValueError("PARENT_H1_SHARE_EVIDENCE_BASIS_MISMATCH")
        share_fact = dict(count=verified_shares[0]["value"], period_end=basis["period_end"],
                          scope="TOTAL_ISSUED_ORDINARY_SHARES", source_refs=[native_binding])
    if (not share_fact or share_fact.get("period_end") != basis["period_end"]
            or share_fact.get("scope") != "TOTAL_ISSUED_ORDINARY_SHARES"
            or not share_fact.get("source_refs")):
        raise ValueError("PARENT_H1_SENSITIVITY_CAPITAL_FACTS_MISSING")
    day = date.fromisoformat(basis["period_end"])
    results = {}
    for name, scenario in assumptions["scenarios"].items():
        if (scenario.get("classification") != "FORECAST_ASSUMPTION"
                or any(not isinstance(scenario.get(key), str) or not scenario[key].strip()
                       for key in ("rationale", "counter_evidence", "reopen_condition"))
                or not scenario.get("evidence_bindings")):
            raise ValueError("PARENT_H1_EXPLICIT_CONDITIONAL_ASSUMPTIONS_REQUIRED")
        for ref in scenario["evidence_bindings"]:
            _read(root, ref)
        inputs = scenario["cash_inputs"]
        if _number(inputs["opening"]["cash"]) != _number(basis["opening_cash"]["forward_opening_cash_cny"]):
            raise ValueError("PARENT_H1_SENSITIVITY_OPENING_CASH_MISMATCH")
        if (_number(inputs["opening"]["book"]) != _number(book_fact["current"])
                or _number(inputs["ordinary_shares"]) != _number(share_fact["count"])):
            raise ValueError("PARENT_H1_SENSITIVITY_CAPITAL_BASIS_MISMATCH")
        try:
            valuation = value_parent_half_year_cash(
                valuation_date=day, first_period_start=date(day.year, 7, 1),
                first_period_end=date(day.year, 12, 31),
                minimum_distribution_by_year={int(year): amount for year, amount in
                                              scenario.get("minimum_distribution_by_year", {}).items()},
                **inputs)
        except ValueError as error:
            results[name] = dict(status="SCENARIO_REJECTED", reason=str(error))
        else:
            results[name] = dict(status="CONDITIONAL_SENSITIVITY_COMPUTED", valuation=valuation)
    return dict(status="RESEARCH_SENSITIVITY_NOT_ADOPTED", symbol=basis["symbol"],
                predecessor_binding=dict(predecessor_binding), assumptions_binding=dict(assumptions_binding),
                period_end=day.isoformat(), scenarios=results, share_evidence_binding=share_evidence_binding,
                formal_eligibility=False, main_range_adopted=False, condition_price=None, action="no_order")

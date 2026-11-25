"""Source-bound aggregate capex adapter for the frozen V2 cash calculation."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

from ...domain.valuation import direct_parent_owner_cash_v1 as legacy
from ...domain.valuation import direct_parent_owner_cash_v2 as arithmetic
from ...domain.valuation.parent_cash_policy import _number
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import require_inside
from .agent_review.quarterly_parent_cash_source import replay_quarterly_parent_cash

VERSION = "direct-owner-gross-capex-v1"
_SPLIT = {"maintenance_capex", "growth_capex"}
_TOTAL = "gross_capex_cny"
_TRACE_FIELDS = {"classification", "condition", "investment_profit_link", "counter_evidence",
                 "reopen_condition", "source_refs"}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _verify_trace(root, trace, as_of, checked, *, terminal):
    fields = _TRACE_FIELDS | ({"stationary_reinvestment"} if terminal else set())
    if (not isinstance(trace, dict) or set(trace) != fields
            or trace["classification"] != "FORECAST_ASSUMPTION"
            or any(not isinstance(trace[key], str) or not trace[key].strip()
                   for key in fields - {"classification", "source_refs"})):
        raise ValueError("GROSS_CAPEX_CONDITION_TRACE_REQUIRED")
    refs = trace["source_refs"]
    if not isinstance(refs, list) or not refs:
        raise ValueError("GROSS_CAPEX_CONDITION_SOURCE_REQUIRED")
    for ref in refs:
        if (not isinstance(ref, dict) or set(ref) !=
                {"path", "sha256", "available_at", "physical_page", "excerpt"}
                or any(not isinstance(ref[key], str) or not ref[key].strip()
                       for key in ref.keys() - {"physical_page"})
                or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"])
                or type(ref["physical_page"]) is not int or ref["physical_page"] < 1):
            raise ValueError("GROSS_CAPEX_CONDITION_SOURCE_INVALID")
        available = datetime.fromisoformat(ref["available_at"])
        if available.utcoffset() is None or available > as_of:
            raise ValueError("GROSS_CAPEX_CONDITION_SOURCE_UNAVAILABLE")
        key = (ref["path"], ref["sha256"])
        if key not in checked:
            path = require_inside(root / "runtime", root / ref["path"], "gross capex source")
            if sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
                raise ValueError("GROSS_CAPEX_CONDITION_SOURCE_CHANGED")
            checked[key] = ["".join(page.split()) for page in extract_pages(path)]
            if sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
                raise ValueError("GROSS_CAPEX_CONDITION_SOURCE_CHANGED")
        pages = checked[key]
        if (ref["physical_page"] > len(pages)
                or "".join(ref["excerpt"].split()) not in pages[ref["physical_page"] - 1]):
            raise ValueError("GROSS_CAPEX_CONDITION_EXCERPT_INVALID")


def compute_gross_capex_receipt(*, root, scenario, symbol, issuer_name, first_year_source, as_of):
    """Return a conditional arithmetic receipt. Source traces remain assumptions."""
    root = Path(root).resolve()
    if as_of.utcoffset() is None:
        raise ValueError("GROSS_CAPEX_CUTOFF_REQUIRED")
    if set(scenario) != {"opening", "years", "terminal", "ordinary_shares",
                         "cost_of_equity", "scope", "currency", "countercase"} or not scenario["years"]:
        raise ValueError("GROSS_CAPEX_SCENARIO_INVALID")
    if scenario["scope"] != arithmetic.SCOPE or scenario["currency"] != "CNY":
        raise ValueError("GROSS_CAPEX_PARENT_CNY_REQUIRED")
    first_year = scenario["years"][0]["year"]
    if type(first_year) is not int or not 1 <= first_year <= 9999:
        raise ValueError("GROSS_CAPEX_FIRST_YEAR_INVALID")
    period_end = f"{first_year:04d}-09-30"
    facts = replay_quarterly_parent_cash(root=root, source=first_year_source, symbol=symbol,
                                        issuer_name=issuer_name, period_end=period_end, now=as_of)
    actual = facts["fields"]["cash_capex"]
    if actual["scope"] != arithmetic.SCOPE or actual["currency"] != "CNY":
        raise ValueError("GROSS_CAPEX_FIRST_YEAR_SOURCE_SCOPE_INVALID")
    minimum = _number(actual["current"])
    if minimum < 0:
        raise ValueError("GROSS_CAPEX_FIRST_YEAR_SOURCE_AMOUNT_INVALID")

    model_inputs = deepcopy(scenario)
    countercase = model_inputs.pop("countercase")
    checked = {}
    for row, terminal in [(row, False) for row in model_inputs["years"]] + [
            (model_inputs["terminal"], True)]:
        policy = row["policy"]
        if set(policy) != (legacy.FLOW_KEYS - _SPLIT) | {_TOTAL}:
            raise ValueError("GROSS_CAPEX_EXCLUSIVE_TOTAL_REQUIRED")
        _verify_trace(root, row.pop("capex_trace", None), as_of, checked, terminal=terminal)
        total = _number(policy.pop(_TOTAL))
        if not terminal and row["year"] == first_year and total < minimum:
            raise ValueError("GROSS_CAPEX_BELOW_FIRST_YEAR_REALIZED")
        if total < 0:
            raise ValueError("GROSS_CAPEX_NEGATIVE")
        # Private arithmetic slots only. Neither slot is a capex classification.
        policy.update(maintenance_capex=str(total), growth_capex="0")

    result = arithmetic.compile_direct_owner_cash_path_v2(**model_inputs)
    if (not isinstance(countercase, dict)
            or set(countercase) != {"operating_cash_cny", "parent_profit_cny"}):
        raise ValueError("GROSS_CAPEX_COUNTERCASE_REQUIRED")
    terminal_policy = model_inputs["terminal"]["policy"]
    for field, value in countercase.items():
        key = field.removesuffix("_cny")
        amount = _number(value)
        if not 0 <= amount < _number(terminal_policy[key]):
            raise ValueError("GROSS_CAPEX_COUNTERCASE_NOT_ADVERSE")
        terminal_policy[key] = str(amount)
    try:
        stress = arithmetic.compile_direct_owner_cash_path_v2(**model_inputs)
    except ValueError as exc:
        counter_result = dict(status="BLOCKED", reason=str(exc))
    else:
        counter_result = dict(status="COMPUTED", per_share_value=stress["per_share_value"],
                              steady_distribution_cny=stress["terminal_steady_distribution_cny"])

    for row in result["annual_rows"] + result["terminal_rows"]:
        policy = row["cash_policy"]
        policy[_TOTAL] = policy.pop("maintenance_capex")
        del policy["growth_capex"]
        row["capex_allocation"] = "UNALLOCATED"
    return dict(
        schema_version=VERSION, action="no_order", formal_eligibility=False,
        classification="CONDITIONAL_RESEARCH_ARITHMETIC",
        as_of=as_of.isoformat(), symbol=symbol, issuer_name=issuer_name,
        scenario=deepcopy(scenario), capex_allocation="UNALLOCATED",
        first_year_source=deepcopy(first_year_source),
        first_year_floor=dict(period_end=period_end, gross_capex_cny=str(minimum),
                              scope=actual["scope"], currency=actual["currency"],
                              physical_page=actual["physical_page"], excerpt=actual["excerpt"]),
        implementation_sha256={
            module.stem: sha256(module.read_bytes()).hexdigest()
            for module in map(Path, (__file__, arithmetic.__file__, legacy.__file__))
        },
        countercase_result=counter_result, calculation=result,
    )


def replay_gross_capex_receipt(*, root, receipt, now):
    """Recheck evidence at the original cutoff and compare the complete receipt."""
    if receipt.get("schema_version") != VERSION:
        raise ValueError("GROSS_CAPEX_RECEIPT_VERSION_INVALID")
    as_of = datetime.fromisoformat(receipt["as_of"])
    if now.utcoffset() is None or as_of.utcoffset() is None or as_of > now:
        raise ValueError("GROSS_CAPEX_RECEIPT_CUTOFF_INVALID")
    rebuilt = compute_gross_capex_receipt(
        root=root, scenario=receipt["scenario"], symbol=receipt["symbol"],
        issuer_name=receipt["issuer_name"], first_year_source=receipt["first_year_source"], as_of=as_of,
    )
    if _canonical(rebuilt) != _canonical(receipt):
        raise ValueError("GROSS_CAPEX_RECEIPT_REPLAY_MISMATCH")
    return rebuilt


WIRE_VERSION = "parent-gross-capex-wire-v1"


def load_wire_plan(root, pin, *, source_fingerprint, as_of):
    if (not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
            or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
        raise ValueError("GROSS_CAPEX_PLAN_BINDING_INVALID")
    root = Path(root).resolve()
    path = require_inside(root / "runtime", root / pin["path"], "gross capex plan")
    if path.stat().st_size > 262144:
        raise ValueError("GROSS_CAPEX_PLAN_TOO_LARGE")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("GROSS_CAPEX_PLAN_CHANGED")
    plan = json.loads(raw)
    if (set(plan) != {"schema_version", "source_fingerprint", "years", "terminal", "countercase"}
            or plan["schema_version"] != WIRE_VERSION
            or plan["source_fingerprint"] != source_fingerprint
            or not isinstance(plan["years"], list) or not plan["years"]):
        raise ValueError("GROSS_CAPEX_PLAN_SOURCE_OR_VERSION_INVALID")
    checked = {}
    for row in plan["years"]:
        if set(row) != {"year", _TOTAL, "capex_trace"} or type(row["year"]) is not int:
            raise ValueError("GROSS_CAPEX_PLAN_YEAR_INVALID")
        if _number(row[_TOTAL]) < 0:
            raise ValueError("GROSS_CAPEX_NEGATIVE")
        _verify_trace(root, row["capex_trace"], as_of, checked, terminal=False)
    tail = plan["terminal"]
    if set(tail) != {_TOTAL, "capex_trace"} or _number(tail[_TOTAL]) < 0:
        raise ValueError("GROSS_CAPEX_PLAN_TERMINAL_INVALID")
    _verify_trace(root, tail["capex_trace"], as_of, checked, terminal=True)
    if set(plan["countercase"]) != {"operating_cash_cny", "parent_profit_cny"}:
        raise ValueError("GROSS_CAPEX_COUNTERCASE_REQUIRED")
    if any(_number(value) < 0 for value in plan["countercase"].values()):
        raise ValueError("GROSS_CAPEX_COUNTERCASE_NOT_ADVERSE")
    return plan


def aggregate_wire(wire, stage, plan, pin):
    """
    Remove private V2 capex slots from the request and expose the locked schedule.
    """
    def project(value):
        if isinstance(value, list):
            return [project(item) for item in value if item != "growth_capex"]
        if isinstance(value, dict):
            return {("gross_capex_cny" if key == "maintenance_capex" else key): project(item)
                    for key, item in value.items() if key != "growth_capex"}
        if value == "maintenance_capex":
            return _TOTAL
        return value

    payload = project(json.loads(wire.user))
    positions = plan["years"]
    if stage == "policy" and [row["year"] for row in positions] != payload["required_years"]:
        raise ValueError("GROSS_CAPEX_PLAN_HORIZON_MISMATCH")
    floor = payload["source_context"].get("annual_capex_floor")
    if (floor is None or floor["year"] != positions[0]["year"]
            or floor["symbol"] != payload["source_context"]["symbol"]
            or floor["scope"] != arithmetic.SCOPE or floor["currency"] != "CNY"):
        raise ValueError("GROSS_CAPEX_PLAN_FIRST_YEAR_SOURCE_REQUIRED")
    if _number(positions[0][_TOTAL]) < _number(floor["minimum_cny"]):
        raise ValueError("GROSS_CAPEX_BELOW_FIRST_YEAR_REALIZED")
    payload["gross_capex_contract"] = dict(version=WIRE_VERSION, binding=pin,
        allocation="UNALLOCATED", accepted=positions if stage == "policy" else plan["terminal"])
    # Preserve the original response grammar apart from the exclusive capex field.
    contract = wire.transport_output_contract
    for expression in ("maintenance_capex and growth_capex", "maintenance_capex + growth_capex",
                       "maintenance_capex - growth_capex", "maintenance_capex, growth_capex"):
        contract = contract.replace(expression, _TOTAL)
    contract = contract.replace("maintenance_capex", _TOTAL).replace("growth_capex", _TOTAL)
    return replace(wire, user=_canonical(payload), output_schema=project(wire.output_schema),
        transport_output_contract=contract + " Echo the exact locked gross_capex_cny amounts "
        "in period order. Allocation is UNALLOCATED. Treat the trace as conditional research. "
        "Link the amounts to the operating and profit assumptions and retain contrary evidence.")


def private_legacy_response(response, stage, plan, *, flat_terminal):
    from .direct_owner_cash_staged_v2 import _identical_prose_duplicate_only

    if response.tool_calls:
        raise ValueError("GROSS_CAPEX_TOOL_CALL_FORBIDDEN")
    data = json.loads(response.text, object_pairs_hook=_identical_prose_duplicate_only)
    if stage == "policy":
        policy = data["series"]
        expected = [row[_TOTAL] for row in plan["years"]]
    else:
        policy = data["policy"] if flat_terminal else data["terminal"]["policy"]
        expected = [plan["terminal"][_TOTAL]]
    if _SPLIT.intersection(policy) or _TOTAL not in policy:
        raise ValueError("GROSS_CAPEX_EXCLUSIVE_TOTAL_REQUIRED")
    total = policy.pop(_TOTAL)
    scalar = "value" in total
    values = [total["value"]] if scalar else total["values"]
    if list(map(_number, values)) != list(map(_number, expected)):
        raise ValueError("GROSS_CAPEX_LOCKED_TOTAL_CHANGED")
    policy["maintenance_capex"] = total
    policy["growth_capex"] = dict(total, **({"value": "0"} if scalar else {"values": ["0"] * len(values)}))
    return replace(response, text=_canonical(data))


def compile_aggregate_e2(root, legacy_candidate, plan, *, pin, source, as_of):
    """Project the frozen compiler result through the aggregate replay contract."""
    candidate = legacy_candidate
    base = candidate["compiled"]["scenarios"]["base"]
    inputs = deepcopy({key: base[key] for key in ("opening", "years", "terminal", "ordinary_shares",
                                                  "cost_of_equity", "scope", "currency")})
    for row, locked in zip(inputs["years"] + [inputs["terminal"]],
                           plan["years"] + [plan["terminal"]], strict=True):
        policy = row["policy"]
        total = _number(policy.pop("maintenance_capex")) + _number(policy.pop("growth_capex"))
        if total != _number(locked[_TOTAL]):
            raise ValueError("GROSS_CAPEX_E2_TOTAL_CHANGED")
        policy[_TOTAL] = str(total)
        row["capex_trace"] = deepcopy(locked["capex_trace"])
    inputs["countercase"] = deepcopy(plan["countercase"])
    spec = candidate["candidate_spec"]
    receipt = compute_gross_capex_receipt(root=root, scenario=inputs, symbol=spec["symbol"],
        issuer_name=spec["issuer_name"], first_year_source=source, as_of=as_of)

    legacy = deepcopy(base["calculation"])
    for row in legacy["annual_rows"] + legacy["terminal_rows"]:
        policy = row["cash_policy"]
        policy[_TOTAL] = str(_number(policy.pop("maintenance_capex")) + _number(policy.pop("growth_capex")))
        row["capex_allocation"] = "UNALLOCATED"
    if _canonical(legacy) != _canonical(receipt["calculation"]):
        raise ValueError("GROSS_CAPEX_FROZEN_CONSUMER_MISMATCH")
    return dict(schema_version=WIRE_VERSION, action="no_order", formal_eligibility=False,
        main_range_adopted=False, publication_status="LEGACY_F1_RECEIPT_NOT_APPLICABLE",
        symbol=spec["symbol"], source_fingerprint=candidate["source_fingerprint"],
        scenario_draft_sha256=deepcopy(candidate["scenario_draft_sha256"]),
        gross_capex_plan_binding=deepcopy(pin), aggregate_base_receipt=receipt,
        other_scenarios={name: deepcopy(row["calculation"])
                         for name, row in candidate["compiled"]["scenarios"].items() if name != "base"})

"""Versioned source dispatch for the immutable V2 compiler and V3 policy preflight.

The three function bodies retain the native draft, annual preflight and compiler
equations. Only their source selection and compiler identity differ.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path

from .direct_owner_cash_compilation_v2 import (
    SCHEMA, _number, _explanation, _reserve_annual_cash_before_optional_payout, financing_maturity_floor,
)
from .direct_owner_cash_agent_draft_v2 import (
    VERSION as DRAFT_VERSION, SCENARIOS, HORIZON, DRIVERS, SERIES, POLICY, TERMINAL_POLICY,
    _canonical, _load_spec, _term,
)
from .direct_owner_cash_staged_v3 import (
    POLICY_MONEY_WIRE, _annual_operating_cash, _post_observation_repayment_floor, validate_policy_money_wire,
)
from .parent_note_grid_sources_v1 import VERSION
from .parent_note_grid_task_inputs_v1 import read_evidence, task_context
from ...domain.valuation.parent_direct_operating_cash import forecast_parent_operating_cash, SCOPE
from ...domain.valuation.direct_parent_owner_cash_v1 import FLOW_KEYS
from ...domain.valuation.direct_parent_owner_cash_v2 import compile_direct_owner_cash_path_v2
from .fresh_issuer_distribution_v1 import apply_fresh_issuer_distribution


def preflight_annual_cash_upper_bound_v3(*, root: Path, spec_binding: dict,
                                         evaluated_at, context: dict,
                                         operating: dict, policy: dict) -> None:
    """Reject a deficit even with zero shareholder payout, using real FY cash.

    This necessary check does not establish refinancing, legal distributability,
    executable price or formal investment qualification.
    """
    spec = _load_spec(Path(root).resolve(), spec_binding)
    basis = context["valuation_date"]
    if basis != spec["valuation_date"] or context["symbol"] != spec["symbol"]:
        raise ValueError("PARENT_V3_CONTEXT_IDENTITY_MISMATCH")
    history = [row for row in context["parent_operating_cash_observations"]
               if row["period_end"] == basis and row["period_start"] == basis[:4] + "-01-01"]
    if len(history) != 1 or context.get("spec_binding") != spec_binding:
        raise ValueError("NOTE_GRID_ANNUAL_OPERATING_HISTORY_MISMATCH")
    historical = history[0]
    opening_id = context["opening_fact_anchors"]["cash"]
    if spec.get("opening", {}).get("cash") != {
            "classification": "FACT", "anchor": opening_id}:
        raise ValueError("PARENT_V3_OPENING_CASH_SCOPE_INVALID")
    opening = context["facts"][opening_id]
    if (opening.get("field") != "closing_cash_and_equivalents_cny"
            or opening.get("period_end") != basis or opening.get("scope") != SCOPE):
        raise ValueError("PARENT_V3_OPENING_CASH_SCOPE_INVALID")
    if context.get("policy_money_wire") == POLICY_MONEY_WIRE:
        validate_policy_money_wire(policy)
    if operating["years"] != policy["years"]:
        raise ValueError("PARENT_V3_YEAR_MISMATCH")
    # Annual forecasts cover the full calendar year. A known interim parent
    # cash movement within that year is a hard floor, not a future estimate.
    for observation in context.get("historical_financing_observations", []):
        cash = observation["financing_cash_flows"]
        period = cash["period_end"]
        year = int(period[:4])
        if (year not in policy["years"] or cash["period_start"] != f"{year}-01-01"
                or period == f"{year}-12-31"):
            continue
        index = policy["years"].index(year)
        for observed_field, forecast_field in (
            ("borrowings_received_cny", "new_borrowing"),
            ("debt_repayments_paid_cny", "debt_repayment"),
        ):
            movement = cash["components"][observed_field]
            if (context.get("policy_money_wire") == POLICY_MONEY_WIRE
                    and (context.get("constraints") or {}).get("issued_financing")
                    and forecast_field == "debt_repayment" and period.endswith("-09-30")
                    and movement["classification"] == "FACT"
                    and Decimal(policy["series"][forecast_field]["values"][index])
                    < _post_observation_repayment_floor(context, year, period, movement["value_cny"])):
                raise ValueError(f"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:{year}:{forecast_field}")
            if (movement["classification"] == "FACT"
                    and Decimal(policy["series"][forecast_field]["values"][index])
                    < Decimal(movement["value_cny"])):
                raise ValueError(
                    f"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:{year}:{forecast_field}")
    capex_floor = context.get("annual_capex_floor")
    if capex_floor and capex_floor["year"] in policy["years"]:
        year = capex_floor["year"]
        index = policy["years"].index(year)
        capex = sum(Decimal(policy["series"][field]["values"][index])
                    for field in ("maintenance_capex", "growth_capex"))
        if capex < Decimal(capex_floor["minimum_cny"]):
            raise ValueError(f"PARENT_V3_ANNUAL_CAPEX_BELOW_REALISED_CASH:{year}")
    receipts_floor = context.get("annual_investment_receipts_floor")
    if receipts_floor and receipts_floor["year"] in policy["years"]:
        year = receipts_floor["year"]
        index = policy["years"].index(year)
        if Decimal(policy["series"]["investment_cash_received"]["values"][index]) < Decimal(
                receipts_floor["minimum_cny"]):
            raise ValueError(f"PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_BELOW_REALISED_CASH:{year}")
    interest_floor = context.get("annual_paid_note_interest_floor")
    if interest_floor and interest_floor["year"] in policy["years"]:
        year = interest_floor["year"]
        index = policy["years"].index(year)
        if Decimal(policy["series"]["interest_outside_cfo"]["values"][index]) < Decimal(
                interest_floor["minimum_cny"]):
            raise ValueError(f"PARENT_V3_ANNUAL_INTEREST_BELOW_REALISED_CASH:{year}")
    mandatory = ("maintenance_capex", "growth_capex", "commitments_outside_capex",
                 "debt_repayment", "interest_outside_cfo", "other_mandatory_cash")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        cash = Decimal(opening["value_cny"])
        for index, year in enumerate(operating["years"]):
            cfo = _annual_operating_cash(historical, context, operating, index, year,
                                         root=root, spec=spec, now=evaluated_at)
            amounts = {field: Decimal(term["values"][index])
                       for field, term in policy["series"].items()}
            if any(value < 0 for value in amounts.values()):
                raise ValueError("PARENT_V3_NEGATIVE_POLICY_AMOUNT")
            cash += (cfo + amounts["investment_cash_received"]
                     + amounts["new_borrowing"]
                     - sum(amounts[field] for field in mandatory))
            event = context["implemented_distribution"]["distribution"]
            if year == date.fromisoformat(event["paid_date"]).year:
                cash -= Decimal(event["total_cny"])
            if cash < amounts["cash_floor"]:
                raise ValueError(f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}")


def assemble_parent_cash_drafts_v2(*, root: Path, spec_binding: dict, drafts: dict,
                                   generated_at: datetime, implemented_distribution=None) -> dict:
    """Return an unapproved source-bound E2 candidate with all three paths.

    A caller must separately retain the raw model responses, provider usage and
    request fingerprints through the existing D1 task store before publication.
    """
    root = Path(root).resolve()
    if generated_at.utcoffset() is None or set(drafts) != set(SCENARIOS):
        raise ValueError("PARENT_DRAFT_CLOCK_OR_SCENARIOS_INVALID")
    context = task_context(root=root, spec_binding=spec_binding,
                                              now=generated_at)
    if context["valuation_date"] != context["facts"]["revenue"]["period_end"]:
        raise ValueError("PARENT_DRAFT_OPERATING_HISTORY_PERIOD_INVALID")
    spec = deepcopy(_load_spec(root, spec_binding))
    spec["scenarios"] = {}
    shares = context["ordinary_shares"]
    if (shares["period_end"] != context["valuation_date"]
            or shares["classification"] not in {"FACT", "DERIVED_FACT"}):
        raise ValueError("PARENT_DRAFT_DATED_SHARES_INVALID")
    spec["ordinary_shares"] = dict(classification=shares["classification"],
                                    period_end=shares["period_end"])
    anchors = set(context["facts"])
    first_year = int(context["valuation_date"][:4]) + 1
    expected_years = list(range(first_year, first_year + HORIZON))
    history_start = context["valuation_date"][:4] + "-01-01"
    for scenario in SCENARIOS:
        draft = drafts[scenario]
        if (not isinstance(draft, dict)
                or set(draft) != {"schema_version", "scenario", "source_fingerprint",
                                  "years", "annual_notes", "series", "terminal",
                                  "cost_of_equity", "rationale", "counter_evidence",
                                  "reopen_condition"}
                or draft["schema_version"] != DRAFT_VERSION or draft["scenario"] != scenario
                or draft["source_fingerprint"] != context["input_fingerprint"]
                or draft["years"] != expected_years
                or set(draft["series"]) != SERIES):
            raise ValueError("PARENT_DRAFT_SOURCE_OR_HORIZON_INVALID:" + scenario)
        notes = draft["annual_notes"]
        if (not isinstance(notes, list) or len(notes) != HORIZON
                or any(not isinstance(note, str) or len(note.strip()) < 12
                       for note in notes)):
            raise ValueError("PARENT_DRAFT_ANNUAL_MECHANISM_REQUIRED")
        for key in ("rationale", "counter_evidence", "reopen_condition"):
            if not isinstance(draft[key], str) or len(draft[key].strip()) < 12:
                raise ValueError("PARENT_DRAFT_SCENARIO_EXPLANATION_REQUIRED")
        vectors = {name: _term(value, anchors, count=HORIZON, note="")
                   for name, value in draft["series"].items()}
        annual = []
        for index, year in enumerate(expected_years):
            driver = dict(historical_start=history_start,
                          historical_end=context["valuation_date"],
                          rationale=draft["rationale"] + " " + notes[index],
                          counter_evidence=draft["counter_evidence"],
                          reopen_condition=draft["reopen_condition"])
            for name in DRIVERS:
                row = deepcopy(vectors[name][index])
                row["rationale"] += " " + notes[index]
                driver[name] = row
            policy = {}
            for name in POLICY:
                row = deepcopy(vectors[name][index])
                row["rationale"] += " " + notes[index]
                policy[name] = row
            annual.append(dict(year=year, operating_forecast=driver, policy=policy))
        terminal = draft["terminal"]
        if (not isinstance(terminal, dict)
                or set(terminal) != {"policy", "remaining_scheduled_events",
                                     "max_transition_years", "financing",
                                     "rationale", "counter_evidence", "reopen_condition"}
                or set(terminal["policy"]) != TERMINAL_POLICY
                or not isinstance(terminal["remaining_scheduled_events"], list)
                or type(terminal["max_transition_years"]) is not int):
            raise ValueError("PARENT_DRAFT_TERMINAL_CONTRACT_INVALID")
        for key in ("rationale", "counter_evidence", "reopen_condition"):
            if not isinstance(terminal[key], str) or len(terminal[key].strip()) < 12:
                raise ValueError("PARENT_DRAFT_TERMINAL_EXPLANATION_REQUIRED")
        tail = {key: terminal[key] for key in ("remaining_scheduled_events",
            "max_transition_years", "rationale", "counter_evidence", "reopen_condition")}
        tail["policy"] = {name: _term(value, anchors, count=1, note="")[0]
                          for name, value in terminal["policy"].items()}
        if terminal["financing"] is not None:
            tail["financing"] = terminal["financing"]
        spec["scenarios"][scenario] = dict(
            rationale=draft["rationale"], counter_evidence=draft["counter_evidence"],
            reopen_condition=draft["reopen_condition"],
            cost_of_equity=_term(draft["cost_of_equity"], anchors, count=1, note="")[0],
            years=annual, terminal=tail)
    # Existing compiler reopens the originals and enforces all cash, debt,
    # distribution and terminal equations. Its rejection is never bypassed.
    distribution_input = ({"implemented_distribution": implemented_distribution}
                          if implemented_distribution is not None else {})
    compiled = compile_source_bound_owner_cash_v2(
        root=root, spec=spec, now=generated_at, **distribution_input)
    return dict(schema_version=DRAFT_VERSION, symbol=context["symbol"],
        source_fingerprint=context["input_fingerprint"],
        scenario_draft_sha256={name: hashlib.sha256(_canonical(drafts[name])).hexdigest()
                               for name in SCENARIOS},
        candidate_spec=spec, compiled=compiled, action="no_order",
        formal_eligibility=False, main_range_adopted=False)


def compile_source_bound_owner_cash_v2(*, root, spec, now, implemented_distribution=None):
    """Reparse pinned financial originals and recompute all annual cash inputs."""
    if (spec.get("schema_version") != SCHEMA or spec.get("action") != "no_order"
            or spec.get("currency") != "CNY" or spec.get("scope") != SCOPE):
        raise ValueError("DIRECT_INPUT_SPEC_CONTRACT_INVALID")
    if (spec.get("source_adapter_version") != VERSION
            or spec.get("operating_sources") != []):
        raise ValueError("DIRECT_INPUT_NUMBERED_SOURCE_REQUIRED")
    if now.utcoffset() is None:
        raise ValueError("DIRECT_INPUT_AWARE_CLOCK_REQUIRED")
    if not spec["valuation_date"].endswith("-12-31"):
        raise ValueError("DIRECT_INPUT_YEAR_END_BASIS_REQUIRED")
    basis = date.fromisoformat(spec["valuation_date"])
    if basis > now.date():
        raise ValueError("DIRECT_INPUT_FUTURE_BASIS")
    evidence = read_evidence(root=root, spec=spec, now=now)
    distribution = evidence["implemented_distribution"]
    if distribution["receipt_binding"] != implemented_distribution:
        raise ValueError("DIRECT_INPUT_IMPLEMENTED_DISTRIBUTION_MISMATCH")
    observations = []
    fields = {"revenue": ("income", "revenue"),
              "cost": ("income", "cost"),
              "customer_cash": ("cash_flow", "customer_cash_cny"),
              "supplier_cash": ("cash_flow", "supplier_cash_cny"),
              "cfo": ("cash_flow", "cfo_cny")}
    for statement in evidence["statements"]:
        row = dict(symbol=spec["symbol"], scope=SCOPE, currency="CNY",
                   classification="FACT", period_start=statement["period_start"],
                   period_end=statement["period_end"], source_refs=[])
        for field, (section, key) in fields.items():
            try:
                sourced = statement[section][key]
                row[field] = sourced["current"]
                row["source_refs"].append(sourced["source_refs"])
            except (KeyError, TypeError) as error:
                raise ValueError("DIRECT_INPUT_NUMBERED_OPERATING_FACT_MISSING:" + field) from error
        observations.append(row)
    statements = {row["period_end"]: row for row in evidence["statements"]}
    if len(statements) != len(evidence["statements"]):
        raise ValueError("DIRECT_INPUT_DUPLICATE_STATEMENT_PERIOD")
    anchors = {}
    for name, ref in spec["fact_anchors"].items():
        if set(ref) != {"period_end", "section", "field", "column"}:
            raise ValueError("DIRECT_INPUT_ANCHOR_CONTRACT")
        if ref["section"]=="operating":
            matched=[row for row in observations if row["period_end"]==ref["period_end"]]
            if len(matched)!=1 or ref["column"]!="current" or ref["field"] not in {"revenue","cost","customer_cash","supplier_cash","cfo"}:
                raise ValueError("DIRECT_INPUT_OPERATING_ANCHOR_INVALID")
            anchors[name]=_number(matched[0][ref["field"]])
            continue
        if ref["section"] not in {"balance_sheet", "income", "cash_flow"} or ref["column"] not in {"current", "comparative"}:
            raise ValueError("DIRECT_INPUT_ANCHOR_SCOPE")
        row = statements[ref["period_end"]][ref["section"]][ref["field"]]
        anchors[name] = _number(row[ref["column"]])
    explanations = []
    def resolve(value):
        if not isinstance(value, dict):
            raise ValueError("DIRECT_INPUT_EXPLICIT_CLASSIFICATION_REQUIRED")
        kind = value.get("classification")
        if kind == "FACT":
            if set(value) != {"classification", "anchor"}:
                raise ValueError("DIRECT_INPUT_FACT_FIELDS")
            return anchors[value["anchor"]]
        if kind != "FORECAST_ASSUMPTION":
            raise ValueError("DIRECT_INPUT_UNKNOWN_NOT_COMPILED")
        _explanation(value)
        if not isinstance(value.get("evidence_anchors"), list) or not value["evidence_anchors"]:
            raise ValueError("DIRECT_INPUT_ASSUMPTION_ANCHORS_REQUIRED")
        for name in value["evidence_anchors"]:
            if name not in anchors:
                raise ValueError("DIRECT_INPUT_UNKNOWN_ANCHOR")
        explanations.append(value)
        if "linear_terms" in value:
            if not isinstance(value["linear_terms"],list) or not value["linear_terms"]:
                raise ValueError("DIRECT_INPUT_LINEAR_TERMS_REQUIRED")
            return sum(anchors[t["anchor"]] * _number(t["factor"]) for t in value["linear_terms"])
        if "anchor" in value:
            return anchors[value["anchor"]] * _number(value["factor"])
        return _number(value["value"])
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        opening = {key: str(resolve(value)) for key, value in spec["opening"].items()}
        # The accounting opening must be the valuation-date parent's actual equity/cash.
        for key, field in (("book", "book_equity_cny"), ("cash", "closing_cash_and_equivalents_cny")):
            ref = spec["opening"][key]
            if ref.get("classification") != "FACT":
                raise ValueError("DIRECT_INPUT_FACTUAL_OPENING_REQUIRED:" + key)
            anchor = spec["fact_anchors"][ref["anchor"]]
            if (anchor["period_end"] != spec["valuation_date"] or anchor["column"] != "current"
                    or anchor["field"] != field):
                raise ValueError("DIRECT_INPUT_OPENING_DATE_OR_SCOPE_MISMATCH")
        share_spec=spec["ordinary_shares"]
        share_class = share_spec.get("classification") if isinstance(share_spec, dict) else None
        if (share_class not in ("FACT", "DERIVED_FACT")
                or share_spec != {"classification": share_class, "period_end": spec["valuation_date"]}):
            raise ValueError("DIRECT_INPUT_DATED_SHARE_FACT_REQUIRED")
        share_fact=statements[spec["valuation_date"]].get("ordinary_shares_evidence")
        if (not isinstance(share_fact,dict) or share_fact.get("period_end")!=spec["valuation_date"]
                or share_fact.get("unit")!="shares" or share_fact.get("scope")!="TOTAL_ISSUED_ORDINARY_SHARES"
                or share_fact.get("classification") != share_class
                or not share_fact.get("source_refs")):
            raise ValueError("DIRECT_INPUT_SHARE_UNIT_SCOPE_OR_PROOF_MISSING")
        shares=str(_number(share_fact["count"]))
        scenarios, cash_forecasts, payout_reservations = {}, {}, {}
        if set(spec["scenarios"]) != {"bear", "base", "bull"}:
            raise ValueError("DIRECT_INPUT_THREE_SCENARIOS_REQUIRED")
        for name, scenario in spec["scenarios"].items():
            _explanation(scenario)
            rows, operating = [], []
            if not scenario["years"] or scenario["years"][0]["year"] != date.fromisoformat(spec["valuation_date"]).year+1:
                raise ValueError("DIRECT_INPUT_FIRST_YEAR_MUST_FOLLOW_BASIS")
            for item in scenario["years"]:
                year = item["year"]
                if type(year) is not int or year <= date.fromisoformat(spec["valuation_date"]).year:
                    raise ValueError("DIRECT_INPUT_FORECAST_YEAR_AFTER_OPENING_REQUIRED")
                driver = item["operating_forecast"]
                selected = [r for r in observations if r["period_start"] == driver["historical_start"]
                            and r["period_end"] == driver["historical_end"]]
                if len(selected) != 1:
                    raise ValueError("DIRECT_INPUT_UNIQUE_OPERATING_HISTORY_REQUIRED")
                _explanation(driver)
                forecast = dict(
                    symbol=spec["symbol"], scope=SCOPE, currency="CNY",
                    classification="FORECAST_ASSUMPTION",
                    period_start=f"{year}-01-01", period_end=f"{year}-12-31",
                    revenue=str(resolve(driver["revenue"])), cost=str(resolve(driver["cost"])),
                    other_operating_cash=str(resolve(driver["other_operating_cash"])),
                    **{key: driver[key] for key in ("rationale", "counter_evidence", "reopen_condition")})
                if "first_year_operating_cash_method" in spec:
                    from .agent_review.quarterly_parent_cash_source import project_parent_annual_operating_cash
                    prediction = project_parent_annual_operating_cash(
                        root=root, spec=spec, now=now, historical=selected[0], forecast=forecast)
                else:
                    prediction = forecast_parent_operating_cash(historical=selected[0], forecast=forecast)
                if set(item["policy"]) != FLOW_KEYS - {"operating_cash"}:
                    raise ValueError("DIRECT_INPUT_EXACT_OWNER_POLICY_REQUIRED")
                policy = {key: str(resolve(value)) for key,value in item["policy"].items()}
                if (Decimal(policy["debt_repayment"])
                        < financing_maturity_floor(evidence.get("constraints"), year)):
                    raise ValueError("DIRECT_INPUT_FINANCING_MATURITY_UNCOVERED")
                policy["operating_cash"] = prediction["operating_cash"]
                rows.append(dict(year=year,policy=policy)); operating.append(prediction)
            terminal = scenario["terminal"]
            _explanation(terminal)
            terminal_policy = {key: str(resolve(value)) for key,value in terminal["policy"].items()}
            tail = dict(policy=terminal_policy,
                remaining_scheduled_events=terminal["remaining_scheduled_events"],
                rationale=terminal["rationale"], max_transition_years=terminal["max_transition_years"])
            if "financing" in terminal:tail["financing"]=terminal["financing"]
            cost = str(resolve(scenario["cost_of_equity"]))
            scenarios[name] = dict(symbol=spec["symbol"], opening=opening, years=rows, terminal=tail,
                ordinary_shares=shares, cost_of_equity=cost, currency="CNY", scope=SCOPE)
            cash_forecasts[name] = operating
        scenarios = apply_fresh_issuer_distribution(scenarios=scenarios, event=distribution,
            symbol=spec["symbol"], valuation_date=spec["valuation_date"])
        for name, scenario in scenarios.items():
            payout_reservations[name] = _reserve_annual_cash_before_optional_payout(
                opening, scenario["years"], _number(shares), _number(scenario["cost_of_equity"]))
            calculation = compile_direct_owner_cash_path_v2(**{k: v for k, v in scenario.items() if k != "symbol"})
            scenario.update(forecast_roes=[row["roe_assumption"] for row in calculation["annual_rows"]],
                forecast_retentions=[row["retention_assumption"] for row in calculation["annual_rows"]],
                calculation=calculation)
    closure=[]
    def collect(value):
        if isinstance(value,dict):
            if isinstance(value.get("path"),str) and isinstance(value.get("sha256"),str):
                binding={"path":value["path"],"sha256":value["sha256"]}
                if binding not in closure:closure.append(binding)
            for item in value.values():collect(item)
        elif isinstance(value,list):
            for item in value:collect(item)
    collect(evidence)
    collect(spec["operating_sources"])
    if "first_year_operating_cash_method" in spec:
        collect(cash_forecasts)
    result = dict(compiler_version="direct-owner-cash-compilation-note-grid-v1", symbol=spec["symbol"], evidence=evidence,
        opening=opening, ordinary_shares=shares,
        scenarios=scenarios, operating_forecasts=cash_forecasts, assumptions=explanations,
        action="no_order", formal_eligibility=False, main_range_adopted=False,
        valuation_date=spec["valuation_date"], source_bindings=closure)
    result["annual_payout_reservations"] = payout_reservations
    return result

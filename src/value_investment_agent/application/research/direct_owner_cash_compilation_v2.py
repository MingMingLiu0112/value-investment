"""Compile numbered, source-replayed parent cash into the existing valuation domain."""
from datetime import date
from decimal import Decimal, localcontext
from .parent_direct_owner_cash_sources_v2 import read_parent_direct_owner_cash_sources_v2
from .parent_direct_owner_cash_unnumbered_v1 import (
    VERSION as UNNUMBERED_SOURCE, FINANCING_VERSION, UNNUMBERED_VERSIONS,
    read_unnumbered_parent_cash, read_unnumbered_parent_financing,
)
from ...domain.valuation.parent_direct_operating_cash import forecast_parent_operating_cash, SCOPE
from ...domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path, FLOW_KEYS

SCHEMA = "direct-owner-cash-research-spec-v1"
VERSION = "direct-owner-cash-compilation-v2"


def financing_maturity_floor(constraints, year):
    """Gross admitted issuer maturities due in a forecast year, before refinancing."""
    issues = (constraints or {}).get("issued_financing", [])
    if not isinstance(issues, list):
        raise ValueError("DIRECT_INPUT_FINANCING_CONSTRAINT_INVALID")
    total = Decimal(0)
    seen = set()
    for issue in issues:
        if (not isinstance(issue, dict) or issue.get("classification") != "FACT"
                or issue.get("scope") != "ISSUER_FINANCING_DISCLOSURE"
                or issue.get("currency") != "CNY" or not issue.get("code")
                or issue["code"] in seen):
            raise ValueError("DIRECT_INPUT_FINANCING_CONSTRAINT_INVALID")
        seen.add(issue["code"])
        if date.fromisoformat(issue["maturity"]).year == year:
            if issue.get("actual_settlement_verified") is True:
                continue
            amount = issue.get("outstanding_at_evaluation_cny")
            if amount is None:
                amount = issue["principal_cny"]
            amount = _number(amount) if isinstance(amount, str) else Decimal(str(amount))
            if not amount.is_finite() or amount < 0:
                raise ValueError("DIRECT_INPUT_FINANCING_CONSTRAINT_INVALID")
            total += amount
    return total


def _number(value):
    if not isinstance(value, str):
        raise ValueError("DIRECT_INPUT_DECIMAL_STRING_REQUIRED")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("DIRECT_INPUT_FINITE_NUMBER_REQUIRED")
    return number


def _explanation(row):
    for name in ("rationale", "counter_evidence", "reopen_condition"):
        if not isinstance(row.get(name), str) or not row[name].strip():
            raise ValueError("DIRECT_INPUT_ASSUMPTION_EXPLANATION_REQUIRED:" + name)


def compile_source_bound_owner_cash_v2(*, root, spec, now):
    """Reparse pinned financial originals and recompute all annual cash inputs."""
    if (spec.get("schema_version") != SCHEMA or spec.get("action") != "no_order"
            or spec.get("currency") != "CNY" or spec.get("scope") != SCOPE):
        raise ValueError("DIRECT_INPUT_SPEC_CONTRACT_INVALID")
    if (spec.get("source_adapter_version") not in {"NUMBERED_CNINFO_V2", *UNNUMBERED_VERSIONS}
            or spec.get("operating_sources") != []):
        raise ValueError("DIRECT_INPUT_NUMBERED_SOURCE_REQUIRED")
    if now.utcoffset() is None:
        raise ValueError("DIRECT_INPUT_AWARE_CLOCK_REQUIRED")
    if not spec["valuation_date"].endswith("-12-31"):
        raise ValueError("DIRECT_INPUT_YEAR_END_BASIS_REQUIRED")
    if date.fromisoformat(spec["valuation_date"]) > now.date():
        raise ValueError("DIRECT_INPUT_FUTURE_BASIS")
    reader = {
        UNNUMBERED_SOURCE: read_unnumbered_parent_cash,
        FINANCING_VERSION: read_unnumbered_parent_financing,
        "NUMBERED_CNINFO_V2": read_parent_direct_owner_cash_sources_v2,
    }[spec["source_adapter_version"]]
    evidence = reader(
        root=root, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
        sources=spec["owner_sources"], evaluated_at=now,
        constraint_binding=spec.get("constraint_binding"),
        fund_selection=spec.get("fund_selection"))
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
        if share_spec!={"classification":"DERIVED_FACT","period_end":spec["valuation_date"]}:
            raise ValueError("DIRECT_INPUT_DATED_SHARE_FACT_REQUIRED")
        share_fact=statements[spec["valuation_date"]].get("ordinary_shares_evidence")
        if (not isinstance(share_fact,dict) or share_fact.get("period_end")!=spec["valuation_date"]
                or share_fact.get("unit")!="shares" or share_fact.get("scope")!="TOTAL_ISSUED_ORDINARY_SHARES"
                or share_fact.get("classification")!="DERIVED_FACT"
                or not share_fact.get("source_refs")):
            raise ValueError("DIRECT_INPUT_SHARE_UNIT_SCOPE_OR_PROOF_MISSING")
        shares=str(_number(share_fact["count"]))
        scenarios, cash_forecasts = {}, {}
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
            calculation = compile_direct_owner_cash_path(opening=opening, years=rows, terminal=tail,
                ordinary_shares=shares, cost_of_equity=cost, scope=SCOPE, currency="CNY")
            scenarios[name] = dict(symbol=spec["symbol"], opening=opening, years=rows, terminal=tail,
                ordinary_shares=shares, cost_of_equity=cost, currency="CNY", scope=SCOPE,
                forecast_roes=[row["roe_assumption"] for row in calculation["annual_rows"]],
                forecast_retentions=[row["retention_assumption"] for row in calculation["annual_rows"]],
                calculation=calculation)
            cash_forecasts[name] = operating
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
    return dict(compiler_version=VERSION, symbol=spec["symbol"], evidence=evidence,
        opening=opening, ordinary_shares=shares,
        scenarios=scenarios, operating_forecasts=cash_forecasts, assumptions=explanations,
        action="no_order", formal_eligibility=False, main_range_adopted=False,
        valuation_date=spec["valuation_date"], source_bindings=closure)

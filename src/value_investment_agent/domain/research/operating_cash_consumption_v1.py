"""Source-verified D2 earnings consumption; never invent an annual cash forecast."""
from copy import deepcopy

from decimal import Decimal, localcontext



from ..valuation.signed_parent_profit import build_signed_parent_profit_path
from .operating_driver_bridge_v1 import build_basis, calculate_path

SCHEMA = "operating-shareholder-consumption-v1"

def _number(value):
    if not isinstance(value, str):
        raise ValueError("EXPLICIT_DECIMAL_REQUIRED")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("FINITE_DECIMAL_REQUIRED")
    return result

def consume_operating_earnings(*, context, bridge):
    """Consume complete witnesses, never splice independently extreme cells."""
    if context.get("action") != "no_order" or bridge.get("action") != "no_order":
        raise ValueError("NO_ORDER_SOURCE_REQUIRED")
    if set(bridge.get("paths", {})) != {"bear", "base", "bull"}:
        raise ValueError("THREE_VERIFIED_OPERATING_PATHS_REQUIRED")
    evidence = context["evidence"]
    basis = build_basis(context)
    for name, path in bridge["paths"].items():
        if calculate_path(basis, bridge["inputs"][name]) != path:
            raise ValueError("OPERATING_PATH_DIFFERS_FROM_SOURCE_RECOMPUTATION")
    def fact(field, period, scope):
        rows = [r for r in evidence if r.get("field") == field and r.get("period") == period
                and r.get("scope") == scope and r.get("unit") == "CNY"
                and r.get("kind") == "VERIFIED_REPORTED_FACT"]
        if len(rows) != 1:
            raise ValueError("UNIQUE_REPORTED_FACT_REQUIRED:" + field + ":" + period)
        return rows[0]
    def refs(rows):
        return [dict(evidence_id=r["id"], source_id=r["source_id"], physical_page=r["physical_page"],
                     pdf_sha256=r["pdf_sha256"], available_at=r["available_at"]) for r in rows]
    history = []
    for period in sorted({r["period"] for r in evidence if r.get("field") == "parent_cfo"}):
        try:
            rows = [fact(k, period, "parent") for k in ("parent_cfo", "parent_investment_cash", "parent_capex")]
        except ValueError:
            continue
        values = [_number(r["value"]) for r in rows]
        history.append(dict(period=period, period_basis=rows[0].get("period_basis"),
            statement_scope="parent", parent_cfo=rows[0]["value"], investment_cash=rows[1]["value"],
            gross_cash_capex=rows[2]["value"], cash_proxy_cny=str(values[0]+values[1]-values[2]),
            evidence=refs(rows), classification="DERIVED_HISTORICAL_PARENT_CASH_PROXY_NOT_FCFE",
            limitations="CFO includes WC; never deduct it twice. Investment receipts are not recurring forecasts. Group cash is not added."))
    scenarios = {}
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        for name, path in bridge["paths"].items():
            period = path["baseline"]["period"]
            if path["scope"] != "consolidated":
                raise ValueError("OPERATING_SCOPE_MISMATCH")
            anchor = [fact("pre_tax_profit", period, "consolidated"),
                      fact("tax", period, "consolidated"),
                      fact("parent_profit", period, "consolidated_parent")]
            if (any(r.get("period_basis") != path["period_basis"] for r in anchor[:2])
                    or anchor[2]["source_id"] != anchor[0]["source_id"]
                    or anchor[2].get("period_basis") not in {path["period_basis"], "UNKNOWN"}):
                raise ValueError("TAX_ATTRIBUTION_PERIOD_MISMATCH")
            pbt, tax, parent = [_number(r["value"]) for r in anchor]
            if pbt <= 0 or not 0 <= tax < pbt or parent <= 0:
                raise ValueError("UNSUPPORTED_TAX_OR_ATTRIBUTION_ANCHOR")
            rate, group = tax/pbt, pbt-tax
            signed_nci_ratio = (group-parent)/group
            witnesses = {}
            for key, point in path["extrema"].items():
                amount = _number(point["pretax_profit_cny"])
                nci = (amount-amount*rate)*signed_nci_ratio
                result = build_signed_parent_profit_path(years=[int(path["period_end"][:4])],
                    group_pbt_cny=[str(amount)], tax_assumptions=[dict(basis="effective_rate", value=str(rate))],
                    signed_nci_cny=[str(nci)], currency="CNY")["rows"][0]
                result.pop("year")
                witnesses[key] = dict(**result, operating_witness=deepcopy(point))
            scenarios[name] = dict(period_start=path["period_start"], period_end=path["period_end"],
                period_basis=path["period_basis"], classification="CONDITIONAL_TAX_AND_SIGNED_NCI_PERSISTENCE",
                effective_tax_rate=str(rate), signed_nci_ratio=str(signed_nci_ratio),
                anchor_evidence=refs(anchor), period_binding="Cold-replayed parent-profit duration matches the same original source and exact period of PBT/tax; summary header is not independently annualized",
                witnesses=witnesses, shareholder_distribution=None,
                normalization_adjustment=None,
                limitation="Complete witnesses, not global cash/value bounds. Tax/NCI persistence is hypothetical. Parent profit is not cash; no annualization or automatic nonrecurring addback.")
    blockers = [
        ("COMPLETE_ANNUAL_OPERATING_PATH_REQUIRED", "valuation",
         "Current D2 is H1. Full annual paths and explicit H2/period bridges are absent; H1 times two is forbidden."),
        ("EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED", "shareholder_cash",
         "Future opening cash/capacity, maintenance/WC, remittance and payout need bound hypotheses; UNKNOWNs are not zero."),
        ("MAIN_ECONOMIC_RANGE_NOT_ADOPTED", "condition_price",
         "Conditional earnings and historical cash proxies cannot become an adopted main value or action-price base."),
        ("CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED", "condition_price",
         "Historical financial capital is not a current quote-comparable basis.")]
    return dict(schema_version=SCHEMA, symbol=context["symbol"], action="no_order",
        status="SOURCE_BOUND_EARNINGS_CONSUMED_CASH_INPUTS_INCOMPLETE", formal_eligibility=False,
        main_range_adopted=False, condition_price=None, personal_quantity=None,
        historical_parent_cash=history, scenarios=scenarios,
        current_blockers=[dict(code=c, stage=s, explanation=e) for c,s,e in blockers],
        future_extensions=["Additional issuer migration after this vertical slice is accepted",
                           "Automated recurring research after the existing refresh contract is accepted"],
        valuation_consumer=dict(status="NOT_CONSUMED", model="residual-income-equity-path-v4",
            reason="Annual horizon and same-period cash policy incomplete; no COGS substitution to hide OPEX differences."),
        price_policy=dict(status="NOT_PREPARED", action="no_order", rules=[], draft_prices=None,
            reason="No adopted value basis or bound price-threshold rationale; no default safety margin."))


def build_rolling_income_inputs(*, context, bridge):
    """A separately declared adverse-margin stress transport, NOT annualization.

    First model year combines independently projected prior-year H2 with the
    existing complete D2 H1 witness. Later years explicitly keep that operating
    income constant. This is a finite sensitivity contract, not a main forecast.
    """
    consumed = consume_operating_earnings(context=context, bridge=bridge)
    basis = build_basis(context)
    evidence = context["evidence"]
    def row(field, period, scope):
        found = [r for r in evidence if r.get("field")==field and r.get("period")==period
                 and r.get("scope")==scope and r.get("unit")=="CNY"
                 and r.get("kind")=="VERIFIED_REPORTED_FACT"]
        if len(found)!=1:
            raise ValueError("ROLLING_PERIOD_FACT_NOT_UNIQUE:"+field+":"+period)
        return found[0]
    results = {}
    with localcontext() as arithmetic:
        arithmetic.prec=48
        for name,path in bridge["paths"].items():
            if path["period_basis"]!="H1" or not path["period_start"].endswith("-01-01"):
                raise ValueError("EXPLICIT_ROLLING_H1_TRANSPORT_ONLY")
            year=int(path["baseline"]["period"][:4])
            if int(path["period_end"][:4]) != year+1:
                raise ValueError("ROLLING_NEXT_H1_REQUIRED")
            fy,prior_h1,latest_h1=f"{year-1}-12-31",f"{year-1}-06-30",f"{year}-06-30"
            if path["baseline"]["period"]!=latest_h1:
                raise ValueError("ROLLING_BASELINE_MISMATCH")
            a,b,c=[basis["baselines"].get(p) for p in (fy,prior_h1,latest_h1)]
            if a is None or b is None or c is None or a["period_basis"]!="FY" or b["period_basis"]!="H1":
                raise ValueError("FULL_YEAR_AND_MATCHED_HALVES_REQUIRED")
            projected,h2_actual,changes={},{},{}
            for field in ("revenue","cost","surcharges","selling","admin","research"):
                av,bv,cv=[_number(x["fields"][field]["value"]) for x in (a,b,c)]
                amount=av-bv
                if amount<0 or bv<=0:
                    raise ValueError("UNSUPPORTED_H2_DIFFERENCE_OR_TREND_BASE")
                h2_actual[field]=str(amount)
                changes[field]=str(cv/bv)
                projected[field]=amount*(cv/bv)
            residual=min(_number(a["other_pretax_cny"])-_number(b["other_pretax_cny"]),Decimal(0))
            h2_pbt=(projected["revenue"]-projected["cost"]-sum(
                projected[k] for k in ("surcharges","selling","admin","research"))+residual)
            historical_h2_pbt=_number(a["fields"]["pre_tax_profit"]["value"])-_number(b["fields"]["pre_tax_profit"]["value"])
            fy_tax,h1_tax=[row("tax",p,"consolidated") for p in (fy,prior_h1)]
            fy_parent,h1_parent=[row("parent_profit",p,"consolidated_parent") for p in (fy,prior_h1)]
            h2_tax=_number(fy_tax["value"])-_number(h1_tax["value"])
            h2_parent=_number(fy_parent["value"])-_number(h1_parent["value"])
            if historical_h2_pbt<=0 or not 0<=h2_tax<historical_h2_pbt or h2_pbt<=0:
                raise ValueError("UNSUPPORTED_H2_PROFIT_TAX_SIGNS")
            h2_rate=h2_tax/historical_h2_pbt
            h2_nci_rate=(historical_h2_pbt-h2_tax-h2_parent)/(historical_h2_pbt-h2_tax)
            h2_tax_projection=h2_pbt*h2_rate
            h2_nci_projection=(h2_pbt-h2_tax_projection)*h2_nci_rate
            witness=consumed["scenarios"][name]["witnesses"]["margin_lower"]
            total_pbt=h2_pbt+_number(witness["group_pbt_cny"])
            total_tax=h2_tax_projection+_number(witness["income_tax_cny"])
            total_nci=h2_nci_projection+_number(witness["signed_nci_cny"])
            years=[]
            for index in range(1,11):
                years.append(dict(year=index,period_start=f"{year+index-1}-07-01",
                    period_end=f"{year+index}-06-30",period_basis="ROLLING_FULL_YEAR",
                    group_pbt_cny=str(total_pbt),tax_assumption=dict(basis="amount_cny",value=str(total_tax)),
                    signed_nci_cny=str(total_nci),currency="CNY",scope="consolidated"))
            results[name]=dict(annual_income_rows=years,h2_reported_components=h2_actual,
                h2_transfer_multipliers=changes,h2_projected_components={k:str(v) for k,v in projected.items()},
                h2_residual_assumption=str(residual),h2_projected_pbt=str(h2_pbt),
                selected_d2_witness="margin_lower",d2_witness=deepcopy(witness),
                annual_profit_persistence="EXPLICIT_CONSTANT_OPERATING_INCOME_STRESS_Y2_TO_Y10_NOT_FORECAST",
                source_periods=[fy,prior_h1,latest_h1],
                evidence_ids=a["evidence_ids"]+b["evidence_ids"]+c["evidence_ids"]+
                    [r["id"] for r in (fy_tax,h1_tax,fy_parent,h1_parent)])
    return dict(action="no_order",symbol=context["symbol"],schema_version="rolling-operating-stress-transport-v1",
        scope="UNADOPTED_STRESS_TRANSPORT_NOT_MAIN_FORECAST",scenarios=results,
        assumptions=[
          "H2 transfers each line's observed H1 change separately; no H1 times two and no asserted seasonal stability.",
          "Positive unclassified prior H2 residual is excluded only as an adverse stress assumption, not proof it is nonrecurring.",
          "Select the full adverse-margin D2 witness, not independently spliced range endpoints.",
          "Y2-Y10 hold model-year operating income constant; no automatic reinvestment return or recovery.",
          "No probability, main Bear/Base/Bull range, current valuation, G3 or transaction follows."])

"""Read-only D2 shareholder consumption outside immutable paid-task code."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from .agent_review.operating_sources_v1 import build_operating_source_context
from ...domain.research.operating_cash_consumption_v1 import SCHEMA, consume_operating_earnings
def read_operating_cash_consumption(*, root, task, now):
    """Read-only source replay outside the immutable paid-task implementation."""
    if task.get("status") != "SUCCEEDED" or task.get("scope") != "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED":
        return dict(schema_version=SCHEMA, status="NOT_STARTED", action="no_order",
                    reason="SUCCEEDED_VERIFIED_OPERATING_TASK_REQUIRED", formal_eligibility=False)
    if "operating_driver_bridge" not in task:
        return dict(schema_version=SCHEMA, status="NOT_STARTED", action="no_order",
                    reason="STRUCTURED_OPERATING_DRIVER_BRIDGE_REQUIRED", formal_eligibility=False)
    cutoff = datetime.fromisoformat(task["research_as_of"])
    if cutoff.utcoffset() is None or now.utcoffset() is None or cutoff > now:
        raise ValueError("SOURCE_CUTOFF_INVALID")
    context = build_operating_source_context(root=root, symbol=task["symbol"], now=cutoff,
                                            binding=task["source_binding"])
    if context["snapshot_fingerprint"] != task["context_fingerprint"]:
        raise ValueError("OPERATING_CONTEXT_CHANGED")
    registry=json.loads((root/"config/current-operating-research-sources-v1.json").read_bytes())
    earnings_error=None
    try:
        result = consume_operating_earnings(context=context, bridge=task["operating_driver_bridge"])
    except (ValueError,KeyError,TypeError) as error:
        # A valid D2 task is not permission to silently fill a missing tax/NCI
        # or other annual attribution fact. Still return an issuer-specific E2
        # readiness record so callers can obtain the exact public evidence.
        earnings_error=str(error)
        result=dict(schema_version=SCHEMA,status="UNASSESSABLE",reason=earnings_error,
                    action="no_order",formal_eligibility=False,condition_price=None,
                    historical_parent_cash=[],current_blockers=[])
    result.update(task_id=task["task_id"], context_fingerprint=task["context_fingerprint"],
                  source_binding=deepcopy(task["source_binding"]), research_as_of=task["research_as_of"])
    ref=registry["cases"].get(task["symbol"],{}).get("cash_followup")
    if earnings_error is not None:
        result["cash_followup_readiness"]=_missing_cash_followup_readiness(
            context=context, registry=registry, result=result, earnings_error=earnings_error)
    elif ref is not None:
        try:
            annual=consume_annual_followup(root=root,spec=_bound_json(root,ref),task=task,context=context,now=now)
            result["annual_followup"]=annual
            result["status"]="CONDITIONAL_EARNINGS_CASH_VALUATION_CONSUMED"
            result["valuation_consumer"].update(status=annual["valuation_status"],
                reason="New explicit rolling-year stress contract consumed by existing ResearchApplicationService and v4 model.")
            result["current_blockers"]=[
                dict(code="ANNUAL_TRANSPORT_AND_CASH_POLICY_NOT_ECONOMICALLY_ADOPTED",stage="economic_research",
                     explanation="The explicit stress transfer and reused cash policies are hypotheses, not a selected main valuation. Original D2 capital UNKNOWNs remain unknown."),
                *[r for r in result["current_blockers"] if r["stage"]=="condition_price"]]
        except (ValueError,OSError,KeyError,TypeError) as error:
            result["annual_followup"]=dict(status="UNASSESSABLE",reason=str(error),action="no_order",formal_eligibility=False)
    else:
        # Do not turn a successful operating-research task into an annual cash
        # path just because the issuer has a consolidated cash-flow statement.
        # This names the issuer-specific missing bindings so an E2 caller can
        # request the right public evidence without guessing a cash policy.
        result["cash_followup_readiness"]=_missing_cash_followup_readiness(
            context=context, registry=registry, result=result)
    from pathlib import Path
    from ...domain.research import operating_cash_consumption_v1 as kernel
    from ...domain.valuation import signed_parent_profit
    result["implementation_sha256"]={m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (kernel,signed_parent_profit)}
    from ...domain.valuation import operating_profit_cash_path_v1, joint_capital_cash_path_v4
    from ...valuation_models import residual_income_path_v4
    result["implementation_sha256"].update({m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (operating_profit_cash_path_v1,joint_capital_cash_path_v4,residual_income_path_v4)})
    result["implementation_sha256"][__name__]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    annual=result.get("annual_followup",{})
    identity=dict(schema_version=SCHEMA,task_id=task["task_id"],source_binding=task["source_binding"],
        context_fingerprint=task["context_fingerprint"],implementation_sha256=result["implementation_sha256"],
        annual_source_spec=annual.get("source_spec"),annual_input_descriptor=annual.get("input_descriptor_sha256"),
        annual_status=annual.get("status"),annual_error=annual.get("reason"))
    result["fingerprint_scope"]="BOUND_INPUTS_AND_IMPLEMENTATIONS_NOT_EXECUTION_METADATA"
    result["consumption_fingerprint"] = hashlib.sha256(json.dumps(identity,sort_keys=True,
        ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return result


def _missing_cash_followup_readiness(*, context, registry, result, earnings_error=None):
    """State why this issuer cannot yet enter the annual E2 cash adapter.

    The output is deliberately a readiness result, not a replacement adapter:
    no cash policy, main range, distribution, or price qualification is inferred
    from a consolidated statement or from a successful D2 task.
    """
    case=registry["cases"].get(context["symbol"], {})
    parent_fields=("parent_cfo", "parent_investment_cash", "parent_capex")
    verified={row.get("field") for row in context["evidence"]
              if row.get("kind")=="VERIFIED_REPORTED_FACT" and row.get("scope")=="parent"}
    financial_refs=[]
    for row in context["evidence"]:
        if row.get("kind")!="VERIFIED_REPORTED_FACT" or row.get("period")!=context["financial_basis"]:
            continue
        ref=dict(evidence_id=row["id"],source_id=row["source_id"],physical_page=row["physical_page"],
                 pdf_sha256=row["pdf_sha256"],available_at=row["available_at"])
        if ref not in financial_refs:
            financial_refs.append(ref)
    missing=[]
    if earnings_error is not None:
        missing.append(dict(code="OPERATING_EARNINGS_FACTS_REQUIRED", category="public_fact",
            reason=earnings_error,
            explanation="The same-period tax/NCI attribution facts required for the operating earnings bridge are missing or ambiguous; the cash adapter does not infer them."))
    missing.extend([
        dict(code="SOURCE_BOUND_CASH_FOLLOWUP_SPEC_REQUIRED", category="source_binding",
             explanation="No immutable cash_followup binding is registered for this issuer; a D2 task cannot select a task state, annual input receipt, or policy package by itself."),
    ])
    absent=[field for field in parent_fields if field not in verified]
    if absent:
        missing.append(dict(code="PARENT_CASH_FLOW_FACTS_REQUIRED", category="public_fact",
            fields=absent,
            explanation="The admitted source context lacks the parent-company CFO, investment-cash and gross-capex facts required to construct a parent cash proxy. Consolidated cash is not substituted."))
    missing.extend([
        dict(code="EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED", category="research_assumption",
             explanation="Maintenance/WC, remittance, payout, cash floor and funding terms require a source-bound same-period policy; unknown values are not zero."),
        dict(code="MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED", category="research_adoption",
             explanation="Conditional D2 operating witnesses have not been adopted as the issuer's main economic range."),
        dict(code="CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED", category="market_alignment",
             explanation="Financial-period capital and distribution facts are not yet aligned to a current eligible quote."),
    ])
    return dict(schema_version="operating-cash-followup-readiness-v1", status="BLOCKED",
        action="no_order", formal_eligibility=False, symbol=context["symbol"],
        issuer_name=context.get("issuer_name"), financial_basis=context["financial_basis"],
        source_binding=deepcopy(context["source_binding"]), cash_followup_registered="cash_followup" in case,
        supported_financial_evidence=financial_refs, historical_parent_cash_rows=len(result.get("historical_parent_cash",[])),
        missing_evidence=missing)

def _bound_json(root, binding):
    import re
    from pathlib import Path
    if (not isinstance(binding,dict) or set(binding)!={"path","sha256"}
        or not isinstance(binding["path"],str) or Path(binding["path"]).is_absolute()
        or ".." in Path(binding["path"]).parts or not isinstance(binding["sha256"],str)
        or re.fullmatch("[0-9a-f]{64}",binding["sha256"]) is None):
        raise ValueError("EXACT_PROJECT_RELATIVE_CASH_BINDING_REQUIRED")
    from ..product.common import require_inside
    path = require_inside(root, root/binding["path"], "cash followup")
    if path.is_absolute() and not path.is_relative_to(root):
        raise ValueError("CASH_FOLLOWUP_OUTSIDE_PROJECT")
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=binding["sha256"]:
        raise ValueError("CASH_FOLLOWUP_BINDING_CHANGED")
    return json.loads(raw)

def consume_annual_followup(*, root, spec, task, context, now):
    """Compile an explicit unadopted stress transport through existing v4 service.

    Not an old v4 proposal: this new contract cold-recomputes every earnings
    row before adapting the source-bound package. No immutable candidate changes.
    """
    from dataclasses import fields, replace
    from zoneinfo import ZoneInfo
    from decimal import Decimal, localcontext
    from ...domain.research.operating_cash_consumption_v1 import build_rolling_income_inputs
    from ...domain.valuation.operating_profit_cash_path_v1 import compile_operating_profit_cash_path, CASH_FIELDS, PROFIT_BASIS
    from ...domain.valuation.joint_capital_cash_path_v4 import SCOPE
    from .first_research_input_v1 import replay_first_research_input
    from .v4_input_adapter import scenario_payload, _v2_payload, V4ResearchInputDescriptor
    from ...m1_valuation_package_builder import build_descriptor
    from ...research_input import ResearchInputDescriptor, ResearchSourceContract, finalize_input_descriptor, build_research_run_spec
    from ..product.source_bound_inputs import source_catalog_sha256, validate_source_bound_descriptor
    from ...research_application import ResearchApplicationService
    from .v4_valuation_router import build_v4_valuation_router
    from ..product.company_research import _serialize_outcome
    from ..product.neutral_valuation_proposal import _json_numbers
    required={"schema_version","action","symbol","task_state_binding","first_input_receipt",
              "generated_at","transport","rationale","countercase","scope"}
    if (set(spec)!=required or spec["schema_version"]!="operating-cash-followup-spec-v1"
        or spec["action"]!="no_order" or spec["symbol"]!=task["symbol"]
        or spec["task_state_binding"]!=task["record_binding"]
        or spec["scope"]!="UNADOPTED_STRESS_NOT_MAIN_FORECAST"
        or spec["transport"]!="rolling-operating-stress-transport-v1"
        or not spec["rationale"] or not spec["countercase"]):
        raise ValueError("CASH_FOLLOWUP_SPEC_OR_TASK_VERSION_MISMATCH")
    made=datetime.fromisoformat(spec["generated_at"])
    if made.utcoffset() is None or made>now or made<datetime.fromisoformat(task["research_as_of"]):
        raise ValueError("CASH_FOLLOWUP_TIME_INVALID")
    # Public bindings alone do not authenticate caller-supplied in-memory values.
    # Reload the exact immutable task chain and reparse originals at this boundary.
    registry=json.loads((root/"config/current-operating-research-sources-v1.json").read_bytes())
    followup_ref=registry["cases"][spec["symbol"]]["cash_followup"]
    if _bound_json(root,followup_ref)!=spec:
        raise ValueError("CASH_FOLLOWUP_CURRENT_SPEC_CHANGED")
    state=_bound_json(root,spec["task_state_binding"])
    from .agent_review.operating_task_v2 import LiveOperatingTaskService
    service=LiveOperatingTaskService(root)
    frozen_spec,frozen_state,frozen_pin=service._load(state["task_id"],recover=False)
    fresh_task=service._view(frozen_spec,frozen_state,frozen_pin,now)
    if frozen_pin!=spec["task_state_binding"] or fresh_task!=task:
        raise ValueError("CASH_FOLLOWUP_TASK_MEMORY_DIFFERS_FROM_COLD_STATE")
    fresh_context=build_operating_source_context(root=root,symbol=fresh_task["symbol"],
        now=datetime.fromisoformat(fresh_task["research_as_of"]),binding=fresh_task["source_binding"])
    if fresh_context!=context:
        raise ValueError("CASH_FOLLOWUP_CONTEXT_MEMORY_DIFFERS_FROM_COLD_SOURCE")
    task,context=fresh_task,fresh_context
    old=replay_first_research_input(root=root,receipt_binding=spec["first_input_receipt"],now=now)
    if old["research_case"]["symbol"]!=task["symbol"] or old["formal_eligibility"] is not False:
        raise ValueError("CASH_POLICY_REUSE_ISSUER_OR_SCOPE_MISMATCH")
    receipt=_bound_json(root,spec["first_input_receipt"])
    package=_bound_json(root,receipt["package_binding"])
    prior_spec=_bound_json(root,receipt["spec_binding"])
    assumptions=_bound_json(root,prior_spec["assumption_binding"])
    proposal=_bound_json(root,receipt["proposal_binding"])
    if (prior_spec["native_facts_binding"]!=task["source_binding"]
        or prior_spec["point_in_time"]["valuation_date"]!=context["financial_basis"]):
        raise ValueError("CASH_POLICY_REUSE_FINANCIAL_BASIS_MISMATCH")
    transport=build_rolling_income_inputs(context=context,bridge=task["operating_driver_bridge"])
    historical=proposal["joint_historical"]
    raw, typed, ledgers={},{},{}
    with localcontext() as arithmetic:
        arithmetic.prec=48
        book=Decimal(package["facts"]["operating_inputs"]["start_book_equity"])
        shares=package["facts"]["operating_inputs"]["ordinary_shares"]
        cash=Decimal(historical["opening_cash"])
        opening=dict(as_of=context["financial_basis"],scope=SCOPE,currency="CNY",
            book_equity_cny=str(book),cash_cny=str(cash),unremitted_cny="0",
            distribution_capacity_cny=historical["opening_distribution_capacity"],
            operating_capital_cny=str(book-cash),productive_capital_cny="0",
            cash_floor_cny=historical["cash_floor"],ordinary_shares=shares)
        for name, research in transport["scenarios"].items():
            prior=assumptions["scenarios"][name]
            drivers=prior["drivers"]
            capital={k:drivers[k] for k in ("operating_allocation","new_operating_return","new_liquidity_return")}
            if any(Decimal(value)!=0 for value in capital.values()):
                raise ValueError("CASH_REUSE_NEW_RETURN_OVERLAP_NOT_PROVEN")
            annual=deepcopy(research["annual_income_rows"])
            for index,row in enumerate(annual):
                policy=drivers["years"][index]
                if policy["year"]!=index+1:
                    raise ValueError("CASH_REUSE_YEAR_MISMATCH")
                row["cash_policy"]={k:policy[k] for k in CASH_FIELDS}
                row["cash_policy"].update(scope=SCOPE,currency="CNY")
            result=compile_operating_profit_cash_path(opening_state=opening,annual_rows=annual,
                capital_policy=capital,terminal_policy=prior["terminal_policy"],
                cost_of_equity=prior["cost_of_equity"],profit_basis=PROFIT_BASIS)
            raw[name]=dict(annual_rows=annual,capital_policy=capital,terminal_policy=prior["terminal_policy"],
                           cost_of_equity=prior["cost_of_equity"])
            typed[name]=result.pop("typed_scenario")
            ledgers[name]=_json_numbers(result)
    # New workflow sources include exact task state, role replies, policy inputs
    # and the explicit research supplement. Existing financial sources are cold reverified.
    data=deepcopy(package)
    source_refs=[spec["task_state_binding"],spec["first_input_receipt"],task["source_binding"]]
    source_refs+=list(task["roles"].values())
    registry=json.loads((root/"config/current-operating-research-sources-v1.json").read_bytes())
    followup_ref=registry["cases"][task["symbol"]]["cash_followup"]
    if _bound_json(root,followup_ref)!=spec:
        raise ValueError("CASH_FOLLOWUP_CURRENT_SPEC_CHANGED")
    source_refs.append(followup_ref)
    for binding in source_refs:
        _bound_json(root,binding)
        if not any(s["local_path"]==binding["path"] and s["sha256"]==binding["sha256"] for s in data["sources"]):
            data["sources"].append(dict(id="cash-followup-"+binding["sha256"],kind="research_artifact",
                local_path=binding["path"],location=binding["path"],sha256=binding["sha256"],
                source_available_at=made.isoformat(),retrieved_at=made.isoformat(),
                availability_basis="CURRENT_CONDITIONAL_RESEARCH_NOT_HISTORICAL_PIT"))
    refs=[dict(id=s["id"],path=s["local_path"],sha256=s["sha256"]) for s in data["sources"]]
    serialized={name:scenario_payload(value) for name,value in typed.items()}
    data.update(descriptor_version="operating-cash-followup-spec-v1",
                run_id="d2-cash-"+followup_ref["sha256"][:24])
    data["point_in_time"].update(research_as_of=made.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        available_at=made.isoformat(),computed_at=made.isoformat())
    data["research_case"].update(as_of=data["point_in_time"]["research_as_of"],generated_at=made.isoformat(),
        run_id=data["run_id"],research_version="operating-cash-followup-spec-v1",evidence_refs=refs,
        thesis=spec["rationale"],counter_evidence=[dict(kind="interpretation",text=spec["countercase"],evidence_refs=[r["id"] for r in refs])],
        blockers=["ECONOMIC_RESEARCH_NOT_APPROVED","ANNUAL_TRANSPORT_AND_CASH_POLICY_ARE_STRESS_ASSUMPTIONS"])
    data["dependencies"].update(rule_version="operating-cash-followup-spec-v1")
    data["facts"].update(scenario_inputs=serialized,evidence_refs=refs)
    rows,bindings=[],[]
    paths=["cost_of_equity","terminal_roe","terminal_growth"]+[
        f"{prefix}.{i}" for prefix in ("forecast_roes","forecast_retentions") for i in range(10)]
    for path in paths:
        bits=path.split(".")
        values={name:(row[bits[0]][int(bits[1])] if len(bits)==2 else row[path]) for name,row in serialized.items()}
        rows.append(dict(name=path,unit="ratio",**values,basis="EXPLICIT_D2_ROLLING_STRESS_NOT_MAIN_FORECAST",
            rationale=spec["rationale"],confidence="low",sensitivity="high",ordering="non_monotonic",evidence_refs=refs))
        bindings += [dict(assumption_name=path,scenario=name,field_path=path,expected_value=value,evidence_refs=refs)
                     for name,value in values.items()]
    data["assumptions"]=dict(assumptions=rows,evidence_refs=refs,blockers=[])
    data["assumption_bindings"]=bindings
    data["source_contract"].update(cutoff_at=made.isoformat(),source_catalog_sha256=source_catalog_sha256(data["sources"]))
    # Reuse the legacy parser only as a typed parser; validate the source contract
    # before restoring v4 terminal economics cold-computed above.
    compatibility=deepcopy(data)
    compatibility["facts"]["scenario_inputs"]={name:_v2_payload(value) for name,value in serialized.items()}
    parse=deepcopy(compatibility)
    parse["schema_version"]="m1-valuation-package-v1"
    parse.pop("source_contract",None)
    legacy=build_descriptor(parse,root=root)
    values={f.name:getattr(legacy,f.name) for f in fields(ResearchInputDescriptor)}
    values.update(source_contract=ResearchSourceContract.from_payload(data["source_contract"]),input_sha256=None)
    validated=finalize_input_descriptor(ResearchInputDescriptor(**values))
    validate_source_bound_descriptor(compatibility,validated)
    values={f.name:getattr(validated,f.name) for f in fields(ResearchInputDescriptor)}
    values.update(facts=replace(validated.facts,scenario_inputs=typed),input_sha256=None)
    descriptor=finalize_input_descriptor(V4ResearchInputDescriptor(**values))
    outcome=ResearchApplicationService(router=build_v4_valuation_router(),now_utc=lambda:now).run_company_research(
        build_research_run_spec(descriptor))
    result=_serialize_outcome(outcome)
    value=json.loads(outcome.valuation.to_json()) if outcome.valuation else {}
    price_policy=_price_policy_probe(root=root,symbol=task["symbol"],valuation=value,descriptor=descriptor,
        sources=data["sources"],made=made,now=now)
    return dict(schema_version="operating-cash-followup-result-v1",symbol=task["symbol"],action="no_order",
        status="CONDITIONAL_STRESS_CONSUMED",formal_eligibility=False,main_range_adopted=False,
        condition_price=None,personal_quantity=None,source_spec=followup_ref,transport=transport,
        rationale=spec["rationale"],countercase=spec["countercase"],
        cash_policy_reuse_binding=prior_spec["assumption_binding"],opening_state=opening,
        annual_cash_inputs=raw,annual_ledgers=ledgers,research_case=data["research_case"],
        valuation=json.loads(outcome.valuation.to_json()) if outcome.valuation else None,
        valuation_status=outcome.valuation.status if outcome.valuation else "NOT_READY",
        model_consumption=result,input_descriptor_sha256=descriptor.input_sha256,
        sources=source_refs,financial_basis=context["financial_basis"],
        scope="UNADOPTED_ROLLING_STRESS_NOT_CURRENT_MAIN_VALUE",
        price_policy=price_policy,
        limitations=transport["assumptions"]+[
          "Prior cash policies are separately bound research hypotheses, not resolution of the original D2 UNKNOWNs.",
          "No current-price comparison: subsequent dividends, events, share continuity and eligible quotes remain unaligned."])

def _price_policy_probe(*, root, symbol, valuation, descriptor, sources, made, now):
    """Exercise the existing policy preparer without selecting an action rule.

    This diagnostic cannot turn unadopted stress values into an action-price
    basis. Empty rules intentionally yield no prices and cannot be registered.
    """
    from datetime import date
    from zoneinfo import ZoneInfo
    from ...domain.decision.value_price_policy import draft_value_price_policy, preview_draft_prices
    from ..decision.value_price_policy import prepare_value_price_policy
    day=made.astimezone(ZoneInfo("Asia/Shanghai")).date()
    plan=dict(symbol=symbol,action="no_order",research_version="operating-cash-followup-spec-v1",
        valuation_input_version=descriptor.input_sha256,model_id=descriptor.requested_model,
        model_type=descriptor.requested_model,model_version="residual-income-equity-path-v4",
        valuation_date=valuation.get("valuation_date"),profile_id=descriptor.profile_id,
        source_bindings=[dict(path=s["local_path"],sha256=s["sha256"]) for s in sources],
        **{name:valuation.get(name+"_value") for name in ("bear","base","bull")})
    diagnostic=draft_value_price_policy(plan,draft_id="d2-cash-diagnostic-"+descriptor.input_sha256[:20],
        policy_id="d2-cash-no-action-rules",rule_version="operating-cash-policy-diagnostic-v1",
        profile_id=descriptor.profile_id,effective_from=day,effective_through=day,
        rationale="仅当前研究版本的接口核验：未采纳压力区间，不设操作规则、默认安全边际或买价。",
        dividend_coverage_risk="未来资本与可分配现金政策仍为条件假设，不证明持续股息。",
        rules=(),thesis_reviews=())
    prices=preview_draft_prices(diagnostic)
    reasons=["UNADOPTED_STRESS_NOT_MAIN_RANGE","EXPLICIT_THRESHOLD_RATIONALE_NOT_SELECTED",
             "CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_NOT_ADMITTED"]
    result=dict(status="NOT_PREPARED",policy_contract=diagnostic["schema_version"],
        action="no_order",rules=[],draft_prices=None,diagnostic_preview_prices=prices,
        formal_eligibility=False,registered=False,source_basis_adopted=False,
        reason="STRESS_NOT_ADOPTED_MAIN_RANGE_AND_CURRENT_ALIGNMENT_NOT_ADMITTED",
        blockers=reasons)
    try:
        prepared=prepare_value_price_policy(root,diagnostic,now=now)
        result["preparation_status"]=prepared["status"]
        result["blockers"]+=prepared["blockers"]
    except (ValueError,OSError,KeyError,TypeError) as error:
        result.update(preparation_status="CURRENT_PUBLIC_RESEARCH_BASIS_UNAVAILABLE",
                      preparation_error=str(error))
    return result

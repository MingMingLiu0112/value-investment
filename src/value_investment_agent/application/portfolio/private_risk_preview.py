"""Non-writing conditional sizing from a reverified current public plan."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from copy import deepcopy
from zoneinfo import ZoneInfo
import hashlib

from ...domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
from ...domain.portfolio.security_attributes import (
    SCHEMA as ATTRIBUTE_SCHEMA, parse_observed_attributes, quantity_rule_blockers,
)
from ..hotspot.current_registry import load_price_conditions, registry_identity
from ..hotspot.independent_price_conditions import project_independent_price_condition
from ..product.quote_bridge import execute_quote_bridge_for_symbol
from ..product.public_snapshot import load_current_packet
from ..product.publication_chain import load_current_chain
from ..decision.value_action_plan import load_registered_value_action_plans, load_value_action_policy
from .private_risk_projection import build_risk_input, review_private_risk_rehearsal
from .private_portfolio_service import PrivatePortfolioService, reconciliation_state
from .security_attributes import load_verified_security_attributes, trading_rules_for

ASSUMPTION_FIELDS = (
    "gap_stress_cny", "entry_slippage_cny", "exit_slippage_cny", "buy_fee_fraction",
    "sell_fee_fraction", "minimum_buy_fee_cny", "minimum_sell_fee_cny", "lot_size",
    "max_trade_notional_cny",
)


def _scenario_preview(scenario, *, symbol, generated_at, core_request=None):
    """Consume a complete hypothetical engine contract without borrowing actual facts.

    Request schema: scenario={acknowledged: true, risk_input: <dual-sleeve-risk-input-v1>}.
    Every portfolio, policy, price, execution and risk value in risk_input is a
    user-supplied hypothesis. Engine validation and vetoes still apply; none of
    these values establish actual reconciliation, liquidity or approval.
    """
    output = {"namespace": "SIMULATED", "scope": "EXPLICIT_HYPOTHETICAL_INPUTS_ONLY",
        "action": "no_order", "status": "NOT_REQUESTED", "review_quantity": None,
        "formal_review_quantity": None, "formal_eligibility": False,
        "trade_eligible": False, "acceptance_authority": "NONE",
        "stop_execution_guaranteed": False, "blockers": [], "engine": None,
        "assumptions": None}
    if scenario is None:
        return output
    if (not isinstance(scenario, dict) or set(scenario) != {"acknowledged", "risk_input"}
            or scenario["acknowledged"] is not True):
        raise ValueError("Scenario requires explicit acknowledgement and a complete hypothetical risk_input")
    risk_input = deepcopy(scenario["risk_input"])
    if not isinstance(risk_input, dict) or risk_input.get("namespace") != "SIMULATED":
        raise ValueError("Scenario risk_input must explicitly use SIMULATED namespace")
    portfolio = risk_input.get("portfolio")
    if (not isinstance(portfolio, dict) or not isinstance(portfolio.get("snapshot"), dict)
            or portfolio["snapshot"].get("namespace") != "SIMULATED"):
        raise ValueError("Scenario portfolio snapshot must explicitly use SIMULATED namespace")
    shared = risk_input.get("shared_budget")
    if not isinstance(shared, dict) or shared.get("policy_scope") != "SYNTHETIC_POLICY_ONLY":
        raise ValueError("Scenario requires explicit SYNTHETIC_POLICY_ONLY budget assumptions")
    request = core_request if core_request is not None else risk_input.get("hotspot_request")
    if not isinstance(request, dict) or request.get("symbol") != symbol:
        raise ValueError("Scenario requires a hypothetical hotspot request for the requested symbol")
    report = review_dual_sleeve_risk(risk_input, generated_at=generated_at, allow_synthetic=True,
        **({"core_request": core_request} if core_request is not None else {}))
    review = report.get("core_quantity_review" if core_request is not None else "hotspot_quantity_review") or {}
    blockers = list(dict.fromkeys([*report.get("blockers", []), *review.get("blockers", [])]))
    output.update(status=review.get("status", "BLOCKED"), blockers=blockers,
        review_quantity=None if blockers else review.get("review_quantity"),
        engine=report, assumptions=risk_input)
    if blockers:
        output["status"] = "BLOCKED"
    return output


def _projected_scenario(scenario, *, journal, symbol, assumptions, binding,
        plan_blockers, actual_revision, repository_root, generated_at, verified_rules=None):
    """Web choices: acknowledged, execution, holding_risks, optional security_risks.

    holding_risks partitions by (sleeve, symbol), with committed_risk_cny.
    security_risks optionally supplies cyclical, common_factors and liquid per
    symbol when official observations cannot certify those economic attributes.
    No cash, IPS, reconciliation, price or quantity overrides are accepted.
    """
    if (not isinstance(scenario, dict)
            or set(scenario) - {"acknowledged", "execution", "holding_risks", "security_risks"}
            or scenario.get("acknowledged") is not True):
        raise ValueError("Scenario choices require explicit acknowledgement and supported fields")
    execution = scenario.get("execution")
    if (not isinstance(execution, dict) or set(execution) != {"liquid", "limit_up", "limit_down"}
            or any(type(value) is not bool for value in execution.values())):
        raise ValueError("Scenario execution requires explicit liquid, limit_up and limit_down booleans")
    if any(not isinstance(scenario.get(key, []), list) for key in ("holding_risks", "security_risks")):
        raise ValueError("Scenario holding_risks and security_risks require lists")
    risks = {}
    for row in scenario.get("holding_risks", []):
        if (not isinstance(row, dict) or set(row) != {"sleeve", "symbol", "committed_risk_cny"}
                or not isinstance(row["sleeve"], str)
                or row["sleeve"] not in {"CORE_VALUE", "HOTSPOT_SATELLITE"}
                or not isinstance(row["symbol"], str)):
            raise ValueError("Scenario holding risks require sleeve, symbol and committed_risk_cny")
        key = (row["sleeve"], row["symbol"])
        if key in risks:
            raise ValueError("Duplicate scenario holding risk")
        value = row["committed_risk_cny"]
        try:
            amount = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError("Committed risk requires an explicit nonnegative finite amount") from error
        if isinstance(value, bool) or not amount.is_finite() or amount < 0:
            raise ValueError("Committed risk requires an explicit nonnegative finite amount")
        risks[key] = str(amount)
    security_risks = {}
    for row in scenario.get("security_risks", []):
        if (not isinstance(row, dict) or "symbol" not in row
                or set(row) - {"symbol", "cyclical", "common_factors", "liquid"}
                or not isinstance(row["symbol"], str) or row["symbol"] in security_risks):
            raise ValueError("Invalid or duplicate scenario security risk")
        for field in ("cyclical", "liquid"):
            if field in row and type(row[field]) is not bool:
                raise ValueError("Scenario cyclical and liquid choices require booleans")
        if "common_factors" in row and (not isinstance(row["common_factors"], list)
                or any(not isinstance(factor, str) or not factor.strip() for factor in row["common_factors"])
                or len(set(row["common_factors"])) != len(row["common_factors"])):
            raise ValueError("Scenario common_factors requires explicit unique text choices")
        if row["symbol"] == symbol and "liquid" in row and row["liquid"] != execution["liquid"]:
            raise ValueError("Candidate liquidity choices conflict")
        security_risks[row["symbol"]] = row
    output = _scenario_preview(None, symbol=symbol, generated_at=generated_at)
    output.update(status="BLOCKED", scope="HYPOTHETICAL_CONFIRMED_ACCOUNT_PROJECTION",
        assumptions=deepcopy(scenario), plan_binding=deepcopy(binding),
        projection={"namespace": "SIMULATED", "account_revision": actual_revision,
            "copied_inputs_scope": "HYPOTHETICAL_COPY_OF_CONFIRMED_ACCOUNT_IPS_AND_VERIFIED_MARKET_NOT_ACTUAL_ELIGIBILITY",
            "reconciliation_inferred": False, "private_inputs_inferred": False},
        required_holding_risks=[], security_risk_gaps=[])
    gaps = list(plan_blockers)
    core = (binding or {}).get("plan", {}).get("strategy") == "CORE_VALUE"
    expiry = (binding or {}).get("plan", {}).get("expires_after_session")
    try:
        if core:
            expiry = binding["valid_until"]
            datetime.fromisoformat(expiry)
        elif not isinstance(expiry, str):
            raise ValueError("Missing plan expiry")
        else:
            date.fromisoformat(expiry)
    except ValueError:
        gaps.append("PLAN_EXPIRY_MISSING_OR_INVALID")
    service = PrivatePortfolioService(journal)
    replayed = service._replay(service.records())
    if replayed is None:
        gaps.append("PRIVATE_PORTFOLIO_NOT_CONNECTED")
    else:
        if replayed.revision != actual_revision:
            gaps.append("SCENARIO_ACCOUNT_REVISION_CHANGED")
        if not replayed.policy.get("_confirmed_at"):
            gaps.append("SCENARIO_CONFIRMED_IPS_REQUIRED")
        if replayed.policy.get("effective_date") and date.fromisoformat(replayed.policy["effective_date"]) > generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date():
            gaps.append("POLICY_NOT_EFFECTIVE")
        reconciliation = reconciliation_state(replayed)
        if reconciliation["status"] != "RECONCILED":
            gaps.append("reconciliation")
        if reconciliation["scope"] != "EXTERNAL_ACCOUNT_STATEMENT":
            gaps.append("EXTERNAL_ACCOUNT_RECONCILIATION_MISSING")
    if gaps:
        output["blockers"] = list(dict.fromkeys(gaps))
        return output
    plan = binding["plan"]
    if core:
        request = {key: assumptions[key] for key in (
            "entry_slippage_cny", "buy_fee_fraction", "minimum_buy_fee_cny", "max_trade_notional_cny")}
        request.update(symbol=symbol, lot_size=int(Decimal(str(assumptions["lot_size"]))),
            entry_price_cny=plan["reference_close"], quote_as_of=plan["market_trade_date"],
            available_at=binding["available_at"], valid_until=expiry,
            liquidity_verified=execution["liquid"], limit_up=execution["limit_up"], limit_down=execution["limit_down"])
        output["core_sizing_inputs"] = deepcopy(request)
    else:
        request = {**assumptions, "lot_size": int(Decimal(str(assumptions["lot_size"]))),
        "symbol": symbol, "sleeve": "HOTSPOT_SATELLITE",
        "entry_price_cny": plan["entry_trigger_price"], "stop_price_cny": plan["invalidation_price"],
        "quote_as_of": plan["market_trade_date"], "available_at": plan["data_available_at"],
        "valid_until": expiry + "T15:00:00+08:00",
        "liquidity_verified": execution["liquid"], "limit_up": execution["limit_up"],
        "limit_down": execution["limit_down"],
        "research_version_sha256": hashlib.sha256(plan["research_version"].encode()).hexdigest(),
        "evidence_ref": "SIMULATED-execution-assumptions:" + plan["case_sha256"]}
    data = deepcopy(build_risk_input(replayed,
        sellable_as_of=generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        namespace="SIMULATED", repository_root=repository_root, generated_at=generated_at,
        hotspot_request=None if core else request, candidate_symbol=symbol))
    data["portfolio"]["snapshot"]["namespace"] = "SIMULATED"
    data["portfolio"]["policy"]["sensitivity"] = "SIMULATED_DEMONSTRATION"
    data["shared_budget"]["policy_scope"] = "SYNTHETIC_POLICY_ONLY"
    if any(row["market_value_cny"] is None for row in data["portfolio"]["snapshot"]["holdings"]):
        gaps.append("holding_market_value")
    if any(Decimal(row["cash_cny"]) < 0 for row in data["sleeves"].values()):
        gaps.append("SLEEVE_CASH_OVERDRAWN")
    expected = {(row["sleeve"], row["symbol"]) for row in data["allocations"]}
    if risks.keys() - expected:
        raise ValueError("Scenario holding risk does not match a confirmed sleeve holding")
    for row in data["allocations"]:
        key = (row["sleeve"], row["symbol"])
        if key not in risks:
            gaps.append("SCENARIO_HOLDING_RISK_MISSING:" + ":".join(key))
            output["required_holding_risks"].append({"sleeve": key[0], "symbol": key[1]})
        else:
            row["committed_risk_cny"] = risks[key]
            row["evidence_ref"] = "SIMULATED-explicit-holding-risk"
    needed = {symbol, *(row["symbol"] for row in data["allocations"])}
    if security_risks.keys() - needed:
        raise ValueError("Scenario security risk is outside candidate and confirmed holdings")
    attributes = {row["symbol"]: row for row in data["security_attributes"] or []}
    projected = []
    for code in sorted(needed):
        attribute = attributes.get(code)
        if attribute is None:
            gaps.append("security_attributes." + code + ".missing")
            continue
        if attribute.get("schema_version") == ATTRIBUTE_SCHEMA:
            # Never mutate an official observation into a purported certified fact.
            # Convert only inside SIMULATED, preserving the original source refs.
            observed = parse_observed_attributes(attribute, now=generated_at)
            snapshot = data["portfolio"]["snapshot"]
            if datetime.fromisoformat(attribute["known_at"]).astimezone(ZoneInfo("Asia/Shanghai")).date() > date.fromisoformat(snapshot["as_of"]):
                gaps.append("security_attributes." + code + ".not_known_at_snapshot")
            holding = next((row for row in snapshot["holdings"] if row["symbol"] == code), None)
            if holding is not None and holding["exchange"] != attribute["exchange"]:
                raise ValueError("Holding and official security exchange differ")
            attribute = {"symbol": code, "industry": observed.industry,
                "cyclical": None, "common_factors": None, "liquidity_profile": "UNKNOWN",
                "evidence_refs": list(observed.evidence_refs)}
        else:
            attribute = deepcopy(attribute)
        choices = security_risks.get(code, {})
        for field in ("cyclical", "common_factors"):
            if field in choices:
                attribute[field] = deepcopy(choices[field])
        liquid = execution["liquid"] if code == symbol else choices.get("liquid")
        if liquid is not None:
            attribute["liquidity_profile"] = "LIQUID" if liquid else "RESTRICTED"
        missing = [field for field in ("industry", "cyclical", "common_factors", "liquidity_profile")
            if attribute.get(field) is None or attribute[field] == "UNKNOWN"]
        if missing:
            output["security_risk_gaps"].append({"symbol": code, "fields": missing})
            gaps.extend("SCENARIO_SECURITY_RISK_MISSING:" + code + ":" + field for field in missing)
        else:
            attribute["evidence_refs"] = [*attribute["evidence_refs"],
                {"id": "SIMULATED-explicit-security-risk", "kind": "hypothetical_assumption"}]
            projected.append(attribute)
    if gaps:
        output["blockers"] = list(dict.fromkeys(gaps))
        return output
    data["security_attributes"] = projected
    calculated = _scenario_preview({"acknowledged": True, "risk_input": data},
        symbol=symbol, generated_at=generated_at, core_request=request if core else None)
    output.update(status=calculated["status"], review_quantity=calculated["review_quantity"],
        blockers=calculated["blockers"], engine=calculated["engine"])
    _enforce_quantity_rule(output, verified_rules)
    return output


def _enforce_quantity_rule(output, rule):
    blockers = quantity_rule_blockers(output.get("review_quantity"), rule)
    if blockers:
        output.update(review_quantity=None, status="BLOCKED",
            blockers=list(dict.fromkeys([*output.get("blockers", []), *blockers])))
        for key in ("hotspot_quantity_review", "core_quantity_review"):
            review = (output.get("engine") or {}).get(key)
            if review:
                review.update(review_quantity=None, status="BLOCKED",
                    blockers=list(dict.fromkeys([*review.get("blockers", []), *blockers])))


def _actionable_decision(result, *, binding, symbol, sleeve, generated_at):
    """Assemble only actual verified inputs; scenario output is never consulted."""
    sizing = result["sizing_preview"]
    engine = result.get("engine") or {}
    facts = result.get("facts") or {}
    plan = (binding or {}).get("plan") or {}
    blockers = list(dict.fromkeys([*result.get("blockers", []),
        *engine.get("blockers", []), *sizing.get("blockers", []), *plan.get("blockers", [])]))
    eligible = (plan.get("risk_review_eligible") is True
        and (plan.get("independent_admission") or {}).get("namespace") == "ACTUAL"
        if sleeve == "HOTSPOT_SATELLITE" else plan.get("formal_eligibility") is True)
    if not binding or not eligible:
        blockers.append("CURRENT_PLAN_NOT_FORMALLY_ELIGIBLE")
    if sleeve == "HOTSPOT_SATELLITE" and plan.get("signal_state") != "TRIGGER_OBSERVED":
        blockers.append("CURRENT_ENTRY_CONDITION_NOT_OBSERVED")
    if sleeve == "CORE_VALUE" and plan.get("current_quote_verified") is not True:
        blockers.append("CURRENT_VALUE_QUOTE_NOT_VERIFIED")
    if (engine.get("namespace") != "ACTUAL" or engine.get("status") != "RISK_REVIEW_CALCULATED"
            or result.get("status") != "RISK_REVIEW_CALCULATED"):
        blockers.append("ACTUAL_RISK_REVIEW_REQUIRED")
    account_scope = facts.get("account_scope")
    if not isinstance(account_scope, str) or not account_scope.strip():
        blockers.append("ACTUAL_ACCOUNT_SCOPE_REQUIRED")
    else:
        normalized_scope = account_scope.upper().replace("-", "_").replace(" ", "_")
        if any(marker in normalized_scope for marker in (
                "TEST_ONLY", "TESTONLY", "SIMULATED", "SIMULATION", "SYNTHETIC")):
            blockers.append("TEST_OR_SIMULATED_ACCOUNT_NOT_ELIGIBLE")
    if not sizing.get("verified_rules"):
        blockers.append("VERIFIED_TRADING_RULE_REQUIRED")
    if (result.get("policy") or {}).get("confirmation_status") != "HUMAN_CONFIRMED":
        blockers.append("CONFIRMED_IPS_REQUIRED")
    if (not facts or facts.get("reconciliation", {}).get("scope") != "EXTERNAL_ACCOUNT_STATEMENT"
            or facts.get("reconciliation_status") != "RECONCILED"):
        blockers.append("EXTERNAL_ACCOUNT_RECONCILIATION_MISSING")
    quantity = sizing.get("review_quantity")
    if type(quantity) is not int or quantity <= 0:
        blockers.append("POSITIVE_ACTUAL_REVIEW_QUANTITY_REQUIRED")
    if plan.get("namespace") in {"SIMULATED", "TEST_ONLY"} or (binding or {}).get("publication_id", "").startswith("TEST_ONLY"):
        blockers.append("TEST_ONLY_PLAN_NOT_FORMAL")
    expiry = plan.get("expires_after_session")
    try:
        if sleeve == "CORE_VALUE":
            end = datetime.fromisoformat((binding or {}).get("valid_until", ""))
            if end.utcoffset() is None:
                raise ValueError("CORE expiry requires timezone")
            expired = end < generated_at
        else:
            expired = date.fromisoformat(expiry) < generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
        if expired:
            blockers.append("CURRENT_PLAN_EXPIRED")
    except (ValueError, TypeError):
        blockers.append("PLAN_EXPIRY_MISSING_OR_INVALID")
    held = any(row.get("symbol") == symbol and any(part.get("sleeve") == sleeve
        and Decimal(part["quantity"]) > 0 for part in row.get("sleeves", []))
        for row in facts.get("positions", []))
    if held and plan.get("add_condition") is None:
        blockers.append("CURRENT_PLAN_ADD_CONDITION_MISSING")
    if held:
        add = plan.get("add_condition")
        if (plan.get("action_intent") != "ADD" or not isinstance(add, dict)
                or not (add.get("triggered") is True or add.get("observed") is True)):
            blockers.append("CURRENT_ADD_CONDITION_NOT_CONFIRMED")
        # A public example's entry thesis is not the account's original thesis.
        # The current journal has no authenticated ownership-binding event.
        blockers.append("PERSONAL_ENTRY_THESIS_CONFIRMATION_RECORD_UNSUPPORTED")
    if plan.get("symbol") != symbol or plan.get("action_intent") not in {"OPEN", "ADD"}:
        blockers.append("CURRENT_PLAN_NOT_BUY_OR_ADD")
    if not held and plan.get("action_intent") == "ADD":
        blockers.append("ADD_REQUIRES_SAME_SLEEVE_HOLDING")
    blockers = list(dict.fromkeys(blockers))
    details = sizing.get("sizing_details") or {}
    assumptions = sizing.get("effective_sizing_inputs") or {}
    admission = plan.get("independent_admission") or {}
    evidence = []
    for ref in [*(plan.get("evidence_refs") or []), *(plan.get("source_bindings") or []),
            *(admission.get("evidence_refs") or [])]:
        if ref not in evidence:
            evidence.append(deepcopy(ref))
    fees = {key: assumptions.get(key) for key in (
        "buy_fee_fraction", "sell_fee_fraction", "minimum_buy_fee_cny", "minimum_sell_fee_cny",
        "entry_slippage_cny", "exit_slippage_cny", "gap_stress_cny")}
    downside = deepcopy(plan.get("downside_risk_scenarios"))
    if downside is None and details.get("stressed_loss_cny") is not None:
        downside = [{key: deepcopy(details.get(key)) for key in (
            "stressed_loss_cny", "stressed_exit_price_cny", "full_capital_at_risk_cny",
            "stop_execution_guaranteed", "t_plus_one", "same_day_exit_available", "limitations")}]
    evaluated_vetoes = {
        "CURRENT_ENTRY_CONDITION_NOT_OBSERVED", "SLEEVE_CASH_OVERDRAWN",
        "hotspot:budget_below_one_lot", "core:budget_below_one_lot",
        "HOTSPOT_SATELLITE:sleeve_cash_budget_insufficient",
        "CORE_VALUE:sleeve_cash_budget_insufficient",
    }
    known_veto = bool(set(blockers) & evaluated_vetoes)
    allowed_vetoes = evaluated_vetoes | {"POSITIVE_ACTUAL_REVIEW_QUANTITY_REQUIRED"}
    negative = "NO_TRADE" if known_veto and set(blockers) <= allowed_vetoes else "UNASSESSABLE"
    outcome = negative if blockers else "ADD" if held else "BUY"
    status = negative if blockers else "CONDITIONAL_MANUAL_REVIEW"
    return {"action": "no_order", "decision_action": outcome,
        "decision_layer": "PERSONAL_ACTION_REVIEW",
        "symbol": symbol, "strategy": sleeve, "status": status,
        "company_name": plan.get("company_name"),
        "generated_at": generated_at.isoformat(), "decision_generated_at": generated_at.isoformat(),
        "plan_generated_at": plan.get("generated_at"),
        "research_as_of": plan.get("research_as_of"), "decision_as_of": plan.get("decision_as_of"),
        "data_trade_date": plan.get("market_trade_date"), "data_available_at": plan.get("data_available_at", (binding or {}).get("available_at")),
        "research_or_structure_version": plan.get("research_version", plan.get("model_or_rule_version")),
        "current_verified_reference_price": plan.get("reference_close") if sleeve == "CORE_VALUE" else plan.get("current_reference_price"),
        "reference_price_scope": plan.get("reference_price_scope"),
        "entry_condition": deepcopy(plan.get("entry_condition")),
        "entry_price_or_range": plan.get("entry_trigger_price"),
        "add_condition": deepcopy(plan.get("add_condition")),
        "reduce_condition": deepcopy(plan.get("reduce_condition")),
        "exit_condition": deepcopy(plan.get("exit_condition")),
        "invalidation_condition": deepcopy(plan.get("invalidation_condition", plan.get("thesis_invalidation"))),
        "plan_expiry": (binding or {}).get("valid_until") if sleeve == "CORE_VALUE" else expiry,
        "valid_from_session": plan.get("valid_from_session"),
        "risk_sizing": deepcopy(details) or None,
        "available_cash_impact": details.get("cash_required_cny"),
        "expected_fees_and_slippage": {"scope": "EXPLICIT_ASSUMPTIONS_NOT_BROKER_CHARGES", **fees} if any(value is not None for value in fees.values()) else None,
        "downside_risk_scenarios": downside,
        "evidence_refs": evidence or None,
        "formal_review_status": (admission.get("review_status") if sleeve == "HOTSPOT_SATELLITE" else plan.get("qualification")),
        "personal_risk_status": engine.get("status"),
        "eligibility": {"status": status,
            "manual_review_eligible": not blockers, "trade_eligible": False,
            "broker_execution_permission": False},
        "decision_reason": "; ".join(blockers) if blockers else "Verified current plan and actual portfolio risk permit conditional manual review.",
        "blockers": blockers, "review_quantity": None if blockers else quantity,
        "plan_binding": binding, "required_confirmation": "Human review of current conditions before any broker operation",
        "trade_eligible": False, "broker_execution_permission": False}


def _current_plan(root, symbol, now):
    packet, error = load_current_packet(root)
    if packet is None:
        return None, "PUBLIC_SNAPSHOT_UNAVAILABLE"
    chain = load_current_chain(root)
    observed = [{"role": row["role"], "path": row["path"], "sha256": row["sha256"]}
        for row in sorted(chain["bindings"], key=lambda row: str(row["role"]))]
    if packet.get("identity_inputs", {}).get("chain") != observed:
        return None, "PUBLICATION_VERSION_MISMATCH"
    frozen_registry = packet.get("identity_inputs", {}).get("current_price_conditions")
    if frozen_registry is None or frozen_registry != registry_identity(root):
        return None, "CURRENT_PRICE_REGISTRY_CHANGED"
    fresh = load_price_conditions(root, now=now, research_version=packet.get("research_version"))
    plan = next((row["price_action_plan"] for row in fresh["items"] if row["symbol"] == symbol), None)
    frozen = next((row["price_action_plan"] for row in packet.get("price_conditions", {}).get("items", [])
        if row["symbol"] == symbol), None)
    if plan is None or frozen != plan:
        return None, "CURRENT_PLAN_UNAVAILABLE_OR_CHANGED"
    if (plan.get("signal_state") in {"STALE", "BLOCKED", "TRIGGER_REJECTED", "EXPIRED"}
            or plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"):
        return None, "CURRENT_PLAN_STALE_OR_INVALIDATED"
    independent = project_independent_price_condition(root, symbol=symbol, plan=plan, now=now)
    return {"publication_id": packet["publication_id"], "plan": independent}, None


def preview_private_hotspot_risk(journal, *, repository_root, generated_at: datetime, payload):
    if payload.get("sleeve") == "CORE_VALUE":
        return preview_private_core_risk(journal, repository_root=repository_root,
            generated_at=generated_at, payload=payload)
    # Always preserve the existing engine's account facts and missing-input report.
    result = review_private_risk_rehearsal(journal, generated_at=generated_at, repository_root=repository_root)
    blockers = []
    binding = None
    if set(payload) - {"symbol", "assumptions", "scenario"}:
        raise ValueError("只接受证券代码和费用、滑点、跳空、交易单位等假设；价格与资格由服务器核验。")
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("请填写六位证券代码。")
    assumptions = payload.get("assumptions", {})
    if not isinstance(assumptions, dict) or set(assumptions) - set(ASSUMPTION_FIELDS):
        raise ValueError("仓位试算包含不支持的假设字段。")
    assumptions = deepcopy(assumptions)
    attributes = load_verified_security_attributes(repository_root, {symbol}, now=generated_at)
    verified_rules = trading_rules_for(attributes, symbol)
    supplied_lot = assumptions.get("lot_size")
    missing = [field for field in ASSUMPTION_FIELDS if assumptions.get(field) in (None, "")]
    blockers.extend("ASSUMPTION_MISSING:" + field for field in missing)
    for field, value in assumptions.items():
        if value in (None, ""):
            continue
        try:
            amount = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError("试算假设必须是明确的非负数字。") from error
        if isinstance(value, bool) or not amount.is_finite() or amount < 0:
            raise ValueError("试算假设必须是明确的非负数字。")
        if field.endswith("fraction") and amount > 1:
            raise ValueError("费用比率应在 0 到 1 之间。")
        if field == "lot_size" and (amount <= 0 or amount != amount.to_integral_value()):
            raise ValueError("交易单位必须是正整数。")
    if verified_rules:
        if supplied_lot not in (None, "") and Decimal(str(supplied_lot)) != verified_rules["lot_size"]:
            raise ValueError("交易单位假设与已核验公开规则冲突。")
        assumptions["lot_size"] = verified_rules["lot_size"]
        blockers = [item for item in blockers if item != "ASSUMPTION_MISSING:lot_size"]
    try:
        binding, error = _current_plan(repository_root, symbol, generated_at)
        if error:
            blockers.append(error)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
        blockers.append("CURRENT_PLAN_UNAVAILABLE_OR_CHANGED")
    if binding:
        plan = binding["plan"]
        try:
            if not isinstance(plan.get("expires_after_session"), str):
                raise ValueError("Missing plan expiry")
            date.fromisoformat(plan["expires_after_session"])
        except ValueError:
            blockers.append("PLAN_EXPIRY_MISSING_OR_INVALID")
        entry, stop = plan.get("entry_trigger_price"), plan.get("invalidation_price")
        if entry is None or stop is None:
            blockers.append("PLAN_PRICE_MISSING")
        elif not Decimal(0) < Decimal(stop) < Decimal(entry):
            blockers.append("PLAN_PROTECTION_INVALID")
    scenario_plan_blockers = list(blockers)
    if binding:
        # The existing engine requires actual verified execution-state booleans.
        # A dual-source close alone does not prove liquidity or price-limit state.
        close = plan.get("current_reference_close", {})
        attribute = next((row for row in attributes or [] if row["symbol"] == symbol), {})
        if attribute.get("liquidity_profile") != "LIQUID":
            blockers.append("CANDIDATE_LIQUIDITY_UNKNOWN")
        if any(type(close.get(key)) is not bool for key in ("limit_up", "limit_down")):
            blockers.append("PRICE_LIMIT_STATE_UNKNOWN")
        if not blockers:
            request = {**assumptions, "lot_size": int(Decimal(str(assumptions["lot_size"]))),
                "symbol": symbol, "sleeve": "HOTSPOT_SATELLITE", "entry_price_cny": entry,
                "stop_price_cny": stop, "quote_as_of": plan["market_trade_date"],
                "available_at": plan["data_available_at"],
                "valid_until": plan["expires_after_session"] + "T15:00:00+08:00",
                "liquidity_verified": True, "limit_up": close["limit_up"], "limit_down": close["limit_down"],
                "research_version_sha256": hashlib.sha256(plan["research_version"].encode()).hexdigest(),
                "evidence_ref": plan["case_sha256"]}
            result = review_private_risk_rehearsal(journal, generated_at=generated_at,
                repository_root=repository_root, hotspot_request=request)
    engine_review = (result.get("engine") or {}).get("hotspot_quantity_review") or {}
    blockers = list(dict.fromkeys([*blockers, *result.get("blockers", []), *engine_review.get("blockers", [])]))
    blockers.extend(quantity_rule_blockers(engine_review.get("review_quantity"), verified_rules))
    _enforce_quantity_rule({"review_quantity": engine_review.get("review_quantity"),
        "engine": result.get("engine")}, verified_rules)
    result["sizing_preview"] = {"symbol": symbol, "review_quantity": None if blockers else engine_review.get("review_quantity"),
        "scope": "CONDITIONAL_SCENARIO_ONLY", "formal_review_quantity": None,
        "blockers": blockers, "status": "BLOCKED" if blockers else engine_review.get("status", "BLOCKED"),
        "plan_binding": binding, "assumptions": deepcopy(payload.get("assumptions", {})),
        "effective_sizing_inputs": assumptions, "verified_rules": verified_rules,
        "trading_unit_basis": ("VERIFIED_PUBLIC_RULE" if verified_rules else
            "EXPLICIT_SCENARIO_ASSUMPTION" if supplied_lot not in (None, "") else "UNKNOWN"),
        "trade_eligible": False,
        "formal_eligibility": binding["plan"].get("formal_eligibility") if binding else None,
        "stop_execution_guaranteed": False, "sizing_details": engine_review or None}
    scenario = payload.get("scenario")
    if isinstance(scenario, dict) and "risk_input" not in scenario:
        result["scenario_preview"] = _projected_scenario(scenario, journal=journal,
            symbol=symbol, assumptions=assumptions, binding=binding,
            plan_blockers=scenario_plan_blockers,
            actual_revision=(result.get("facts") or {}).get("revision"),
            repository_root=repository_root, generated_at=generated_at, verified_rules=verified_rules)
    else:
        result["scenario_preview"] = _scenario_preview(scenario,
            symbol=symbol, generated_at=generated_at)
        if scenario is not None:
            result["scenario_preview"]["scope"] = "TEST_ONLY_RAW_ENGINE_INPUT"
    result["actionable_decision"] = _actionable_decision(result, binding=binding,
        symbol=symbol, sleeve="HOTSPOT_SATELLITE", generated_at=generated_at)
    return result


def _current_value_plan(root, symbol, now):
    packet, error = load_current_packet(root)
    if packet is None:
        return None, "PUBLIC_SNAPSHOT_UNAVAILABLE"
    chain = load_current_chain(root)
    observed = [{"role": row["role"], "path": row["path"], "sha256": row["sha256"]}
        for row in sorted(chain["bindings"], key=lambda row: str(row["role"]))]
    if packet.get("identity_inputs", {}).get("chain") != observed:
        return None, "PUBLICATION_VERSION_MISMATCH"
    fresh = load_registered_value_action_plans(root, now=now, symbols=[symbol])
    plan = next((item for item in fresh["items"] if item["symbol"] == symbol), None)
    frozen = packet.get("value_price_conditions", {}).get(symbol)
    # The public packet adds presentation aliases; compare every authoritative
    # field reconstructed by the registered-plan loader, not those aliases.
    if plan is None or not isinstance(frozen, dict) or any(frozen.get(key) != value for key, value in plan.items()):
        return None, "CURRENT_VALUE_PLAN_UNAVAILABLE_OR_CHANGED"
    if (plan.get("formal_eligibility") is not True or plan.get("current_quote_verified") is not True
            or plan.get("strategy") != "CORE_VALUE" or plan.get("action_intent") not in {"OPEN", "ADD"}):
        return None, "VALUE_PLAN_NOT_QUALIFIED_FOR_SIZING"
    registration = (plan.get("safety_margin_policy") or {}).get("source_binding")
    policy = load_value_action_policy(root=root, binding=registration, symbol=symbol, now=now)
    if policy is None:
        return None, "VALUE_REGISTERED_POLICY_REQUIRED"
    execution = execute_quote_bridge_for_symbol(root, symbol, today=now)
    quote = execution.get("quote") or {}
    verified = (execution.get("compatibility") or {}).get("verified_quote") or {}
    execution_close = (quote if verified.get("eligible") is True
        and quote.get("quote_date") == quote.get("latest_completed_session") == plan["market_trade_date"]
        and str(quote.get("display_price")) == str(plan["reference_close"]) else {})
    return {"publication_id": packet["publication_id"], "plan": plan,
        "available_at": packet["generated_at"],
        "execution_close": execution_close,
        "valid_until": policy.effective_through.isoformat() + "T23:59:59+08:00"}, None


def preview_private_core_risk(journal, *, repository_root, generated_at, payload):
    """Registered value plan with actual risk facts; scenarios remain separate."""
    if set(payload) - {"symbol", "sleeve", "assumptions", "scenario"}:
        raise ValueError("Unsupported CORE sizing fields")
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit():
        raise ValueError("CORE sizing requires a six-digit security")
    required = {"lot_size", "max_trade_notional_cny", "entry_slippage_cny", "buy_fee_fraction", "minimum_buy_fee_cny"}
    assumptions = deepcopy(payload.get("assumptions", {}))
    if not isinstance(assumptions, dict) or set(assumptions) != required:
        raise ValueError("CORE requires explicit tranche budget, unit, slippage and buy costs")
    for key, value in assumptions.items():
        try:
            amount = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError("CORE assumptions require finite nonnegative numbers") from error
        if isinstance(value, bool) or not amount.is_finite() or amount < 0:
            raise ValueError("CORE assumptions require finite nonnegative numbers")
        if key == "buy_fee_fraction" and amount > 1:
            raise ValueError("CORE fee fraction exceeds one")
        if key == "lot_size" and (amount <= 0 or amount != amount.to_integral_value()):
            raise ValueError("CORE trading unit requires a positive integer")
    result = review_private_risk_rehearsal(journal, generated_at=generated_at, repository_root=repository_root)
    attributes = load_verified_security_attributes(repository_root, {symbol}, now=generated_at)
    rules = trading_rules_for(attributes, symbol)
    if rules and Decimal(str(assumptions["lot_size"])) != rules["lot_size"]:
        raise ValueError("CORE trading unit conflicts with verified rules")
    binding, blockers = None, []
    try:
        binding, error = _current_value_plan(repository_root, symbol, generated_at)
        if error:
            blockers.append(error)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        blockers.append("CURRENT_VALUE_PLAN_UNAVAILABLE_OR_CHANGED")
    scenario = payload.get("scenario")
    if scenario is None:
        projected = _scenario_preview(None, symbol=symbol, generated_at=generated_at)
    else:
        projected = _projected_scenario(scenario, journal=journal, symbol=symbol,
            assumptions=assumptions, binding=binding, plan_blockers=blockers,
            actual_revision=(result.get("facts") or {}).get("revision"),
            repository_root=repository_root, generated_at=generated_at, verified_rules=rules)
    attribute = next((row for row in attributes or [] if row["symbol"] == symbol), {})
    close = (binding or {}).get("execution_close") or {}
    if attribute.get("liquidity_profile") != "LIQUID":
        blockers.append("CANDIDATE_LIQUIDITY_UNKNOWN")
    if any(type(close.get(key)) is not bool for key in ("limit_up", "limit_down")):
        blockers.append("PRICE_LIMIT_STATE_UNKNOWN")
    if not rules:
        blockers.append("VERIFIED_TRADING_RULE_REQUIRED")
    if binding and not blockers:
        plan = binding["plan"]
        request = {key: assumptions[key] for key in (
            "entry_slippage_cny", "buy_fee_fraction", "minimum_buy_fee_cny", "max_trade_notional_cny")}
        request.update(symbol=symbol, lot_size=int(Decimal(str(assumptions["lot_size"]))),
            entry_price_cny=plan["reference_close"], quote_as_of=plan["market_trade_date"],
            available_at=binding["available_at"], valid_until=binding["valid_until"],
            liquidity_verified=True, limit_up=close["limit_up"], limit_down=close["limit_down"])
        result = review_private_risk_rehearsal(journal, generated_at=generated_at,
            repository_root=repository_root, core_request=request)
    review = (result.get("engine") or {}).get("core_quantity_review") or {}
    blockers = list(dict.fromkeys([*blockers, *result.get("blockers", []), *review.get("blockers", []),
        *quantity_rule_blockers(review.get("review_quantity"), rules)]))
    _enforce_quantity_rule({"review_quantity": review.get("review_quantity"), "engine": result.get("engine")}, rules)
    result["sizing_preview"] = {"symbol": symbol, "sleeve": "CORE_VALUE",
        "review_quantity": None if blockers else review.get("review_quantity"),
        "formal_review_quantity": None, "status": "BLOCKED" if blockers else review.get("status", "BLOCKED"),
        "formal_eligibility": (binding or {}).get("plan", {}).get("formal_eligibility", False),
        "trade_eligible": False, "plan_binding": binding,
        "effective_sizing_inputs": assumptions, "verified_rules": rules,
        "sizing_details": review or None, "blockers": blockers}
    result["scenario_preview"] = projected
    result["actionable_decision"] = _actionable_decision(result, binding=binding,
        symbol=symbol, sleeve="CORE_VALUE", generated_at=generated_at)
    return result

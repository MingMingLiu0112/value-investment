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
from ..product.public_snapshot import load_current_packet
from ..product.publication_chain import load_current_chain
from .private_risk_projection import build_risk_input, review_private_risk_rehearsal
from .private_portfolio_service import PrivatePortfolioService, reconciliation_state
from .security_attributes import load_verified_security_attributes, trading_rules_for

ASSUMPTION_FIELDS = (
    "gap_stress_cny", "entry_slippage_cny", "exit_slippage_cny", "buy_fee_fraction",
    "sell_fee_fraction", "minimum_buy_fee_cny", "minimum_sell_fee_cny", "lot_size",
    "max_trade_notional_cny",
)


def _scenario_preview(scenario, *, symbol, generated_at):
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
    request = risk_input.get("hotspot_request")
    if not isinstance(request, dict) or request.get("symbol") != symbol:
        raise ValueError("Scenario requires a hypothetical hotspot request for the requested symbol")
    report = review_dual_sleeve_risk(risk_input, generated_at=generated_at, allow_synthetic=True)
    review = report.get("hotspot_quantity_review") or {}
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
    request = {**assumptions, "lot_size": int(Decimal(str(assumptions["lot_size"]))),
        "symbol": symbol, "sleeve": "HOTSPOT_SATELLITE",
        "entry_price_cny": plan["entry_trigger_price"], "stop_price_cny": plan["invalidation_price"],
        "quote_as_of": plan["market_trade_date"], "available_at": plan["data_available_at"],
        "valid_until": plan["expires_after_session"] + "T15:00:00+08:00",
        "liquidity_verified": execution["liquid"], "limit_up": execution["limit_up"],
        "limit_down": execution["limit_down"],
        "research_version_sha256": hashlib.sha256(plan["research_version"].encode()).hexdigest(),
        "evidence_ref": "SIMULATED-execution-assumptions:" + plan["case_sha256"]}
    data = deepcopy(build_risk_input(replayed,
        sellable_as_of=generated_at.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        namespace="SIMULATED", repository_root=repository_root, generated_at=generated_at,
        hotspot_request=request))
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
        symbol=symbol, generated_at=generated_at)
    output.update(status=calculated["status"], review_quantity=calculated["review_quantity"],
        blockers=calculated["blockers"], engine=calculated["engine"])
    _enforce_quantity_rule(output, verified_rules)
    return output


def _enforce_quantity_rule(output, rule):
    blockers = quantity_rule_blockers(output.get("review_quantity"), rule)
    if blockers:
        output.update(review_quantity=None, status="BLOCKED",
            blockers=list(dict.fromkeys([*output.get("blockers", []), *blockers])))
        review = (output.get("engine") or {}).get("hotspot_quantity_review")
        if review:
            review.update(review_quantity=None, status="BLOCKED",
                blockers=list(dict.fromkeys([*review.get("blockers", []), *blockers])))


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
    if (plan.get("signal_state") in {"STALE", "BLOCKED", "TRIGGER_REJECTED"}
            or plan.get("candidate_lifecycle") == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"):
        return None, "CURRENT_PLAN_STALE_OR_INVALIDATED"
    return {"publication_id": packet["publication_id"], "plan": plan}, None


def preview_private_hotspot_risk(journal, *, repository_root, generated_at: datetime, payload):
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
    return result

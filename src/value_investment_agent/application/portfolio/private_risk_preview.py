"""Non-writing conditional sizing from a reverified current public plan."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib

from ..hotspot.current_registry import load_price_conditions, registry_identity
from ..product.public_snapshot import load_current_packet
from ..product.publication_chain import load_current_chain
from .private_risk_projection import review_private_risk_rehearsal
from .security_attributes import load_verified_security_attributes

ASSUMPTION_FIELDS = (
    "gap_stress_cny", "entry_slippage_cny", "exit_slippage_cny", "buy_fee_fraction",
    "sell_fee_fraction", "minimum_buy_fee_cny", "minimum_sell_fee_cny", "lot_size",
    "max_trade_notional_cny",
)


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
    if set(payload) - {"symbol", "assumptions"}:
        raise ValueError("只接受证券代码和费用、滑点、跳空、交易单位等假设；价格与资格由服务器核验。")
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("请填写六位证券代码。")
    assumptions = payload.get("assumptions", {})
    if not isinstance(assumptions, dict) or set(assumptions) - set(ASSUMPTION_FIELDS):
        raise ValueError("仓位试算包含不支持的假设字段。")
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
        # The existing engine requires actual verified execution-state booleans.
        # A dual-source close alone does not prove liquidity or price-limit state.
        close = plan.get("current_reference_close", {})
        attributes = load_verified_security_attributes(repository_root, {symbol}, now=generated_at)
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
    result["sizing_preview"] = {"symbol": symbol, "review_quantity": None if blockers else engine_review.get("review_quantity"),
        "blockers": blockers, "status": "BLOCKED" if blockers else engine_review.get("status", "BLOCKED"),
        "plan_binding": binding, "assumptions": assumptions, "trade_eligible": False,
        "formal_eligibility": binding["plan"].get("formal_eligibility") if binding else None,
        "stop_execution_guaranteed": False, "sizing_details": engine_review or None}
    return result

"""Explicit private IPS input; partial drafts never supply default preferences."""
from datetime import date
from decimal import Decimal

from .dual_sleeve_risk import decimal, timestamp

AMOUNTS = ("investable_assets_cny", "core_value_budget_cny", "hotspot_budget_cny",
    "cash_reserve_cny", "minimum_cash_cny", "emergency_cash_cny", "liquidity_needs_cny",
    "dividend_income_goal_cny", "time_horizon_years")
PERCENTAGES = ("max_single_security_pct", "max_single_industry_pct", "max_cyclical_exposure_pct",
    "hotspot_single_trade_risk_pct", "max_drawdown_pct", "max_factor_pct")
BOOLEANS = ("financing_allowed", "risk_tools_allowed", "concentration_allowed")
REQUIRED = ("investable_assets_cny", "core_value_budget_cny", "hotspot_budget_cny",
    "cash_reserve_cny", "minimum_cash_cny", "max_single_security_pct", "max_single_industry_pct",
    "hotspot_single_trade_risk_pct", "max_drawdown_pct", "financing_allowed",
    "dividend_income_goal_cny", "effective_date", "time_horizon_years", "risk_tolerance",
    "concentration_allowed", "max_factor_pct", "risk_tools_allowed")
SLEEVES = ("CORE_VALUE", "HOTSPOT_SATELLITE")


def normalize_policy(source):
    if not isinstance(source, dict):
        raise ValueError("policy must be an object")
    allowed = set(AMOUNTS + PERCENTAGES + BOOLEANS) | {
        "effective_date", "risk_tolerance", "tax_regime", "restrictions", "sleeves",
        "security_attribute_bindings", "action"}
    if set(source) - allowed or source.get("action", "no_order") != "no_order":
        raise ValueError("unknown policy fields or action")
    result = {"action": "no_order"}
    for key in AMOUNTS + PERCENTAGES:
        if source.get(key) is not None:
            value = decimal(source[key], key)
            if key in PERCENTAGES and value > 100:
                raise ValueError(key + " must be <= 100")
            if key in ("investable_assets_cny", "time_horizon_years") and value <= 0:
                raise ValueError(key + " must be positive")
            if key in ("max_single_security_pct", "max_single_industry_pct") and value <= 0:
                raise ValueError(key + " must be positive")
            result[key] = str(value)
    for key in BOOLEANS:
        if source.get(key) is not None:
            if type(source[key]) is not bool:
                raise ValueError(key + " must be an explicit boolean")
            result[key] = source[key]
    if source.get("effective_date") is not None:
        result["effective_date"] = date.fromisoformat(source["effective_date"]).isoformat()
    for key in ("risk_tolerance", "tax_regime"):
        if source.get(key) is not None:
            if not isinstance(source[key], str) or not source[key].strip():
                raise ValueError(key + " must be nonempty text")
            result[key] = source[key].strip()
    if result.get("risk_tolerance") not in (None, "UNKNOWN", "CONSERVATIVE", "BALANCED", "GROWTH"):
        raise ValueError("unknown risk_tolerance")
    if "restrictions" in source:
        if not isinstance(source["restrictions"], list) or any(
                not isinstance(item, str) or not item.strip() for item in source["restrictions"]):
            raise ValueError("restrictions must be a text list")
        result["restrictions"] = source["restrictions"]
    if source.get("sleeves") is not None:
        if not isinstance(source["sleeves"], dict) or set(source["sleeves"]) - set(SLEEVES):
            raise ValueError("unknown sleeve policy")
        result["sleeves"] = {}
        for sleeve, values in source["sleeves"].items():
            if not isinstance(values, dict) or set(values) - {"cash_cny", "risk_budget_cny", "single_security_risk_cny"}:
                raise ValueError("sleeve requires cash_cny, risk_budget_cny and optional single_security_risk_cny")
            result["sleeves"][sleeve] = {
                key: str(decimal(value, sleeve + "." + key))
                for key, value in values.items() if value is not None}
    if source.get("security_attribute_bindings") is not None:
        bindings = source["security_attribute_bindings"]
        if not isinstance(bindings, dict):
            raise ValueError("security_attribute_bindings must be an object")
        result["security_attribute_bindings"] = {}
        for symbol, binding in bindings.items():
            if len(symbol) != 6 or not symbol.isdigit() or not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
                raise ValueError("invalid security attribute binding")
            from .dual_sleeve_risk import digest, text
            text(binding["path"], "security attribute path")
            digest(binding["sha256"], "security attribute digest")
            result["security_attribute_bindings"][symbol] = dict(binding)
    if all(key in result for key in ("investable_assets_cny", "core_value_budget_cny", "hotspot_budget_cny", "cash_reserve_cny")):
        reserved = sum(Decimal(result[key]) for key in ("core_value_budget_cny", "hotspot_budget_cny", "cash_reserve_cny"))
        if reserved > Decimal(result["investable_assets_cny"]):
            raise ValueError("sleeve budgets and reserve exceed investable_assets_cny")
    if "cash_reserve_cny" in result and "minimum_cash_cny" in result and Decimal(result["cash_reserve_cny"]) < Decimal(result["minimum_cash_cny"]):
        raise ValueError("cash reserve is below minimum_cash_cny")
    return result


def missing_policy_fields(policy):
    missing = [key for key in REQUIRED if policy.get(key) is None]
    if policy.get("risk_tolerance") == "UNKNOWN":
        missing.append("risk_tolerance")
    for sleeve in SLEEVES:
        for field in ("cash_cny", "risk_budget_cny") + (("single_security_risk_cny",) if sleeve == "HOTSPOT_SATELLITE" else ()):
            if policy.get("sleeves", {}).get(sleeve, {}).get(field) is None:
                missing.append(f"sleeves.{sleeve}.{field}")
    return list(dict.fromkeys(missing))


def validate_policy_confirmation(policy, *, confirmed_at, cash_cny):
    missing = missing_policy_fields(policy)
    if missing:
        raise ValueError("Missing confirmed IPS fields: " + ", ".join(missing))
    moment = timestamp(confirmed_at, "confirmed_at")
    # Future policies are retained, but the adapter must not activate them early.
    cash = sum(Decimal(policy["sleeves"][s]["cash_cny"]) for s in SLEEVES)
    if cash + Decimal(policy["cash_reserve_cny"]) != cash_cny:
        raise ValueError("sleeve cash and reserve must exactly partition current ledger cash")
    return moment

"""Compare reported series, never equate parent profit with group cash flow."""
from decimal import Decimal
import re

from ...domain.research.reported_trends import reported_change


def reported_earnings_cash_trends(review: dict) -> dict | None:
    if (review.get("schema_version") != "disclosed-metric-review-v1"
            or review.get("action") != "no_order"
            or any(review.get(key) is not False for key in (
                "financial_gate_admitted", "forecast_assumptions_approved", "strict_pit_admitted"))):
        raise ValueError("reported trends require non-admitted reviewed facts")
    names = ("reported_parent_net_profit", "reported_operating_cash_flow")
    facts = {name: {} for name in names}
    bindings = []
    for fact in review["facts"]:
        name = fact["metric_name"]
        if name not in facts:
            continue
        if (fact["symbol"] != review["symbol"] or fact["unit"] != "CNY"
                or fact["verification_status"] != "TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY"
                or not re.fullmatch(r"[0-9]{4}", fact["period"])):
            raise ValueError("reported trends require verified annual CNY series")
        if fact["period"] in facts[name]:
            raise ValueError("duplicate reported trend fact")
        facts[name][fact["period"]] = Decimal(fact["value"])
        bindings.append(fact["source_binding"])
    if not all(facts.values()):
        return None
    if any(binding != bindings[0] for binding in bindings):
        raise ValueError("reported trends must bind one report original")
    periods = sorted(set(facts[names[0]]) & set(facts[names[1]]))
    rows = []
    for prior, current in zip(periods, periods[1:]):
        if int(current) != int(prior) + 1:
            continue
        profit, cash = [reported_change(facts[name][prior], facts[name][current]) for name in names]
        rows.append({"prior_period": prior, "current_period": current,
                     "parent_profit": profit, "operating_cash": cash,
                     "opposite_directions": {profit["direction"], cash["direction"]} == {"UP", "DOWN"}})
    return {"schema_version": "reported-earnings-cash-trends-v1", "symbol": review["symbol"],
            "source_binding": bindings[0], "rows": rows,
            "cash_conversion_ratio": None, "quality_assessment_admitted": False,
            "financial_gate_admitted": False, "forecast_approved": False, "action": "no_order"}

"""Pre-versioned, descriptive daily ranking; never trade admission."""
from decimal import Decimal

RULE_VERSION = "hotspot-dated-sector-liquidity-ranking-v1"
RANKING = ["industry_relative_strength_desc", "turnover_cny_desc", "symbol_asc"]


def rank_daily_candidates(rows: list[dict], *, trade_date: str, limit: int = 5) -> dict:
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Daily candidate limit must be 1..10")
    valid, excluded, seen = [], [], set()
    for row in rows:
        symbol = row["symbol"]
        if symbol in seen:
            raise ValueError("Duplicate daily security")
        seen.add(symbol)
        reason = None
        try:
            price, change, amount = (Decimal(str(row[key])) for key in
                                      ("close", "change_percent", "amount_cny"))
            if not all(n.is_finite() for n in (price, change, amount)) or price <= 0 or amount <= 0:
                reason = "INVALID_OR_NO_TURNOVER"
        except (KeyError, ValueError, ArithmeticError):
            reason = "MISSING_MARKET_FACTS"
        if row.get("trade_date") != trade_date or row.get("status") != "DATED_COMPLETED_QUOTE":
            reason = "NOT_LATEST_COMPLETED_SESSION"
        if not row.get("industry"):
            reason = "CLASSIFICATION_UNKNOWN"
        if "ST" in row.get("company_name", "").upper() or "退" in row.get("company_name", ""):
            reason = "NAME_RISK_EXCLUSION"
        if not symbol.startswith(("0", "3", "6")):
            reason = "VENUE_NOT_SUPPORTED"
        if reason:
            excluded.append({"symbol": symbol, "reason": reason})
        else:
            valid.append(row)
    if not valid:
        return dict(rule_version=RULE_VERSION, ranking=RANKING, candidates=[], sectors=[],
                    excluded=excluded, market=None, action="no_order")
    valid.sort(key=lambda row: row["symbol"])
    excluded.sort(key=lambda row: row["symbol"])
    mean = sum(Decimal(r["change_percent"]) for r in valid) / len(valid)
    sectors = {}
    for row in valid:
        sectors.setdefault(row["industry"], []).append(Decimal(row["change_percent"]))
    strength = {name: sum(values) / len(values) - mean for name, values in sectors.items()}
    ordered = sorted(valid, key=lambda r: (-strength[r["industry"]], -Decimal(r["amount_cny"]), r["symbol"]))
    # This ordering selects observations, not entries. No weights or thresholds
    # depend on the day's result; minute structure is assessed only afterward.
    candidates = [{**row, "rank": index + 1, "industry_relative_strength_percent": str(strength[row["industry"]]),
                   "persistence": "UNKNOWN", "fund_flows": "UNKNOWN", "catalyst": "UNKNOWN",
                   "formal_eligibility": False, "action": "no_order"}
                  for index, row in enumerate(ordered[:limit])]
    return dict(rule_version=RULE_VERSION, ranking=RANKING, candidates=candidates,
                sectors=[dict(industry=name, securities=len(sectors[name]), relative_strength_percent=str(value),
                              trade_date=trade_date, persistence="UNKNOWN", status="DATED_COVERED_UNIVERSE_OBSERVATION")
                         for name, value in sorted(strength.items(), key=lambda item: (-item[1], item[0]))],
                excluded=excluded, market=dict(trade_date=trade_date, covered_securities=len(valid),
                     equal_weight_change_percent=str(mean), advancing=sum(Decimal(r["change_percent"]) > 0 for r in valid),
                     declining=sum(Decimal(r["change_percent"]) < 0 for r in valid), regime_admission="UNKNOWN"),
                action="no_order")

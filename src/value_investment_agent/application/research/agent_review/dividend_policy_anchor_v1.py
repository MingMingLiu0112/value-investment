"""Extract a narrow, source-bound per-share dividend-plan anchor for D2.

The plan is a disclosed management policy, not proof of cash availability or a
forecast distribution.  Unsupported wording is left unquantified.
"""
from decimal import Decimal, InvalidOperation
import re


def disclosed_per_share_growth_anchor(context):
    rows = context.get("evidence", [])
    basis = context.get("financial_basis")
    if basis is None:
        periods = [row.get("period") for row in rows if row.get("unit") == "TEXT"
                   and isinstance(row.get("period"), str) and row["period"].endswith("-12-31")]
        basis = max(periods) if periods else None
    if not isinstance(basis, str) or len(basis) < 4:
        return None
    base_year = int(basis[:4])
    dividend = []
    plans = []
    for row in rows:
        if (row.get("unit") != "TEXT" or row.get("period") != basis
                or not isinstance(row.get("text"), str)):
            continue
        text = re.sub(r"\s+", "", row["text"])
        amount = re.search(r"累计每股分红([0-9]+(?:\.[0-9]+)?)元", text)
        if amount:
            dividend.append((row, amount.group(1)))
        period = re.search(r"(\d{4})[-－—](\d{4})年度.{0,100}?每股派发的现金股利.{0,80}?同比增长不低于([0-9]+(?:\.[0-9]+)?)%", text)
        if period:
            plans.append((row, period.groups()))
    if len(dividend) != 1 or len(plans) != 1:
        return None
    payment, amount = dividend[0]
    plan, (start, end, growth) = plans[0]
    if (payment.get("source_id") != plan.get("source_id")
            or payment.get("pdf_sha256") != plan.get("pdf_sha256")
            or not (int(start) <= base_year < base_year + 1 <= int(end))):
        return None
    try:
        prior_dps = Decimal(amount)
        minimum_growth = Decimal(growth) / Decimal(100)
    except InvalidOperation:
        return None
    if prior_dps <= 0 or not 0 <= minimum_growth <= 1:
        return None
    return dict(status="DISCLOSED_CONDITIONAL_PER_SHARE_PLAN",
        base_year=base_year, target_year=base_year + 1,
        base_dps_cny=str(prior_dps), minimum_growth_ratio=str(minimum_growth),
        conditional_minimum_dps_cny=str(prior_dps * (1 + minimum_growth)),
        evidence_ids=[payment["id"], plan["id"]],
        source_id=payment["source_id"], pdf_sha256=payment["pdf_sha256"],
        limitation="Disclosed per-share policy is conditional; it does not establish future cash capacity, shares outstanding, payout ratio, or paid dividend.",
        action="no_order")


def disclosed_attributable_profit_payout_anchor(context):
    """Extract a dated payout *target*, preserving its exact profit denominator.

    A management target is neither parent cash availability nor a guarantee.
    Only one complete, source-bound annual policy span is admissible.
    """
    candidates = []
    for row in context.get("evidence", []):
        if row.get("unit") != "TEXT" or not isinstance(row.get("text"), str):
            continue
        text = re.sub(r"\s+", "", row["text"])
        window = re.search(r"(\d{4})-(\d{4})年度.{0,130}?归属于上市公司股东净利润的比例分别不低于"
                           r"(\d+(?:\.\d+)?)%、(\d+(?:\.\d+)?)%、(\d+(?:\.\d+)?)%"
                           r"，且均不低于人民币(\d+(?:\.\d+)?)亿元", text)
        if window:
            candidates.append((row, window.groups()))
    if len(candidates) != 1:
        return None
    row, (first, last, *amounts) = candidates[0]
    first_year, last_year = int(first), int(last)
    if last_year - first_year != 2 or row.get("period") is None:
        return None
    try:
        ratios = [Decimal(value) / Decimal(100) for value in amounts[:3]]
        floor = Decimal(amounts[3]) * Decimal(100000000)
    except InvalidOperation:
        return None
    if any(not 0 <= ratio <= 1 for ratio in ratios) or floor <= 0:
        return None
    return dict(status="DISCLOSED_CONDITIONAL_ATTRIBUTABLE_PROFIT_PAYOUT_TARGET",
        fiscal_years=list(range(first_year, last_year + 1)),
        minimum_ratios=[str(ratio) for ratio in ratios],
        minimum_annual_cash_cny=str(floor),
        profit_basis="consolidated_parent_attributable",
        evidence_ids=[row["id"]], source_id=row["source_id"],
        pdf_sha256=row["pdf_sha256"], report_period=row["period"],
        limitation="Management target conditional on operations and capacity; not parent profit, distributable cash, declaration, payment, or a forecast guarantee.",
        action="no_order")

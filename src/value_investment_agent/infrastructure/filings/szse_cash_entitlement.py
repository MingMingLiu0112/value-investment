"""Adapt native Shenzhen implementation observations to F2 entitlement evidence."""
from decimal import Decimal

from .native_capital_observation_v1 import _compact, parse_native_capital_observation


def parse_mixed_cash_entitlement(pages: list[str], *, symbol: str) -> dict:
    """Verify the entitlement while leaving issuer direct payment unresolved."""
    result = parse_native_capital_observation(pages, symbol=symbol)
    text = _compact("".join(pages))
    if (
        result["kind"] != "dividend_implementation"
        or "本次利润分配不送红股,不以资本公积金转增股本。" not in text
        or "以下A股股东的现金红利由我公司自行派发:" not in text
        or any(word in text for word in ("更正", "修订", "取消", "作废", "撤销", "配股", "拆股", "合股"))
        or not result["record_date"] < result["ex_date"]
    ):
        raise ValueError("UNSUPPORTED_SZSE_MIXED_CASH_LAYOUT")
    return {
        "parser_version": "szse-mixed-payment-cash-entitlement-v1",
        "symbol": symbol,
        "currency": "CNY",
        "cash_per_share": str(Decimal(result["dividend_per_10_shares_cny"]) / 10),
        "eligible_distribution_shares": result["distribution_base_shares"],
        "excluded_repurchase_shares": result["excluded_repurchase_shares"],
        "published_date": result["observation_date"],
        "record_date": result["record_date"],
        "ex_date": result["ex_date"],
        "clearing_house_scheduled_payment_date": result["agency_payment_date"],
        "issuer_direct_payment_date": None,
        "cash_payment_status": "ISSUER_DIRECT_PAYMENT_UNVERIFIED",
        "term_pages": result["term_pages"],
        "action": "no_order",
    }

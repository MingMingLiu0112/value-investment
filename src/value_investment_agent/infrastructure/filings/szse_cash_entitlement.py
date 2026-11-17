"""Adapt native Shenzhen implementation observations to F2 entitlement evidence."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re

from .native_capital_observation_v1 import _compact, parse_native_capital_observation


def parse_mixed_cash_entitlement(pages: list[str], *, symbol: str) -> dict:
    """Verify the entitlement while leaving issuer direct payment unresolved."""
    text = _compact("".join(pages))
    if re.search(r"[0-9]{4}年中期分红派息实施公告", text):
        return _parse_interim_fixed_total(pages, symbol)
    result = parse_native_capital_observation(pages, symbol=symbol)
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


def _parse_interim_fixed_total(pages: list[str], symbol: str) -> dict:
    """Extract the implemented interim terms and reconcile the authorized gross amount."""
    normalized = [_compact(page) for page in pages]
    text = "".join(normalized)
    header = normalized[0]
    title = r"([0-9]{4})年中期分红派息实施公告"
    integer = r"([0-9,]{1,20})"
    money = r"([0-9,]{1,20}\.[0-9]{1,8})"
    day = r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日"

    def term(pattern: str, scope: str = text) -> re.Match[str]:
        matches = list(re.finditer(pattern, scope))
        if len(matches) != 1:
            raise ValueError("SZSE_INTERIM_CASH_TERM_MISSING_OR_AMBIGUOUS")
        return matches[0]

    codes = set(re.findall(r"证券代码:([0-9]{6})(?![0-9])", header))
    if (
        codes != {symbol}
        or "本次利润分配公司不送红股,不进行资本公积金转增股本。" not in text
        or any(word in text for word in ("更正", "修订", "取消", "作废", "撤销", "配股", "拆股", "合股"))
    ):
        raise ValueError("UNSUPPORTED_SZSE_INTERIM_CASH_LAYOUT")
    fiscal_year = int(term(title, header)[1])
    authorized = term(
        rf"以公司现有总股本{integer}股为基数,向全体股东每10股派"
        rf"{money}元人民币现金\(含税\),现金分红金额{money}元\(含税\)"
    )
    implemented = term(
        rf"现有总股本剔除已回购股份{integer}股后的{integer}股为基数,"
        rf"向全体股东每10股派{money}元人民币现金\(含税;"
    )
    shares = int(implemented[2].replace(",", ""))
    excluded = int(implemented[1].replace(",", ""))
    cash_per_share = Decimal(implemented[3].replace(",", "")) / 10
    approved_total = Decimal(authorized[3].replace(",", ""))
    if (
        shares <= 0
        or excluded != 0
        or shares != int(authorized[1].replace(",", ""))
        or cash_per_share <= 0
        or cash_per_share * 10 != Decimal(authorized[2].replace(",", ""))
        or (cash_per_share * shares).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != approved_total
    ):
        raise ValueError("SZSE_INTERIM_CASH_AMOUNT_DOES_NOT_RECONCILE")

    def read_date(pattern: str) -> date:
        return date(*(int(value) for value in term(pattern).groups()))

    publication = read_date("董事会" + day)
    record = read_date("股权登记日:" + day)
    ex = read_date("除权除息日:" + day)
    agency_payment = read_date("代派的A股股东现金红利将于" + day)
    term("以下A股股东的现金红利由我公司自行派发:")
    if not (fiscal_year <= publication.year and publication <= record < ex <= agency_payment):
        raise ValueError("SZSE_INTERIM_CASH_DATE_ORDER_INVALID")

    return {
        "parser_version": "szse-mixed-payment-interim-fixed-total-v1",
        "symbol": symbol,
        "currency": "CNY",
        "fiscal_year": fiscal_year,
        "cash_per_share": str(cash_per_share),
        "gross_declared_cash_cny": str(approved_total),
        "eligible_distribution_shares": shares,
        "excluded_repurchase_shares": excluded,
        "published_date": publication.isoformat(),
        "record_date": record.isoformat(),
        "ex_date": ex.isoformat(),
        "clearing_house_scheduled_payment_date": agency_payment.isoformat(),
        "issuer_direct_payment_date": None,
        "cash_payment_status": "ISSUER_DIRECT_PAYMENT_UNVERIFIED",
        "term_pages": [
            index for index, page in enumerate(normalized, 1)
            if any(label in page for label in ("现金分红金额", "分红派息日期", "代派的A股股东现金红利", "董事会" + str(publication.year)))
        ],
        "action": "no_order",
    }

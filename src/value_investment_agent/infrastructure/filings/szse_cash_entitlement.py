"""Replay explicit Shenzhen A-share cash entitlements with mixed payment channels."""
from datetime import date
from decimal import Decimal
import re
import unicodedata


def parse_mixed_cash_entitlement(pages: list[str], *, symbol: str) -> dict:
    """Read gross entitlement and the clearing schedule, leaving self-payment unknown."""
    if not pages or len(pages) > 16 or any(not page.strip() for page in pages):
        raise ValueError("UNSUPPORTED_SZSE_MIXED_CASH_LAYOUT")
    normalized = [re.sub(r"\s+", "", unicodedata.normalize("NFKC", p)) for p in pages]
    text = "".join(normalized)
    if (
        len(text) > 120_000
        or f"证券代码:{symbol}证券简称:" not in normalized[0]
        or not re.search(r"20\d{2}年度分红派息实施公告", normalized[0])
        or "本次利润分配不送红股,不以资本公积金转增股本。" not in text
        or any(word in text for word in ("更正", "修订", "取消", "作废", "撤销", "配股", "拆股", "合股"))
    ):
        raise ValueError("UNSUPPORTED_SZSE_MIXED_CASH_LAYOUT")

    day = r"(20\d{2})年(\d{1,2})月(\d{1,2})日"
    number = r"(\d{1,3}(?:,\d{3})+|\d+)"
    patterns = {
        "scheme": (
            r"二、本次实施的利润分配方案公司20\d{2}年度利润分配方案以固定总额的方式分配:"
            r"以公司现有总股本剔除已回购股份" + number + r"股后的" + number
            + r"股为基数,向全体股东每10股派(\d+(?:\.\d+)?)元人民币现金\(含税;"
        ),
        "record": r"三、分红派息日期1\.股权登记日:" + day + r"。",
        "ex": r"2\.除权除息日:" + day + r"。四、分红派息对象",
        "clearing": (
            r"五、分配方法1\.公司此次委托中国结算深圳分公司代派的A股股东现金红利将于"
            + day + r"通过股东托管证券公司\(或其他托管机构\)直接划入其资金账户。"
            r"2\.以下A股股东的现金红利由我公司自行派发:"
        ),
        "published": r"董事会" + day + "$",
    }
    fields = {}
    term_pages = {}
    for name, pattern in patterns.items():
        matches = [(i, m) for i, page in enumerate(normalized, 1) for m in re.finditer(pattern, page)]
        if len(matches) != 1:
            raise ValueError("SZSE_MIXED_CASH_FIELD_MISSING_OR_CONFLICTING:" + name)
        term_pages[name], match = matches[0]
        fields[name] = match.groups()

    excluded, eligible = (int(v.replace(",", "")) for v in fields["scheme"][:2])
    per_share = Decimal(fields["scheme"][2]) / 10
    published, record, ex_date, clearing = (
        date(*map(int, fields[name])) for name in ("published", "record", "ex", "clearing")
    )
    if eligible <= 0 or per_share <= 0 or not published <= record < ex_date <= clearing:
        raise ValueError("SZSE_MIXED_CASH_AMOUNTS_OR_CHRONOLOGY_INVALID")
    return {
        "parser_version": "szse-mixed-payment-cash-entitlement-v1",
        "symbol": symbol,
        "currency": "CNY",
        "cash_per_share": str(per_share),
        "eligible_distribution_shares": str(eligible),
        "excluded_repurchase_shares": str(excluded),
        "published_date": published.isoformat(),
        "record_date": record.isoformat(),
        "ex_date": ex_date.isoformat(),
        "clearing_house_scheduled_payment_date": clearing.isoformat(),
        "issuer_direct_payment_date": None,
        "cash_payment_status": "ISSUER_DIRECT_PAYMENT_UNVERIFIED",
        "term_pages": term_pages,
        "action": "no_order",
    }

"""Replay fund subscription bounds as supplemental, undated evidence."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from .operating_horizon_sources_v1 import _bound
from .task_execution_v1 import _hash
from ...product.common import require_inside
from ....infrastructure.filings.pdf_text import extract_pages


def replay_parent_fund_evidence(*, root: Path, context: dict, selection: dict,
                                cutoff: datetime) -> dict:
    if set(selection) != {"receipt", "issuer_name", "symbol", "available_at"}:
        raise ValueError("PARENT_FUND_SELECTION_INVALID")
    symbol, issuer = selection["symbol"], selection["issuer_name"]
    if symbol != context.get("symbol") or issuer != context.get("issuer_name"):
        raise ValueError("PARENT_FUND_ISSUER_CHANGED")
    available = datetime.fromisoformat(selection["available_at"])
    if cutoff.utcoffset() is None or available.utcoffset() is None or available > cutoff:
        raise ValueError("PARENT_FUND_SOURCE_NOT_AVAILABLE")
    ref = selection["receipt"]
    receipt = _bound(root, ref)
    if (receipt.get("symbol") != symbol or receipt.get("currency") != "CNY"
            or receipt.get("classification") != "CONDITIONAL_BALANCE_BOUND_NOT_TIMED_CASH_FLOW"
            or receipt.get("formal_eligibility") is not False or receipt.get("action") != "no_order"
            or any(receipt.get(field) is not None for field in (
                "parent_paid_cny", "period_2027_commitment_cash_cny", "capital_call_date"))):
        raise ValueError("PARENT_FUND_RECEIPT_SCOPE_INVALID")
    try:
        total, parent, paid = (Decimal(receipt[key]) for key in
                               ("group_subscribed_cny", "parent_subscribed_cny", "fund_paid_cny"))
    except (TypeError, InvalidOperation) as error:
        raise ValueError("PARENT_FUND_AMOUNT_INVALID") from error
    if not all(value.is_finite() and value > 0 and value % 10000 == 0
               for value in (total, parent, paid)) or parent > total or paid > total:
        raise ValueError("PARENT_FUND_AMOUNT_INVALID")
    fund = receipt["fund"]
    if not isinstance(fund, str) or not fund.strip():
        raise ValueError("PARENT_FUND_NAME_REQUIRED")

    def pdf(role):
        source = receipt[role]
        date_match = re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/\d{10}\.PDF",
                                  source["url"], re.IGNORECASE)
        if not date_match or date.fromisoformat(date_match[1]) > available.date():
            raise ValueError("PARENT_FUND_SOURCE_NOT_AVAILABLE")
        path = require_inside(root / "runtime", root / source["path"], "parent fund PDF")
        if _hash(path.read_bytes()) != source["sha256"]:
            raise ValueError("PARENT_FUND_SOURCE_HASH_CHANGED")
        pages = ["".join(page.split()) for page in extract_pages(path)]
        if issuer not in "".join(pages) or fund not in "".join(pages) or symbol not in pages[0]:
            raise ValueError("PARENT_FUND_PDF_IDENTITY_CHANGED")
        return source, pages

    original, op = pdf("original")
    amended, ap = pdf("amended")
    def check(source, pages, text):
        locators = [loc for loc in source["locators"]
                    if loc["normalized_text_sha256"] == _hash(text.encode("utf-8"))]
        if len(locators) != 1:
            raise ValueError("PARENT_FUND_LOCATOR_CHANGED")
        page = locators[0]["physical_page"]
        if type(page) is not int or not 1 <= page <= len(pages) or pages[page - 1].count(text) != 1:
            raise ValueError("PARENT_FUND_LOCATOR_CHANGED")
        return page

    check(original, op, f"认缴出资总额：{total / 10000:,.0f}万元人民币")
    # The table source binds the trailing printed percentage through its locator.
    parent_prefix = f"{issuer}有限合伙人{parent / 10000:,.0f}"
    matches = re.findall(re.escape(parent_prefix) + r"[0-9]{1,3}\.[0-9]{2}", "".join(op))
    if len(matches) != 1:
        raise ValueError("PARENT_FUND_PARENT_ROW_CHANGED")
    check(original, op, matches[0])
    check(original, op, "最终以普通合伙人发出的提款通知记载为准")
    paid_day = date.fromisoformat(receipt["paid_as_of"])
    if paid_day > available.date():
        raise ValueError("PARENT_FUND_SOURCE_NOT_AVAILABLE")
    paid_page = check(amended, ap, f"实缴出资合计{paid / 10000:,.0f}万元")
    paid_date_label = f"{paid_day.year}年{paid_day.month}月{paid_day.day}日"
    if paid_date_label not in ap[paid_page - 1]:
        raise ValueError("PARENT_FUND_PAID_PERIOD_CHANGED")
    check(amended, ap, "不涉及各合伙人其他权利义务变化")
    bounds = [str(parent - min(parent, paid)), str(parent - max(Decimal(0), paid - (total - parent)))]
    if receipt["parent_unpaid_diagnostic_cny"] != bounds:
        raise ValueError("PARENT_FUND_BOUND_CHANGED")
    text = (f"母公司基金认缴承诺{parent}元，基金已披露合计实缴{paid}元。"
            f"在合伙人构成和认缴额未变且各方未超额实缴的条件下，母公司未缴余额代理为{bounds[0]}至{bounds[1]}元。"
            "具体缴款取决于提款通知，未核验母公司实际实缴或未来年度付款金额及时间。")
    return dict(id=f"official:parent-fund:{symbol}:{ref['sha256']}",
                source_id="official:" + amended["sha256"], pdf_sha256=amended["sha256"],
                available_at=available.isoformat(), period=paid_day.isoformat(), physical_page=paid_page,
                scope="ISSUER_PARENT_UNDATED_COMMITMENT_BOUND", unit="TEXT",
                field="parent_fund_commitment_without_payment_schedule",
                text=text, text_sha256=_hash(text.encode("utf-8")),
                kind="CONDITIONAL_BALANCE_BOUND_NOT_TIMED_CASH_FLOW")

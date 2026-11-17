"""Read bounded, numbered guarantee announcements for candidate review."""
from decimal import Decimal
import re
import unicodedata

from .operating_event_terms import _day

TITLE = "关于为全资子公司提供担保的进展公告"
_DATE = r"20\d{2}年\d{1,2}月\d{1,2}日"
_CN_DIGITS = "〇一二三四五六七八九"
_CN_DATE = r"[二〇一二三四五六七八九]{4}年[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}日"
_AMOUNT = r"\d+(?:\.\d+)?"


def _one(pattern, text):
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("PARENT_GUARANTEE_TERM_MISSING_OR_AMBIGUOUS")
    return matches[0]


def _publication(text):
    if re.fullmatch(_DATE, text):
        return _day(text)
    year, month, day = re.split("[年月日]", text)[:3]

    def number(value):
        if "十" not in value:
            return _CN_DIGITS.index(value)
        tens, units = value.split("十")
        return (10 * (_CN_DIGITS.index(tens) if tens else 1)
                + (_CN_DIGITS.index(units) if units else 0))

    return _day(f"{''.join(str(_CN_DIGITS.index(x)) for x in year)}年{number(month)}月{number(day)}日")


def parse_parent_guarantee_event(pages, *, symbol):
    if not 1 <= len(pages) <= 8 or sum(map(len, pages)) > 40000:
        raise ValueError("PARENT_GUARANTEE_COMPLETE_PAGES_REQUIRED")
    normalized = []
    for number, page in enumerate(pages, 1):
        match = re.match(r"\s*(\d+)\s*[\r\n]+", page)
        if not match or int(match[1]) != number or "\ufffd" in page:
            raise ValueError("PARENT_GUARANTEE_PAGE_SEQUENCE_INVALID")
        normalized.append(re.sub(r"\s+", "", unicodedata.normalize("NFKC", page[match.end():])))
    body = "".join(normalized)
    heading = _one(r"^证券代码:(\d{6})证券简称:[^:]+?公告编号:临(20\d{2})-\d{3}"
                   r"([^:]+?股份有限公司)" + TITLE, body)
    footer = _one(r"特此公告。?" + re.escape(heading[3]) + rf"董事会({_DATE}|{_CN_DATE})$", body)
    if heading[1] != symbol or body.count("证券代码:") != 1:
        raise ValueError("PARENT_GUARANTEE_ISSUER_MISMATCH")
    published = _publication(footer[1])
    signed = _one(rf"担保的基本情况({_DATE})[,，]" + re.escape(heading[3])
                  + r".{1,1600}?签署了保证协议", body)
    signed_on = _day(signed[1])
    if signed_on > published or not published.startswith(heading[2]):
        raise ValueError("PARENT_GUARANTEE_DATE_INVALID")
    total = _one(rf"担保债务本金合计不超过({_AMOUNT})亿新西兰元", body)
    fx = _one(rf"1新西兰元对人民币({_AMOUNT})元", body)
    details = _one(r"三、担保协议的主要内容(.+?)四、担保的必要性和合理性", body)
    caps = list(re.compile(
        rf"(?:担保最高本金限额|担保授信金额|担保贷款本金余额):"
        rf"(?:合计不超过)?({_AMOUNT})亿新西兰元",
    ).finditer(body, details.start(1), details.end(1)))
    amounts = [Decimal(item[1]) * 100000000 for item in caps]
    maximum = Decimal(total[1]) * 100000000
    rate = Decimal(fx[1])
    if (not amounts or min(amounts) <= 0 or sum(amounts) != maximum or rate <= 0
            or body.count("连带责任保证担保") < len(amounts)):
        raise ValueError("PARENT_GUARANTEE_PRINCIPAL_NOT_RECONCILED")
    excerpts = []
    spans = [("issuer", heading), ("signed_on", signed), ("principal", total),
                         ("fx", fx), ("publication", footer)]
    spans.extend(("bank_principal_limit", match) for match in caps)
    for field, match in spans:
        start = 0
        for page_no, page in enumerate(normalized, 1):
            end = start + len(page)
            if start < match.end() and end > match.start():
                excerpts.append(dict(field=field, physical_page=page_no,
                    text=page[max(0, match.start()-start):match.end()-start]))
            start = end
    converted = maximum * rate
    return dict(parser_version="parent-guarantee-event-v1", event_type="PARENT_SUBSIDIARY_GUARANTEE",
        symbol=symbol, published_date=published, effective_date=None, signed_on=signed_on,
        principal_limit_nzd=str(maximum), principal_limit_cny=str(converted),
        scope="CONTINGENT_PRINCIPAL_LIMIT_NOT_CASH_OUTFLOW",
        summary=f"母公司于{signed_on}签署连带责任保证协议，公告本金上限折合人民币{converted:.2f}元。",
        implication="须核对实际提款、担保履行及是否与既有合并负债重叠。",
        evidence_excerpts=excerpts, physical_pages=sorted({row["physical_page"] for row in excerpts}),
        affected_model_fields=[], limitations=["本金上限不等于已经提款或代偿。"], action="no_order")

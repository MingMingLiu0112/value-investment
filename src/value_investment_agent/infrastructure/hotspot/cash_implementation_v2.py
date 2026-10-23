"""Versioned, bounded SZSE A-share cash implementation; legacy v1 stays unchanged."""
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import re

from .cash_implementation import _compact, _pdf, revision_warning
from ..evidence.historical_distribution_correspondence import verify_distribution_correspondence
from ..evidence.historical_price_correspondence import require_inside, sha256_file
from ...domain.hotspot.cash_basis import reconcile_cash_basis
from ...quote_sessions import CHINA


PARSER_VERSION = "szse-a-gross-versus-ex-reference-v2"
NUMBER = r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"
DAY = r"(20\d{2})年(\d{1,2})月(\d{1,2})日"
TAX_BODY = (r";扣税后,通过深股通持有股份的香港市场投资者、境外机构\(含QFII、RQFII\)"
    r"以及持有首发前限售股的个人和证券投资基金每10股派人民币" + NUMBER + r"元;"
    r"持有首发后限售股、股权激励限售股及无限售流通股的个人股息红利税实行差别化税率征收,"
    r"公司暂不扣缴个人所得税,待个人转让股票时,根据其持股期限计算应纳税额【注】;"
    r"持有首发后限售股、股权激励限售股及无限售流通股的证券投资基金所涉红利税,"
    r"对香港投资者持有基金份额部分按10%征收,对内地投资者持有基金份额部分实行差别化税率征收")
TAX_NOTE = (r"。【注:根据先进先出的原则,以投资者证券账户为单位计算持股期限,"
    r"持股1个月\(含1个月\)以内,每10股补缴税款人民币" + NUMBER + r"元;"
    r"持股1个月以上至1年\(含1年\)的,每10股补缴税款人民币" + NUMBER
    + r"元;持股超过1年的,不需补缴税款。】")


def _cash_statement_tail(value):
    """Consume the entire cash statement, including bounded tax-only notes."""
    depth = 1
    for index, character in enumerate(value):
        depth += (character == "(") - (character == ")")
        if depth == 0:
            tax, remainder = value[:index], value[index + 1:]
            if tax:
                if not re.fullmatch(TAX_BODY, tax) or not re.fullmatch(TAX_NOTE, remainder):
                    raise ValueError("Unsupported tax-only statement or note")
            elif remainder != "。":
                raise ValueError("Unconsumed operative distribution terms")
            return
    raise ValueError("Incomplete parenthesized cash statement")


def parse_cash_implementation_pages_v2(pages, *, symbol):
    if (not pages or len(pages) > 16 or any(not page.strip() for page in pages)
            or sum(map(len, pages)) > 120_000 or not re.fullmatch(r"[03][0-9]{5}", symbol)):
        raise ValueError("Complete bounded SZSE implementation pages required")
    content = []
    for index, page in enumerate(pages, 1):
        lines = [line for line in page.splitlines() if line.strip()]
        if lines and lines[0].strip() == str(index):
            lines = lines[1:]
        content.append("\n".join(lines))
    header, text = _compact(content[0]), _compact("".join(content))
    title = re.findall(r"20\d{2}年度A股权益分派实施公告", header)
    number = re.findall(r"公告编号:(20\d{2}-\d+)", header)
    if (f"证券代码:{symbol}" not in header or header.count("证券代码:") != 1
            or len(title) != 1 or len(number) != 1 or revision_warning(pages)):
        raise ValueError("Unique issuer, implementation identity and unrevised body required")
    period = title[0][:4]
    noncash_denial = period + "年度,公司不实施资本公积金转增股本,不送红股。"
    if text.count(noncash_denial) != 1:
        raise ValueError("Explicit no-bonus/no-capitalization scheme required")
    if any(word in text.replace(noncash_denial, "") for word in (
            "转增", "送红股", "配股", "股份拆细", "合股", "缩股")):
        raise ValueError("Noncash/rights terms are outside this cash-only contract")
    prefix = (r"实施的" + period + r"年度A股权益分派方案为:以公司现有A股总股本" + NUMBER
        + r"股剔除回购专用账户中已回购股份" + NUMBER + r"股后的股本" + NUMBER
        + r"股为基数,向全体股东每10股派发现金分红人民币" + NUMBER + r"元\(含税")
    schemes = re.findall(prefix, text)
    if len(schemes) != 2 or len(set(schemes)) != 1:
        raise ValueError("Header and operative A-share scheme must agree")
    if text.count("二、本次实施的权益分派方案") != 1 or text.count("三、股权登记日与除权除息日") != 1:
        raise ValueError("Unique operative cash section required")
    scheme = text.split("二、本次实施的权益分派方案", 1)[1].split("三、股权登记日与除权除息日", 1)[0]
    scheme_match = re.match(r"公司" + prefix, scheme)
    if scheme_match is None:
        raise ValueError("Cash terms must start the operative implementation section")
    _cash_statement_tail(scheme[scheme_match.end():])
    totals = re.findall(r"即" + NUMBER + r"股[×*]" + NUMBER + r"元/股=" + NUMBER + r"元。", text)
    if len(totals) != 2 or len(set(totals)) != 1:
        raise ValueError("Gross payout equations must be present and consistent")
    ref_header = re.findall(r"按公司现有A股总股本折算的每10股现金分红为" + NUMBER
        + r"元\(保留小数点后六位数,最后一位直接截取,不四舍五入\)", header)
    ref_equation = re.findall(r"=\(" + NUMBER + r"元/" + NUMBER + r"股\)[×*]10=" + NUMBER
        + r"元\(保留到小数点后六位,最后一位直接截取,不四舍五入\)", text)
    deductions = re.findall(r"=股权登记日收盘价-" + NUMBER + r"元/股。", text)
    if len(ref_header) != 1 or len(ref_equation) != 1 or len(deductions) != 2 or len(set(deductions)) != 1:
        raise ValueError("Explicit consistent reference formula and truncation required")
    total, excluded, eligible, gross10 = [Decimal(v.replace(",", "")) for v in schemes[0]]
    eligible2, gross2, payout = [Decimal(v.replace(",", "")) for v in totals[0]]
    payout2, total2, ref10 = [Decimal(v.replace(",", "")) for v in ref_equation[0]]
    if (eligible2 != eligible or gross2 != gross10 / 10 or payout2 != payout or total2 != total
            or Decimal(ref_header[0]) != ref10):
        raise ValueError("Payout/reference equations use conflicting share or currency bases")
    basis = reconcile_cash_basis(total_a_shares=total, nonparticipating_a_shares=excluded,
        eligible_a_shares=eligible, gross_per_10_eligible_a_shares=gross10,
        declared_total_gross_cash_cny=payout, reference_per_10_total_a_shares=ref10,
        reference_deduction_per_total_a_share=deductions[0])
    chronology = re.findall(r"三、股权登记日与除权除息日本次权益分派的股权登记日为:" + DAY
        + r",除权除息日为:" + DAY + r"。四、权益分派对象", text)
    record_header = re.findall(r"本次权益分派的股权登记日为" + DAY, header)
    payment_header = re.findall(r"本次权益分派的除息日及现金红利发放日为" + DAY, header)
    payments = re.findall(r"代派的A股股东现金红利将于" + DAY + r"通过股东托管证券公司", text)
    footer = re.search(r"董事会" + DAY + r"$", text)
    if (len(chronology) != 1 or len(record_header) != 1 or len(payment_header) != 1
            or len(payments) != 1 or footer is None or len(re.findall(r"董事会" + DAY, text)) != 1):
        raise ValueError("Unique explicit implementation chronology required")
    record = date(*map(int, chronology[0][:3]))
    ex = date(*map(int, chronology[0][3:]))
    payment, published = date(*map(int, payments[0])), date(*map(int, footer.groups()))
    if int(period) >= published.year:
        raise ValueError("Only completed annual periods before publication year supported")
    if (date(*map(int, record_header[0])) != record or date(*map(int, payment_header[0])) != ex
            or not published <= record < ex == payment
            or re.findall(r"股权登记日为:?" + DAY, text) != [record_header[0], record_header[0]]
            or re.findall(r"(?:除权除息日|除息日)为:?" + DAY, text) != [chronology[0][3:]]):
        raise ValueError("Record/ex/payment/header/publication dates conflict")
    return dict(parser_version=PARSER_VERSION, symbol=symbol, announcement_number=number[0],
        title=title[0], published_date=published.isoformat(), record_date=record.isoformat(),
        period_scope="COMPLETED_ANNUAL_PERIOD_ONLY",
        ex_date=ex.isoformat(), cash_payment_date=payment.isoformat(), cash_basis=basis,
        body_page_count=len(pages), read_pages=list(range(1, len(pages) + 1)),
        term_pages=dict(scheme=[i for i, page in enumerate(pages, 1)
            if "二、本次实施的权益分派方案" in _compact(page)],
            reference_formula=[i for i, page in enumerate(pages, 1)
                if "=股权登记日收盘价-" in _compact(page)], publication=[len(pages)]),
        amendment_chain_verified=False, exchange_formula_approval_independently_proven=False,
        scope="DECLARED_IMPLEMENTATION_ARITHMETIC_NOT_ACCOUNT_RECEIPT_OR_FULL_ACTION_CHAIN", action="no_order")


def load_cash_implementation_v2(*, root: Path, symbol: str, record_date: date,
        registry_binding: dict, now: datetime, related_disclosure_bindings: tuple = ()) -> dict:
    if now.utcoffset() is None or type(record_date) is not date:
        raise ValueError("Explicit record date and aware cutoff required")
    root = root.resolve()
    available = datetime.fromisoformat(registry_binding["available_at"])
    path = require_inside(root, root / registry_binding["path"], "cash v2 registry")
    if (Path(registry_binding["path"]).is_absolute() or available.utcoffset() is None or available > now
            or path.stat().st_size > 4 * 1024**2 or sha256_file(path) != registry_binding["sha256"]):
        raise ValueError("Cash v2 registry unavailable")
    rows = [row for row in json.loads(path.read_bytes())["events"]
        if row["symbol"] == symbol and row["record_date"] == record_date.isoformat()]
    if len(rows) != 1 or len(rows[0]["evidence"]) != 1:
        raise ValueError("One event and bound original required")
    event = rows[0]
    original = dict(event["evidence"][0], available_at=available.isoformat())
    pages, _ = _pdf(root, original, now)
    terms = parse_cash_implementation_pages_v2(pages, symbol=symbol)
    basis = terms["cash_basis"]
    if (any(terms[key] != event[key] for key in ("record_date", "ex_date", "cash_payment_date"))
            or Decimal(event["cash_per_share"]) != Decimal(basis["gross_cash_per_eligible_a_share"])
            or Decimal(event.get("bonus_shares_per_share") or "0") != 0
            or event.get("currency", "CNY") != "CNY" or event.get("share_class", "A") != "A"):
        raise ValueError("Registry must match gross A-share entitlement, not reference deduction")
    for key in ("total_a_shares", "nonparticipating_a_shares", "eligible_a_shares",
            "reference_deduction_per_total_a_share"):
        if key in event and Decimal(event[key]) != Decimal(basis[key]):
            raise ValueError("Registry share/reference basis differs from implementation body")
    if (f'/finalpage/{terms["published_date"]}/' not in original["url"]
            or date.fromisoformat(terms["ex_date"]) > now.astimezone(CHINA).date()):
        raise ValueError("Implementation publication/effectivity unavailable")
    proof = verify_distribution_correspondence(root=root, symbol=symbol,
        sessions=[dict(date=record_date.isoformat())] * 2,
        cash_events=[dict(event_id=symbol + ":" + record_date.isoformat(), record_date=event["record_date"],
            ex_date=event["ex_date"], payment_date=event["cash_payment_date"],
            cash_per_share=event["cash_per_share"], bonus_shares_per_share="0", bonus_listing_date=None)],
        references=[dict(kind="reviewed_event_registry", path=registry_binding["path"], sha256=registry_binding["sha256"]),
            dict(kind="distribution", **event["evidence"][0])])
    if proof["status"] != "MATCH":
        raise ValueError("Gross entitlement registry correspondence failed")
    if len(related_disclosure_bindings) > 16:
        raise ValueError("Related document budget exceeded")
    warnings = []
    for binding in related_disclosure_bindings:
        related, _ = _pdf(root, binding, now)
        if f"证券代码:{symbol}" not in _compact(related[0]):
            raise ValueError("Related original issuer unresolved")
        if revision_warning(related):
            warnings.append(dict(binding=dict(binding), status="REVISION_OR_CANCELLATION_REQUIRES_LINKAGE"))
    refs = [dict(registry_binding), original, *map(dict, related_disclosure_bindings)]
    if any(sha256_file(require_inside(root, root / ref["path"], "cash v2 source")) != ref["sha256"] for ref in refs):
        raise ValueError("Cash v2 source changed during read")
    return dict(terms=terms, registry_correspondence=proof, evidence_bindings=refs,
        body_evidence_binding=dict(path=original["path"], sha256=original["sha256"], url=original["url"]),
        revision_status="PENDING_LINKAGE" if warnings else "ABSENCE_NOT_PROVEN", revision_warnings=warnings,
        complete_window_coverage=False, historical_availability_proven=False,
        price_mapping=None, original_protection_adjusted=False, formal_eligibility=False, action="no_order")

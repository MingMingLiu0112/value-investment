"""Read an explicit A-share repurchase within an HK next-day disclosure form."""
from datetime import date, datetime
from decimal import Decimal
import re

from .cash_implementation import _compact, _pdf
from ...quote_sessions import CHINA


def parse_hk_form_a_share_buyback(pages, *, symbol):
    if (not pages or len(pages) > 16 or sum(map(len, pages)) > 120_000
            or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)):
        raise ValueError("Bounded readable capital disclosure required")
    header, text = _compact(pages[0]), _compact("".join(pages))
    if any(not re.match(r"FF305第" + str(index) + r"頁共" + str(len(pages)) + r"頁v[0-9.]+", _compact(page))
            for index, page in enumerate(pages, 1)):
        raise ValueError("Complete consistently numbered original form pages required")
    identity = f"證券代號(如上市){symbol}說明A股股票於深圳證券交易所上市"
    if ("FF305" not in header or "翌日披露報表" not in header or "狀態:新提交" not in header
            or "股份類別A於香港聯交所上市否" not in header or identity not in header
            or header.count("股份類別") != 1 or header.count("證券代號") != 1
            or "贖回/購回股份(擬註銷但截至期終結存日期尚未註銷)" not in header):
        raise ValueError("Explicit A-share identity and pending-cancellation form required")
    stamps = re.findall(r"呈交日期:(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    if len(stamps) != 1 or text.count("呈交日期") != 1 or text.count("購回報告第二章節") != 1:
        raise ValueError("Unique submission date and repurchase section required")
    section = text.split("購回報告第二章節", 1)[1].split("第二章節註釋", 1)[0]
    if any(word in header + section for word in ("更正", "修訂", "撤銷", "作廢")):
        raise ValueError("Changed operative capital form requires separate lineage review")
    if (identity not in section or "股份類別A於香港聯交所上市否" not in section
            or section.count("股份類別") != 1 or section.count("證券代號") != 1):
        raise ValueError("Repurchase section does not identify the same A share")
    number = r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"
    table_header = ("交易日購回股份數目購回方式(註1)每股購回價或每股最高購回價(元)"
        "每股最低購回價(元)付出的價格總額(元)")
    if section.count(table_header) != 1 or section.count("合共購回股份總數") != 1:
        raise ValueError("Unique complete repurchase table required")
    table = section.split(table_header, 1)[1].split("合共購回股份總數", 1)[0]
    row = re.fullmatch(r"1\)\.(20\d{2})年(\d{1,2})月(\d{1,2})日" + number
        + r"於其他證券交易所進行深圳證券交易所RMB" + number + r"RMB" + number + r"RMB" + number, table)
    totals = re.findall(r"合共購回股份總數" + number + r"合共付出的價格總額\(元\)RMB" + number
        + r"購回股份\(擬註銷\)數目" + number + r"購回股份\(擬持作庫存股份\)數目" + number, section)
    if (row is None or len(totals) != 1 or len(re.findall(r"[0-9]+\)\.20\d{2}年\d{1,2}月\d{1,2}日", section)) != 1):
        raise ValueError("One explicit purchase row and reconciled totals required")
    row, total = row.groups(), [Decimal(v.replace(",", "")) for v in totals[0]]
    quantity, high, low, cash = [Decimal(v.replace(",", "")) for v in row[3:]]
    submitted, traded = date(*map(int, stamps[0])), date(*map(int, row[:3]))
    if (traded != submitted or quantity <= 0 or quantity != quantity.to_integral_value()
            or not 0 < low <= high or not low * quantity <= cash <= high * quantity
            or total != [quantity, cash, quantity, Decimal(0)]):
        raise ValueError("Repurchase date, price bounds or intended cancellation totals conflict")
    return dict(symbol=symbol, share_class="A", execution_venue="SZSE", currency="CNY",
        form="HK_FF305", submitted_date=submitted.isoformat(), trade_date=traded.isoformat(),
        bought_shares=str(quantity), total_paid_cny=str(cash), high_price_cny=str(high), low_price_cny=str(low),
        intended_for_cancellation_shares=str(quantity), effective_cancellation_proven=False,
        completed_cancelled_shares=None, price_adjustment_allowed=False,
        term_pages=[1, next(i for i, page in enumerate(pages, 1) if "購回報告第二章節" in _compact(page))],
        scope="DECLARED_A_SHARE_BUYBACK_NOT_EFFECTIVE_CANCELLATION_OR_COMPLETE_ACTION_COVERAGE",
        action="no_order")


def inspect_capital_disclosures(*, root, symbol, announcements, acquired_at, now):
    result = dict(observations=[], unresolved=[], complete_coverage_proven=False,
        comparison_allowed=False, historical_availability_proven=False, action="no_order")
    if len(announcements) > 16:
        result["unresolved"].append(dict(reason="DOCUMENT_COUNT_EXCEEDS_BOUNDED_REVIEW"))
        return result
    for item in announcements:
        try:
            if len(item["evidence_bindings"]) != 1:
                raise ValueError("One capital original required")
            ref = item["evidence_bindings"][0]
            binding = dict(path=ref["path"], sha256=ref["sha256"], url=item["source_url"], available_at=acquired_at)
            pages, _ = _pdf(root, binding, now)
            parsed = parse_hk_form_a_share_buyback(pages, symbol=symbol)
            published = datetime.fromisoformat(item["published_at"]).astimezone(CHINA).date().isoformat()
            if parsed["submitted_date"] != published or f"/finalpage/{published}/" not in binding["url"]:
                raise ValueError("Capital form date differs from bound official publication")
            result["observations"].append(dict(terms=parsed, evidence_binding=binding))
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            result["unresolved"].append(dict(announcement_id=item.get("announcement_id"), reason=str(error)))
    return result

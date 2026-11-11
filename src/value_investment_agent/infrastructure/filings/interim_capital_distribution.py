"""Bounded interim-report fields, never an absence-of-actions certificate.

The caller binds these observations to consumed native capital facts and the
retained official original. Checkbox scope and reporting period are preserved.
"""
from datetime import date
from decimal import Decimal
import re
import unicodedata


VERSION = "interim-capital-distribution-fields-v2"


def parse_interim_capital_distribution(pages, *, symbol):
    if not pages or len(pages) > 300 or sum(map(len, pages)) > 2_000_000:
        raise ValueError("BOUNDED_INTERIM_ORIGINAL_REQUIRED")
    compact = lambda s: re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))
    normalized = [compact(p) for p in pages]
    if (not re.search(r"公司代码:" + re.escape(symbol) + r"(?:公司简称|$)", normalized[0])
            or not re.search(r"20\d{2}年半年度报告$", normalized[0])
            or "摘要" in normalized[0]):
        raise ValueError("FULL_INTERIM_REPORT_IDENTITY_REQUIRED")

    def one(pattern):
        found = [(i, m) for i, text in enumerate(normalized, 1)
                 for m in re.finditer(pattern, text)]
        if len(found) != 1:
            raise ValueError("INTERIM_FIELD_MISSING_OR_AMBIGUOUS")
        return found[0]

    period_page, period = one(r"报告期指(20\d{2})年1月1日至(20\d{2})年6月30日")
    if period[1] != period[2] or period[1] + "年半年度报告" not in normalized[0]:
        raise ValueError("INTERIM_REPORT_PERIOD_CONFLICT")
    as_of = date(int(period[1]), 6, 30).isoformat()
    # This is an issued-share quantity in the share movement table, not the
    # monetary share-capital line of the balance sheet.
    number = r"([0-9]{1,3}(?:,[0-9]{3})+)"
    capital_page, capital = one(r"三、股份总数" + number + r"100-" + number
        + r"-" + number + number + r"1002、股份变动情况说明")
    before, reduction, subtotal, after = [Decimal(v.replace(",", "")) for v in capital.groups()]
    if before - reduction != after or reduction != subtotal or min(before, reduction, after) <= 0:
        raise ValueError("INTERIM_CAPITAL_ROLLFORWARD_CONFLICT")
    ordinary_row = "1、人民币普通股" + capital[0].split("三、股份总数", 1)[1].split("2、股份变动情况说明", 1)[0]
    if ("单位:股本次变动前本次变动增减" not in normalized[capital_page - 1]
            or ordinary_row + "2、境内上市的外资股" not in normalized[capital_page - 1]):
        raise ValueError("INTERIM_CAPITAL_TABLE_UNIT_REQUIRED")
    cancellation_page, cancellation = one(r"截至资产负债表日,公司已累计回购股份" + number
        + r"股,已支付总金额([0-9,.]+)元\(不含交易费用\),并已在中国证券登记结算有限责任公司"
        r"上海分公司办理完成注销。")
    if Decimal(cancellation[1].replace(",", "")) != reduction:
        raise ValueError("INTERIM_CANCELLATION_DIFFERS_FROM_CAPITAL_TABLE")
    proposal_page, _ = one(r"半年度拟定的利润分配预案、公积金转增股本预案是否分配或转增否三、")
    subsequent_page, _ = one(r"十六、资产负债表日后事项1、重要的非调整事项□适用√不适用"
        r"2、利润分配情况□适用√不适用3、销售退回")
    capital_followup_page, _ = one(r"报告期后到半年报披露日期间发生股份变动对每股收益、每股净资产等财务指标的影响"
        r"\(如有\)□适用√不适用4、")
    dividend_page, table = one(r"42、未分配利润(.*?)43、营业收入和营业成本")
    # Bind the row to its OWN table, not another currency/unit header on the
    # same page. Only this explicit current/prior column order is supported.
    header = "√适用□不适用单位:元币种:人民币项目本期上年度"
    if not table[1].startswith(header):
        raise ValueError("INTERIM_DIVIDEND_TABLE_UNIT_CURRENCY_OR_PERIOD_UNSUPPORTED")
    rows = list(re.finditer(r"应付普通股股利([0-9,]+\.[0-9]{2})([0-9,]+\.[0-9]{2})"
                           r"转作股本的普通股股利", table[1][len(header):]))
    if len(rows) != 1:
        raise ValueError("INTERIM_DIVIDEND_ROW_MISSING_OR_AMBIGUOUS")
    dividend = rows[0]
    # A disclosure of dividends charged to retained earnings is not evidence of
    # receipt or proof that a particular later valuation cash flow includes it.
    amount = Decimal(dividend[1].replace(",", ""))
    return dict(parser_version=VERSION, symbol=symbol, period_end=as_of,
        ordinary_shares=str(after), cancelled_shares=str(reduction),
        declared_ordinary_dividend_cny=str(amount),
        cancellation_state="DISCLOSED_BUYBACK_COMPLETED_BY_REPORT_END",
        interim_proposal_state="NO_INTERIM_DISTRIBUTION_OR_CAPITALIZATION_PROPOSED",
        subsequent_distribution_state="REPORT_SUBSEQUENT_DISTRIBUTION_SECTION_NOT_APPLICABLE",
        subsequent_capital_state="REPORT_SUBSEQUENT_PER_SHARE_IMPACT_SECTION_NOT_APPLICABLE",
        opening_pending_actions_complete=False, closing_continuity_proven=False,
        term_pages=dict(period=[period_page], capital=[capital_page], cancellation=[cancellation_page],
            proposal=[proposal_page], subsequent_distribution=[subsequent_page],
            subsequent_capital=[capital_followup_page], declared_dividend=[dividend_page]),
        action="no_order")

"""Observe printed parent cash rows in paginated or sparse statements."""
import re

from . import parent_cash_research as legacy
from ...infrastructure.filings.stock_identity_table_v1 import labelled_security_codes

OPTIONAL_FINANCING = {"borrowings_received_cny", "debt_repaid_cny"}


def observe_parent_cash_rows(*, pages: list[str], symbol: str,
                             issuer_name: str, period: str) -> dict:
    """Reuse strict parsing, keeping omitted financing amounts unknown."""
    periods = legacy._period_pair(period)
    report = legacy.PERIODS[periods][0]
    owner = legacy._compact(issuer_name)
    # The exact issuer/report text and labelled security code must still pass
    # the legacy identity check. Only an isolated printed page number is removed.
    cover_pattern = re.compile(
        r"(?m)^(?P<title>[^\r\n]+?)[ \t]+[0-9]{1,3}[ \t]*(?=\r?$)")
    normalized = list(pages)
    for index, page in enumerate(normalized[:8]):
        normalized[index] = cover_pattern.sub(
            lambda match: match["title"] if legacy._compact(match["title"])
                in {owner + report, owner + report + "全文"} else match[0], page)
    if labelled_security_codes(pages[:8], symbol=symbol) != {symbol}:
        raise ValueError("PARENT_CASH_ISSUER_OR_REPORT_MISMATCH")
    # Adapt the authenticated table code to the older parser's labelled input.
    # This projection adds no page and does not touch source files or table rows.
    normalized[0] += f"\n股票代码：{symbol}\n"
    for index, page in enumerate(normalized):
        lines = page.splitlines()
        for pos, line in enumerate(lines):
            title = legacy._compact(line)
            if (title == "母公司现金流量表" and pos >= 2
                    and legacy._compact(lines[pos - 2]) == legacy.PERIODS[periods][1]
                    and legacy._compact(lines[pos - 1]) in {"编制单位：" + owner, "编制单位:" + owner}):
                # Same-page title and its original two preceding header lines.
                lines[pos - 2:pos + 1] = [line, lines[pos - 2], lines[pos - 1]]
            elif title == "合并所有者权益变动表" and pos:
                previous = legacy._compact(lines[pos - 1]).replace("：", ":")
                if previous == "财务报告编制单位:" + owner + legacy.PERIODS[periods][1]:
                    # The exact next table's header cannot belong to parent cash.
                    lines[pos - 1:pos + 1] = [line, lines[pos - 1]]
        normalized[index] = "\n".join(lines)
    spec = dict(symbol=symbol, issuer=issuer_name, periods=list(periods),
                column_labels=legacy._column_labels(periods))
    rows, unknown = {}, {}
    for field in sorted(legacy._partial_fields(periods)):
        try:
            rows[field] = legacy.extract_parent_cash_statement(
                pages=normalized, spec=spec, observation_fields={field})["rows"][field]
        except ValueError as error:
            if str(error) == "PARENT_CASH_TWO_PRINTED_VALUES_REQUIRED:" + field:
                unknown[field] = "PRINTED_TWO_COLUMN_AMOUNT_NOT_PROVEN"
            elif field in OPTIONAL_FINANCING and str(error) == "PARENT_CASH_ROW_MISSING_OR_AMBIGUOUS:" + field:
                # The parser has already verified scope, headings, period, and sections.
                # No value is assigned for either a missing or ambiguous optional row.
                unknown[field] = "OPTIONAL_FINANCING_ROW_NOT_UNIQUELY_PRINTED"
            else:
                raise
    if not {"cfo_cny", "closing_cash_and_equivalents_cny"} <= rows.keys():
        raise ValueError("PARENT_CASH_LAYOUT_ESSENTIAL_ROWS_MISSING")
    return dict(rows=rows, unknown_fields=unknown, periods=list(periods), action="no_order")

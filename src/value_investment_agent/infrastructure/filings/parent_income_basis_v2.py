"""Source-bound standalone-parent profit from unnumbered annual/H1 tables.

The caller authenticates the report issuer, period, original hash and PIT.
Only the exact parent income table, its two printed columns and the net-profit
row are accepted. Consolidated attributable profit is never substituted.
"""
from decimal import Decimal
import hashlib
import re


VERSION = "parent-income-basis-v2-unnumbered-continuation"
AMOUNT = re.compile(r"-?[0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2}")


def extract_unnumbered_parent_income_facts(*, pages, source, source_id):
    period = source["period"]
    if period.endswith("-12-31"):
        year, basis, column = int(period[:4]), "FY", "年度"
    elif period.endswith("-06-30"):
        year, basis, column = int(period[:4]), "H1", "年半年度"
    else:
        return dict(evidence=[], gaps=["ANNUAL_OR_INTERIM_PARENT_INCOME_ONLY"])
    title = [(i, j) for i, page in enumerate(pages) for j, line in enumerate(page.splitlines())
             if line.strip() == "母公司利润表"]
    if len(title) != 1:
        return dict(evidence=[], gaps=["UNIQUE_UNNUMBERED_PARENT_INCOME_TITLE_REQUIRED"])
    start_page, start_line = title[0]
    lines = []
    ended = False
    for page_index in range(start_page, min(start_page + 3, len(pages))):
        for line in pages[page_index].splitlines()[start_line + 1 if page_index == start_page else 0:]:
            if line.strip() == "合并现金流量表":
                ended = True
                break
            lines.append((page_index + 1, line.strip()))
        if ended:
            break
    if not ended:
        return dict(evidence=[], gaps=["UNNUMBERED_PARENT_INCOME_TABLE_END_REQUIRED"])
    header = "".join(line.replace(" ", "") for _, line in lines[:10])
    expected = f"项目附注{year}{column}{year - 1}{column}"
    if "单位：元币种：人民币" not in header or expected not in header:
        return dict(evidence=[], gaps=["UNNUMBERED_PARENT_INCOME_UNIT_OR_COLUMNS_INVALID"])
    rows = [(i, line) for i, (_, line) in enumerate(lines)
            if re.match(r"^四、净利润（净亏损以", line)]
    if len(rows) != 1:
        return dict(evidence=[], gaps=["UNIQUE_PARENT_NET_PROFIT_ROW_REQUIRED"])
    at, label = rows[0]
    # The FY row prints both amounts beside its label. The H1 row wraps its
    # label onto the next physical line and prints amounts on the line after.
    amount_line = label
    amount_page = lines[at][0]
    values = AMOUNT.findall(amount_line)
    if len(values) == 1:
        return dict(evidence=[], gaps=["PARENT_NET_PROFIT_TWO_PERIOD_AMOUNTS_REQUIRED"])
    if len(values) != 2:
        if (at + 2 >= len(lines) or lines[at + 1][1] != "列）"
                or not lines[at + 2][1]):
            return dict(evidence=[], gaps=["PARENT_NET_PROFIT_PRINTED_ROW_AMBIGUOUS"])
        amount_page, amount_line = lines[at + 2]
        values = AMOUNT.findall(amount_line)
    if len(values) != 2 or not amount_line.endswith(values[-1]):
        return dict(evidence=[], gaps=["PARENT_NET_PROFIT_TWO_PERIOD_AMOUNTS_REQUIRED"])
    value = Decimal(values[0].replace(",", ""))
    return dict(evidence=[dict(
        id="parent-income:" + hashlib.sha256(
            (source["sha256"] + ":" + period + ":parent_net_profit").encode()).hexdigest(),
        source_id=source_id, pdf_sha256=source["sha256"],
        available_at=source["available_at"], period=period, period_basis=basis,
        scope="parent", unit="CNY", field="parent_net_profit", value=str(value),
        kind="VERIFIED_REPORTED_FACT", physical_page=amount_page,
        text=label + " " + amount_line, verification_method=VERSION + ":exact-parent-net-profit-two-period-row",
        assurance_basis="Standalone-parent historical profit; not consolidated attributable profit or distributable cash.")], gaps=[])

"""Source-bound parent net profit from numbered official income statements.

The acquisition caller authenticates issuer, reporting period and PDF hash.
Parent profit is a reported historical flow, not forecast parent cash access.
"""
from decimal import Decimal
import hashlib
import re

from .parent_balance_basis_v1 import AMOUNT


VERSION = "parent-income-basis-v1-numbered-cninfo"
TITLE = re.compile(r"^4[、．.]\s*母公司利润表$")
END = re.compile(r"^5[、．.]\s*合并现金流量表$")


def extract_numbered_parent_income_facts(*, pages, source, source_id):
    period = source["period"]
    if period.endswith("-12-31"):
        year = int(period[:4])
        columns = f"项目{year}年度{year - 1}年度"
        basis = "FY"
    elif period.endswith("-06-30"):
        year = int(period[:4])
        columns = f"项目{year}年半年度{year - 1}年半年度"
        basis = "H1"
    else:
        return dict(evidence=[], gaps=["ANNUAL_OR_INTERIM_PARENT_INCOME_ONLY"])
    titles = [(i, j) for i, page in enumerate(pages)
              for j, line in enumerate(page.splitlines()) if TITLE.fullmatch(line.strip())]
    if len(titles) != 1:
        return dict(evidence=[], gaps=["UNIQUE_NUMBERED_PARENT_INCOME_TITLE_REQUIRED"])
    page_index, start = titles[0]
    segments, ended = [], False
    for i in range(page_index, min(len(pages), page_index + 3)):
        lines = pages[i].splitlines()[start + 1:] if i == page_index else pages[i].splitlines()
        for line in lines:
            if END.fullmatch(line.strip()):
                ended = True
                break
            segments.append((i + 1, line.strip()))
        if ended:
            break
    if not ended:
        return dict(evidence=[], gaps=["NUMBERED_PARENT_INCOME_TABLE_END_REQUIRED"])
    header = "".join(line.replace(" ", "") for _, line in segments[:10])
    if "单位：元" not in header or columns not in header:
        return dict(evidence=[], gaps=["NUMBERED_PARENT_INCOME_UNIT_OR_COLUMNS_INVALID"])
    starts = [i for i, (_, line) in enumerate(segments) if line.startswith("四、净利润（净亏损以")]
    if len(starts) != 1:
        return dict(evidence=[], gaps=["UNIQUE_PARENT_NET_PROFIT_ROW_REQUIRED"])
    at = starts[0]
    # In this layout the label wraps onto one short continuation line; the two
    # amounts occupy the following physical line. Never read a later row.
    if (at + 2 >= len(segments) or segments[at + 1][1] != "列）"):
        return dict(evidence=[], gaps=["PARENT_NET_PROFIT_PRINTED_ROW_AMBIGUOUS"])
    physical_page, value_line = segments[at + 2]
    values = AMOUNT.findall(value_line)
    if len(values) != 2 or not value_line.endswith(values[-1]):
        return dict(evidence=[], gaps=["PARENT_NET_PROFIT_TWO_PERIOD_AMOUNTS_REQUIRED"])
    text = " ".join(item[1] for item in segments[at:at + 3])
    row = dict(id="parent-income:" + hashlib.sha256(
        (source["sha256"] + ":" + period + ":parent_net_profit").encode()).hexdigest(),
        source_id=source_id, pdf_sha256=source["sha256"],
        available_at=source["available_at"], period=period, period_basis=basis,
        scope="parent", unit="CNY", field="parent_net_profit",
        value=str(Decimal(values[0].replace(",", ""))),
        kind="VERIFIED_REPORTED_FACT", physical_page=physical_page,
        text=text, verification_method=VERSION + ":exact-wrapped-parent-net-profit-two-period-row",
        assurance_basis="Standalone-parent historical profit; not consolidated attributable profit or distributable cash.")
    return dict(evidence=[row], gaps=[])

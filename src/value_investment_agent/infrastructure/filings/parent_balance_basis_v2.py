"""Strict parent balance rows for numbered CNINFO statement layouts.

The acquisition layer verifies issuer, period and original hash before calling
this extractor. Reported balances are not distributable cash or forecasts.
"""
from decimal import Decimal
import hashlib
import re

from .parent_balance_basis_v1 import AMOUNT


VERSION = "parent-balance-basis-v2-numbered-cninfo"
LABELS = {
    "parent_cash_balance": "货币资金",
    "parent_ordinary_share_capital": "股本",
    "parent_surplus_reserve": "盈余公积",
    "parent_retained_earnings": "未分配利润",
}
TITLE = re.compile(r"^2[、．.]\s*母公司资产负债表$")
END = re.compile(r"^3[、．.]\s*合并利润表$")


def extract_numbered_parent_balance_facts(*, pages, source, source_id, issuer_name):
    period = source["period"]
    if not (period.endswith("-12-31") or period.endswith("-06-30")):
        return dict(evidence=[], gaps=["ANNUAL_OR_INTERIM_PARENT_BALANCE_ONLY"])
    titles = [(i, j) for i, page in enumerate(pages)
              for j, line in enumerate(page.splitlines()) if TITLE.fullmatch(line.strip())]
    if len(titles) != 1:
        return dict(evidence=[], gaps=["UNIQUE_NUMBERED_PARENT_BALANCE_TITLE_REQUIRED"])
    page_index, start = titles[0]
    segments, ended = [], False
    for i in range(page_index, min(len(pages), page_index + 4)):
        lines = pages[i].splitlines()[start + 1:] if i == page_index else pages[i].splitlines()
        for line in lines:
            if END.fullmatch(line.strip()):
                ended = True
                break
            segments.append((i + 1, line.strip()))
        if ended:
            break
    if not ended:
        return dict(evidence=[], gaps=["NUMBERED_PARENT_BALANCE_TABLE_END_REQUIRED"])
    header = "".join(line.replace(" ", "") for _, line in segments[:12])
    if "单位：元" not in header or "项目期末余额期初余额" not in header:
        return dict(evidence=[], gaps=["NUMBERED_PARENT_BALANCE_UNIT_OR_COLUMNS_INVALID"])
    evidence, gaps = [], []
    for field, label in LABELS.items():
        matches = [(page, row) for page, row in segments
                   if row == label or row.startswith(label + " ")]
        if len(matches) != 1:
            gaps.append("UNIQUE_PARENT_BALANCE_ROW_REQUIRED:" + field)
            continue
        physical_page, row = matches[0]
        values = AMOUNT.findall(row[len(label):])
        if len(values) != 2 or not row.endswith(values[-1]):
            gaps.append("PARENT_BALANCE_TWO_PERIOD_AMOUNTS_REQUIRED:" + field)
            continue
        evidence.append(dict(
            id="parent-balance-v2:" + hashlib.sha256(
                (source["sha256"] + ":" + period + ":" + field).encode()).hexdigest(),
            source_id=source_id, pdf_sha256=source["sha256"],
            available_at=source["available_at"], period=period,
            period_basis="H1" if period.endswith("-06-30") else "FY",
            scope="parent", unit="CNY", field=field,
            value=str(Decimal(values[0].replace(",", ""))),
            kind="VERIFIED_REPORTED_FACT", physical_page=physical_page,
            text=row, verification_method=VERSION + ":exact-parent-table-two-period-row",
            assurance_basis="Reported parent balance only; neither distributable cash nor dividend capacity.",
        ))
    return dict(evidence=evidence, gaps=gaps)

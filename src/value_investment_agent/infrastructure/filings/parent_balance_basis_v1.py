"""Read exact parent balance-sheet rows from one verified annual original.

These reported balances are research facts, not distributable cash, a legal
dividend-capacity opinion, or an economic forecast. Unsupported layouts leave
precise gaps instead of borrowing consolidated rows.
"""
from decimal import Decimal
import hashlib
import re


VERSION = "parent-balance-basis-v1"
LABELS = {
    "parent_cash_balance": "货币资金",
    "parent_ordinary_share_capital": "实收资本（或股本）",
    "parent_surplus_reserve": "盈余公积",
    "parent_retained_earnings": "未分配利润",
}
AMOUNT = re.compile(r"-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}")


def extract_parent_balance_facts(*, pages, source, source_id, issuer_name):
    period = source["period"]
    if not (period.endswith("-12-31") or period.endswith("-06-30")):
        return dict(evidence=[], gaps=["ANNUAL_OR_INTERIM_PARENT_BALANCE_ONLY"])
    year = int(period[:4])
    current_heading = f"{year}年{6 if period.endswith('-06-30') else 12}月{30 if period.endswith('-06-30') else 31}日"
    previous_heading = f"{year - 1}年12月31日"
    starts = [(i, j) for i, page in enumerate(pages) for j, line in enumerate(page.splitlines())
              if line.strip() == "母公司资产负债表"]
    if len(starts) != 1:
        return dict(evidence=[], gaps=["UNIQUE_PARENT_BALANCE_TITLE_REQUIRED"])
    page_index, start = starts[0]
    segments = []
    ended = False
    for i in range(page_index, min(len(pages), page_index + 4)):
        lines = pages[i].splitlines()[start + 1:] if i == page_index else pages[i].splitlines()
        for line in lines:
            if line.strip() == "合并利润表":
                ended = True
                break
            segments.append((i + 1, line.strip()))
        if ended:
            break
    if not ended:
        return dict(evidence=[], gaps=["PARENT_BALANCE_TABLE_END_REQUIRED"])
    header = "".join(line.replace(" ", "") for _, line in segments[:12])
    if ("编制单位：" + issuer_name not in header
            or "单位：元币种：人民币" not in header
            or current_heading not in header
            or previous_heading not in header):
        return dict(evidence=[], gaps=["PARENT_BALANCE_OWNER_UNIT_OR_COLUMNS_INVALID"])
    evidence, gaps = [], []
    for field, label in LABELS.items():
        positions = [i for i, (_, line) in enumerate(segments)
                     if line == label or line.startswith(label + " ")]
        if len(positions) != 1:
            gaps.append("UNIQUE_PARENT_BALANCE_ROW_REQUIRED:" + field)
            continue
        position = positions[0]
        physical_page, row = segments[position]
        values = AMOUNT.findall(row[len(label):])
        # The official PDF renderer keeps the row, note reference and both
        # year columns on one line. Do not consume values from the next row.
        if len(values) != 2 or not row.endswith(values[-1]):
            gaps.append("PARENT_BALANCE_TWO_PERIOD_AMOUNTS_REQUIRED:" + field)
            continue
        current = str(Decimal(values[0].replace(",", "")))
        text = row
        evidence.append(dict(id="parent-balance:" + hashlib.sha256(
            (source["sha256"] + ":" + period + ":" + field).encode()).hexdigest(),
            source_id=source_id, pdf_sha256=source["sha256"],
            available_at=source["available_at"], period=period,
            period_basis="H1" if period.endswith("-06-30") else "FY",
            scope="parent", unit="CNY", field=field, value=current,
            kind="VERIFIED_REPORTED_FACT", physical_page=physical_page,
            text=text, verification_method=VERSION + ":exact-parent-table-two-period-row",
            assurance_basis="Reported parent balance only; neither distributable cash nor dividend capacity."))
    return dict(evidence=evidence, gaps=gaps)

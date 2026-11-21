"""Read the two-page parent-only nine-month cash statement layout."""
from datetime import date
from decimal import Decimal
import re

from .native_capital_observation_v1 import _compact
from .quarterly_operating_facts_v1 import CASH_FIELDS, MONEY


FIELDS = {
    **CASH_FIELDS,
    "investment_income_cash_cny": "取得投资收益收到的现金",
    "net_investing_cash_cny": "投资活动产生的现金流量净额",
    "borrowings_received_cny": "取得借款收到的现金",
    "debt_repayments_paid_cny": "偿还债务支付的现金",
    "distribution_or_interest_cash_cny": "分配股利、利润或偿付利息支付的现金",
    "net_financing_cash_cny": "筹资活动产生的现金流量净额",
    "net_cash_change_cny": "五、现金及现金等价物净增加额",
    "opening_cash_cny": "加:期初现金及现金等价物余额",
    "closing_cash_cny": "六、期末现金及现金等价物余额",
}


def parse_paginated_parent_cash(pages, *, symbol, issuer_name, period_end):
    year = date.fromisoformat(period_end).year
    issuer = _compact(issuer_name)
    if (not re.fullmatch(r"[0-9]{6}", symbol) or not issuer
            or period_end != f"{year}-09-30" or not 2 <= len(pages) <= 80):
        raise ValueError("PARENT_PAGINATED_Q3_IDENTITY_INVALID")
    cover = _compact(pages[0])
    if (set(re.findall(r"证券代码:?([0-9]{6})(?![0-9])", cover)) != {symbol}
            or f"{issuer}{year}年第三季度报告" not in cover):
        raise ValueError("PARENT_PAGINATED_Q3_COVER_MISMATCH")
    lines = [(index, line.strip(), _compact(line)) for index, page in enumerate(pages, 1)
             for line in page.splitlines() if line.strip()]
    starts = [index for index, (_, _, line) in enumerate(lines) if line == "母公司现金流量表"]
    if len(starts) != 1:
        raise ValueError("PARENT_PAGINATED_Q3_TABLE_NOT_UNIQUE")
    start = starts[0]
    header = "".join(row[2] for row in lines[start+1:start+9])
    if any(row[0] != lines[start][0] for row in lines[start + 1:start + 9]):
        raise ValueError("PARENT_PAGINATED_Q3_HEADER_CROSSES_PAGE")
    expected = (f"{year}年1—9月编制单位:{issuer}单位:元币种:人民币审计类型:未经审计项目"
                f"{year}年前三季度(1-9月){year-1}年前三季度(1-9月)")
    if header != expected:
        raise ValueError("PARENT_PAGINATED_Q3_COLUMNS_OR_SCOPE_MISMATCH")
    end = next((i for i in range(start+9, len(lines))
                if lines[i][2].startswith("公司负责人:")), None)
    if end is None or lines[end][0] != lines[start][0] + 1:
        raise ValueError("PARENT_PAGINATED_Q3_TABLE_END_UNVERIFIED")
    rows = lines[start+9:end]
    if any(line.endswith(("现金流量表", "资产负债表", "利润表")) for _, _, line in rows):
        raise ValueError("PARENT_PAGINATED_Q3_TABLE_OWNERSHIP_CHANGED")
    headings = (
        "一、经营活动产生的现金流量:",
        "二、投资活动产生的现金流量:",
        "三、筹资活动产生的现金流量:",
    )
    boundaries = []
    for heading in headings:
        locations = [i for i, (_, _, line) in enumerate(rows) if line == heading]
        if len(locations) != 1:
            raise ValueError("PARENT_PAGINATED_Q3_SECTION_NOT_UNIQUE")
        boundaries.append(locations[0])
    if boundaries != sorted(boundaries):
        raise ValueError("PARENT_PAGINATED_Q3_SECTION_ORDER_INVALID")
    fields = {}
    for field, label in FIELDS.items():
        pattern = re.compile(re.escape(_compact(label)) + MONEY + MONEY)
        matches = []
        for i, (page, _, line) in enumerate(rows):
            if not line.startswith(_compact(label)[:10]):
                continue
            for width in range(1, min(3, len(rows)-i)+1):
                candidate = rows[i:i+width]
                if any(row[0] != page for row in candidate):
                    continue
                match = pattern.fullmatch("".join(row[2] for row in candidate))
                if match:
                    matches.append((i, page, "\n".join(row[1] for row in candidate), match.groups()))
        if len(matches) != 1:
            raise ValueError("PARENT_PAGINATED_Q3_ROW_MISSING_OR_AMBIGUOUS:" + field)
        index, page, excerpt, amounts = matches[0]
        if field in {"cfo", "customer_cash", "supplier_cash"}:
            in_section = boundaries[0] < index < boundaries[1]
        elif field in {"cash_capex", "investment_income_cash_cny", "net_investing_cash_cny"}:
            in_section = boundaries[1] < index < boundaries[2]
        else:
            in_section = boundaries[2] < index
        if not in_section:
            raise ValueError("PARENT_PAGINATED_Q3_ROW_SECTION_MISMATCH:" + field)
        current, comparative = (str(Decimal(value.replace(",", ""))) for value in amounts)
        fields[field] = dict(current=current, comparative=comparative, physical_page=page,
                             excerpt=excerpt, currency="CNY", scope="ISSUER_PARENT_STANDALONE")
    residual = {}
    for column in ("current", "comparative"):
        value = lambda name: Decimal(fields[name][column])
        change = value("net_cash_change_cny")
        if value("opening_cash_cny") + change != value("closing_cash_cny"):
            raise ValueError("PARENT_PAGINATED_Q3_CASH_BALANCE_MISMATCH")
        residual[column] = str(change - sum(value(name) for name in (
            "cfo", "net_investing_cash_cny", "net_financing_cash_cny")))
    return dict(schema_version="quarterly-parent-cash-paginated-v2", symbol=symbol,
                period_end=period_end, comparative_end=f"{year-1}-09-30", period_basis="YTD_9M",
                fields=fields, net_change_minus_reported_flows_cny=residual, action="no_order")

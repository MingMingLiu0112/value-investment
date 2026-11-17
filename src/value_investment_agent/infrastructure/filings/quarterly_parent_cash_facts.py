"""Parse explicit parent-only nine-month cash flow rows from a verified original."""

from datetime import date
from decimal import Decimal
import re

from .native_capital_observation_v1 import _compact
from .quarterly_operating_facts_v1 import CASH_FIELDS, MONEY


def parse_quarterly_parent_cash_facts(pages, *, symbol, issuer_name, period_end):
    """Accept the explicit YTD comparative layout and retain original row text."""
    year = date.fromisoformat(period_end).year
    issuer = _compact(issuer_name)
    if (not re.fullmatch(r"[0-9]{6}", symbol) or not issuer or not pages
            or period_end != f"{year}-09-30" or len(pages) > 80):
        raise ValueError("PARENT_QUARTER_IDENTITY_INVALID")
    cover = _compact(pages[0])
    if (set(re.findall(r"证券代码:?([0-9]{6})(?![0-9])", cover)) != {symbol}
            or f"{issuer}{year}年第三季度报告" not in cover):
        raise ValueError("PARENT_QUARTER_COVER_MISMATCH")

    marker = "母公司现金流量表"
    matches = [(index, page) for index, page in enumerate(pages, 1)
               if marker in {_compact(line) for line in page.splitlines()}]
    if len(matches) != 1:
        raise ValueError("PARENT_QUARTER_STATEMENT_REQUIRED")
    index, page = matches[0]
    lines = page.splitlines()
    start = next(i for i, line in enumerate(lines) if _compact(line) == marker)
    header = _compact("".join(lines[start + 1:start + 5]))
    if (not header.startswith(f"{year}年1—9月编制单位:{issuer}单位:元币种:人民币")
            or f"项目{year}年前三季度(1-9月){year-1}年前三季度(1-9月)" not in header):
        raise ValueError("PARENT_QUARTER_COLUMNS_SCOPE_OR_CURRENCY_INVALID")

    fields = {}
    for field, label in {**CASH_FIELDS, "investment_income_cash_cny": "取得投资收益收到的现金"}.items():
        pattern = re.compile(re.escape(_compact(label)) + MONEY + MONEY)
        rows = [(line, pattern.fullmatch(_compact(line))) for line in lines[start + 5:]]
        found = [(line, match) for line, match in rows if match]
        if len(found) != 1:
            raise ValueError("PARENT_QUARTER_ROW_MISSING_OR_AMBIGUOUS:" + field)
        line, match = found[0]
        fields[field] = {
            "current": str(Decimal(match[1].replace(",", ""))),
            "comparative": str(Decimal(match[2].replace(",", ""))),
            "physical_page": index, "excerpt": line.strip(),
            "currency": "CNY", "scope": "ISSUER_PARENT_STANDALONE",
        }
    return {"symbol": symbol, "period_start": f"{year}-01-01", "period_end": period_end,
            "comparative_start": f"{year-1}-01-01", "comparative_end": f"{year-1}-09-30",
            "period_basis": "YTD_9M", "fields": fields, "action": "no_order"}

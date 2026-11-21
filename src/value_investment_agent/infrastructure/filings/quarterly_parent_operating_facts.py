"""Parent-only nine-month operating facts from one complete quarterly original."""

from datetime import date
from decimal import Decimal
import re

from .native_capital_observation_v1 import _compact
from .quarterly_operating_facts_v1 import MONEY
from .quarterly_parent_cash_facts import parse_quarterly_parent_cash_facts


SCOPE = "ISSUER_PARENT_STANDALONE"
PARSER_VERSION = "quarterly-parent-operating-facts-v1"
LABELS = {"revenue": "一、营业收入", "cost": "减：营业成本",
          "net_profit": "四、净利润（净亏损以“-”号填列）"}


def parse_quarterly_parent_operating_facts(pages, *, symbol, issuer_name, period_end):
    """Read the explicit parent income table and replay parent cash on the same pages."""
    if (not isinstance(pages, list) or not 1 <= len(pages) <= 80
            or any(not isinstance(page, str) for page in pages)
            or sum(map(len, pages)) > 1_000_000):
        raise ValueError("PARENT_OPERATING_COMPLETE_ORIGINAL_REQUIRED")
    cash = parse_quarterly_parent_cash_facts(
        pages, symbol=symbol, issuer_name=issuer_name, period_end=period_end)
    year = date.fromisoformat(period_end).year
    issuer = _compact(issuer_name)
    marker = "母公司利润表"
    matches = [(index, page) for index, page in enumerate(pages, 1)
               if marker in {_compact(line) for line in page.splitlines()}]
    if len(matches) != 1:
        raise ValueError("PARENT_OPERATING_INCOME_STATEMENT_REQUIRED")
    index, page = matches[0]
    lines = page.splitlines()
    start = next(i for i, line in enumerate(lines) if _compact(line) == marker)
    header = _compact("".join(lines[start + 1:start + 5]))
    if (not header.startswith(f"{year}年1—9月编制单位:{issuer}单位:元币种:人民币")
            or f"项目{year}年前三季度(1-9月){year-1}年前三季度(1-9月)" not in header):
        raise ValueError("PARENT_OPERATING_COLUMNS_SCOPE_OR_CURRENCY_INVALID")
    # The exact parent section ends at its sign-off; another statement cannot fill a missing row.
    body = lines[start + 5:]
    if any("合并利润表" in _compact(line) or "母公司现金流量表" in _compact(line)
           for line in body):
        raise ValueError("PARENT_OPERATING_STATEMENT_BOUNDARY_INVALID")
    fields = {}
    for field, label in LABELS.items():
        pattern = re.compile(re.escape(_compact(label)) + MONEY + MONEY)
        found = [(line, match) for line in body
                 if (match := pattern.fullmatch(_compact(line)))]
        if len(found) != 1:
            raise ValueError("PARENT_OPERATING_ROW_MISSING_OR_AMBIGUOUS:" + field)
        line, match = found[0]
        fields[field] = {
            "current": str(Decimal(match[1].replace(",", ""))),
            "comparative": str(Decimal(match[2].replace(",", ""))),
            "physical_page": index, "excerpt": line.strip(),
            "currency": "CNY", "scope": SCOPE, "period_basis": "YTD_9M",
        }
    return {"parser_version": PARSER_VERSION, "symbol": symbol,
            "period_start": cash["period_start"], "period_end": cash["period_end"],
            "comparative_start": cash["comparative_start"],
            "comparative_end": cash["comparative_end"],
            "period_basis": "YTD_9M", "scope": SCOPE, "currency": "CNY",
            "fields": fields, "cash_fields": cash["fields"], "action": "no_order"}


def build_quarterly_parent_operating_observations(pages, *, symbol, issuer_name,
                                                   period_end):
    """Return two typed inputs; application must bind original path/hash before admission."""
    facts = parse_quarterly_parent_operating_facts(
        pages, symbol=symbol, issuer_name=issuer_name, period_end=period_end)
    result = []
    for column, start, end in (("current", facts["period_start"], facts["period_end"]),
                               ("comparative", facts["comparative_start"],
                                facts["comparative_end"])):
        fields = {key: facts["fields"][key] if key in facts["fields"]
                  else facts["cash_fields"][key]
                  for key in ("revenue", "cost", "net_profit", "customer_cash",
                              "supplier_cash", "cfo")}
        result.append({"symbol": symbol, "scope": SCOPE, "currency": "CNY",
                       "period_start": start, "period_end": end,
                       "period_basis": "YTD_9M", "classification": "FACT",
                       **{key: fields[key][column] for key in fields},
                       "source_refs": [
                           {"field": key, "physical_page": item["physical_page"],
                            "excerpt": item["excerpt"], "column": column}
                           for key, item in fields.items()],
                       "source_binding_required": True, "action": "no_order"})
    return result

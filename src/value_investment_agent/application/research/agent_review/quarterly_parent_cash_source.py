"""Replay parent cash facts with an explicit official original and observation time."""

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import re

from ...product.common import require_inside
from ....infrastructure.filings.pdf_text import extract_pages
from ....infrastructure.filings.quarterly_operating_facts_v1 import MONEY
from ....infrastructure.filings.quarterly_parent_cash_facts import parse_quarterly_parent_cash_facts


def replay_quarterly_parent_cash(*, root, source, symbol, issuer_name, period_end, now,
                                 include_financing=False):
    fields = {"path", "sha256", "url", "acquired_at"}
    if (not isinstance(source, dict) or set(source) != fields
            or any(not isinstance(source[key], str) for key in fields)
            or not re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF",
                                source["url"])
            or not re.fullmatch(r"[a-f0-9]{64}", source["sha256"])):
        raise ValueError("PARENT_QUARTER_SOURCE_BINDING_INVALID")
    acquired = datetime.fromisoformat(source["acquired_at"])
    if acquired.utcoffset() is None or now.utcoffset() is None or acquired > now:
        raise ValueError("PARENT_QUARTER_SOURCE_NOT_AVAILABLE")
    relative = source["path"]
    if not relative.startswith("runtime/") or "\\" in relative or ".." in relative.split("/"):
        raise ValueError("PARENT_QUARTER_SOURCE_PATH_INVALID")
    path = require_inside(root / "runtime", root / relative, "parent quarter source")
    if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("PARENT_QUARTER_SOURCE_HASH_CHANGED")
    pages = extract_pages(path)
    result = parse_quarterly_parent_cash_facts(
        pages, symbol=symbol, issuer_name=issuer_name, period_end=period_end)
    if include_financing:
        anchor = result["fields"]["cfo"]
        lines = pages[anchor["physical_page"] - 1].splitlines()
        section = [index for index, line in enumerate(lines)
                   if re.fullmatch(r"三[、.]筹资活动产生的现金流量[:：]", "".join(line.split()))]
        if len(section) != 1:
            raise ValueError("PARENT_QUARTER_FINANCING_SECTION_REQUIRED")
        result["financing"] = {}
        for field, label in (("borrowings_received_cny", "取得借款收到的现金"),
                             ("debt_repayments_paid_cny", "偿还债务支付的现金")):
            pattern = re.compile(re.escape(label) + MONEY + MONEY)
            rows = [(line, pattern.fullmatch("".join(line.split())))
                    for line in lines[section[0] + 1:]]
            matches = [(line, matched) for line, matched in rows if matched]
            if len(matches) != 1:
                raise ValueError("PARENT_QUARTER_FINANCING_ROW_MISSING_OR_AMBIGUOUS:" + field)
            line, match = matches[0]
            amounts = [Decimal(value.replace(",", "")) for value in match.groups()]
            if min(amounts) < 0:
                raise ValueError("PARENT_QUARTER_FINANCING_NEGATIVE_GROSS_FLOW:" + field)
            result["financing"][field] = {
                "current": str(amounts[0]), "comparative": str(amounts[1]),
                "excerpt": line.strip(), "physical_page": anchor["physical_page"],
                "currency": anchor["currency"], "scope": anchor["scope"],
            }
    if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("PARENT_QUARTER_SOURCE_HASH_CHANGED")
    return {**result, "source": dict(source), "available_at": acquired.isoformat()}


def quarterly_parent_cash_evidence(*, root, source, symbol, issuer_name, period_end, now):
    """Build D2 rows while preserving standalone scope and both YTD periods."""
    facts = replay_quarterly_parent_cash(
        root=root, source=source, symbol=symbol, issuer_name=issuer_name,
        period_end=period_end, now=now)
    source_id = "cninfo:" + source["url"].rsplit("/", 1)[1].removesuffix(".PDF")
    field_names = {
        "cfo": "parent_cfo",
        "cash_capex": "parent_capex",
        "customer_cash": "parent_customer_cash",
        "supplier_cash": "parent_supplier_cash",
        "investment_income_cash_cny": "parent_investment_cash",
    }
    rows = []
    for field, item in facts["fields"].items():
        target = field_names[field]
        for column, period in (("current", facts["period_end"]),
                               ("comparative", facts["comparative_end"])):
            value = item[column]
            text = f"母公司{period}止九个月：{target}为{value}元。原文：{item['excerpt']}"
            rows.append({
                "id": f"{source_id}:parent-ytd:{target}:{period}", "source_id": source_id,
                "pdf_sha256": source["sha256"], "available_at": facts["available_at"],
                "period": period, "period_basis": "YTD_9M", "scope": item["scope"],
                "unit": "CNY", "field": target, "value": value, "text": text,
                "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "physical_page": item["physical_page"],
                "kind": "REPORTED_HISTORICAL_FACT_NOT_FORECAST",
            })
    return rows

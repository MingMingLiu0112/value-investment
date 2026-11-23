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


def bridge_quarterly_parent_operating_cash(*, root, source, symbol, issuer_name,
                                           period_end, now, historical, annual_forecast):
    """Rebase annual operating drivers on verified nine-month flows."""
    from decimal import localcontext
    from ....domain.valuation.parent_remaining_year_cash import build_parent_remaining_year_cash
    from ....infrastructure.filings.quarterly_parent_operating_facts import (
        build_quarterly_parent_operating_observations,
    )

    bound = replay_quarterly_parent_cash(
        root=root, source=source, symbol=symbol, issuer_name=issuer_name,
        period_end=period_end, now=now)
    path = require_inside(root / "runtime", root / source["path"], "parent quarter source")
    pages = extract_pages(path)
    if sha256(path.read_bytes()).hexdigest() != bound["source"]["sha256"]:
        raise ValueError("PARENT_QUARTER_SOURCE_HASH_CHANGED")
    current, prior = build_quarterly_parent_operating_observations(
        pages, symbol=symbol, issuer_name=issuer_name, period_end=period_end)
    for row in (current, prior):
        row["source_refs"] = [
            {**ref, **bound["source"], "available_at": bound["available_at"]}
            for ref in row["source_refs"]
        ]
    year = period_end[:4]
    if (annual_forecast.get("symbol") != symbol
            or annual_forecast.get("period_start") != f"{year}-01-01"
            or annual_forecast.get("period_end") != f"{year}-12-31"):
        raise ValueError("PARENT_QUARTER_ANNUAL_FORECAST_IDENTITY_INVALID")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        observed_other = (Decimal(current["cfo"]) - Decimal(current["customer_cash"])
                          + Decimal(current["supplier_cash"]))
        q4 = {
            **annual_forecast,
            "period_start": f"{year}-10-01",
            "source_refs": [*annual_forecast["source_refs"], *current["source_refs"]],
            "revenue": str(Decimal(annual_forecast["revenue"]) - Decimal(current["revenue"])),
            "cost": str(Decimal(annual_forecast["cost"]) - Decimal(current["cost"])),
            "other_operating_cash": str(Decimal(annual_forecast["other_operating_cash"])
                                        - observed_other),
        }
    return build_parent_remaining_year_cash(
        historical_full_year=historical, historical_nine_months=prior,
        current_nine_months=current, q4_forecast=q4, as_of=now.date())


def project_parent_annual_operating_cash(*, root, spec, now, historical, forecast):
    """Use identical annual cash arithmetic for preflight and compilation."""
    from datetime import date
    from zoneinfo import ZoneInfo
    from ....domain.valuation.parent_direct_operating_cash import forecast_parent_operating_cash

    method = spec.get("first_year_operating_cash_method")
    if method is None:
        return forecast_parent_operating_cash(historical=historical, forecast=forecast)
    if method != "OBSERVED_9M_PLUS_CONDITIONAL_Q4_V1":
        raise ValueError("PARENT_ANNUAL_OPERATING_CASH_METHOD_UNSUPPORTED")
    year = int(spec["valuation_date"][:4]) + 1
    if forecast["period_end"] != f"{year}-12-31":
        return forecast_parent_operating_cash(historical=historical, forecast=forecast)
    source = spec["quarterly_financing_source"]
    period_end = f"{year}-09-30"
    published = date.fromisoformat(source["url"].rsplit("/", 2)[-2])
    acquired = datetime.fromisoformat(source["acquired_at"])
    if (acquired.utcoffset() is None or not date.fromisoformat(period_end) <= published
            <= acquired.astimezone(ZoneInfo("Asia/Shanghai")).date()):
        raise ValueError("PARENT_QUARTER_SOURCE_DATE_UNVERIFIED")
    bridge = bridge_quarterly_parent_operating_cash(
        root=root, source=source, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
        period_end=period_end, now=now, historical=historical,
        annual_forecast={**forecast, "source_refs": historical["source_refs"]})
    annual = bridge["full_year"]
    return {
        "schema_version": bridge["schema_version"],
        "symbol": bridge["symbol"],
        "scope": bridge["scope"],
        "currency": bridge["currency"],
        "period_start": bridge["period_start"],
        "period_end": bridge["period_end"],
        "classification": bridge["classification"],
        "assumptions": dict(forecast),
        "source_refs": [*historical["source_refs"], *bridge["current_nine_months"]["source_refs"]],
        "customer_cash": annual["customer_cash"]["total"],
        "supplier_cash": annual["supplier_cash"]["total"],
        "other_operating_cash": forecast["other_operating_cash"],
        "operating_cash": annual["cfo"]["total"],
        "remaining_year_bridge": bridge,
        "action": "no_order",
        "formal_eligibility": False,
    }


def quarterly_parent_annual_capex_floor(facts):
    """Project a realised gross capex floor without inventing its split."""

    capex = facts["fields"]["cash_capex"]
    amount = Decimal(capex["current"])
    if not amount.is_finite() or amount < 0:
        raise ValueError("PARENT_QUARTER_CAPEX_NOT_GROSS_CASH")
    return {
        "symbol": facts["symbol"],
        "year": int(facts["period_end"][:4]),
        "period_start": facts["period_start"],
        "observed_through": facts["period_end"],
        "minimum_cny": str(amount),
        "annual_policy_fields": ["maintenance_capex", "growth_capex"],
        "scope": capex["scope"],
        "currency": capex["currency"],
        "source_ref": {
            **facts["source"],
            "available_at": facts["available_at"],
            "physical_page": capex["physical_page"],
            "excerpt": capex["excerpt"],
        },
    }


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

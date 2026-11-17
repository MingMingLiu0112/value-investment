"""Read-only D2 parent facts from pinned numbered CNINFO report originals."""
from __future__ import annotations

from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path
import json
import re

from . import parent_direct_owner_cash_sources as prior
from .parent_cash_observation_v2 import extract_numbered_parent_cash_statement
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.parent_balance_basis_v2 import extract_numbered_parent_balance_facts, AMOUNT
from ...infrastructure.filings.parent_income_basis_v1 import extract_numbered_parent_income_facts
from ..product.common import require_inside, sha256_file

VERSION = "parent-direct-owner-cash-sources-v2"
LAYOUT = {"balance": "NUMBERED_CNINFO_V2", "cash": "NUMBERED_CNINFO_V2",
          "income": "NUMBERED_CNINFO_V1"}
_BALANCE = {"parent_cash_balance": "monetary_funds_cny",
            "parent_ordinary_share_capital": "share_capital_cny",
            "parent_surplus_reserve": "surplus_reserve_cny",
            "parent_retained_earnings": "retained_earnings_cny"}
_EXTRA_CASH = {"customer_cash_cny": "销售商品、提供劳务收到的现金",
               "supplier_cash_cny": "购买商品、接受劳务支付的现金"}


def _fact(value, comparative, page, excerpt, source, period, field, *, balance=False):
    ref = dict(path=source["path"], sha256=source["sha256"],
               available_at=source["available_at"], physical_page=page,
               excerpt=excerpt, field=field, current_period=period,
               comparative_period=(f"{int(period[:4])-1}-12-31" if balance
                                   else f"{int(period[:4])-1}{period[4:]}"))
    return dict(current=value, comparative=comparative, physical_page=page,
                excerpt=excerpt, classification="FACT", scope=prior.SCOPE,
                currency="CNY", source_refs=ref)


def _read(root, symbol, issuer_name, item, evaluated_at):
    if not isinstance(item, dict) or set(item) != {"period_end", "layout", "receipt_binding"}:
        raise ValueError("OWNER_CASH_V2_SOURCE_SCHEMA_INVALID")
    if item["layout"] != LAYOUT:
        raise ValueError("OWNER_CASH_V2_LAYOUT_UNSUPPORTED")
    period = item["period_end"]
    day = date.fromisoformat(period)
    if day.isoformat() != period or period[4:] not in ("-12-31", "-06-30"):
        raise ValueError("OWNER_CASH_V2_PERIOD_INVALID")
    pin = item["receipt_binding"]
    if (not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
            or not isinstance(pin["path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
        raise ValueError("OWNER_CASH_V2_RECEIPT_BINDING_INVALID")
    packet = load_retained_official_report(root=root, receipt_binding=pin,
        symbol=symbol, issuer_name=issuer_name, period=period)
    published = date.fromisoformat(packet["published_date"])
    available = datetime.combine(published + timedelta(days=1), time(),
                                 timezone(timedelta(hours=8)))
    if available > evaluated_at:
        raise ValueError("OWNER_CASH_V2_NOT_YET_AVAILABLE")
    source = packet["source"]
    original = require_inside(root / "runtime", root / source["path"], "numbered parent original")
    if sha256_file(original) != source["sha256"]:
        raise ValueError("OWNER_CASH_V2_ORIGINAL_HASH_CHANGED")
    pages = extract_pages(original)
    cash = extract_numbered_parent_cash_statement(pages=pages, symbol=symbol,
        issuer_name=issuer_name, period=period)
    balance_result = extract_numbered_parent_balance_facts(pages=pages, source=source,
        source_id=packet["source_id"], issuer_name=issuer_name)
    income_result = extract_numbered_parent_income_facts(pages=pages, source=source,
        source_id=packet["source_id"])
    if sha256_file(original) != source["sha256"]:
        raise ValueError("OWNER_CASH_V2_ORIGINAL_CHANGED")
    reference = dict(path=source["path"], sha256=source["sha256"],
        available_at=source["available_at"], receipt_binding=dict(pin),
        source_id=packet["source_id"], source_url=source["source_url"],
        published_date=packet["published_date"])
    gaps, balance, income, flows = [], {}, {}, {}
    for row in balance_result["evidence"]:
        field = _BALANCE[row["field"]]
        printed = AMOUNT.findall(row["text"])
        if len(printed) != 2 or row["value"] != printed[0].replace(",", ""):
            raise ValueError("OWNER_CASH_V2_BALANCE_ROW_CHANGED")
        balance[field] = _fact(row["value"], printed[1].replace(",", ""), row["physical_page"], row["text"],
                               source, period, field, balance=True)
    for gap in balance_result["gaps"]:
        gaps.append(dict(table="balance", field=None, reason=gap, value=None))
    for row in income_result["evidence"]:
        field = "parent_net_profit_cny"
        printed = AMOUNT.findall(row["text"])
        if len(printed) != 2 or row["value"] != printed[0].replace(",", ""):
            raise ValueError("OWNER_CASH_V2_INCOME_ROW_CHANGED")
        income[field] = _fact(row["value"], printed[1].replace(",", ""), row["physical_page"], row["text"],
                              source, period, field)
    for gap in income_result["gaps"]:
        gaps.append(dict(table="income", field=None, reason=gap, value=None))
    lines = [(page, line.strip()) for page, text in enumerate(pages, 1)
             for line in text.splitlines()]
    income_starts = [i for i, (_, line) in enumerate(lines)
                     if re.fullmatch(r"4[、．.]\s*母公司利润表", line)]
    income_ends = [i for i, (_, line) in enumerate(lines)
                   if re.fullmatch(r"5[、．.]\s*合并现金流量表", line)]
    if len(income_starts) != 1 or len(income_ends) != 1 or income_starts[0] >= income_ends[0]:
        raise ValueError("OWNER_CASH_V2_INCOME_TABLE_INVALID")
    for field, label in (("revenue", "一、营业收入"), ("cost", "减：营业成本")):
        matches = [(page, line) for page, line in lines[income_starts[0]:income_ends[0]]
                   if line.startswith(label)]
        if len(matches) != 1:
            gaps.append(dict(table="income", field=field, reason="ROW_NOT_UNIQUE", value=None))
            continue
        page, line = matches[0]
        values = AMOUNT.findall(line[len(label):])
        if len(values) != 2 or not line.endswith(values[-1]):
            gaps.append(dict(table="income", field=field, reason="TWO_PRINTED_VALUES_REQUIRED", value=None))
            continue
        income[field] = _fact(*(v.replace(",", "") for v in values), page, line,
                              source, period, field)
    for field, row in cash["rows"].items():
        flows[field] = _fact(row["columns"][0]["value"], row["columns"][1]["value"],
                             row["physical_page"], row["evidence_excerpt"], source, period, field)
    for field in cash["unknown_fields"]:
        gaps.append(dict(table="cash_flow", field=field, reason="ROW_NOT_UNAMBIGUOUS", value=None))
    # Additional operating receipts retain the same numbered-table ownership.
    starts = [i for i, (_, line) in enumerate(lines) if prior._compact(line) == "6、母公司现金流量表"]
    ends = [i for i, (_, line) in enumerate(lines) if prior._compact(line) == "7、合并所有者权益变动表"]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("OWNER_CASH_V2_PARENT_TABLE_INVALID")
    for field, label in _EXTRA_CASH.items():
        matches = [(page, line) for page, line in lines[starts[0]:ends[0]]
                   if prior._compact(line).startswith(prior._compact(label))]
        if len(matches) != 1:
            gaps.append(dict(table="cash_flow", field=field, reason="ROW_NOT_UNIQUE", value=None))
            continue
        page, line = matches[0]
        values = prior.MONEY.findall(line[len(label):])
        if len(values) != 2:
            gaps.append(dict(table="cash_flow", field=field, reason="TWO_PRINTED_VALUES_REQUIRED", value=None))
            continue
        flows[field] = _fact(*(v.replace(",", "") for v in values), page, line,
                             source, period, field)
    year = day.year
    return dict(symbol=symbol, issuer_name=issuer_name, scope=prior.SCOPE, currency="CNY",
        classification="FACT", period_start=f"{year}-01-01", period_end=period,
        period_basis="FY" if day.month == 12 else "H1",
        opening_balance_as_of=f"{year-1}-12-31",
        comparative_flow_start=f"{year-1}-01-01",
        comparative_flow_end=f"{year-1}{period[4:]}", source_binding=reference,
        balance_sheet=balance, income=income, cash_flow=flows, gaps=gaps,
        checks=dict(cash_statement_reconciled=False, balance_equation_reconciled=False))


def read_parent_direct_owner_cash_sources_v2(*, root, symbol, issuer_name, sources,
        evaluated_at, constraint_binding=None, fund_selection=None):
    """Replay pinned numbered receipts into the v1 D2 source shape, without orders."""
    if (not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None
            or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
            or not isinstance(issuer_name, str) or not issuer_name.strip()
            or not isinstance(sources, list) or not sources):
        raise ValueError("OWNER_CASH_V2_IDENTITY_OR_SOURCES_INVALID")
    root = Path(root).resolve()
    statements = [_read(root, symbol, issuer_name, item, evaluated_at) for item in sources]
    if len({s["period_end"] for s in statements}) != len(statements):
        raise ValueError("OWNER_CASH_V2_DUPLICATE_PERIOD")
    statements.sort(key=lambda s: s["period_end"])
    for earlier in statements:
        for later in statements:
            if earlier["period_end"] != later["opening_balance_as_of"]:
                continue
            for field in earlier["balance_sheet"].keys() & later["balance_sheet"].keys():
                if earlier["balance_sheet"][field]["current"] != later["balance_sheet"][field]["comparative"]:
                    raise ValueError("OWNER_CASH_V2_BALANCE_CONTINUITY_CHANGED:" + field)
            end = earlier["cash_flow"].get("closing_cash_and_equivalents_cny")
            begin = later["cash_flow"].get("opening_cash_and_equivalents_cny")
            if end and begin and end["current"] != begin["current"]:
                raise ValueError("OWNER_CASH_V2_CASH_CONTINUITY_CHANGED")
    constraints = (prior._constraints(root, constraint_binding, symbol, issuer_name, evaluated_at)
                   if constraint_binding is not None else None)
    charter = None
    if constraint_binding is not None:
        _, raw = prior._bound(root, constraint_binding)
        charter = json.loads(raw, object_pairs_hook=prior._unique)["charter"]
    for statement in statements:
        statement["ordinary_shares_evidence"] = (prior._ordinary_shares(
            root, statement, charter, issuer_name, evaluated_at)
            if statement["period_basis"] == "FY" else None)
    fund = (prior.replay_parent_fund_evidence(root=root,
        context=dict(symbol=symbol, issuer_name=issuer_name),
        selection=fund_selection, cutoff=evaluated_at) if fund_selection is not None else None)
    return dict(schema_version=VERSION, symbol=symbol, issuer_name=issuer_name,
        evaluated_at=evaluated_at.isoformat(), statements=statements, constraints=constraints,
        fund_commitment_evidence=fund, fund_selection=fund_selection,
        status="SOURCE_BOUND_PARENT_BRIDGE_FACTS_NOT_OWNER_CASH", action="no_order",
        formal_eligibility=False, owner_cash_cny=None, distribution_capacity_cny=None,
        working_capital_cash_component=None, unresolved=[
            "UNRESTRICTED_CASH_AND_OPERATING_FLOOR",
            "PARENT_STATUTORY_RESERVE_COMPONENT_AND_FUTURE_APPROPRIATION",
            "DISTRIBUTABLE_PROFIT_AND_APPROVAL", "FUTURE_NET_BORROWING_AND_SETTLEMENT_SCHEDULE",
            "INTEREST_VERSUS_DIVIDEND_SPLIT", "MAINTENANCE_GROWTH_AND_COMMITMENT_OVERLAP",
            "INVESTMENT_INCOME_CASH_RECURRING_AND_SUBSIDIARY_REMITTANCE_SPLIT",
            "INVESTMENT_PRINCIPAL_RECYCLING_AND_REQUIRED_REINVESTMENT",
            "UNDATED_FUND_CAPITAL_CALLS", "PARENT_TO_ORDINARY_OWNER_MAPPING"])

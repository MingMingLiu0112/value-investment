"""Read-only D2 parent facts from pinned numbered CNINFO report originals."""
from __future__ import annotations

from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal
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
_EXTRA_BALANCE = {
    "assets_cny": "资产总计",
    "liabilities_cny": "负债合计",
    "book_equity_cny": "所有者权益合计",
    "short_term_borrowings_cny": "短期借款",
    "long_term_borrowings_cny": "长期借款",
    "current_noncurrent_liabilities_cny": "一年内到期的非流动负债",
    "bonds_payable_cny": "应付债券",
    "lease_liabilities_cny": "租赁负债",
    "other_current_liabilities_cny": "其他流动负债",
}
_EXTRA_CASH = {"customer_cash_cny": "销售商品、提供劳务收到的现金",
               "supplier_cash_cny": "购买商品、接受劳务支付的现金",
               "borrowings_received_cny": "取得借款收到的现金",
               "debt_repayments_paid_cny": "偿还债务支付的现金"}


def _fact(value, comparative, page, excerpt, source, period, field, *, balance=False):
    ref = dict(path=source["path"], sha256=source["sha256"],
               available_at=source["available_at"], physical_page=page,
               excerpt=excerpt, field=field, current_period=period,
               comparative_period=(f"{int(period[:4])-1}-12-31" if balance
                                   else f"{int(period[:4])-1}{period[4:]}"))
    return dict(current=value, comparative=comparative, physical_page=page,
                excerpt=excerpt, classification="FACT", scope=prior.SCOPE,
                currency="CNY", source_refs=ref)


def _one_printed_amount_columns(original, page, label, printed):
    """Locate a sole printed amount in the actual PDF table, never fill its blank peer.

    PDFium text preserves the row label and amount but loses empty column
    positions. The table geometry supplies that position only when the amount
    uniquely identifies one three-column row on this physical page.
    """
    import pdfplumber

    matches = []
    with pdfplumber.open(original) as pdf:
        for table in pdf.pages[page - 1].extract_tables():
            for row in table:
                if (not row or len(row) != 3 or not isinstance(row[0], str)
                        or re.sub(r"\s+", "", row[0]) != re.sub(r"\s+", "", label)):
                    continue
                current = (row[1] or "").replace(",", "").strip()
                comparative = (row[2] or "").replace(",", "").strip()
                if current == printed and not comparative:
                    matches.append((printed, None))
                elif comparative == printed and not current:
                    matches.append((None, printed))
    if len(matches) != 1:
        raise ValueError("OWNER_CASH_V2_SINGLE_AMOUNT_COLUMN_AMBIGUOUS")
    return matches[0]


def _parent_fx_row(original, first_page, last_page, expected):
    """Recover the wrapped signed FX line from the numbered parent cash table."""
    import pdfplumber

    label = "四、汇率变动对现金及现金等价物的影响"
    matches = []
    with pdfplumber.open(original) as pdf:
        for index in range(first_page - 1, last_page):
            for table in pdf.pages[index].extract_tables():
                for row in table:
                    if (row and len(row) == 3 and isinstance(row[0], str)
                            and re.sub(r"\s+", "", row[0]) == label):
                        amounts = [(value or "").replace(",", "").strip()
                                   for value in row[1:]]
                        if (all(re.fullmatch(r"-?[0-9]+\.[0-9]{2}", value)
                                for value in amounts)
                                and [Decimal(value) for value in amounts] == expected):
                            matches.append((index + 1, row[0].replace("\n", " "), amounts))
    if len(matches) != 1:
        raise ValueError("OWNER_CASH_V2_PARENT_FX_ROW_AMBIGUOUS")
    return matches[0]


def _numbered_ordinary_shares(root, statement, issuer, evaluated_at):
    """Reconcile a split annual share table with the dated report narrative.

    This deliberately covers one explicit table layout. A different layout
    yields no share proof rather than converting CNY share capital into shares.
    """
    source = statement["source_binding"]
    path, _ = prior._bound(root, source)
    pages = extract_pages(path)
    if statement["period_basis"] != "FY":
        return None
    year = statement["period_end"][:4]
    starts = [i for i, text in enumerate(pages)
              if any(prior._compact(line) == "第六节股份变动及股东情况"
                     for line in text.splitlines())]
    if len(starts) != 1:
        return None
    try:
        import pdfplumber
    except ImportError as error:
        raise ValueError("OWNER_CASH_V2_TABLE_READER_UNAVAILABLE") from error
    labels = {"一、有限售条件股份": "restricted",
              "二、无限售条件股份": "unrestricted",
              "1、人民币普通股": "rmb_ordinary",
              "三、股份总数": "total"}
    rows = {}
    with pdfplumber.open(path) as pdf:
        for index in (starts[0], starts[0] + 1):
            if index >= len(pdf.pages):
                continue
            for table in pdf.pages[index].extract_tables():
                for row in table:
                    if not row or not row[0]:
                        continue
                    label = re.sub(r"\s+", "", row[0])
                    if label not in labels:
                        continue
                    if label in rows or len(row) <= 8 or not row[8]:
                        raise ValueError("OWNER_CASH_V2_SHARE_TABLE_AMBIGUOUS")
                    raw = re.sub(r"\s+", "", row[8])
                    if not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+", raw):
                        raise ValueError("OWNER_CASH_V2_SHARE_TABLE_AMOUNT_INVALID")
                    rows[label] = (int(raw.replace(",", "")), index + 1, label + " " + raw)
    if set(rows) != set(labels):
        return None
    restricted, unrestricted, ordinary, total = (rows[key][0] for key in labels)
    if restricted + unrestricted != total or ordinary != unrestricted:
        raise ValueError("OWNER_CASH_V2_SHARE_TABLE_RECONCILIATION_CHANGED")
    no_preferred = [(i, line.strip()) for i, text in enumerate(pages, 1)
                    for line in text.splitlines()
                    if prior._compact(line) == "报告期公司不存在优先股。"]
    dated = []
    pattern = re.compile(r"截至" + year + r"年12月31日,公司股份总数为([0-9,]+)股")
    for i, text in enumerate(pages, 1):
        for line in text.splitlines():
            compact = prior._compact(line)
            match = pattern.search(compact)
            if match:
                dated.append((i, line.strip(), int(match.group(1).replace(",", ""))))
    if len(no_preferred) != 1 or len(dated) != 1:
        return None
    capital = statement["balance_sheet"].get("share_capital_cny")
    if (dated[0][2] != total or capital is None
            or Decimal(capital["current"]) != Decimal(total)):
        raise ValueError("OWNER_CASH_V2_DATED_SHARE_COUNT_CONFLICT")
    prior._bound(root, source)
    return dict(classification="DERIVED_FACT", period_end=statement["period_end"],
                unit="shares", scope="TOTAL_ISSUED_ORDINARY_SHARES",
                count=str(total), treasury_excluded=False,
                derivation="ANNUAL_SHARE_TABLE_AND_DATED_TOTAL_NO_PREFERRED",
                source_refs=[
                    dict(source, physical_page=rows[key][1], excerpt=rows[key][2])
                    for key in ("一、有限售条件股份", "二、无限售条件股份",
                                "1、人民币普通股", "三、股份总数")
                ] + [dict(source, physical_page=no_preferred[0][0],
                          excerpt=no_preferred[0][1]),
                     dict(source, physical_page=dated[0][0], excerpt=dated[0][1]),
                     capital["source_refs"]])


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
    lines = [(page, line.strip()) for page, text in enumerate(pages, 1)
             for line in text.splitlines()]
    balance_starts = [i for i, (_, line) in enumerate(lines)
                      if re.fullmatch(r"2[、．.]\s*母公司资产负债表", line)]
    balance_ends = [i for i, (_, line) in enumerate(lines)
                    if re.fullmatch(r"3[、．.]\s*合并利润表", line)]
    if (len(balance_starts) != 1 or len(balance_ends) != 1
            or balance_starts[0] >= balance_ends[0]):
        raise ValueError("OWNER_CASH_V2_BALANCE_TABLE_INVALID")
    for field, label in _EXTRA_BALANCE.items():
        matches = [(page, line) for page, line in
                   lines[balance_starts[0]:balance_ends[0]]
                   if line == label or line.startswith(label + " ")]
        if len(matches) != 1:
            gaps.append(dict(table="balance", field=field,
                             reason="ROW_NOT_UNIQUE", value=None))
            continue
        page, line = matches[0]
        values = AMOUNT.findall(line[len(label):])
        if not values or len(values) > 2 or not line.endswith(values[-1]):
            gaps.append(dict(table="balance", field=field,
                             reason="TWO_PRINTED_VALUES_REQUIRED", value=None))
            continue
        columns = (tuple(value.replace(",", "") for value in values)
                   if len(values) == 2 else
                   _one_printed_amount_columns(original, page, label, values[0].replace(",", "")))
        balance[field] = _fact(*columns,
                               page, line, source, period, field, balance=True)
        if len(values) == 1:
            gaps.append(dict(table="balance", field=field,
                             reason="COMPARATIVE_CELL_BLANK" if columns[0] is not None
                             else "CURRENT_CELL_BLANK", value=None))
    balance_check = all(field in balance for field in (
        "assets_cny", "liabilities_cny", "book_equity_cny"))
    if balance_check:
        for column in ("current", "comparative"):
            if (Decimal(balance["assets_cny"][column])
                    != Decimal(balance["liabilities_cny"][column])
                    + Decimal(balance["book_equity_cny"][column])):
                raise ValueError("OWNER_CASH_V2_BALANCE_EQUATION_CHANGED")
    for row in income_result["evidence"]:
        field = "parent_net_profit_cny"
        printed = AMOUNT.findall(row["text"])
        if len(printed) != 2 or row["value"] != printed[0].replace(",", ""):
            raise ValueError("OWNER_CASH_V2_INCOME_ROW_CHANGED")
        income[field] = _fact(row["value"], printed[1].replace(",", ""), row["physical_page"], row["text"],
                              source, period, field)
    for gap in income_result["gaps"]:
        gaps.append(dict(table="income", field=None, reason=gap, value=None))
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
    interest = [(page, line) for page, line in
                lines[income_starts[0]:income_ends[0]]
                if line.startswith("其中：利息费用 ")]
    if len(interest) == 1:
        page, line = interest[0]
        values = AMOUNT.findall(line[len("其中：利息费用"):])
        if len(values) == 2 and line.endswith(values[-1]):
            income["interest_expense_cny"] = _fact(
                *(v.replace(",", "") for v in values), page, line,
                source, period, "interest_expense_cny")
        else:
            gaps.append(dict(table="income", field="interest_expense_cny",
                             reason="TWO_PRINTED_VALUES_REQUIRED", value=None))
    else:
        gaps.append(dict(table="income", field="interest_expense_cny",
                         reason="ROW_NOT_UNIQUE", value=None))
    for field, row in cash["rows"].items():
        flows[field] = _fact(row["columns"][0]["value"], row["columns"][1]["value"],
                             row["physical_page"], row["evidence_excerpt"], source, period, field)
    # Additional operating receipts retain the same numbered-table ownership.
    starts = [i for i, (_, line) in enumerate(lines) if prior._compact(line) == "6、母公司现金流量表"]
    ends = [i for i, (_, line) in enumerate(lines) if prior._compact(line) == "7、合并所有者权益变动表"]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("OWNER_CASH_V2_PARENT_TABLE_INVALID")
    if "fx_cny" in cash["unknown_fields"]:
        expected_fx = [Decimal(flows["reported_net_change_cny"][column])
                       - sum(Decimal(flows[field][column]) for field in (
                           "cfo_cny", "cfi_cny", "cff_cny"))
                       for column in ("current", "comparative")]
        page, label, amounts = _parent_fx_row(original, lines[starts[0]][0],
                                              lines[ends[0]][0], expected_fx)
        flows["fx_cny"] = _fact(*amounts, page, label + " " + " ".join(amounts),
                                source, period, "fx_cny")
    for field in cash["unknown_fields"]:
        if field not in _EXTRA_CASH and field not in flows:
            gaps.append(dict(table="cash_flow", field=field,
                             reason="ROW_NOT_UNAMBIGUOUS", value=None))
    for field, label in _EXTRA_CASH.items():
        if field in flows:
            continue
        matches = [(page, line) for page, line in lines[starts[0]:ends[0]]
                   if prior._compact(line).startswith(prior._compact(label))]
        if len(matches) != 1:
            gaps.append(dict(table="cash_flow", field=field, reason="ROW_NOT_UNIQUE", value=None))
            continue
        page, line = matches[0]
        values = prior.MONEY.findall(line[len(label):])
        if not values or len(values) > 2:
            gaps.append(dict(table="cash_flow", field=field, reason="TWO_PRINTED_VALUES_REQUIRED", value=None))
            continue
        columns = (tuple(value.replace(",", "") for value in values)
                   if len(values) == 2 else
                   _one_printed_amount_columns(original, page, label, values[0].replace(",", "")))
        flows[field] = _fact(*columns, page, line,
                             source, period, field)
        if len(values) == 1:
            gaps.append(dict(table="cash_flow", field=field,
                             reason="COMPARATIVE_CELL_BLANK" if columns[0] is not None
                             else "CURRENT_CELL_BLANK", value=None))
    cash_check = all(field in flows for field in (
        "cfo_cny", "cfi_cny", "cff_cny", "fx_cny", "reported_net_change_cny",
        "opening_cash_and_equivalents_cny", "closing_cash_and_equivalents_cny"))
    if cash_check:
        for column in ("current", "comparative"):
            if (sum(Decimal(flows[field][column]) for field in (
                    "cfo_cny", "cfi_cny", "cff_cny", "fx_cny"))
                    != Decimal(flows["reported_net_change_cny"][column])
                    or Decimal(flows["opening_cash_and_equivalents_cny"][column])
                    + Decimal(flows["reported_net_change_cny"][column])
                    != Decimal(flows["closing_cash_and_equivalents_cny"][column])):
                raise ValueError("OWNER_CASH_V2_PARENT_CASH_EQUATION_CHANGED")
    if sha256_file(original) != source["sha256"]:
        raise ValueError("OWNER_CASH_V2_ORIGINAL_CHANGED")
    year = day.year
    return dict(symbol=symbol, issuer_name=issuer_name, scope=prior.SCOPE, currency="CNY",
        classification="FACT", period_start=f"{year}-01-01", period_end=period,
        period_basis="FY" if day.month == 12 else "H1",
        opening_balance_as_of=f"{year-1}-12-31",
        comparative_flow_start=f"{year-1}-01-01",
        comparative_flow_end=f"{year-1}{period[4:]}", source_binding=reference,
        balance_sheet=balance, income=income, cash_flow=flows, gaps=gaps,
        checks=dict(cash_statement_reconciled=cash_check,
                    balance_equation_reconciled=balance_check))


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
    for statement in statements:
        statement["ordinary_shares_evidence"] = _numbered_ordinary_shares(
            root, statement, issuer_name, evaluated_at)
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

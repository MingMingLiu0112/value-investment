"""Read-only parent owner-cash bridge evidence; no owner-cash calculation.

Explicit caller-pinned retained sources only. FY/H1 cash rows reuse the strict
parent reader; nine-month cash cross-checks reuse the quarterly parent reader.
Book debt is not dated repayment, investment receipts are not all dividends,
and parent equity/retained earnings are not legal distribution capacity.
"""
from datetime import date, datetime
from decimal import Decimal, localcontext
import json
import re
from pathlib import Path

from . import parent_cash_research as cash_reader
from .parent_direct_cash_research import _bound, _clock, _unique
from .agent_review.parent_cash_constraint_evidence import replay_parent_cash_constraint_evidence
from .agent_review.parent_fund_evidence import replay_parent_fund_evidence
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.stock_identity_table_v1 import labelled_security_codes
from ...infrastructure.filings.quarterly_parent_cash_facts import parse_quarterly_parent_cash_facts
from ...infrastructure.filings.native_capital_observation_v1 import _compact

VERSION = "parent-direct-owner-cash-sources-v1"
SCOPE = "ISSUER_PARENT_STANDALONE"
MONEY = re.compile(r"(?<![\d,.])-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}(?![\d,.])")
BALANCE = {
    "monetary_funds_cny": "货币资金",
    "book_equity_cny": "所有者权益（或股东权益）合计",
    "share_capital_cny": "实收资本（或股本）",
    "surplus_reserve_cny": "盈余公积", "retained_earnings_cny": "未分配利润",
    "short_term_borrowings_cny": "短期借款", "long_term_borrowings_cny": "长期借款",
    "current_noncurrent_liabilities_cny": "一年内到期的非流动负债",
    "bonds_payable_cny": "应付债券", "lease_liabilities_cny": "租赁负债",
    "other_current_liabilities_cny": "其他流动负债",
    "assets_cny": "资产总计", "liabilities_cny": "负债合计",
}
EXTRA_CASH = {
    "investment_recovery_cash_cny": "收回投资收到的现金",
    "investment_paid_cny": "投资支付的现金",
    "acquisitions_cash_cny": "取得子公司及其他营业单位支付的现金净额",
}
TITLES = {"母公司资产负债表", "合并资产负债表", "母公司利润表", "合并利润表",
          "母公司现金流量表", "合并现金流量表", "母公司所有者权益变动表", "合并所有者权益变动表"}


def _fail(reason):
    raise ValueError("OWNER_CASH_SOURCE_" + reason)


def _statement(pages, title, issuer, period):
    """Authenticate and bound one table, retaining physical pages for each row."""
    year = int(period[:4])
    month = int(period[5:7])
    suffix = {12: "年度", 6: "半年度", 9: "第三季度"}[month]
    report_header = _compact(issuer) + f"{year}年{suffix}报告"
    starts = [(i, j) for i, page in enumerate(pages) for j, line in enumerate(page.splitlines())
              if _compact(line) == title]
    if len(starts) != 1:
        _fail("PARENT_TABLE_NOT_UNIQUE:" + title)
    page_index, line_index = starts[0]
    first_lines = [line for line in pages[page_index].splitlines() if line.strip()]
    if not first_lines or _compact(first_lines[0]) != report_header:
        _fail("TABLE_ISSUER_OR_REPORT_CHANGED")
    selected, ended = [], False
    for index in range(page_index, min(page_index + 4, len(pages))):
        lines = pages[index].splitlines()
        if index > page_index:
            nonempty = [line for line in lines if line.strip()]
            if not nonempty or _compact(nonempty[0]) != report_header:
                _fail("CONTINUATION_ISSUER_CHANGED")
        for line in lines[line_index + 1 if index == page_index else 0:]:
            text = _compact(line)
            if text in TITLES or re.match(r"^(?:公司负责人|法定代表人|主管会计工作负责人|会计机构负责人):", text):
                ended = True
                break
            if line.strip():
                selected.append((index + 1, line.strip()))
        if ended:
            break
    if not ended:
        _fail("TABLE_END_REQUIRED:" + title)
    header = "".join(_compact(line) for _, line in selected[:7])
    current = date.fromisoformat(period)
    if title == "母公司资产负债表":
        columns = f"{year}年{month}月{current.day}日{year-1}年12月31日"
        if "编制单位:" + _compact(issuer) not in header:
            _fail("BALANCE_COMPILER_CHANGED")
    else:
        columns = (f"{year}年度{year-1}年度" if month == 12 else
                   f"{year}年半年度{year-1}年半年度" if month == 6 else
                   f"{year}年前三季度(1-9月){year-1}年前三季度(1-9月)")
        if not re.search(fr"{year}年1[—－–-]{month}月", header):
            _fail("FLOW_PERIOD_CHANGED")
    if ("单位:元币种:人民币" not in header
            or not any(_compact(line) in {"项目" + columns, "项目附注" + columns}
                       for _, line in selected[:7])
            or "调整前" in header or "调整后" in header):
        _fail("UNIT_OR_PERIOD_COLUMNS_CHANGED")
    for _, line in selected:
        text = _compact(line)
        if "单位:万元" in text or "币种:美元" in text:
            _fail("CONTINUATION_UNIT_CHANGED")
    return selected


def _row(segments, label, *, prefix=False):
    found = [(p, line) for p, line in segments if
             (line.startswith(label) if prefix else line.split(maxsplit=1)[:1] == [label])]
    if len(found) != 1:
        return None, "ROW_MISSING_OR_AMBIGUOUS"
    page, line = found[0]
    amounts = MONEY.findall(line)
    if len(amounts) != 2 or not line.endswith(amounts[-1]):
        return None, "TWO_PRINTED_COLUMNS_NOT_PROVEN"
    return dict(current=str(Decimal(amounts[0].replace(",", ""))),
                comparative=str(Decimal(amounts[1].replace(",", ""))),
                physical_page=page, excerpt=line), None


def _source_refs(source, field, row, period, balance=False):
    year = int(period[:4])
    return dict(path=source["path"], sha256=source["sha256"], available_at=source["available_at"],
                physical_page=row["physical_page"], excerpt=row["excerpt"], field=field,
                current_period=period, comparative_period=f"{year-1}-12-31" if balance else f"{year-1}{period[4:]}")


def _read_statement(root, symbol, issuer, source, evaluated_at):
    if not isinstance(source, dict) or set(source) != {"path", "sha256", "period_end", "available_at"}:
        _fail("EXPLICIT_STATEMENT_BINDING_REQUIRED")
    period = source["period_end"]
    day = date.fromisoformat(period)
    if day.isoformat() != period or period[4:] not in {"-12-31", "-06-30", "-09-30"}:
        _fail("SUPPORTED_PERIOD_REQUIRED")
    available = _clock(source["available_at"], evaluated_at)
    if day > available.date():
        _fail("REPORT_AFTER_SOURCE_AVAILABILITY")
    path, _ = _bound(root, source)
    pages = extract_pages(path)
    _bound(root, source)
    if labelled_security_codes(pages[:8], symbol=symbol) != {symbol}:
        _fail("SECURITY_IDENTITY_CHANGED")
    tables = {name: _statement(pages, name, issuer, period) for name in
              ("母公司资产负债表", "母公司利润表", "母公司现金流量表")}
    year = day.year
    gaps, balance, income, flows = [], {}, {}, {}

    def add(target, field, row, gap, kind):
        if row is None:
            gaps.append(dict(field=field, table=kind, reason=gap, value=None))
        else:
            target[field] = dict(row, classification="FACT", scope=SCOPE, currency="CNY",
                                 source_refs=_source_refs(source, field, row, period, kind == "balance"))

    for field, label in BALANCE.items():
        row, gap = _row(tables["母公司资产负债表"], label)
        add(balance, field, row, gap, "balance")
    row, gap = _row(tables["母公司利润表"], "四、净利润", prefix=True)
    add(income, "parent_net_profit_cny", row, gap, "income")
    for field, label in (("revenue", "一、营业收入"), ("cost", "减：营业成本"),
                         ("interest_expense_cny", "其中：利息费用")):
        row, gap = _row(tables["母公司利润表"], label)
        add(income, field, row, gap, "income")
    if "interest_expense_cny" in income:
        income["interest_expense_cny"].update(accounting_basis="ACCRUAL", establishes_cash_interest_paid=False)
    if day.month in {6, 12}:
        periods = cash_reader._period_pair(period)
        spec = dict(symbol=symbol, issuer=issuer, periods=list(periods),
                    column_labels=cash_reader._column_labels(periods))
        for field in cash_reader.LABELS:
            try:
                parsed = cash_reader.extract_parent_cash_statement(
                    pages=pages, spec=spec, observation_fields={field})["rows"][field]
                row = dict(current=parsed["columns"][0]["value"], comparative=parsed["columns"][1]["value"],
                           physical_page=parsed["physical_page"], excerpt=parsed["evidence_excerpt"])
                add(flows, field, row, None, "cash_flow")
            except ValueError as error:
                if str(error) not in {"PARENT_CASH_TWO_PRINTED_VALUES_REQUIRED:" + field,
                                      "PARENT_CASH_ROW_MISSING_OR_AMBIGUOUS:" + field}:
                    raise
                add(flows, field, None, str(error), "cash_flow")
    else:
        # The existing Q3 parser independently authenticates its cover and cash
        # table. Additional financing/balance rows remain in the bounded table.
        quarter = parse_quarterly_parent_cash_facts(pages, symbol=symbol, issuer_name=issuer, period_end=period)
        for field, label in cash_reader.LABELS.items():
            candidates = [(p, re.sub(r"^(?:[一二三四五六]、|加[:：])", "", line))
                          for p, line in tables["母公司现金流量表"]]
            row, gap = _row(candidates, label)
            add(flows, field, row, gap, "cash_flow")
        for old, new in (("cfo", "cfo_cny"), ("cash_capex", "gross_capex_cny"),
                         ("investment_income_cash_cny", "investment_income_cash_cny")):
            if new not in flows or any(flows[new][col] != quarter["fields"][old][col] for col in ("current", "comparative")):
                _fail("QUARTER_CROSSCHECK_CHANGED")
    for field, label in EXTRA_CASH.items():
        row, gap = _row(tables["母公司现金流量表"], label)
        add(flows, field, row, gap, "cash_flow")
    cash_keys = ("cfo_cny", "cfi_cny", "cff_cny", "fx_cny", "reported_net_change_cny",
                 "opening_cash_and_equivalents_cny", "closing_cash_and_equivalents_cny")
    checks = dict(cash_statement_reconciled=False, balance_equation_reconciled=False)
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        if all(key in flows for key in cash_keys):
            for col in ("current", "comparative"):
                v = {k: Decimal(flows[k][col]) for k in cash_keys}
                net = sum(v[k] for k in cash_keys[:4])
                if (net != v["reported_net_change_cny"] or
                        v["opening_cash_and_equivalents_cny"] + net != v["closing_cash_and_equivalents_cny"]):
                    _fail("CASH_RECONCILIATION_CHANGED")
            checks["cash_statement_reconciled"] = True
        if all(k in balance for k in ("assets_cny", "liabilities_cny", "book_equity_cny")):
            for col in ("current", "comparative"):
                if Decimal(balance["assets_cny"][col]) != Decimal(balance["liabilities_cny"][col]) + Decimal(balance["book_equity_cny"][col]):
                    _fail("BALANCE_EQUATION_CHANGED")
            checks["balance_equation_reconciled"] = True
    return dict(symbol=symbol, issuer_name=issuer, scope=SCOPE, currency="CNY", classification="FACT",
                period_start=f"{year}-01-01", period_end=period,
                period_basis={12: "FY", 6: "H1", 9: "YTD_9M"}[day.month],
                opening_balance_as_of=f"{year-1}-12-31", comparative_flow_start=f"{year-1}-01-01",
                comparative_flow_end=f"{year-1}{period[4:]}", source_binding=dict(source),
                balance_sheet=balance, income=income, cash_flow=flows, gaps=gaps, checks=checks)


def _constraints(root, binding, symbol, issuer, evaluated_at):
    _, raw = _bound(root, binding)
    packet = json.loads(raw, object_pairs_hook=_unique)
    # Reuse the existing hash/row/maturity replay, but explicitly discard its
    # parent-labelled reserve narrative: the cited note is not a parent table.
    replayed = replay_parent_cash_constraint_evidence(root=root, binding=binding, symbol=symbol, now=evaluated_at)
    originals = {}
    for key in ("charter", "financing_source"):
        source = packet[key]
        _clock(source["available_at"], evaluated_at)
        path, _ = _bound(root, source)
        pages = extract_pages(path)
        _bound(root, source)
        if _compact(issuer) not in _compact("".join(pages[:3])):
            _fail("CONSTRAINT_ISSUER_CHANGED")
        if key == "financing_source" and labelled_security_codes(pages[:3], symbol=symbol) != {symbol}:
            _fail("CONSTRAINT_SECURITY_CHANGED")
        originals[key] = pages
    rules = []
    rule_labels = {
        "statutory_reserve_rule": ("第一百五十五条", "第一百五十六条"),
        "cash_distribution_conditions": ("1、实施现金分配条件", "2、利润分配期间间隔"),
    }
    for field, (start, end) in rule_labels.items():
        found = [(i + 1, page) for i, page in enumerate(originals["charter"])
                 if _compact(start) in _compact(page) and _compact(end) in _compact(page)]
        if len(found) != 1:
            _fail("CHARTER_RULE_NOT_UNIQUE")
        page, text = found[0]
        compact = _compact(text)
        excerpt = compact[compact.index(_compact(start)):compact.index(_compact(end))]
        rules.append(dict(field=field, scope="ISSUER_ARTICLES_RULE_TEXT", classification="FACT",
                          text=excerpt, source_refs=dict(packet["charter"], physical_page=page),
                          establishes_future_appropriation=False, establishes_distribution_capacity=False))
    financing = []
    for item in packet["issuer_financing"]:
        candidates = [r for r in replayed if r["scope"] == "ISSUER_FINANCING_DISCLOSURE" and r["id"].endswith(":" + item["code"])]
        if len(candidates) != 1:
            _fail("FINANCING_REPLAY_MISSING")
        financing.append(dict(item, classification="FACT", scope="ISSUER_FINANCING_DISCLOSURE", currency="CNY",
                              issue_date=candidates[0]["period"], source_refs=dict(packet["financing_source"], physical_page=item["physical_page"]),
                              actual_settlement_verified=False, refinancing_verified=False,
                              outstanding_at_evaluation_cny=None))
    return dict(receipt_binding=binding, charter_rules=rules, issued_financing=financing,
                excluded_parent_claims=[dict(field="statutory_surplus_reserve_cny", value=None,
                    reason="RESERVE_NOTE_NOT_ADMITTED_AS_PARENT_COMPONENT; matching parent total is not statutory-component proof",
                    source_refs=dict(path=packet["legal_reserve"]["fy_pdf"], sha256=packet["legal_reserve"]["fy_pdf_sha256"],
                                     physical_page=packet["legal_reserve"]["fy_page"]))])


def _ordinary_shares(root, statement, charter, issuer, evaluated_at):
    """A report-end share table plus explicit ordinary-class evidence, not CNY capital."""
    source = statement["source_binding"]
    path, _ = _bound(root, source)
    pages = extract_pages(path)
    _bound(root, source)
    integer = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
    pattern = re.compile(r"^三、股份总数\s+(" + integer + r")\s+100(?:\.00)?\s+(-?" + integer
                         + r")\s+(-?" + integer + r")\s+(" + integer + r")\s+100(?:\.00)?$")
    found = []
    for page, text in enumerate(pages, 1):
        compact = _compact(text)
        if not all(label in compact for label in ("股份变动情况表", "单位:股", "本次变动前", "本次变动增减", "本次变动后")):
            continue
        if _compact(issuer) not in compact or str(statement["period_end"][:4]) + "年年度报告" not in compact:
            continue
        for line in text.splitlines():
            match = pattern.fullmatch(line.strip())
            if match:
                opening, change, subtotal, closing = [int(v.replace(",", "")) for v in match.groups()]
                if change != subtotal or opening + subtotal != closing or closing <= 0:
                    _fail("SHARE_TABLE_RECONCILIATION_CHANGED")
                found.append((page, line.strip(), closing))
    if not found:
        return None
    if len(found) != 1:
        _fail("SHARE_TABLE_NOT_UNIQUE")
    if charter is None:
        return None
    _clock(charter["available_at"], evaluated_at)
    path, _ = _bound(root, charter)
    articles = extract_pages(path)
    _bound(root, charter)
    if _compact(issuer) not in _compact("".join(articles[:3])):
        _fail("SHARE_CHARTER_ISSUER_CHANGED")
    classes = [(p, m.group(0), int(m.group(1).replace(",", "")))
               for p, text in enumerate(articles, 1)
               for m in re.finditer(r"公司已发行的股份数为(" + integer + r")股,均为普通股。", _compact(text))]
    if len(classes) != 1 or classes[0][2] != found[0][2]:
        _fail("ORDINARY_SHARE_CLASS_OR_COUNT_NOT_PROVEN")
    page, excerpt, count = found[0]
    class_page, class_excerpt, _ = classes[0]
    return dict(classification="FACT", period_end=statement["period_end"], unit="shares",
                scope="TOTAL_ISSUED_ORDINARY_SHARES", count=str(count),
                source_refs=[dict(source, physical_page=page, excerpt=excerpt),
                             dict(charter, physical_page=class_page, excerpt=class_excerpt)],
                treasury_excluded=False)


def read_parent_direct_owner_cash_sources(*, root, symbol, issuer_name, sources,
                                         evaluated_at, constraint_binding=None, fund_selection=None):
    """Replay explicit {path, sha256, period_end, available_at} source entries.

    current/comparative balance columns are closing/prior-calendar-year closing;
    flow columns are current/prior same-length YTD, never successive quarters.
    available_at must be the caller's retained acquisition binding, not a guessed
    publication clock. No acquisition, persistence or model invocation occurs.
    """
    if (not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None
            or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
            or not isinstance(issuer_name, str) or not issuer_name.strip() or not sources):
        _fail("IDENTITY_SOURCES_AND_AWARE_CLOCK_REQUIRED")
    root = Path(root).resolve()
    statements = [_read_statement(root, symbol, issuer_name, s, evaluated_at) for s in sources]
    if len({s["period_end"] for s in statements}) != len(statements):
        _fail("DUPLICATE_PERIOD")
    statements.sort(key=lambda s: s["period_end"])
    for prior in statements:
        for following in statements:
            if prior["period_end"] != following["opening_balance_as_of"]:
                continue
            for field in prior["balance_sheet"].keys() & following["balance_sheet"].keys():
                if prior["balance_sheet"][field]["current"] != following["balance_sheet"][field]["comparative"]:
                    _fail("BALANCE_CONTINUITY_CHANGED:" + field)
            end = prior["cash_flow"].get("closing_cash_and_equivalents_cny")
            begin = following["cash_flow"].get("opening_cash_and_equivalents_cny")
            if end and begin and end["current"] != begin["current"]:
                _fail("CASH_CONTINUITY_CHANGED")
    constraints = (_constraints(root, constraint_binding, symbol, issuer_name, evaluated_at)
                   if constraint_binding is not None else None)
    charter = None
    if constraint_binding is not None:
        _, raw = _bound(root, constraint_binding)
        charter = json.loads(raw, object_pairs_hook=_unique)["charter"]
    for statement in statements:
        statement["ordinary_shares_evidence"] = (_ordinary_shares(root, statement, charter, issuer_name, evaluated_at)
                                                 if statement["period_basis"] == "FY" else None)
    fund = (replay_parent_fund_evidence(root=root, context=dict(symbol=symbol, issuer_name=issuer_name),
                                     selection=fund_selection, cutoff=evaluated_at)
            if fund_selection is not None else None)
    return dict(schema_version=VERSION, symbol=symbol, issuer_name=issuer_name,
                evaluated_at=evaluated_at.isoformat(), statements=statements, constraints=constraints,
                fund_commitment_evidence=fund, fund_selection=fund_selection,
                status="SOURCE_BOUND_PARENT_BRIDGE_FACTS_NOT_OWNER_CASH", action="no_order", formal_eligibility=False,
                owner_cash_cny=None, distribution_capacity_cny=None, working_capital_cash_component=None,
                unresolved=["UNRESTRICTED_CASH_AND_OPERATING_FLOOR", "PARENT_STATUTORY_RESERVE_COMPONENT_AND_FUTURE_APPROPRIATION",
                            "DISTRIBUTABLE_PROFIT_AND_APPROVAL", "FUTURE_NET_BORROWING_AND_SETTLEMENT_SCHEDULE",
                            "INTEREST_VERSUS_DIVIDEND_SPLIT", "MAINTENANCE_GROWTH_AND_COMMITMENT_OVERLAP",
                            "INVESTMENT_INCOME_CASH_RECURRING_AND_SUBSIDIARY_REMITTANCE_SPLIT",
                            "INVESTMENT_PRINCIPAL_RECYCLING_AND_REQUIRED_REINVESTMENT",
                            "UNDATED_FUND_CAPITAL_CALLS", "PARENT_TO_ORDINARY_OWNER_MAPPING"])

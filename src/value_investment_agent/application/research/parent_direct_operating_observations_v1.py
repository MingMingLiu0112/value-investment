"""Replay wrapped FY/H1 parent operating cash rows from official receipts."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from . import parent_direct_owner_cash_sources as parent
from .parent_cash_research import _receipt_issuer_query

VERSION = "parent-direct-operating-observations-v1"
_SECTION = "一、经营活动产生的现金流量:"
_END = "二、投资活动产生的现金流量:"
_FIELDS = {
    "customer_cash": "销售商品、提供劳务收到的",
    "supplier_cash": "购买商品、接受劳务支付的",
}


def _wrapped_operating_rows(table):
    segments = [(page, parent._compact(line)) for page, line in table]
    starts = [i for i, (_, line) in enumerate(segments) if line.startswith(_SECTION)]
    ends = [i for i, (_, line) in enumerate(segments) if line == _END]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("PARENT_DIRECT_OPERATING_SECTION_NOT_UNIQUE")
    start, end = starts[0], ends[0]
    result = {}
    for field, label in _FIELDS.items():
        hits = [i for i in range(start, end)
                if segments[i][1].removeprefix(_SECTION) == label]
        if len(hits) != 1 or hits[0] + 2 >= end:
            raise ValueError("PARENT_DIRECT_OPERATING_ROW_NOT_UNIQUE:" + field)
        index = hits[0]
        span = table[index:index + 3]
        if len({page for page, _ in span}) != 1 or segments[index + 1][1] != "现金":
            raise ValueError("PARENT_DIRECT_OPERATING_ROW_BOUNDARY:" + field)
        values = span[2][1].split()
        if len(values) != 2 or not all(re.fullmatch(parent.MONEY, value) for value in values):
            raise ValueError("PARENT_DIRECT_OPERATING_TWO_COLUMNS_REQUIRED:" + field)
        result[field] = dict(
            current=values[0].replace(",", ""), comparative=values[1].replace(",", ""),
            physical_page=span[0][0], excerpt="\n".join(line for _, line in span),
        )
    return result


def _other_cash(cash, column):
    """Separate observed non-trade cash without assigning its economic nature."""
    values = {name: Decimal(row[column]) for name, row in cash.items()}
    receipts = values["inflow"] - values["customer_cash"]
    payments = values["outflow"] - values["supplier_cash"]
    if min(values.values()) < 0 or min(receipts, payments) < 0:
        raise ValueError("PARENT_DIRECT_OPERATING_TRADE_ROWS_EXCEED_SUBTOTAL")
    return dict(
        classification="DERIVED_FACT",
        other_operating_receipts_cny=str(receipts),
        other_operating_payments_cny=str(payments),
        other_operating_net_cash_cny=str(receipts - payments),
        recurrence="UNKNOWN",
    )


def read_wrapped_parent_operating_observations(*, root, symbol, issuer_name,
                                              receipt_bindings, evaluated_at):
    """Return both printed flow columns with page provenance and exact subtotals."""
    root = Path(root).resolve()
    if evaluated_at.utcoffset() is None or not receipt_bindings:
        raise ValueError("PARENT_DIRECT_OPERATING_RECEIPTS_AND_CLOCK_REQUIRED")
    sources = []
    refs = {}
    for entry in receipt_bindings:
        period, pin = entry["period"], entry["receipt_binding"]
        if period in refs or period[4:] not in {"-06-30", "-12-31"}:
            raise ValueError("PARENT_DIRECT_OPERATING_PERIOD_INVALID")
        query = _receipt_issuer_query(root=root, receipt_binding=pin)
        packet = load_retained_official_report(
            root=root, receipt_binding=pin, symbol=symbol, issuer_name=query, period=period,
        )
        source = packet["source"]
        available = max(datetime.fromisoformat(value) for value in
                        (source["available_at"], packet["fetched_at"], packet["completed_at"]))
        sources.append(dict(path=source["path"], sha256=source["sha256"],
                            period_end=period, available_at=available.isoformat()))
        refs[period] = pin
    statements = parent.read_parent_direct_owner_cash_sources(
        root=root, symbol=symbol, issuer_name=issuer_name, sources=sources,
        evaluated_at=evaluated_at,
    )["statements"]
    observed = []
    for statement in statements:
        period = statement["period_end"]
        source = statement["source_binding"]
        path, _ = parent._bound(root, source)
        pages = parent.extract_pages(path)
        parent._bound(root, source)
        table = parent._statement(pages, "母公司现金流量表", issuer_name, period)
        cash = _wrapped_operating_rows(table)
        for field, label in (("inflow", "经营活动现金流入小计"),
                             ("outflow", "经营活动现金流出小计")):
            cash[field], _ = parent._row(table, label)
            if cash[field] is None:
                raise ValueError("PARENT_DIRECT_OPERATING_SUBTOTAL_MISSING:" + field)
        cfo = statement["cash_flow"]["cfo_cny"]
        for column in ("current", "comparative"):
            if Decimal(cash["inflow"][column]) - Decimal(cash["outflow"][column]) != Decimal(cfo[column]):
                raise ValueError("PARENT_DIRECT_OPERATING_SUBTOTAL_MISMATCH")
            current = column == "current"
            observed.append(dict(
                symbol=symbol, scope=statement["scope"], currency="CNY", classification="FACT",
                period_start=statement["period_start" if current else "comparative_flow_start"],
                period_end=period if current else statement["comparative_flow_end"],
                revenue=statement["income"]["revenue"][column],
                cost=statement["income"]["cost"][column],
                customer_cash=cash["customer_cash"][column], supplier_cash=cash["supplier_cash"][column],
                cfo=cfo[column], other_operating_cash=_other_cash(cash, column),
                source_refs=dict(
                    receipt=refs[period], column=column,
                    income={key: statement["income"][key]["source_refs"] for key in ("revenue", "cost")},
                    cfo=cfo["source_refs"],
                    cash={key: parent._source_refs(source, key, row, period) for key, row in cash.items()},
                ),
            ))
    return dict(schema_version=VERSION, observed=observed, action="no_order", formal_eligibility=False)

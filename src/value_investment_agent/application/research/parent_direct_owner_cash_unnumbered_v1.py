"""Replay official unnumbered parent statements without changing numbered receipts."""
from datetime import datetime
from decimal import Decimal
import re
from pathlib import Path

from .parent_cash_research import _receipt_issuer_query
from . import parent_direct_owner_cash_sources as parent
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report

VERSION = "UNNUMBERED_OFFICIAL_CNINFO_V1"


def _annual_share_anchor(pages, statement):
    if statement["period_basis"] != "FY":
        return None
    headings = [
        (index, text) for index, text in enumerate(pages, 1)
        if all(key in parent._compact(text) for key in (
            "第六节股份变动及股东情况", "股份变动情况表", "单位:股",
            "本次变动前", "本次变动后",
        ))
    ]
    preferred = [
        index for index, text in enumerate(pages, 1)
        if "九、优先股相关情况□适用√不适用" in parent._compact(text)
    ]
    if len(headings) != 1 or len(preferred) != 1:
        return None
    page, text = headings[0]
    if not page <= preferred[0] <= page + 8:
        return None
    amounts = r"([0-9][0-9,]*)"
    ratio = r"[0-9]+(?:\.[0-9]+)?"
    movement = r"(-?[0-9][0-9,]*)"
    patterns = {
        "restricted": rf"(?:.*比例\(%\)\s+)?一、有限售条件股份\s+{amounts}\s+{ratio}\s+{amounts}\s+{ratio}",
        "unrestricted": rf"二、无限售条件流通股份\s+{amounts}\s+{ratio}\s+{movement}\s+{movement}\s+{amounts}\s+{ratio}",
        "ordinary": rf"1、人民币普通股\s+{amounts}\s+{ratio}\s+{movement}\s+{movement}\s+{amounts}\s+{ratio}",
        "total": rf"三、股份总数\s+{amounts}\s+100\s+{movement}\s+{movement}\s+{amounts}\s+100",
    }
    rows = {}
    refs = []
    source = statement["source_binding"]
    for key, pattern in patterns.items():
        matches = [(line, match) for line in text.splitlines()
                   if (match := re.fullmatch(pattern, line.strip()))]
        if len(matches) != 1:
            return None
        line, match = matches[0]
        rows[key] = [int(value.replace(",", "")) for value in match.groups()]
        refs.append(dict(source, physical_page=page, excerpt=line.strip()))
    start, change, subtotal, closing = rows["total"]
    restricted_start, restricted_end = rows["restricted"]
    unrestricted_start, unrestricted_change, unrestricted_subtotal, unrestricted_end = rows["unrestricted"]
    capital = statement["balance_sheet"].get("share_capital_cny")
    if (rows["ordinary"] != rows["unrestricted"] or change != subtotal
            or unrestricted_change != unrestricted_subtotal
            or unrestricted_start + unrestricted_subtotal != unrestricted_end
            or restricted_start + unrestricted_start != start or start + subtotal != closing
            or restricted_end + unrestricted_end != closing or closing <= 0
            or capital is None or Decimal(capital["current"]) != Decimal(closing)):
        raise ValueError("UNNUMBERED_PARENT_ANNUAL_SHARE_RECONCILIATION_CHANGED")
    refs.append(dict(source, physical_page=preferred[0], excerpt="九、优先股相关情况：不适用"))
    refs.append(capital["source_refs"])
    return dict(classification="DERIVED_FACT", period_end=statement["period_end"],
                unit="shares", scope="TOTAL_ISSUED_ORDINARY_SHARES", count=str(closing),
                derivation="ANNUAL_SHARE_TABLE_AND_NO_PREFERRED",
                treasury_excluded=False, source_refs=refs)


def read_unnumbered_parent_cash(*, root, symbol, issuer_name, sources, evaluated_at,
                                constraint_binding=None, fund_selection=None):
    if not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None or not sources:
        raise ValueError("UNNUMBERED_PARENT_AWARE_CLOCK_AND_RECEIPTS_REQUIRED")
    root = Path(root).resolve()
    originals = []
    for row in sources:
        if (not isinstance(row, dict) or set(row) != {"period_end", "receipt_binding"}
                or not isinstance(row["period_end"], str)
                or row["period_end"][4:] not in {"-12-31", "-06-30"}):
            raise ValueError("UNNUMBERED_PARENT_SOURCE_CONTRACT_INVALID")
        pin = row["receipt_binding"]
        packet = load_retained_official_report(
            root=root, receipt_binding=pin, symbol=symbol,
            issuer_name=_receipt_issuer_query(root=root, receipt_binding=pin),
            period=row["period_end"],
        )
        if datetime.fromisoformat(packet["completed_at"]) > evaluated_at:
            raise ValueError("UNNUMBERED_PARENT_ACQUISITION_AFTER_CUTOFF")
        source = packet["source"]
        originals.append({**{key: source[key] for key in ("path", "sha256", "available_at")},
                          "period_end": row["period_end"]})
    result = parent.read_parent_direct_owner_cash_sources(
        root=root, symbol=symbol, issuer_name=issuer_name, sources=originals,
        evaluated_at=evaluated_at, constraint_binding=constraint_binding, fund_selection=fund_selection,
    )
    for statement in result["statements"]:
        if not all(statement["checks"].values()):
            raise ValueError("UNNUMBERED_PARENT_STATEMENT_NOT_RECONCILED")
        for field in ("opening_cash_and_equivalents_cny", "closing_cash_and_equivalents_cny", "cfo_cny"):
            if field not in statement["cash_flow"]:
                raise ValueError("UNNUMBERED_PARENT_REQUIRED_CASH_FACT_MISSING:" + field)
        source = statement["source_binding"]
        path, _ = parent._bound(root, source)
        pages = extract_pages(path)
        table = parent._statement(
            pages, "母公司现金流量表", issuer_name, statement["period_end"])
        parent._bound(root, source)
        if statement.get("ordinary_shares_evidence") is None:
            statement["ordinary_shares_evidence"] = _annual_share_anchor(pages, statement)
        for field, label in (
            ("customer_cash_cny", "销售商品、提供劳务收到的现金"),
            ("supplier_cash_cny", "购买商品、接受劳务支付的现金"),
        ):
            row, _ = parent._row(table, label)
            if row is None:
                raise ValueError("UNNUMBERED_PARENT_REQUIRED_CASH_FACT_MISSING:" + field)
            statement["cash_flow"][field] = {
                **row, "classification": "FACT", "scope": parent.SCOPE, "currency": "CNY",
                "source_refs": parent._source_refs(source, field, row, statement["period_end"]),
            }
    return {**result, "source_adapter_version": VERSION}

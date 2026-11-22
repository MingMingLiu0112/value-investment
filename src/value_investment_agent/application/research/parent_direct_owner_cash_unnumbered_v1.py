"""Replay official unnumbered parent statements without changing numbered receipts."""
from datetime import datetime
from pathlib import Path

from .parent_cash_research import _receipt_issuer_query
from . import parent_direct_owner_cash_sources as parent
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report

VERSION = "UNNUMBERED_OFFICIAL_CNINFO_V1"


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
        table = parent._statement(
            extract_pages(path), "母公司现金流量表", issuer_name, statement["period_end"])
        parent._bound(root, source)
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

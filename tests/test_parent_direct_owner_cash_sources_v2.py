from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
from decimal import Decimal

import pytest

from value_investment_agent.application.research.parent_direct_owner_cash_sources_v2 import (
    LAYOUT, VERSION, read_parent_direct_owner_cash_sources_v2,
)
from value_investment_agent.application.research import parent_direct_owner_cash_sources_v2 as adapter


def _sources(root):
    result = []
    for period, folder in (("2025-12-31", "fy2025"), ("2026-06-30", "h12026")):
        relative = f"runtime/value-d2-000568-20261110/{folder}/receipt.json"
        result.append(dict(period_end=period, layout=dict(LAYOUT), receipt_binding=dict(
            path=relative, sha256=hashlib.sha256((root / relative).read_bytes()).hexdigest())))
    return result


def _read(root, sources, **overrides):
    args = dict(root=root, symbol="000568", issuer_name="泸州老窖股份有限公司",
                sources=sources, evaluated_at=datetime.now(timezone.utc))
    args.update(overrides)
    return read_parent_direct_owner_cash_sources_v2(**args)


def test_real_numbered_receipts_and_fail_closed():
    root = Path(os.environ.get("VALUE_REAL_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
    if not (root / "runtime/value-d2-000568-20261110/fy2025/original.pdf").exists():
        pytest.skip("Retained official originals unavailable")
    sources = _sources(root)
    result = _read(root, sources)
    assert result["schema_version"] == VERSION
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert [s["period_end"] for s in result["statements"]] == ["2025-12-31", "2026-06-30"]
    shares = result["statements"][0]["ordinary_shares_evidence"]
    assert shares["count"] == "1471941963"
    assert shares["classification"] == "DERIVED_FACT"
    assert {ref["physical_page"] for ref in shares["source_refs"]} >= {60, 61, 67, 97}
    assert result["statements"][1]["ordinary_shares_evidence"] is None
    for statement in result["statements"]:
        assert statement["balance_sheet"]["monetary_funds_cny"]["source_refs"]["sha256"]
        for field in ("assets_cny", "liabilities_cny", "book_equity_cny",
                      "current_noncurrent_liabilities_cny", "long_term_borrowings_cny"):
            assert statement["balance_sheet"][field]["source_refs"]["physical_page"]
        assert (Decimal(statement["balance_sheet"]["assets_cny"]["current"])
                == Decimal(statement["balance_sheet"]["liabilities_cny"]["current"])
                + Decimal(statement["balance_sheet"]["book_equity_cny"]["current"]))
        assert statement["income"]["parent_net_profit_cny"]["source_refs"]["physical_page"]
        assert statement["income"]["interest_expense_cny"]["source_refs"]["physical_page"]
        assert statement["checks"]["balance_equation_reconciled"] is True
        assert statement["checks"]["cash_statement_reconciled"] is True
        assert statement["cash_flow"]["fx_cny"]["source_refs"]["physical_page"] in {46, 84}
        if statement["period_basis"] == "FY":
            assert "short_term_borrowings_cny" not in statement["balance_sheet"]
            assert statement["cash_flow"]["borrowings_received_cny"]["current"] is None
            assert statement["cash_flow"]["borrowings_received_cny"]["comparative"] == "2000000000.00"
        else:
            assert statement["balance_sheet"]["short_term_borrowings_cny"]["current"] == "3001758333.34"
            assert statement["balance_sheet"]["short_term_borrowings_cny"]["comparative"] is None
            assert statement["cash_flow"]["borrowings_received_cny"]["current"] == "3000000000.00"
            assert statement["cash_flow"]["borrowings_received_cny"]["comparative"] is None
        assert any(gap["field"] == "short_term_borrowings_cny"
                   for gap in statement["gaps"])
        assert "bonds_payable_cny" not in statement["balance_sheet"]
        assert any(gap["field"] == "bonds_payable_cny"
                   for gap in statement["gaps"])
        for field in ("revenue", "cost"):
            assert statement["income"][field]["current"]
            assert statement["income"][field]["comparative"]
        for field in ("cfo_cny", "customer_cash_cny", "supplier_cash_cny"):
            assert statement["cash_flow"][field]["source_refs"]["excerpt"]
    with pytest.raises(ValueError):
        _read(root, sources, symbol="000569")
    with pytest.raises(ValueError):
        _read(root, sources, issuer_name="另一股份有限公司")
    bad = [dict(s) for s in sources]
    bad[0]["receipt_binding"] = dict(bad[0]["receipt_binding"], sha256="0" * 64)
    with pytest.raises(ValueError):
        _read(root, bad)
    bad = [dict(s) for s in sources]
    bad[0]["period_end"] = "2024-12-31"
    with pytest.raises(ValueError):
        _read(root, bad)
    bad = [dict(s) for s in sources]
    bad[1]["layout"] = dict(LAYOUT, income="UNKNOWN")
    with pytest.raises(ValueError, match="LAYOUT_UNSUPPORTED"):
        _read(root, bad)


def test_split_share_table_requires_all_reconciliations(monkeypatch, tmp_path):
    """TEST_ONLY table fixture; the separate real-original test checks PDFium."""
    import pdfplumber

    def table_row(label, number):
        return [label] + [""] * 7 + [number]

    class Page:
        def __init__(self, rows):
            self.rows = rows

        def extract_tables(self):
            return [self.rows] if self.rows else []

    class PDF:
        def __init__(self, rows):
            self.pages = [Page([]), Page(rows[:3]), Page(rows[3:])]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    pages = [
        "报告首页",
        "第六节 股份变动及股东情况",
        "三、股份总数",
        "报告期公司不存在优先股。",
        "截至2025年12月31日，公司股份总数为10股。",
    ]
    rows = [table_row("一、有限售条件股份", "2"),
            table_row("二、无限售条件股份", "8"),
            table_row("1、人民币普通股", "8"),
            table_row("三、股份总数", "10")]
    monkeypatch.setattr(adapter.prior, "_bound", lambda *_args: (tmp_path / "source.pdf", b""))
    monkeypatch.setattr(adapter, "extract_pages", lambda *_args: pages)
    monkeypatch.setattr(pdfplumber, "open", lambda *_args: PDF(rows))
    statement = {
        "period_basis": "FY", "period_end": "2025-12-31",
        "source_binding": {"path": "runtime/source.pdf", "sha256": "a" * 64},
        "balance_sheet": {"share_capital_cny": {
            "current": "10", "source_refs": {"physical_page": 2}}},
    }
    result = adapter._numbered_ordinary_shares(
        tmp_path, statement, "TEST_ONLY", datetime.now(timezone.utc))
    assert result["count"] == "10"
    assert result["classification"] == "DERIVED_FACT"
    rows[2][8] = "7"
    with pytest.raises(ValueError, match="SHARE_TABLE_RECONCILIATION_CHANGED"):
        adapter._numbered_ordinary_shares(
            tmp_path, statement, "TEST_ONLY", datetime.now(timezone.utc))


def test_single_printed_amount_needs_unique_pdf_column(monkeypatch, tmp_path):
    import pdfplumber

    class Page:
        def __init__(self, rows):
            self.rows = rows

        def extract_tables(self):
            return [self.rows]

    class PDF:
        def __init__(self, rows):
            self.pages = [Page(rows)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    rows = [["TEST_ONLY current", "1,000.00", ""]]
    monkeypatch.setattr(pdfplumber, "open", lambda *_args: PDF(rows))
    assert adapter._one_printed_amount_columns(tmp_path / "test.pdf", 1,
                                                "TEST_ONLY current", "1000.00") == (
        "1000.00", None)
    rows[0] = ["TEST_ONLY comparative", "", "1,000.00"]
    assert adapter._one_printed_amount_columns(tmp_path / "test.pdf", 1,
                                                "TEST_ONLY comparative", "1000.00") == (
        None, "1000.00")
    rows.append(["TEST_ONLY comparative", "1,000.00", ""])
    with pytest.raises(ValueError, match="COLUMN_AMBIGUOUS"):
        adapter._one_printed_amount_columns(tmp_path / "test.pdf", 1,
                                            "TEST_ONLY comparative", "1000.00")

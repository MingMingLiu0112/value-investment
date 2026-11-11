"""Numbered parent statement: actual source replay and strict rejection checks."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os

import pytest

from value_investment_agent.application.research.parent_cash_observation_v2 import (
    extract_numbered_parent_cash_statement, replay_numbered_parent_cash_observations,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.application.research.agent_review.operating_horizon_sources_v1 import (
    build_operating_horizon_source_context,
)


ISSUER = "泸州老窖股份有限公司"
ARCHIVE = "runtime/value-d2-000568-20261110"


def test_real_numbered_parent_cash_reports():
    root_value = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if root_value is None:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source replay")
    root = Path(root_value).resolve(strict=True)
    refs = []
    for period, folder in (("2025-12-31", "fy2025"), ("2026-06-30", "h12026")):
        relative = f"{ARCHIVE}/{folder}/receipt.json"
        receipt = root / relative
        refs.append(dict(period=period, receipt_binding=dict(
            path=relative, sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())))
    result = replay_numbered_parent_cash_observations(root=root, symbol="000568",
        issuer_name=ISSUER, receipt_bindings=refs, now=datetime.now(timezone.utc))
    assert result["status"] == "SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    annual, interim = result["historical_statements"]
    from value_investment_agent.application.research.parent_cash_research import LABELS
    assert list(annual["rows"]) == [field for field in LABELS if field in annual["rows"]]
    assert list(interim["rows"]) == [field for field in LABELS if field in interim["rows"]]
    assert annual["rows"]["cfo_cny"]["columns"][0]["value"] == "4506071680.73"
    assert annual["rows"]["gross_capex_cny"]["statement_scope"] == "listed_parent_only"
    assert "borrowings_received_cny" in annual["ambiguous_printed_columns"]
    assert "borrowings_received_cny" not in annual["rows"]
    assert interim["balances"][0]["opening_cash_and_equivalents_cny"] != ""
    assert result["whole_statement_reconciled"] is False


def test_official_cover_identity_period_and_unit_remain_strict():
    root_value = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if root_value is None:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real official-source negative cases")
    original = Path(root_value) / ARCHIVE / "fy2025" / "original.pdf"
    pages = extract_pages(original)
    args = dict(pages=pages, symbol="000568", issuer_name=ISSUER, period="2025-12-31")
    with pytest.raises(ValueError, match="ISSUER_PERIOD_OR_CODE"):
        extract_numbered_parent_cash_statement(**dict(args, symbol="000569"))
    with pytest.raises(ValueError, match="ISSUER_PERIOD_OR_CODE"):
        extract_numbered_parent_cash_statement(**dict(args, issuer_name="另一公司股份有限公司"))
    with pytest.raises(ValueError, match="ISSUER_PERIOD_OR_CODE"):
        extract_numbered_parent_cash_statement(**dict(args, period="2026-06-30"))
    altered = list(pages)
    altered[82] = altered[82].replace("单位：元", "单位：万元")
    with pytest.raises(ValueError, match="COLUMNS_OR_UNIT"):
        extract_numbered_parent_cash_statement(**dict(args, pages=altered))


def test_real_numbered_parent_cash_reaches_bounded_d2_source_context():
    root_value = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if root_value is None:
        pytest.skip("Set VALUE_REAL_SOURCE_ROOT for real D2 source integration")
    context = build_operating_horizon_source_context(root=Path(root_value),
        symbol="000568", now=datetime.now(timezone.utc))
    parent_rows = [row for row in context["evidence"] if ":parent-cash-v2:" in row["id"]]
    assert len(parent_rows) == 13
    assert all(row["scope"] == "ISSUER_PARENT_STANDALONE" for row in parent_rows)
    assert all(row["pdf_sha256"] and row["receipt_binding"] for row in parent_rows)
    assert any("PRINTED_COLUMN_AMBIGUOUS:borrowings_received_cny" in gap["reason"]
               for gap in context["statement_basis_gaps"])
    assert context["action"] == "no_order" and context["formal_eligibility"] is False

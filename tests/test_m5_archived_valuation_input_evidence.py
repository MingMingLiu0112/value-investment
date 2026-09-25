"""Pin archived equity/share observations without promoting them to model inputs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import pytest
from pypdf import PdfReader


ROOT = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", Path(__file__).resolve().parents[1]))
LOCAL = Path(__file__).resolve().parents[1]
POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-latest.json"
ASSUMPTIONS_POINTER = ROOT / "runtime/valuation-assumptions/600519-current-latest.json"
PDF = ROOT / "runtime/m5-600519-disclosure-queue-20260924/source/600519/announcements/2026-08-15/1225475868.pdf"
FACTS = LOCAL / "runtime/m5-verified-facts-actual-20260925.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pinned(pointer_path: Path) -> dict:
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    evidence_path = (ROOT / pointer["path"]).resolve() / "evidence.json"
    assert evidence_path.is_relative_to(ROOT.resolve())
    assert _sha(evidence_path) == pointer["sha256"]
    return json.loads(evidence_path.read_text(encoding="utf-8"))


def test_archived_equity_shares_are_source_bound_but_not_new_valuation_inputs():
    if any(not path.is_file() for path in (POINTER, ASSUMPTIONS_POINTER, PDF, FACTS)):
        pytest.skip("Archived ACTUAL evidence is unavailable")
    equity = _pinned(POINTER)
    assumptions = _pinned(ASSUMPTIONS_POINTER)
    facts = json.loads(FACTS.read_text(encoding="utf-8"))["payload"]
    basis = equity["current_disclosed_basis"]

    assert basis["period_end"] == facts["facts"][0]["report_period_end"] == "2026-06-30"
    assert basis["source_id"] == f"cninfo:{facts['announcement_id']}"
    assert basis["source_url"] == facts["source_url"]
    assert basis["raw_file_hash"] == facts["pdf_sha256"] == _sha(PDF)
    assert datetime.fromisoformat(basis["available_at"]) <= datetime.fromisoformat(facts["available_at"])
    assert Decimal(basis["parent_equity_cny"]) > 0
    assert Decimal(basis["issued_shares"]) > 0

    reader = PdfReader(str(PDF))
    share_page = reader.pages[basis["share_evidence"]["physical_page"] - 1].extract_text() or ""
    equity_page = reader.pages[basis["equity_bridge"]["physical_page"] - 1].extract_text() or ""
    balance_page = reader.pages[27].extract_text() or ""
    assert "1,252,270,215 100 -2,188,614 -2,188,614 1,250,081,601 100" in share_page
    assert "251,253,594,419.50 244,637,811,032.18" in balance_page
    assert "251,253,594,419.50" in equity_page

    assert equity["valuation_approved"] is False
    assert basis["as_of_registry_verified"] is False
    assert assumptions["mapping_only"] is True
    assert assumptions["valuation_recalculated"] is False
    assert assumptions["valuation_approved"] is False

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from value_investment_agent.quote_session_conversion import (
    quote_snapshot_from_bundle_file,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = (
    ROOT
    / "runtime"
    / "quote-sessions"
    / "20260923T005634211464Z"
    / "bundle.json"
)
BUNDLE_SHA256 = (
    "5e49dc79bbc0132b040175e993e2f5dd5a3813c7167ade7aa2afc5c51cea19c0"
)


@pytest.mark.skipif(not BUNDLE.exists(), reason="archived quote runtime missing")
def test_archived_yili_quote_becomes_a_bound_verified_close():
    snapshot = quote_snapshot_from_bundle_file(
        BUNDLE,
        ROOT,
        symbol="600887",
        ref_id="yili_quote_20260922",
        expected_sha256=BUNDLE_SHA256,
    )

    assert snapshot.status == "verified_close"
    assert snapshot.quote_date == date(2026, 9, 22)
    assert snapshot.current_price == Decimal("26.77")
    assert any(
        ref.get("id") == "yili_quote_20260922-tencent"
        and ref["source_url"] == "https://qt.gtimg.cn/q=sh600887,sh600741,sh600519"
        and ref["sha256"]
        == "7bec3f3c94b275fbf9732e0d7116871d522fc146bc37e3bc58193a06860f5d2f"
        for ref in snapshot.evidence_refs
    )


@pytest.mark.skipif(not BUNDLE.exists(), reason="archived quote runtime missing")
def test_bundle_hash_mismatch_fails_closed():
    with pytest.raises(ValueError, match="hash does not match"):
        quote_snapshot_from_bundle_file(
            BUNDLE,
            ROOT,
            symbol="600887",
            ref_id="yili_quote_20260922",
            expected_sha256="0" * 64,
        )


@pytest.mark.skipif(not BUNDLE.exists(), reason="archived quote runtime missing")
def test_missing_symbol_reference_fails_closed():
    with pytest.raises(ValueError, match="no reference"):
        quote_snapshot_from_bundle_file(
            BUNDLE,
            ROOT,
            symbol="600000",
            ref_id="other_quote",
        )

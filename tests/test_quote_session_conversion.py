from __future__ import annotations

from datetime import date, datetime, timezone
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
@pytest.mark.parametrize('current_b1', [False, True])
def test_next_morning_archive_replays_history_but_cannot_claim_current_b1(current_b1):
    snapshot = quote_snapshot_from_bundle_file(
        BUNDLE,
        ROOT,
        symbol="600887",
        ref_id="yili_quote_20260922",
        expected_sha256=BUNDLE_SHA256,
        require_current_b1=current_b1,
    )

    assert snapshot.status == ("unverified" if current_b1 else "verified_close")
    assert snapshot.blockers == (["B1 requires same-session post-close acquisition"] if current_b1 else [])
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


@pytest.mark.skipif(not BUNDLE.exists(), reason="archived quote runtime missing")
def test_current_quote_bridge_displays_latest_historical_close_without_admitting_it():
    from value_investment_agent.application.product.quote_bridge import admit_quote_for_research
    path, digest, verdict = admit_quote_for_research(ROOT, BUNDLE, '600887', '2026-09-22',
        today=datetime(2026, 9, 23, 2, tzinfo=timezone.utc))
    assert path is None and digest is None
    assert verdict['status'] == 'HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY'
    assert verdict['is_historical_close'] is True
    assert verdict['price_admitted'] is False
    assert verdict['latest_completed_session'] == '2026-09-22'

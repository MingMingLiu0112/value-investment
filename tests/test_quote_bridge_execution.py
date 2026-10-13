"""TL7-P1: one archived close must reach the CLI and the Web through the same rule."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.application.product import quote_bridge
from value_investment_agent.application.product.quote_bridge import (
    execute_quote_bridge_for_symbol,
    pin_quote_bridge_for_symbol,
)
from value_investment_agent.quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE


ROOT = Path(__file__).resolve().parents[1]
REAL_POINTER = ROOT / "config/current-quote-bridge.json"
REAL_PACKAGE = (ROOT / "runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5"
                / "pending-candidate/package.json")
REAL_BUNDLE = ROOT / "runtime/quote-sessions/20261012T092313080159Z/bundle.json"
TODAY = datetime(2026, 10, 13, 4, tzinfo=timezone.utc)


def _write(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(tmp_path: Path, *, research_as_of: str = "2026-10-11") -> tuple[Path, Path]:
    bundle = tmp_path / "runtime/quotes/bundle.json"
    _write(bundle, {"finished_at": "2026-10-12T09:23:13+00:00",
                    "references": {"600887": {}}, "documents": {}})
    package = tmp_path / "runtime/cases/package.json"
    _write(package, {"symbol": "600887", "package_version": "pending-600887-2026-10-11-test",
                     "point_in_time": {"research_as_of": research_as_of}})
    return bundle, package


def _verified(monkeypatch, *, quote_date: datetime, price: str) -> None:
    monkeypatch.setattr(quote_bridge, "quote_snapshot_from_bundle_file", lambda *a, **k:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE, quote_date=quote_date, current_price=price,
                        blockers=[], evidence_refs=[{
                            "kind": "quote_provider_document", "provider": "tencent",
                            "source_url": "https://qt.gtimg.cn/q=sh600887",
                            "fetched_at": "2026-10-12T09:23:12+00:00", "sha256": "a" * 64}]))
    monkeypatch.setattr(quote_bridge, "resolve_session_reference",
                        lambda *a: {"calendar_exchange": "SSE", "calendar_documents": []})
    monkeypatch.setattr(quote_bridge, "latest_sse_2026_session",
                        lambda *a: (quote_date.isoformat(), ["b" * 64]))


def test_missing_registration_is_fail_closed(tmp_path):
    execution = execute_quote_bridge_for_symbol(tmp_path, "600887", today=TODAY)
    assert execution["status"] == "POINTER_UNAVAILABLE"
    assert execution["price_admitted"] is False
    assert execution["quote"] is None
    assert execution["action"] == "no_order"


def test_unregistered_symbol_reports_pending_instead_of_borrowing_a_quote(tmp_path):
    bundle, package = _case(tmp_path)
    pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package,
                                registered_at="2026-10-13T00:00:00+00:00")
    execution = execute_quote_bridge_for_symbol(tmp_path, "000333", today=TODAY)
    assert execution["status"] == "PENDING_EXTERNAL_DATA"
    assert execution["quote"] is None
    assert execution["research_day"] is None


def test_tampered_research_package_blocks_the_registered_quote(tmp_path):
    bundle, package = _case(tmp_path)
    pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package,
                                registered_at="2026-10-13T00:00:00+00:00")
    package.write_text(json.dumps({"symbol": "600887"}), encoding="utf-8")
    execution = execute_quote_bridge_for_symbol(tmp_path, "600887", today=TODAY)
    assert execution["status"] == "NOT_ADMITTED"
    assert "Hash" in execution["reason"]
    assert execution["price_admitted"] is False


def test_registered_quote_after_the_cutoff_is_displayed_but_not_admitted(tmp_path, monkeypatch):
    bundle, package = _case(tmp_path)
    pinned = pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package,
                                        registered_at="2026-10-13T00:00:00+00:00")
    _verified(monkeypatch, quote_date=datetime(2026, 10, 12).date(), price="27.96")
    execution = execute_quote_bridge_for_symbol(tmp_path, "600887", today=TODAY)
    assert execution["status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert execution["quote"]["quote_date"] == "2026-10-12"
    assert execution["quote"]["display_price"] == "27.96"
    assert execution["quote"]["is_historical_close"] is True
    assert execution["price_admitted"] is False
    assert execution["research_day"] == "2026-10-11"
    assert execution["research_case"]["package_version"] == "pending-600887-2026-10-11-test"
    assert execution["sources"][0]["provider"] == "tencent"
    assert execution["next_step"]
    assert execution["pointer"]["sha256"] == pinned["pointer_sha256"]
    assert execution["pointer"]["sha256"] == hashlib.sha256(
        (tmp_path / "config/current-quote-bridge.json").read_bytes()).hexdigest()


def test_close_inside_the_registered_cutoff_is_admitted(tmp_path, monkeypatch):
    bundle, package = _case(tmp_path, research_as_of="2026-10-12")
    pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package,
                                registered_at="2026-10-13T00:00:00+00:00")
    _verified(monkeypatch, quote_date=datetime(2026, 10, 12).date(), price="27.96")
    execution = execute_quote_bridge_for_symbol(
        tmp_path, "600887", today=datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc))
    assert execution["status"] == "QUOTE_VERIFIED_FOR_RESEARCH_INPUT"
    assert execution["price_admitted"] is True


@pytest.mark.skipif(
    not (REAL_POINTER.is_file() and REAL_PACKAGE.is_file() and REAL_BUNDLE.is_file()),
    reason="the real 600887 quote registration is not present in this checkout")
def test_real_600887_registration_stays_unadmitted_until_the_cutoff_covers_it():
    execution = execute_quote_bridge_for_symbol(ROOT, "600887", today=TODAY)
    assert execution["action"] == "no_order"
    assert execution["status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert execution["price_admitted"] is False
    assert execution["research_day"] == "2026-10-11"
    assert execution["research_case"]["package_version"].startswith("pending-600887-2026-10-11")
    assert execution["quote"] == {
        "quote_date": "2026-10-12", "display_price": "27.96",
        "collected_at": "2026-10-12T09:23:13.080145+00:00",
        "display_scope": "LAST_COMPLETED_CLOSE_DISPLAY_ONLY", "is_historical_close": True,
        "latest_completed_session": "2026-10-12",
        "bundle_path": "runtime/quote-sessions/20261012T092313080159Z/bundle.json",
        "bundle_sha256": "628f52aa203a5ddc43a860d35772645f2903b163deea592264f00f79a9774f4f"}
    providers = {row.get("provider") for row in execution["sources"]
                 if row.get("kind") == "quote_provider_document"}
    assert providers == {"tencent", "sina"}


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


def test_next_morning_collection_is_last_close_display_not_same_session_permission(tmp_path, monkeypatch):
    from datetime import date
    bundle, _ = _case(tmp_path)
    raw = json.loads(bundle.read_bytes())
    raw['finished_at'] = '2026-10-12T17:00:00+00:00'
    _write(bundle, raw)
    _verified(monkeypatch, quote_date=date(2026, 10, 12), price='28.10')
    def convert(*args, **kwargs):
        strict = kwargs.get('require_current_b1')
        return SimpleNamespace(status='unverified' if strict else QUOTE_STATUS_VERIFIED_CLOSE,
            quote_date=date(2026, 10, 12), current_price='28.10', evidence_refs=[],
            blockers=['B1 requires same-session post-close acquisition'] if strict else [])
    monkeypatch.setattr(quote_bridge, 'quote_snapshot_from_bundle_file', convert)
    path, digest, verdict = quote_bridge.admit_quote_for_research(
        tmp_path, bundle, '600887', '2026-10-12', today=TODAY)
    assert path is None and digest is None
    assert verdict['status'] == 'HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY'
    assert verdict['latest_completed_session'] == '2026-10-12'
    assert verdict['display_price'] == '28.10'
    assert verdict['price_admitted'] is False
    monkeypatch.setattr(quote_bridge, 'latest_sse_2026_session', lambda *a: ('2026-10-13', ['b'*64]))
    _, _, stale = quote_bridge.admit_quote_for_research(tmp_path, bundle, '600887', '2026-10-12', today=TODAY)
    assert stale['status'] == 'NOT_ADMITTED'


def test_missing_registration_is_fail_closed(tmp_path):
    execution = execute_quote_bridge_for_symbol(tmp_path, "600887", today=TODAY)
    assert execution["status"] == "POINTER_UNAVAILABLE"
    assert execution["price_admitted"] is False
    assert execution["quote"] is None
    assert execution["compatibility"] is None
    assert execution["action"] == "no_order"


def test_quote_only_registration_never_invents_a_research_cutoff_or_permission(tmp_path, monkeypatch):
    from datetime import date
    bundle, package = _case(tmp_path)
    _verified(monkeypatch, quote_date=date(2026, 10, 12), price="28.10")
    pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, None)
    execution = execute_quote_bridge_for_symbol(tmp_path, "600887", today=TODAY)
    assert execution["status"] == "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY"
    assert execution["research_case"] is execution["research_day"] is None
    assert execution["quote"]["display_price"] == "28.10"
    assert execution["compatibility"]["verified_quote"]["eligible"] is True
    assert execution["price_admitted"] is False
    assert all(not row["eligible"] for key, row in execution["compatibility"].items()
               if key != "verified_quote")
    from value_investment_agent.application.product.research_validity_review import review_registered_research_validity
    review = review_registered_research_validity(root=tmp_path, review_cutoff=date(2026, 10, 12),
        today=TODAY, output_path=Path("runtime/review.json"))
    assert review["reviews"][0]["status"] == "NO_REGISTERED_RESEARCH"
    assert review["reviews"][0]["formal_eligibility"] is False
    pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package)
    with pytest.raises(ValueError, match="已有研究绑定"):
        pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, None)


def test_pin_without_explicit_timestamp_stamps_utc_now(tmp_path):
    """SAFE_REFRESH relies on the default registration stamp path."""
    bundle, package = _case(tmp_path)
    pinned = pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package)
    assert pinned["registered_at"]
    stamp = datetime.fromisoformat(pinned["registered_at"])
    assert stamp.tzinfo is not None
    pointer = json.loads((tmp_path / "config/current-quote-bridge.json").read_text(encoding="utf-8"))
    assert pointer["quotes"]["600887"]["registered_at"] == pinned["registered_at"]
    assert pointer["quotes"]["600887"]["quote_bundle_sha256"] == pinned["quote_bundle_sha256"]


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
    ladder = execution["compatibility"]
    assert ladder["verified_quote"]["eligible"] is True
    assert ladder["research_compatible"]["eligible"] is False
    assert ladder["historical_reconstruction_eligible"]["eligible"] is False
    assert ladder["comparison_eligible"]["eligible"] is False
    assert ladder["formal_decision_eligible"]["eligible"] is False
    assert "2026-10-11" in ladder["research_compatible"]["reason"]


def test_close_inside_the_registered_cutoff_is_admitted(tmp_path, monkeypatch):
    bundle, package = _case(tmp_path, research_as_of="2026-10-12")
    pin_quote_bridge_for_symbol(tmp_path, "600887", bundle, package,
                                registered_at="2026-10-13T00:00:00+00:00")
    _verified(monkeypatch, quote_date=datetime(2026, 10, 12).date(), price="27.96")
    execution = execute_quote_bridge_for_symbol(
        tmp_path, "600887", today=datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc))
    assert execution["status"] == "QUOTE_VERIFIED_FOR_RESEARCH_INPUT"
    assert execution["price_admitted"] is True
    ladder = execution["compatibility"]
    assert ladder["verified_quote"]["eligible"] is True
    assert ladder["research_compatible"]["eligible"] is True
    assert ladder["historical_reconstruction_eligible"]["eligible"] is True
    assert ladder["comparison_eligible"]["eligible"] is True
    assert ladder["formal_decision_eligible"]["eligible"] is False


@pytest.mark.skipif(
    not (REAL_POINTER.is_file() and REAL_PACKAGE.is_file()),
    reason="the real 600887 quote registration is not present in this checkout")
def test_real_600887_registration_stays_unadmitted_until_the_cutoff_covers_it():
    entry = json.loads(REAL_POINTER.read_text(encoding="utf-8"))["quotes"]["600887"]
    if not (ROOT / entry["quote_bundle"]).is_file():
        pytest.skip("the registered quote bundle is not present in this checkout")
    package_path = (ROOT / entry["research_package"]).resolve()
    assert package_path.is_relative_to(ROOT.resolve())
    if not package_path.is_file():
        pytest.skip("the explicitly registered research package is not present in this checkout")
    package_bytes = package_path.read_bytes()
    assert hashlib.sha256(package_bytes).hexdigest() == entry["research_package_sha256"]
    package = json.loads(package_bytes)
    # Replay at the registration instant: the daily entry (SAFE_REFRESH) moves
    # this pointer whenever a newer dual-source close is registered.
    execution = execute_quote_bridge_for_symbol(
        ROOT, "600887", today=datetime.fromisoformat(entry["registered_at"]))
    assert execution["action"] == "no_order"
    assert execution["quote_verification_status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert execution["status"] == ("INCREMENTAL_VALIDITY_BLOCKED" if "incremental_validity_binding" in entry
                                    else "QUOTE_VERIFIED_BUT_RESEARCH_STALE")
    assert execution["price_admitted"] is False
    assert execution["research_day"] == package["point_in_time"]["research_as_of"]
    assert execution["research_case"]["package_version"] == package["package_version"]
    quote = execution["quote"]
    assert quote["bundle_path"] == entry["quote_bundle"]
    assert quote["bundle_sha256"] == entry["quote_bundle_sha256"]
    assert quote["quote_date"] > execution["research_day"]
    # The newest registered close is also the latest completed session, so the
    # freshness projection cannot fall back to UNKNOWN (TL9 MVP-1 dates).
    assert quote["latest_completed_session"] == quote["quote_date"]
    assert quote["display_price"]
    providers = {row.get("provider") for row in execution["sources"]
                 if row.get("kind") == "quote_provider_document"}
    assert providers == {"tencent", "sina"}
    ladder = execution["compatibility"]
    assert ladder["verified_quote"]["eligible"] is True
    assert ladder["research_compatible"]["eligible"] is False
    assert ladder["comparison_eligible"]["eligible"] is False
    assert ladder["formal_decision_eligible"]["eligible"] is False


"""TL8-D: the daily research status comes from registered real inputs only."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from value_investment_agent.application.product import daily_research_status
from value_investment_agent.application.product.daily_research_status import (
    build_daily_research_status,
    registered_quote_symbols,
)


ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime(2026, 10, 13, 4, tzinfo=timezone.utc)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _execution(symbol: str, *, research_day: str, quote_date: str | None,
               status: str = "QUOTE_VERIFIED_BUT_RESEARCH_STALE") -> dict:
    quote = None if quote_date is None else {"quote_date": quote_date, "display_price": "27.96"}
    return {"symbol": symbol, "status": status, "research_day": research_day, "quote": quote,
            "price_admitted": False, "reason": "fixture", "next_step": "fixture-next"}


def test_missing_pointer_registers_no_symbols(tmp_path):
    assert registered_quote_symbols(tmp_path) == []
    summary = build_daily_research_status(tmp_path, today=TODAY)
    assert summary["status"] == "NO_REGISTERED_QUOTES"
    assert summary["registry_status"] == "ABSENT"
    assert summary["registered_count"] == 0
    assert summary["needs_re_research_count"] == 0
    assert summary["rows"] == []
    assert summary["action"] == "no_order"


def test_unreadable_pointer_is_unknown_not_empty(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "current-quote-bridge.json").write_text("{not json", encoding="utf-8")
    assert registered_quote_symbols(tmp_path) == []
    summary = build_daily_research_status(tmp_path, today=TODAY)
    # A damaged registry file must never read as "nothing is registered".
    assert summary["status"] == "REGISTRY_UNAVAILABLE"
    assert summary["registry_status"] == "UNAVAILABLE"
    assert "不代表没有登记" in summary["reason"]
    assert summary["rows"] == []
    assert summary["action"] == "no_order"


def test_packet_flags_an_unreadable_registry_instead_of_silence(tmp_path):
    from value_investment_agent.application.product import daily_public_packet

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "current-quote-bridge.json").write_text("{not json", encoding="utf-8")
    rows, blockers = daily_public_packet._bridge_rows(
        tmp_path, datetime(2026, 10, 13, 4, tzinfo=timezone.utc))
    assert rows == []
    assert blockers == ["QUOTE_REGISTRY_UNAVAILABLE"]


def test_close_after_the_research_cutoff_requires_re_research(tmp_path):
    _write(tmp_path / "config/current-quote-bridge.json",
           {"quotes": {"600887": {"quote_bundle": "runtime/q.json"}}})
    original = daily_research_status.execute_quote_bridge_for_symbol
    daily_research_status.execute_quote_bridge_for_symbol = lambda root, symbol, *, today: _execution(
        symbol, research_day="2026-10-11", quote_date="2026-10-12")
    try:
        summary = build_daily_research_status(tmp_path, today=TODAY, names={"600887": "伊利股份"})
    finally:
        daily_research_status.execute_quote_bridge_for_symbol = original
    row = summary["rows"][0]
    assert row["name"] == "伊利股份"
    assert row["needs_re_research"] is True
    assert row["research_covers_close"] is False
    assert summary["needs_re_research_count"] == 1
    assert summary["verified_close_count"] == 1


def test_close_inside_the_research_window_covers_the_quote(tmp_path):
    _write(tmp_path / "config/current-quote-bridge.json",
           {"quotes": {"600887": {"quote_bundle": "runtime/q.json"}}})
    original = daily_research_status.execute_quote_bridge_for_symbol
    daily_research_status.execute_quote_bridge_for_symbol = lambda root, symbol, *, today: _execution(
        symbol, research_day="2026-10-12", quote_date="2026-10-12",
        status="QUOTE_VERIFIED_FOR_RESEARCH_INPUT")
    try:
        summary = build_daily_research_status(tmp_path, today=TODAY)
    finally:
        daily_research_status.execute_quote_bridge_for_symbol = original
    row = summary["rows"][0]
    assert row["needs_re_research"] is False
    assert row["research_covers_close"] is True
    assert summary["needs_re_research_count"] == 0


def test_one_symbol_failure_stays_isolated_and_is_never_upgraded(tmp_path):
    _write(tmp_path / "config/current-quote-bridge.json",
           {"quotes": {"600887": {"quote_bundle": "runtime/q.json"},
                       "000333": {"quote_bundle": "runtime/m.json"}}})
    original = daily_research_status.execute_quote_bridge_for_symbol

    def broken(root, symbol, *, today):
        if symbol == "600887":
            raise ValueError("fixture failure")
        return _execution(symbol, research_day="2026-10-11", quote_date="2026-10-12")

    daily_research_status.execute_quote_bridge_for_symbol = broken
    try:
        summary = build_daily_research_status(tmp_path, today=TODAY)
    finally:
        daily_research_status.execute_quote_bridge_for_symbol = original
    by_symbol = {row["symbol"]: row for row in summary["rows"]}
    assert by_symbol["600887"]["bridge_status"] == "EXECUTION_FAILED"
    assert by_symbol["600887"]["price_admitted"] is False
    assert by_symbol["000333"]["needs_re_research"] is True


def test_daily_summary_cli_writes_once_and_then_reports_unchanged():
    relative = Path("runtime") / f".pytest-tl8-d-{uuid.uuid4().hex[:12]}" / "daily-summary.json"
    target = ROOT / relative
    try:
        first = subprocess.run(
            [sys.executable, str(ROOT / "scripts/current/build_daily_research_summary.py"),
             "--output", str(relative)],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert first.returncode == 0, first.stderr
        written = json.loads(first.stdout)
        assert written["status"] == "WRITTEN"
        assert written["action"] == "no_order"
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "daily-research-summary-v1"
        assert payload["action"] == "no_order"
        assert payload["content"]["action"] == "no_order"
        canonical = json.dumps(payload["content"], ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
        assert payload["content_sha256"] == hashlib.sha256(canonical).hexdigest()
        second = subprocess.run(
            [sys.executable, str(ROOT / "scripts/current/build_daily_research_summary.py"),
             "--output", str(relative)],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert second.returncode == 0, second.stderr
        assert json.loads(second.stdout)["status"] == "UNCHANGED"
    finally:
        shutil.rmtree(target.parent, ignore_errors=True)

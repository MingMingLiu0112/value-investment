from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.presentation import daily_trade_assistant as daily
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE


def _bundle(root: Path, finished_at: datetime) -> Path:
    path = root / "runtime/quotes/bundle.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"finished_at": finished_at.isoformat()}), encoding="utf-8")
    return path


def test_verified_quote_after_research_cutoff_is_audited_but_not_admitted(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 9, tzinfo=timezone.utc)
    bundle = _bundle(tmp_path, datetime(2026, 10, 9, 8, tzinfo=timezone.utc))
    monkeypatch.setattr(daily, "quote_snapshot_from_bundle_file", lambda *args, **kwargs:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE,
                        quote_date=datetime(2026, 10, 9).date(), blockers=[], evidence_refs=[
                            {"id": "source-tencent", "sha256": "a" * 64},
                            {"id": "source-sina", "sha256": "b" * 64},
                        ]))
    path, digest, check = daily._quote_for_case(tmp_path, bundle, "600519", "2026-10-08", today=now)
    assert path is digest is None
    assert check["status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert check["quote_date"] == "2026-10-09"
    assert check["bundle_sha256"] == sha256_file(bundle)
    assert len(check["source_evidence"]) == 2


def test_old_quote_archive_never_becomes_current_price(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    bundle = _bundle(tmp_path, datetime(2026, 10, 8, 16, tzinfo=timezone.utc))
    monkeypatch.setattr(daily, "quote_snapshot_from_bundle_file", lambda *args, **kwargs:
        SimpleNamespace(status=QUOTE_STATUS_VERIFIED_CLOSE,
                        quote_date=datetime(2026, 10, 8).date(), blockers=[], evidence_refs=[]))
    path, digest, check = daily._quote_for_case(tmp_path, bundle, "600519", "2026-10-09", today=now)
    assert path is digest is None
    assert check["status"] == "NOT_ADMITTED"
    assert "历史行情" in check["reason"]


def test_invalid_quote_does_not_enter_research_input(tmp_path, monkeypatch):
    now = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    bundle = _bundle(tmp_path, now)
    monkeypatch.setattr(daily, "quote_snapshot_from_bundle_file", lambda *args, **kwargs:
        SimpleNamespace(status="unverified", quote_date=None,
                        blockers=["price_conflict"], evidence_refs=[]))
    path, digest, check = daily._quote_for_case(tmp_path, bundle, "600519", "2026-10-09", today=now)
    assert path is digest is None
    assert check["status"] == "NOT_ADMITTED"
    assert "price_conflict" in check["reason"]


def test_quote_notice_is_read_only_and_source_linked():
    payload = {"companies": [{"symbol": "600519", "company_name": "贵州茅台",
                              "price": {"status": "UNAVAILABLE"}}],
               "audit": {"evidence": []}, "today_items": [], "overview": {"pending_count": 0}}
    check = {"status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE", "quote_date": "2026-10-09",
             "bundle_path": "runtime/quotes/bundle.json", "bundle_sha256": "a" * 64,
             "reason": "ResearchCase 截止日较早"}
    daily._project_quote_gate(payload, symbol="600519", quote_check=check)
    assert payload["companies"][0]["price"] == {"status": "UNAVAILABLE"}
    assert payload["today_items"][0]["evidence_refs"] == [payload["audit"]["evidence"][0]["evidence_id"]]
    assert payload["today_items"][0]["current_status"] == "尚未构成买卖依据"
    assert payload["overview"]["pending_count"] == 1


def test_security_research_survives_absent_private_portfolio(tmp_path, monkeypatch):
    package = tmp_path / "config/package.json"
    package.parent.mkdir()
    package.write_text(json.dumps({"symbol": "000651", "point_in_time": {
        "research_as_of": "2026-09-22"}}), encoding="utf-8")
    request = tmp_path / "config/request.json"
    request.write_text(json.dumps({"symbol": "000651"}), encoding="utf-8")
    case = {"package": "config/package.json", "package_sha256": sha256_file(package),
            "schedule_request": "config/request.json", "schedule_request_sha256": sha256_file(request)}

    def build(**kwargs):
        value = {"symbol": kwargs["symbol"], "action": "no_order",
                 "suggested_state": "NO_ACTION", "decision_recommendation": None,
                 "valuation": None, "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
                 "position_guidance": None}
        kwargs["output_path"].write_text(json.dumps(value), encoding="utf-8")
        return {"result": value}

    monkeypatch.setattr(daily, "build_current_workbench_for_symbol", build)
    receipt = daily.run_daily_trade_assistant(root=tmp_path, symbol="000651", case=case,
        output_dir=tmp_path / "runtime/run", agent_mode="none")
    assert receipt["recommendation_type"] == "NO_ACTION"
    assert receipt["position_guidance"] is None
    assert receipt["portfolio_input_status"] == "BLOCKED_PRIVATE_INPUT"
    assert receipt["canonical_workbook_written"] is False
    assert "preview" not in receipt["outputs"]
    assert (tmp_path / receipt["outputs"]["report"]["path"]).is_file()


def test_source_hash_change_rejected_before_new_output(tmp_path):
    package = tmp_path / "package.json"
    package.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="package hash mismatch"):
        daily.run_daily_trade_assistant(root=tmp_path, symbol="600519",
            case={"package": "package.json", "package_sha256": "0" * 64},
            output_dir=tmp_path / "runtime/run", agent_mode="none")
    assert not (tmp_path / "runtime/run").exists()


@pytest.mark.parametrize("kind", ["BUY_CANDIDATE", "ADD_CANDIDATE", "HOLD",
                                   "TRIM_CANDIDATE", "SELL_CANDIDATE", "NO_ACTION"])
def test_report_names_existing_recommendation_without_creating_orders(kind):
    workbench = {"symbol": "600519", "valuation": {"status": "conditional_research_only"},
                 "decision_recommendation": {"recommendation_type": kind,
                     "decision_as_of": "2026-10-08", "valuation_range": {"bear": "400",
                         "base": "500", "bull": "600", "currency": "CNY"},
                     "blockers": ["待审阅"], "thesis": "经营逻辑", "next_events": [{"text": "年报"}]}}
    text = daily._render_report(workbench, None, {"status": "PENDING_EXTERNAL_DATA"},
                                None, None, None)
    assert kind in text
    assert daily.DECISION_NAMES[kind] in text
    assert "action=no_order" in text
    assert "Bear / Base / Bull：400.00 / 500.00 / 600.00 CNY" in text
    assert "BLOCKED_PRIVATE_INPUT" in text

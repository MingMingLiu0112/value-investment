from decimal import Decimal
from copy import deepcopy
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
import json

import pytest
from value_investment_agent.historical_asof import select_asof


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_parent_equity_inputs", ROOT / "scripts" / "build_moutai_consolidated_equity_inputs.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_summary_parser_uses_current_year_parent_scope_only():
    text = """
        归属于上市公司股东的净利润82,320,067,101.6886,228,146,421.62
        归属于上市公司股东的净资产244,637,811,032.18233,105,984,399.47
        股本1,252,270,215.001,256,197,800.00
    """
    assert MODULE.summary_numbers(text) == {
        "parent_equity_cny": Decimal("244637811032.18"),
        "parent_profit_cny": Decimal("82320067101.68"),
        "reported_share_capital_cny": Decimal("1252270215.00"),
    }


def test_summary_parser_rejects_ambiguous_or_missing_labels():
    text = "归属于上市公司股东的净资产1.00归属于上市公司股东的净资产2.00股本1.00"
    try:
        MODULE.summary_numbers(text)
    except ValueError as error:
        assert "exactly one" in str(error)
    else:
        raise AssertionError("ambiguous parent equity must be rejected")


def test_share_count_requires_share_units_and_reconciled_ordinary_scope():
    text = """
        单位：股 本次变动前 本次变动后
        1、人民币普通股 1,256,197,800 100 -3,927,585 -3,927,585 1,252,270,215 100
        三、股份总数 1,256,197,800 100 -3,927,585 -3,927,585 1,252,270,215 100
    """
    assert MODULE.share_numbers(text)["ending_issued_shares"] == Decimal("1252270215")
    with pytest.raises(ValueError, match="unit"):
        MODULE.share_numbers(text.replace("单位：股", "单位：元"))
    with pytest.raises(ValueError, match="reconcile"):
        MODULE.share_numbers(text.replace("1,252,270,215", "1,252,270,216"))
    with pytest.raises(ValueError, match="ambiguous"):
        MODULE.share_numbers(text + text)


def test_actual_annual_facts_cannot_enter_decisions_before_verified_publication_bound():
    result = MODULE.build()
    current = result["chain"][-1]
    assert current["published_date"] == "2026-04-17"
    assert current["share_evidence"]["monetary_capital_used_as_shares"] is False
    point = {**current, "symbol": "600519", "field_name": "parent_equity_cny",
             "period_label": current["period_end"], "value": current["parent_equity_cny"],
             "unit": "CNY", "validation_status": "verified",
             "publication_date_verified": True, "availability_bound_verified": True,
             "availability_method": current["availability_basis"]}
    arguments = {"symbol": "600519", "field_name": "parent_equity_cny", "period_label": "2025-12-31"}
    for decision_at in ("2026-04-03T15:00:00+08:00", "2026-04-17T23:59:59+08:00"):
        assert select_asof([point], decision_at=decision_at, **arguments) == []
    assert select_asof([point], decision_at="2026-04-18T00:00:00+08:00", **arguments) == [point]


def test_official_index_date_and_pdf_path_disagreement_is_rejected(tmp_path, monkeypatch):
    payload = json.loads(MODULE.INDEX.read_text(encoding="utf-8"))
    row = next(row for row in payload["response"]["announcements"] if row["announcementId"] == "1225114741")
    row["adjunctUrl"] = "finalpage/2026-04-02/1225114741.PDF"
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(MODULE, "INDEX", path)
    monkeypatch.setattr(MODULE, "INDEX_SHA256", MODULE.digest(path))
    with pytest.raises(ValueError, match="index date and PDF"):
        MODULE.annual_report_metadata()


def test_actual_interim_basis_separates_profit_oci_shares_and_review_availability():
    result = MODULE.build()
    basis = result["current_disclosed_basis"]
    assert result["chain"][-1]["period_end"] == "2025-12-31"
    assert basis["published_date"] == "2026-08-15"
    assert basis["available_at"] == "2026-08-16T00:00:00+08:00"
    assert basis["parent_profit_h1_cny"] == "44516880421.86"
    assert basis["parent_oci_h1_cny"] == "11538418.03"
    assert basis["parent_comprehensive_income_h1_cny"] == "44528418839.89"
    bridge = basis["equity_bridge"]
    assert sum(Decimal(bridge[key]) for key in ("opening_equity_cny", "net_profit_cny",
               "oci_cny", "repurchase_equity_change_cny", "distribution_equity_change_cny")) == Decimal("251253594419.50")
    assert basis["issued_shares"] == "1250081601"
    assert basis["ttm_parent_profit_cny"] == "81433985225.44"
    assert basis["ttm_ex_nonrecurring_parent_profit_cny"] == "81367067677.44"
    assert basis["ex_nonrecurring_profit_bridge"]["reported_ttm_minus_ex_nonrecurring_ttm_cny"] == "66917548.00"
    assert bridge["deduct_reported_distributions_again"] is False
    assert datetime.fromisoformat(basis["assessment_available_at"]) > datetime.fromisoformat(basis["available_at"])
    assert datetime.fromisoformat(basis["assessment_available_at"]) == datetime.fromisoformat(basis["event_query"]["checked_at"])


def test_comprehensive_income_parser_rejects_scope_and_arithmetic_errors():
    text = "单位：元币种：人民币 归属于母公司所有者权益 （一）综合收益总额 11,538,418.03 44,516,880,421.86 44,528,418,839.89"
    assert MODULE.comprehensive_income_numbers(text)["parent_profit_cny"] == Decimal("44516880421.86")
    with pytest.raises(ValueError, match="reconcile"):
        MODULE.comprehensive_income_numbers(text.replace("11,538,418.03", "11,538,418.04"))
    with pytest.raises(ValueError, match="scope"):
        MODULE.comprehensive_income_numbers(text.replace("归属于母公司所有者权益", "少数股东权益"))


def test_ex_nonrecurring_profit_does_not_parse_reported_profit_as_recurring():
    text = "归属于上市公司股东的净利润 44,516,880,421.86 45,402,962,298.10"
    with pytest.raises(ValueError, match="ex-nonrecurring"):
        MODULE.ex_nonrecurring_profit_numbers(text)
    assert MODULE.ex_nonrecurring_profit_numbers(
        "归属于上市公司股东的扣除非 经常性损益的净利润 -1,234.50 2,345.60 -152.63"
    ) == {"current": Decimal("-1234.50"), "prior": Decimal("2345.60")}


@pytest.mark.parametrize("change", ["new", "removed", "changed", "incomplete", "duplicate", "filtered", "early_time"])
def test_unreviewed_or_incomplete_capital_inventory_cannot_be_carried_forward(change):
    old = json.loads((ROOT / MODULE.CURRENT_REFERENCES["reviewed_index"][0]).read_text(encoding="utf-8"))
    current = json.loads(MODULE.CURRENT_INDEX.read_text(encoding="utf-8"))
    MODULE.validate_capital_inventory(old, current)
    rows = current["response"]["announcements"]
    if change in ("new", "duplicate"):
        item = deepcopy(rows[0])
        if change == "new":
            item["announcementId"] = "unreviewed-announcement"
        rows.append(item)
        current["response"]["totalAnnouncement"] += 1
    elif change == "removed":
        rows.pop()
        current["response"]["totalAnnouncement"] -= 1
    elif change == "changed":
        rows[0]["adjunctUrl"] += "changed"
    elif change == "incomplete":
        current["response"]["hasMore"] = True
    elif change == "filtered":
        current["query"]["searchkey"] = "回购"
    else:
        current["fetched_at"] = "2026-09-13T16:00:00+08:00"
    with pytest.raises(ValueError):
        MODULE.validate_capital_inventory(old, current)

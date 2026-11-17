"""TEST_ONLY note layouts and retained official/Sina original replay, no fetching."""
from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

import pytest
import requests

from value_investment_agent.infrastructure.screening.value_evidence_enrichment_v1 import (
    extract_income_comparatives, RetainedAnnualSource)
from value_investment_agent.application.research.income_source_correlation import (
    correlate_income_inputs, reverify_income_inputs)
from value_investment_agent.application.research.value_evidence_enrichment_v1 import enrich_retained_company

NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


def page(note):
    return """TEST_ONLY
合并利润表
2025 年 1—12 月
单位：元 币种：人民币
项目 附注 2025 年度 2024 年度
一、营业总收入 999.00 888.00
其中：营业收入 """+note+""" 200.00 180.00
五、净利润（净亏损以“-”号填列） 35.00 28.00
归属于母公司股东的净利润（净亏损以“-”号填列） 30.00 25.00
少数股东损益 5.00 3.00
"""


@pytest.mark.parametrize("note", ["七-46", "七、46", "七 - 46", "七、 46", "七（46）", "七(46)", "46"])
def test_explicit_note_forms_keep_two_amounts_and_original_excerpt(note):
    rows = extract_income_comparatives([page(note)], "2025-12-31")
    assert len(rows) == 2
    revenue = next(r for r in rows if r["field_name"] == "revenue")
    profit = next(r for r in rows if r["field_name"] == "net_income")
    assert (revenue["value"], revenue["prior_value"]) == ("200.00", "180.00")
    assert note in revenue["excerpt"]
    assert (profit["value"], profit["prior_value"]) == ("30.00", "25.00")
    assert revenue["period_label"] == "2025-12-31" and revenue["prior_period_label"] == "2024-12-31"
    assert revenue["currency"] == revenue["unit"] == "CNY"
    assert revenue["statement_scope"] == "consolidated"


@pytest.mark.parametrize("note", ["七-46.5", "七、46A", "七-046", "七/", "七-"])
def test_malformed_note_is_not_an_amount_or_ignored_text(note):
    rows = extract_income_comparatives([page(note)], "2025-12-31")
    assert not any(r["field_name"] == "revenue" for r in rows)


@pytest.mark.parametrize("old,new", [
    ("合并利润表", "母公司利润表"),
    ("人民币", "美元"),
    ("单位：元 币种：人民币", "币种：人民币"),
    ("2025 年度 2024 年度", "2024 年度 2025 年度"),
    ("2025 年度 2024 年度", "2025 年半年度 2024 年半年度"),
    ("200.00 180.00", "200.00"),
    ("200.00 180.00", "200.00 180.00 160.00"),
    ("其中：营业收入", "其中：营业总收入"),
])
def test_scope_unit_period_and_missing_comparative_not_relaxed(old,new):
    rows = extract_income_comparatives([page("七-46").replace(old,new)], "2025-12-31")
    assert not any(r["field_name"] == "revenue" for r in rows)


def test_duplicate_revenue_is_retained_for_correlation_to_reject():
    text = page("七、46").replace("五、净利润", "营业收入 七、46 200.00 180.00\n五、净利润")
    rows = extract_income_comparatives([text], "2025-12-31")
    assert len([r for r in rows if r["field_name"] == "revenue"]) == 2


REAL_CASES = [
    ("sse-research-20261102T122836", "600066"),
    ("sse-research-20261102T122836", "600323"),
    ("sse-research-followup-20261102T123448", "600428"),
    ("sse-research-followup-20261102T123448", "600897"),
    ("sse-research-followup-20261102T123448", "600933"),
]


@pytest.mark.parametrize("run,symbol", REAL_CASES)
def test_real_retained_official_and_sina_income_replay(tmp_path, monkeypatch, run, symbol):
    configured = os.environ.get("INCOME_COMPARATIVE_REAL_ROOT")
    if not configured:
        if os.environ.get("INCOME_COMPARATIVE_REAL_REQUIRED") == "1":
            pytest.fail("INCOME_COMPARATIVE_REAL_ROOT required")
        pytest.skip("Explicit retained public-original root opt-in")
    root = Path(configured)
    base = Path("runtime/sse-value-research") / run / "queue-inputs/enrichment"
    official_receipt_path = root / base / (symbol+"-official-original/receipt.json")
    secondary_receipt_path = root / base / (symbol+"-income-original/acquisition.json")
    official_receipt = json.loads(official_receipt_path.read_bytes())
    source = RetainedAnnualSource(**official_receipt["source"])
    acquired = json.loads(secondary_receipt_path.read_bytes())
    secondary = {k: acquired[k] for k in ("path","sha256","acquired_at")}
    secondary["source_url"] = acquired["url"]
    secondary["receipt"] = dict(path=secondary_receipt_path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(secondary_receipt_path.read_bytes()).hexdigest())
    original_files = [official_receipt_path, secondary_receipt_path, root/source.path, root/secondary["path"]]
    before = {p: (p.read_bytes(),p.stat().st_mtime_ns) for p in original_files}
    assert hashlib.sha256((root/source.path).read_bytes()).hexdigest() == source.sha256
    assert hashlib.sha256((root/secondary["path"]).read_bytes()).hexdigest() == secondary["sha256"]
    # Preserve every receipt byte and relative binding in an isolated replay root.
    for original in original_files:
        target = tmp_path / original.relative_to(root)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(original.read_bytes())
    def no_network(*args,**kwargs):
        raise AssertionError("Retained income replay must not fetch")
    monkeypatch.setattr(requests.sessions.Session,"request",no_network)
    points = correlate_income_inputs(tmp_path,source,secondary,evaluation_at=NOW)
    assert len(points) == 4
    assert {(p["field_name"],p["period_label"]) for p in points} == {
        (f,y) for f in ("revenue","net_income") for y in ("2025-12-31","2024-12-31")}
    assert all(p["metadata"]["historical_pit_admission"] == "NOT_ADMITTED"
               and p["metadata"]["economic_approval"] is False for p in points)
    assert all(p["available_at"] == max(source.available_at,secondary["acquired_at"]) for p in points)
    reverify_income_inputs(tmp_path,source,points,evaluation_at=NOW)
    enriched = enrich_retained_company(tmp_path,source,points,evaluation_at=NOW,
                                      cache_dir=tmp_path/".tmp/review",write_cache=False)
    growth = [p for p in enriched["adopted_points"] if p["field_name"] in {"revenue_yoy","net_income_yoy"}]
    assert {p["field_name"] for p in growth} == {"revenue_yoy","net_income_yoy"}
    assert before == {p: (p.read_bytes(),p.stat().st_mtime_ns) for p in original_files}
    (tmp_path/"actual-income-replay.json").write_text(json.dumps(
        dict(symbol=symbol,source=asdict(source),points=points,growth=growth,
             income_growth_adoption=enriched["income_growth_adoption"]),
        ensure_ascii=False,indent=2,default=str),encoding="utf-8")

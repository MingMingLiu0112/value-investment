"""Chinese-note parsing; real official PDFs plus explicitly TEST_ONLY secondary bytes."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as extraction
from value_investment_agent.application.research.income_source_correlation import (
    correlate_income_inputs, reverify_income_inputs,
)
from value_investment_agent.application.research.value_evidence_enrichment_v1 import (
    enrich_retained_company,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages


def page(note="七（61）", revenue="120.00 100.00", profit="24.00 20.00"):
    return ("600887 2025年年度报告\n合并利润表\n2025年度 2024年度\n单位：元 币种：人民币\n"
            f"营业收入 {note} {revenue}\n归属于母公司股东的净利润 {note} {profit}\n")


@pytest.mark.parametrize("note", ["七（61）", "七(61)", "七 （ 61 ）", "十一（6）", "七（61）\n", "61", ""])
def test_note_forms_preserve_two_amounts_and_nonadmission(note):
    rows = extraction.extract_income_comparatives([page(note)], "2025-12-31")
    assert [(row["field_name"], Decimal(row["value"]), Decimal(row["prior_value"])) for row in rows] == [
        ("revenue", Decimal("120"), Decimal("100")), ("net_income", Decimal("24"), Decimal("20"))]
    assert all(row["status"] == "SOURCE_LOCATED_NOT_INDEPENDENTLY_ADMITTED" for row in rows)
    assert all(row["page"] == 1 and row["unit"] == "CNY" and row["period_label"] == "2025-12-31" for row in rows)


@pytest.mark.parametrize("note", ["七（61)", "七(61）", "七（", "七（0）", "七（1234）", "七（61.5）", "七（61）解释文字"])
def test_malformed_notes_cannot_be_skipped(note):
    assert extraction.extract_income_comparatives([page(note)], "2025-12-31") == []


@pytest.mark.parametrize("mutation", ["missing_current", "missing_comparison", "third_column", "parent", "interim", "wrong_year", "restated", "unknown_currency"])
def test_row_and_statement_boundaries_remain_conservative(mutation):
    text = page()
    if mutation == "missing_current": text = page(revenue="100.00")
    elif mutation == "missing_comparison": text = page(revenue="120.00")
    elif mutation == "third_column": text = page(revenue="120.00 100.00 90.00")
    elif mutation == "parent": text = text.replace("合并利润表", "母公司利润表")
    elif mutation == "interim": text = text.replace("2025年度 2024年度", "2025年半年度 2024年半年度")
    elif mutation == "wrong_year": text = text.replace("2025年度 2024年度", "2024年度 2023年度")
    elif mutation == "restated": text = text.replace("2025年度 2024年度", "2025年度 调整后 2024年度")
    elif mutation == "unknown_currency": text = text.replace("币种：人民币", "币种：美元")
    rows = extraction.extract_income_comparatives([text], "2025-12-31")
    assert not any(row["field_name"] == "revenue" for row in rows)


@pytest.fixture(scope="module", params=["600519", "600887"])
def official(request):
    raw = os.environ.get("INCOME_NOTE_REAL_ROOT")
    if not raw:
        pytest.skip("Explicit read-only retained public root required; no downloads")
    spec_path = Path(__file__).resolve().parents[1]/"docs/current/two-company-earnings-bridge-20261024/sources.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))["companies"][request.param][0]
    path = Path(raw)/spec["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]
    rows = extraction.extract_income_comparatives(extract_pages(path), "2025-12-31")
    expected = {
        "600519": {"revenue": ("168838102514.79", "170899152276.34", 61),
                   "net_income": ("82320067101.68", "86228146421.62", 62)},
        "600887": {"revenue": ("115636231250.05", "115393310976.69", 86),
                   "net_income": ("11565166497.81", "8452859993.18", 87)},
    }[request.param]
    assert len(rows) == 2
    assert {row["field_name"]: (row["value"], row["prior_value"], row["page"]) for row in rows} == expected
    return path, spec, rows


def test_real_two_company_originals(official):
    path, spec, rows = official
    assert path.is_file()
    assert all(row["currency"] == "CNY" and row["statement_scope"] == "consolidated" for row in rows)
    assert all(row["prior_period_label"] == "2024-12-31" for row in rows)
    if spec["symbol"] == "600887":
        assert "七（61）" in next(row["excerpt"] for row in rows if row["field_name"] == "revenue")


@pytest.fixture
def official_with_test_only_secondary(tmp_path, official):
    original, spec, rows = official
    clock = datetime.now(timezone.utc)
    path = tmp_path/"runtime/official.pdf"
    path.parent.mkdir()
    shutil.copyfile(original, path)
    source = extraction.RetainedAnnualSource(spec["symbol"], "2025-12-31", "runtime/official.pdf",
        spec["sha256"], spec["source_url"], clock.isoformat())
    # These are test-generated JSON/receipt bytes, NOT independently acquired
    # Sina evidence. They exercise the unchanged verifier without mocking it.
    reports = {}
    for column, period in (("value", "20251231"), ("prior_value", "20241231")):
        reports[period] = dict(rCurrency="CNY", rType="合并期末", publish_date=spec["published_date"].replace("-", ""),
            data=[dict(item_field="BIZINCO" if row["field_name"] == "revenue" else "PARENETP",
                       item_source="lrb", item_value=row[column]) for row in rows])
    payload = dict(TEST_ONLY=True, result=dict(data=dict(report_list=reports)))
    secondary_path = tmp_path/"runtime/TEST_ONLY-secondary.json"
    secondary_path.write_text(json.dumps(payload), encoding="utf-8")
    descriptor = dict(path="runtime/TEST_ONLY-secondary.json", sha256=hashlib.sha256(secondary_path.read_bytes()).hexdigest(),
        acquired_at=clock.isoformat(), source_url="https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022?paperCode=sh"+spec["symbol"]+"&source=lrb&type=0")
    receipt_path = tmp_path/"runtime/TEST_ONLY-acquisition.json"
    def reseal_test_only():
        secondary_path.write_text(json.dumps(payload), encoding="utf-8")
        descriptor["sha256"] = hashlib.sha256(secondary_path.read_bytes()).hexdigest()
        receipt = dict(url=descriptor["source_url"], path=descriptor["path"], sha256=descriptor["sha256"],
            acquired_at=descriptor["acquired_at"], bytes=secondary_path.stat().st_size, action="no_order")
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        descriptor["receipt"] = dict(path="runtime/TEST_ONLY-acquisition.json", sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
    reseal_test_only()
    return tmp_path, source, descriptor, clock+timedelta(seconds=1), payload, reseal_test_only


def test_real_official_with_test_only_secondary_uses_actual_correlation_and_enrichment(official_with_test_only_secondary):
    root, source, secondary, cutoff, _, _ = official_with_test_only_secondary
    points = correlate_income_inputs(root, source, secondary, evaluation_at=cutoff)
    assert len(points) == 4
    assert all(point["metadata"]["economic_approval"] is False for point in points)
    reverify_income_inputs(root, source, points, evaluation_at=cutoff)
    result = enrich_retained_company(root, source, points, evaluation_at=cutoff,
        cache_dir=root/".tmp/TEST_ONLY-extraction")
    assert {row["field_name"] for row in result["adopted_points"]} == {"revenue_yoy", "net_income_yoy"}
    assert result["after"]["total_score"] is None
    assert result["debt_scope"]["complete_debt_verified"] is False
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


@pytest.mark.parametrize("damage", ["missing", "conflict", "wrong_scope", "source_drift", "late"])
def test_real_original_does_not_replace_secondary_verification(official_with_test_only_secondary, damage):
    root, source, secondary, cutoff, payload, reseal = official_with_test_only_secondary
    if damage == "missing": (root/secondary["path"]).unlink()
    elif damage == "source_drift": (root/secondary["path"]).write_bytes(b"changed TEST_ONLY bytes")
    elif damage == "late": secondary["acquired_at"] = (cutoff+timedelta(days=1)).isoformat()
    else:
        report = payload["result"]["data"]["report_list"]["20251231"]
        if damage == "conflict": report["data"][0]["item_value"] = "1.00"
        else: report["rType"] = "母公司"
        reseal()
    with pytest.raises((ValueError, FileNotFoundError)):
        correlate_income_inputs(root, source, secondary, evaluation_at=cutoff)

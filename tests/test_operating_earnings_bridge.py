from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import operating_earnings_bridge as module


def synthetic_statement(periods):
    amounts = {key: ["100.00", "80.00"] for key in module.REQUIRED}
    for col in (0, 1):
        number = lambda key: Decimal(amounts[key][col])
        amounts["total_revenue"][col] = str(number("operating_revenue")+number("interest_income"))
        amounts["total_cost"][col] = str(sum(number(key) for key in module.COSTS if key in amounts))
        amounts["operating_profit"][col] = str(number("total_revenue")-number("total_cost"))
        amounts["profit_before_tax"][col] = str(number("operating_profit")+number("nonoperating_income")-number("nonoperating_expense"))
        amounts["net_profit"][col] = str(number("profit_before_tax")-number("income_tax"))
        amounts["parent_profit"][col] = str(number("net_profit")-number("minority_profit"))
        amounts["ex_parent_profit"][col] = str(number("parent_profit")-Decimal("5.00"))
    rows = {}
    for key, values in amounts.items():
        scope = ("CONSOLIDATED_AFTER_TAX_PARENT" if key in {"parent_profit", "ex_parent_profit"} else
                 "CONSOLIDATED_AFTER_TAX_MINORITY" if key == "minority_profit" else
                 "CONSOLIDATED_AFTER_TAX" if key == "net_profit" else "CONSOLIDATED_STATEMENT_LINE")
        rows[key] = dict(values=values, periods=periods, currency="CNY", unit="CNY", scope=scope,
            source_id="SYNTHETIC_TEST_ONLY", sha256="0"*64, physical_page=1)
    return dict(symbol="600887", periods=periods, rows=rows)


@pytest.fixture
def inputs():
    return dict(annual=synthetic_statement(["FY2025", "FY2024"]),
                interim=synthetic_statement(["H12026", "H12025"]))


def test_common_contract_and_independent_fraction_identity(inputs):
    result = module.build_operating_earnings_bridge(**inputs)
    for name in ("h1_change", "annual_change"):
        bridge = result[name]
        independently_summed = sum(Fraction(row["contribution_cny"]) for row in bridge["rows"])
        assert independently_summed == Fraction(bridge["current_ex_parent_profit_cny"])-Fraction(bridge["base_ex_parent_profit_cny"])
        assert bridge["arithmetic_residual_cny"] == "0.00"
        assert all(row["fact_refs"] for row in bridge["rows"])
    assert result["normalized_parent_profit_cny"] is None
    assert result["tax_rate_assumption"] is None
    assert result["parent_attribution_assumption"] is None
    assert result["action"] == "no_order"
    assert not any(result[key] for key in ("g3_changed", "price_admitted", "strategy_admitted", "normalized_earnings_admitted"))


@pytest.mark.parametrize("mutation", ["missing", "null", "bool", "nonfinite", "currency", "scope", "period", "identity", "duplicate_period", "broken_net"])
def test_bad_facts_refused(inputs, mutation):
    statement = inputs["interim"]
    row = statement["rows"]["finance"]
    if mutation == "missing": del statement["rows"]["finance"]
    elif mutation == "null": row["values"][0] = None
    elif mutation == "bool": row["values"][0] = True
    elif mutation == "nonfinite": row["values"][0] = "NaN"
    elif mutation == "currency": row["currency"] = "HKD"
    elif mutation == "scope": row["scope"] = "PARENT_LEGAL_ENTITY"
    elif mutation == "period": row["periods"] = ["FY2025", "H12025"]
    elif mutation == "identity": statement["symbol"] = "600519"
    elif mutation == "duplicate_period": statement["periods"] = ["H12026", "H12026"]
    elif mutation == "broken_net": statement["rows"]["net_profit"]["values"][0] = "999.00"
    with pytest.raises(ValueError): module.build_operating_earnings_bridge(**inputs)


def test_residual_is_explicit_not_fabricated_zero(inputs):
    # A deliberate undisaggregated cost changes only the residual; no invented row.
    inputs["interim"]["rows"]["total_cost"]["values"][0] = "700.00"
    result = module.build_operating_earnings_bridge(**inputs)
    rows = {row["field"]: row for row in result["h1_change"]["rows"]}
    assert Decimal(rows["cost_unallocated"]["current_cny"]) != 0
    assert Decimal(rows["operating_unallocated"]["current_cny"]) != 0
    assert result["h1_change"]["arithmetic_residual_cny"] == "0.00"
    assert result["normalized_range"] is None
    assert result["breakdown_status"] == "RECONCILED_WITH_UNALLOCATED_RESIDUALS"


def test_decimal_precision_independent_of_callers_context(inputs):
    with localcontext() as context:
        context.prec = 4
        result = module.build_operating_earnings_bridge(**inputs)
    assert Fraction(result["h1_change"]["computed_change_cny"]) == -Fraction(120)


def test_missing_source_and_nan_fail_closed(inputs):
    inputs["annual"]["rows"]["finance"]["sha256"] = None
    with pytest.raises(ValueError): module.build_operating_earnings_bridge(**inputs)


@pytest.fixture(scope="module")
def real_results():
    raw = os.environ.get("EARNINGS_BRIDGE_REAL_ROOT")
    if not raw:
        pytest.skip("Opt-in retained public originals; no network or private accounts")
    root = Path(raw)
    location = Path(__file__).resolve().parents[1]/"docs/current/two-company-earnings-bridge-20261024/sources.json"
    spec = json.loads(location.read_text(encoding="utf-8"))
    result = {}
    for symbol, items in spec["companies"].items():
        specs = [dict(item, fields=spec["common_fields"]+item["extra_fields"]) for item in items]
        result[symbol] = module.research_from_retained_sources(root=root, specs=specs,
            now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc))
    return result


@pytest.mark.parametrize("symbol", ["600519", "600887"])
def test_retained_originals_fraction_crosscheck(real_results, symbol):
    result = real_results[symbol]
    annual, interim = result["original_statements"]
    for bridge_name, statement in (("annual_change", annual), ("h1_change", interim)):
        rows = statement["rows"]
        def pair(key): return [Fraction(value) for value in rows[key]["values"]]
        for column in (0, 1):
            assert pair("operating_profit")[column]+pair("nonoperating_income")[column]-pair("nonoperating_expense")[column] == pair("profit_before_tax")[column]
            assert pair("profit_before_tax")[column]-pair("income_tax")[column]-pair("minority_profit")[column] == pair("parent_profit")[column]
        bridge = result[bridge_name]
        assert sum(Fraction(row["contribution_cny"]) for row in bridge["rows"]) == pair("ex_parent_profit")[0]-pair("ex_parent_profit")[1]
        assert all(row["path"] and row["source_url"].startswith("https://static.cninfo.com.cn/") and row["excerpt"] for row in rows.values())
    for field, value in result["ttm"]["lines_cny"].items():
        if field in annual["rows"]:
            assert Fraction(value) == Fraction(annual["rows"][field]["values"][0])+Fraction(interim["rows"][field]["values"][0])-Fraction(interim["rows"][field]["values"][1])


def test_real_yili_drivers_are_not_parent_addbacks(real_results):
    result = real_results["600887"]
    rows = {row["field"]: row for row in result["h1_change"]["rows"]}
    assert rows["asset_impairment"]["contribution_cny"] == "-2118427686.17"
    assert rows["income_tax"]["contribution_cny"] == "-751939373.03"
    assert rows["minority_profit"]["contribution_cny"] == "269901722.69"
    assert result["h1_change"]["computed_change_cny"] == "-1420586985.11"
    assert all(item["after_tax_parent_adjustment_cny"] is None and item["proposed_addback_cny"] is None for item in result["normalization_open_items"])


def test_real_moutai_finance_scope_not_transplanted(real_results):
    result = real_results["600519"]
    rows = {row["field"]: row for row in result["h1_change"]["rows"]}
    assert rows["interest_expense"]["profit_effect_sign"] == -1
    assert rows["finance"]["contribution_cny"] == "-243406956.91"
    assert "asset_impairment" not in rows  # blank is not a fabricated observed zero
    assert result["ttm"]["lines_cny"]["ex_parent_profit"] == "81367067677.44"


def test_forged_source_and_future_availability_rejected(tmp_path):
    path = tmp_path/"fake.pdf"
    path.write_bytes(b"not read as approved finance")
    binding = dict(path="fake.pdf", sha256="0"*64)
    with pytest.raises(ValueError, match="drift"): module._source_path(tmp_path, binding)
    base = dict(binding, published_date="2026-10-25", original_acquired_at=None)
    with pytest.raises(ValueError, match="unavailable"):
        module.research_from_retained_sources(root=tmp_path, specs=[base, base],
            now=datetime(2026, 10, 24, tzinfo=timezone.utc))


def test_final_source_recheck_rejects_drift(tmp_path, monkeypatch, inputs):
    source = tmp_path/"fake.pdf"
    source.write_bytes(b"fixture")
    spec = dict(path="fake.pdf", sha256=hashlib.sha256(b"fixture").hexdigest(),
        published_date="2026-01-01", original_acquired_at=None, source_id="TEST_ONLY", source_url="TEST_ONLY")
    statements = iter(inputs.values())
    def extracted(**kwargs): return next(statements)
    original = module.build_operating_earnings_bridge
    def drift(**kwargs):
        result = original(**kwargs)
        source.write_bytes(b"changed")
        return result
    monkeypatch.setattr(module, "extract_statement", extracted)
    monkeypatch.setattr(module, "build_operating_earnings_bridge", drift)
    with pytest.raises(ValueError, match="drift"):
        module.research_from_retained_sources(root=tmp_path, specs=[spec, spec],
            now=datetime(2026, 10, 24, tzinfo=timezone.utc))


@pytest.mark.parametrize("failure", ["columns", "issuer", "currency", "blank_comparative", "duplicate", "path_escape", "future_acquired", "naive_acquired"])
def test_extractor_negative_boundaries(tmp_path, monkeypatch, failure):
    source = tmp_path/"fixture.pdf"
    source.write_bytes(b"SYNTHETIC_PDF_PARSER_TEST_ONLY")
    text = ("600887 伊利 合并利润表 单位：元 币种：人民币 2026年半年度 2025年半年度\n"
            "一、营业总收入 10,000.00 9,000.00\n其中：营业收入 9,000.00 8,000.00\n"
            "利息收入 1,000.00 1,000.00\n二、营业总成本 5,000.00 4,000.00")
    spec = dict(symbol="600887", issuer="伊利", path="fixture.pdf", sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        statement_pages=[1], summary_page=1, column_labels=["2026年半年度", "2025年半年度"],
        fields=["total_revenue", "operating_revenue", "interest_income"], periods=["H12026", "H12025"],
        source_id="TEST_ONLY", source_url="TEST_ONLY", original_acquired_at=None, published_date="2026-01-01")
    if failure == "columns": text = text.replace("2026年半年度 2025年半年度", "2025年半年度 2026年半年度")
    elif failure == "issuer": spec["symbol"] = "600519"
    elif failure == "currency": text = text.replace("单位：元", "单位：千元")
    elif failure == "blank_comparative": text = text.replace("10,000.00 9,000.00", "10,000.00")
    elif failure == "duplicate": text += " 一、营业总收入 10,000.00 9,000.00"
    elif failure == "path_escape": spec["path"] = "../fixture.pdf"
    elif failure == "future_acquired": spec["original_acquired_at"] = "2026-10-25T00:00:00+00:00"
    elif failure == "naive_acquired": spec["original_acquired_at"] = "2026-01-01T00:00:00"
    monkeypatch.setattr(module, "extract_pages", lambda path: [text])
    with pytest.raises(ValueError):
        if "acquired" in failure:
            module.research_from_retained_sources(root=tmp_path, specs=[spec, spec],
                now=datetime(2026, 10, 24, tzinfo=timezone.utc))
        else:
            module.extract_statement(root=tmp_path, spec=spec)


def test_extractor_keeps_column_separators(tmp_path, monkeypatch):
    path = tmp_path/"test.pdf"
    path.write_bytes(b"TEST_ONLY")
    text = "600887伊利 合并利润表 单位：元 币种：人民币2026年半年度2025年半年度\n一、营业总收入 10,000.00 9,000.00\n二、营业总成本 5,000.00 4,000.00"
    monkeypatch.setattr(module, "extract_pages", lambda path: [text])
    spec = dict(symbol="600887", issuer="伊利", path="test.pdf", sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        statement_pages=[1], summary_page=1, column_labels=["2026年半年度", "2025年半年度"],
        fields=["total_revenue"], periods=["H12026", "H12025"], source_id="TEST_ONLY", source_url="TEST_ONLY",
        original_acquired_at=None, published_date="2026-01-01")
    assert module.extract_statement(root=tmp_path, spec=spec)["rows"]["total_revenue"]["values"] == ["10000.00", "9000.00"]


def test_saved_public_research_replays_without_saved_amounts():
    raw = os.environ.get("EARNINGS_BRIDGE_REAL_ROOT")
    if not raw:
        pytest.skip("Opt-in retained originals")
    project = Path(__file__).resolve().parents[1]
    location = project/"docs/current/two-company-earnings-bridge-20261024/research-results.json"
    saved = json.loads(location.read_text(encoding="utf-8"))
    for key in ("source_spec_fingerprint", "implementation_fingerprint"):
        ref = saved[key]
        path = project/ref["path"]
        assert ref["hash_normalization"] == "UTF8_LF_NOT_RAW_OFFICIAL_SOURCE_HASH"
        assert hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == ref["sha256"]
    spec = json.loads((project/saved["source_spec_fingerprint"]["path"]).read_text(encoding="utf-8"))
    for symbol, retained in saved["results"].items():
        specs = [dict(item, fields=spec["common_fields"]+item["extra_fields"]) for item in spec["companies"][symbol]]
        actual = module.research_from_retained_sources(root=Path(raw), specs=specs,
            now=datetime.fromisoformat(retained["observed_at"]))
        assert actual == retained

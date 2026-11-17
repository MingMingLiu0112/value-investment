"""Replay controls; synthetic amounts deliberately differ from retained filings."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from value_investment_agent.application.research import parent_direct_cash_research as subject


NOW = datetime(2028, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def case(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    pages = ["公司代码：600123\n示例股份有限公司\n2026年半年度报告",
             "示例股份有限公司2026年半年度报告\n母公司利润表\n2026年1—6月\n"
             "单位：元 币种：人民币\n项目 附注 2026年半年度 2025年半年度\n"
             "一、营业收入 十九（4） 100.00 90.00\n减：营业成本 十九（4） 60.00 50.00",
             "示例股份有限公司2026年半年度报告\n母公司现金流量表\n2026年1—6月\n"
             "单位：元 币种：人民币\n项目 附注 2026年半年度 2025年半年度\n"
             "一、经营活动产生的现金流量：\n销售商品、提供劳务收到的现金 95.00 80.00\n"
             "购买商品、接受劳务支付的现金 55.00 45.00\n"
             "经营活动现金流入小计 98.00 82.00\n经营活动现金流出小计 68.00 57.00\n"
             "经营活动产生的现金流量净额 30.00 25.00\n二、投资活动产生的现金流量："]
    pdf = runtime / "original.pdf"
    pdf.write_bytes(b"synthetic PDF bytes; extraction isolated in tests")
    original = dict(path="runtime/original.pdf", sha256=sha256(pdf.read_bytes()).hexdigest())
    cash = dict(schema_version="parent-trade-cash-intra-year-reconciliation-v1",
                symbol="600123", scope=subject.SCOPE, currency="CNY", action="no_order",
                formal_eligibility=False, operating_wc_cash_cny=None,
                computed_at="2026-08-30T00:00:00+00:00",
                original_bindings=[dict(original, physical_page=3)],
                period_amounts={"2026H1": dict(customer_cash="95.00", supplier_cash="55.00",
                                               net_operating_cash="30.00", net_trade_cash="40.00",
                                               other_operating_cash="-10.00")})
    receipt = dict(schema_version="parent-trade-accrual-countercheck-v1",
                   symbol="600123", scope="actual_parent_standalone", currency="CNY",
                   period_basis="H1", action="no_order", operating_wc_cash_cny=None,
                   computed_at="2026-08-30T00:01:00+00:00",
                   observed={"2026": dict(revenue="100.00", cost="60.00", received="95.00", paid="55.00")},
                   income_refs=[dict(original, physical_page=2, excerpt=line)
                                for line in pages[1].splitlines()[-2:]])

    def write(name, value):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        (runtime / name).write_bytes(raw)
        return dict(path="runtime/" + name, sha256=sha256(raw).hexdigest())

    def seal():
        receipt["source_cash_countercheck"] = write("cash.json", cash)
        return write("receipt.json", receipt)

    monkeypatch.setattr(subject, "extract_pages", lambda path: pages)
    return dict(root=tmp_path, pages=pages, pdf=pdf, receipt=receipt, cash=cash, seal=seal)


def run(case, **kwargs):
    return subject.read_parent_direct_cash_research(
        root=case["root"], receipt_binding=case["seal"](), evaluated_at=kwargs.get("evaluated_at", NOW))


def test_observed_values_scope_and_exact_source_locators(case):
    result = run(case)
    row, = result["observed"]
    assert {key: row[key] for key in ("symbol", "scope", "currency", "period_start", "period_end")} == {
        "symbol": "600123", "scope": subject.SCOPE, "currency": "CNY",
        "period_start": "2026-01-01", "period_end": "2026-06-30"}
    assert [row[key] for key in ("revenue", "cost", "customer_cash", "supplier_cash", "cfo")] == [
        "100.00", "60.00", "95.00", "55.00", "30.00"]
    assert len(row["source_refs"]["originals"]) == 7
    assert row["classification"] == "FACT"
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


@pytest.mark.parametrize("field", ["revenue", "cost", "received", "paid"])
def test_resealed_receipt_amount_cannot_override_original(case, field):
    case["receipt"]["observed"]["2026"][field] = "999.00"
    with pytest.raises(ValueError, match="ACCRUAL_AMOUNT_CHANGED"):
        run(case)


@pytest.mark.parametrize("field", ["customer_cash", "supplier_cash", "net_operating_cash", "other_operating_cash"])
def test_resealed_cash_receipt_cannot_override_original(case, field):
    case["cash"]["period_amounts"]["2026H1"][field] = "999.00"
    with pytest.raises(ValueError, match="CASH_AMOUNT_CHANGED|CASH_RECONCILIATION_CHANGED"):
        run(case)


@pytest.mark.parametrize("before,after", [
    ("母公司利润表", "合并利润表"),
    ("单位：元", "单位：万元"),
    ("2026年半年度 2025年半年度", "2025年半年度 2026年半年度"),
    ("100.00 90.00", "100.00"),
    ("100.00 90.00", "101.00 90.00"),
])
def test_original_scope_units_period_columns_and_amounts(case, before, after):
    case["pages"][1] = case["pages"][1].replace(before, after)
    with pytest.raises(ValueError, match="PARENT_DIRECT_CASH_"):
        run(case)


def test_original_subtotal_reconciliation(case):
    case["pages"][2] = case["pages"][2].replace("98.00 82.00", "99.00 82.00")
    with pytest.raises(ValueError, match="CFO_SUBTOTAL_MISMATCH"):
        run(case)


def test_original_hash_and_receipt_hash(case):
    binding = case["seal"]()
    case["pdf"].write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        subject.read_parent_direct_cash_research(root=case["root"], receipt_binding=binding, evaluated_at=NOW)
    binding["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        subject.read_parent_direct_cash_research(root=case["root"], receipt_binding=binding, evaluated_at=NOW)


def test_time_identity_and_path(case):
    with pytest.raises(ValueError, match="AWARE_EVALUATION"):
        run(case, evaluated_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="RECEIPT_NOT_AVAILABLE"):
        run(case, evaluated_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    case["pages"][0] = case["pages"][0].replace("600123", "600124")
    with pytest.raises(ValueError, match="SECURITY_IDENTITY_CHANGED"):
        run(case)
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        subject.read_parent_direct_cash_research(root=case["root"],
            receipt_binding=dict(path="../outside.json", sha256="0" * 64), evaluated_at=NOW)


def test_wrong_locator_and_duplicate_table(case):
    case["cash"]["original_bindings"][0]["physical_page"] = 2
    with pytest.raises(ValueError, match="PAGE_CHANGED"):
        run(case)
    case["cash"]["original_bindings"][0]["physical_page"] = 3
    case["pages"].append(case["pages"][2])
    with pytest.raises(ValueError, match="PARENT_TABLE_NOT_UNIQUE"):
        run(case)


def annual_binding(case):
    for i, page in enumerate(case["pages"]):
        case["pages"][i] = (page.replace("年半年度报告", "年年度报告")
                             .replace("年半年度", "年度").replace("1—6月", "1—12月"))
    original = case["cash"]["original_bindings"][0]
    receipt = dict(schema_version="official-report-acquisition-v1", report_kind="annual",
                   status="ORIGINAL_ACQUIRED_NOT_FACT_ADMITTED",
                   fetched_at="2027-04-30T00:00:00+00:00",
                   source=dict(path=original["path"], sha256=original["sha256"], symbol="600123",
                               period="2026-12-31", available_at="2027-04-30T00:00:00+00:00"))
    raw = json.dumps(receipt).encode()
    path = case["root"] / "runtime/annual.json"
    path.write_bytes(raw)
    return dict(path="runtime/annual.json", sha256=sha256(raw).hexdigest())


def test_annual_acquisition_replays_original_and_domain_contract(case):
    from value_investment_agent.domain.valuation.parent_direct_operating_cash import forecast_parent_operating_cash

    result = subject.read_parent_direct_cash_research(root=case["root"],
        receipt_binding=annual_binding(case), evaluated_at=NOW)
    row, = result["observed"]
    assert row["period_end"] == "2026-12-31" and row["revenue"] == "100.00"
    assert row["classification"] == "FACT"
    assert row["source_refs"]["originals"][0]["physical_page"] == 2
    forecast = dict(symbol=row["symbol"], scope=row["scope"], currency="CNY",
                    period_start="2027-01-01", period_end="2027-12-31",
                    classification="FORECAST_ASSUMPTION", revenue="100.00", cost="60.00",
                    other_operating_cash="-10.00", rationale="Constant driver stress",
                    counter_evidence="Settlement timing can change", reopen_condition="New payment evidence")
    assert forecast_parent_operating_cash(historical=row, forecast=forecast)["operating_cash"] == "30.00"


def test_annual_cannot_relabel_h1_as_fy(case):
    binding = annual_binding(case)
    case["pages"][2] = case["pages"][2].replace("1—12月", "1—6月")
    with pytest.raises(ValueError, match="UNIT_OR_PERIOD_COLUMNS_CHANGED"):
        subject.read_parent_direct_cash_research(root=case["root"], receipt_binding=binding, evaluated_at=NOW)


def test_hash_checked_after_pdf_extraction(case, monkeypatch):
    def changing_pdf(path):
        path.write_bytes(b"mutated while extracting")
        return case["pages"]

    monkeypatch.setattr(subject, "extract_pages", changing_pdf)
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        run(case)


@pytest.mark.parametrize("annual", [False, True], ids=["H1", "FY"])
@pytest.mark.parametrize("field", ["revenue", "cost"])
@pytest.mark.parametrize("boundary", ["合并利润表", "（四）合并利润表", "公司负责人：测试人员"])
def test_missing_parent_income_row_cannot_be_taken_after_boundary(case, annual, field, boundary):
    binding = annual_binding(case) if annual else case["seal"]()
    lines = case["pages"][1].splitlines()
    missing = next(line for line in lines if line.startswith(subject.LABELS[field] + " "))
    # Keep exactly the receipt's amount and excerpt after the boundary. A hash-
    # bound matching amount still cannot authenticate a row from another table.
    case["pages"][1] = "\n".join(line for line in lines if line != missing) + "\n" + boundary + "\n" + missing
    with pytest.raises(ValueError, match="ROW_NOT_UNIQUE:" + field):
        subject.read_parent_direct_cash_research(root=case["root"], receipt_binding=binding, evaluated_at=NOW)


@pytest.mark.parametrize("annual", [False, True], ids=["H1", "FY"])
def test_valid_parent_rows_ignore_later_consolidated_rows(case, annual):
    binding = annual_binding(case) if annual else case["seal"]()
    case["pages"][1] += "\n公司负责人：测试人员\n合并利润表\n一、营业收入 999.00 888.00\n减：营业成本 777.00 666.00"
    row, = subject.read_parent_direct_cash_research(
        root=case["root"], receipt_binding=binding, evaluated_at=NOW)["observed"]
    assert (row["revenue"], row["cost"], row["classification"]) == ("100.00", "60.00", "FACT")


def test_parent_header_cannot_be_borrowed_from_next_table(case):
    case["pages"][1] = case["pages"][1].replace("母公司利润表\n", "母公司利润表\n合并利润表\n")
    with pytest.raises(ValueError, match="UNIT_OR_PERIOD_COLUMNS_CHANGED"):
        run(case)


@pytest.mark.parametrize("annual", [False, True], ids=["H1", "FY"])
def test_source_arithmetic_ignores_and_preserves_caller_precision(case, annual):
    from decimal import localcontext
    binding = annual_binding(case) if annual else case["seal"]()
    expected = subject.read_parent_direct_cash_research(
        root=case["root"], receipt_binding=binding, evaluated_at=NOW)
    with localcontext() as context:
        context.prec = 2
        actual = subject.read_parent_direct_cash_research(
            root=case["root"], receipt_binding=binding, evaluated_at=NOW)
        assert actual == expected
        assert context.prec == 2

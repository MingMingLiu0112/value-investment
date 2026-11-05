"""TEST_ONLY fixtures and opt-in public originals; no synthetic PDF claims."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pytest
from value_investment_agent.infrastructure.filings import operating_statement_basis_v1 as m
from value_investment_agent.domain.research.operating_driver_bridge_v1 import build_basis

NAME = "测试经营股份有限公司"
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
def source():
    return dict(symbol="600323", period="2025-06-30", path="source.pdf",
        sha256=hashlib.sha256(b"TEST_ONLY").hexdigest(),
        source_url="https://static.cninfo.com.cn/finalpage/2025-08-20/123456.PDF",
        available_at="2025-08-21T00:00:00+00:00")
def pages():
    return [f"{NAME}\n2025年半年度报告\n公司的中文名称 {NAME}\n证券代码：600323",
        f"合并利润表\n2025年1—6月\n编制单位：{NAME}\n单位：元 币种：人民币\n"
        "项目 附注 2025年半年度 2024年半年度\n"
        "营业收入 七、1 100.00 90.00\n营业成本 七、2 30.00 25.00\n"
        "税金及附加 七、3 3.00 2.00\n销售费用 七、4 4.00 3.00\n"
        "管理费用 七、5 5.00 4.00\n研发费用 七、6 6.00 5.00\n"
        "利润总额 七、7 40.00 35.00\n所得税费用 七、8 8.00 7.00\n"
        "归属于母公司所有者的净利润 七、9 30.00 26.00\n母公司利润表"]
def parse(p):
    return m._parse(p, source())
def test_complete():
    result = parse(pages())
    assert result["gaps"] == []
    assert len(result["evidence"]) == 18
    assert len(build_basis({"evidence": result["evidence"]})["baselines"]) == 2
    assert result["action"] == "no_order"
    assert result["formal_eligibility"] is False
    anchors = {(row["field"], row["scope"], row["period"]): row for row in result["evidence"]
               if row.get("auxiliary_anchor")}
    assert anchors[("tax", "consolidated", "2025-06-30")]["value"] == "8.00"
    assert anchors[("parent_profit", "consolidated_parent", "2025-06-30")]["value"] == "30.00"


def test_auxiliary_anchors_are_optional_and_never_enter_driver_basis():
    p = pages()
    p[1] = p[1].replace("所得税费用 七、8 8.00 7.00\n", "")
    p[1] = p[1].replace("归属于母公司所有者的净利润 七、9 30.00 26.00\n", "")
    result = parse(p)
    assert result["gaps"] == []
    assert len(result["evidence"]) == 14
    assert len(build_basis({"evidence": result["evidence"]})["baselines"]) == 2


def test_parent_cash_rows_require_the_named_parent_cash_flow_statement():
    p = pages()
    p.append(
        f"母公司现金流量表\n2025年1—6月\n编制单位：{NAME}\n单位：元 币种：人民币\n"
        "项目 附注 2025年半年度 2024年半年度\n"
        "经营活动产生的现金流量净额 -20.00 30.00\n"
        "取得投资收益收到的现金 40.00 50.00\n"
        "购建固定资产、无形资产和其他长期资产支付的现金\n5.00 6.00\n"
    )
    result = parse(p)
    rows = [row for row in result["evidence"] if row.get("parent_cash_anchor")]
    assert len(rows) == 6
    assert {(row["field"], row["scope"], row["period"], row["value"]) for row in rows} >= {
        ("parent_cfo", "parent", "2025-06-30", "-20.00"),
        ("parent_investment_cash", "parent", "2025-06-30", "40.00"),
        ("parent_capex", "parent", "2025-06-30", "5.00"),
    }
    assert len(build_basis({"evidence": result["evidence"]})["baselines"]) == 2
@pytest.mark.parametrize("name", ["测试经营母公司有限公司", NAME+"分公司", ""])
def test_preparer_must_be_exact(name):
    p = pages()
    p[1] = p[1].replace("编制单位："+NAME, "编制单位："+name)
    r = parse(p)
    assert any(g["reason"] == "STATEMENT_PREPARER_NOT_EXACT_LEGAL_OWNER" for g in r["gaps"])
    assert r["evidence"] == []
def test_same_line_unit_boundary():
    p = pages()
    p[1] = p[1].replace(NAME+"\n单位", NAME+" 单位")
    assert parse(p)["gaps"] == []
def test_cross_line_amounts_rejected():
    p = pages()
    p[1] = p[1].replace("6.00 5.00", "6.00\n5.00")
    r = parse(p)
    assert any(g["field"] == "research" and g["reason"] == "MISSING_OR_AMBIGUOUS_TWO_PERIOD_AMOUNTS" for g in r["gaps"])
    assert not any(x["field"] == "research" for x in r["evidence"])
    assert build_basis({"evidence": r["evidence"]})["baselines"] == {}
def test_note_wrap_allowed():
    p = pages()
    p[1] = p[1].replace("研发费用 七、6 ", "研发费用\n七、6\n")
    assert parse(p)["gaps"] == []
@pytest.mark.parametrize("old,new,reason", [
    ("研发费用 七、6 6.00 5.00\n", "", "MISSING_FIELD"),
    ("研发费用 七、6 6.00 5.00", "研发费用 七、6 6.00", "MISSING_OR_AMBIGUOUS_TWO_PERIOD_AMOUNTS"),
    ("研发费用 七、6 6.00 5.00", "研发费用 七、6 6.00 5.00\n研发费用 七、6 6.00 5.00", "DUPLICATE_FIELD"),
    ("单位：元", "单位：万元", "EXPLICIT_YUAN_RENMINBI_REQUIRED"),
    ("币种：人民币", "币种：美元", "EXPLICIT_YUAN_RENMINBI_REQUIRED"),
    ("2025年半年度 2024年半年度", "2024年半年度 2025年半年度", "EXPLICIT_ORDERED_PERIOD_COLUMNS_REQUIRED"),
    ("合并利润表", "母公司利润表", "CONSOLIDATED_INCOME_TABLE_MISSING_OR_DUPLICATE"),
])
def test_gaps(old,new,reason):
    p = pages()
    p[1] = p[1].replace(old,new)
    r = parse(p)
    assert any(g["reason"] == reason for g in r["gaps"])
    assert r["complete_periods"] == []
@pytest.mark.parametrize("path", ["/absolute.pdf", "D:/absolute.pdf", "../outside.pdf"])
def test_relative_path_only(tmp_path,path):
    s = source()
    s["path"] = path
    with pytest.raises(ValueError,match="PROJECT_RELATIVE_SOURCE_PATH_REQUIRED"):
        m.load_operating_statement_basis(root=tmp_path,source=s,evaluation_at=NOW)
def test_readonly_fixture(tmp_path,monkeypatch):
    pdf = tmp_path/"source.pdf"
    pdf.write_bytes(b"TEST_ONLY")
    monkeypatch.setattr(m,"validate_pdf_original",lambda p: None)
    monkeypatch.setattr(m,"extract_pages",lambda p,limit: pages())
    def fail(*a,**k):
        pytest.fail("write attempted")
    monkeypatch.setattr(Path,"write_bytes",fail)
    monkeypatch.setattr(Path,"write_text",fail)
    monkeypatch.setattr(Path,"mkdir",fail)
    assert m.load_operating_statement_basis(root=tmp_path,source=source(),evaluation_at=NOW)["gaps"] == []
@pytest.mark.parametrize("symbol,receipt,page", [
    ("600323","runtime/sse-value-research/sse-research-20261102T122836/queue-inputs/enrichment/600323-official-original/receipt.json",99),
    ("603365","runtime/sse-value-auto-refresh/cycle-20261103T011758-94276cc0/batch-1/queue-inputs/enrichment/603365-official-original/receipt.json",68),
])
def test_real_annual_group_owner(symbol,receipt,page,monkeypatch):
    location = os.environ.get("OPERATING_STATEMENT_REAL_ROOT")
    if not location:
        if os.environ.get("OPERATING_STATEMENT_REAL_REQUIRED") == "1":
            pytest.fail("real root required")
        pytest.skip("public original opt-in")
    root = Path(location)
    s = json.loads((root/receipt).read_text(encoding="utf-8"))["source"]
    assert s["symbol"] == symbol
    pdf = root/s["path"]
    before = (pdf.stat().st_mtime_ns,hashlib.sha256(pdf.read_bytes()).hexdigest())
    def fail(*a,**k):
        pytest.fail("write attempted")
    monkeypatch.setattr(Path,"write_bytes",fail)
    monkeypatch.setattr(Path,"write_text",fail)
    monkeypatch.setattr(Path,"mkdir",fail)
    r = m.load_operating_statement_basis(root=root,source=s,evaluation_at=NOW)
    assert r["gaps"] == []
    assert r["status"] == "COMPLETE_SOURCE_BOUND_STATEMENT"
    assert len(r["evidence"]) >= 14
    assert set(build_basis({"evidence": r["evidence"]})["baselines"]) == {"2025-12-31", "2024-12-31"}
    proof = r["owner_proof"]
    assert proof["method"] == "SAME_ANNUAL_FINANCIAL_STATEMENT_GROUP"
    assert 1 <= page-proof["compiler_page"] <= 8
    assert proof["source_binding"] == s
    assert proof["owner_evidence"]["compiler_name"] == r["issuer_name"]
    if symbol == "600323":
        anchors = {(row["field"], row["scope"], row["period"]): row for row in r["evidence"]
                   if row.get("auxiliary_anchor")}
        assert ("tax", "consolidated", "2025-12-31") in anchors
        assert ("parent_profit", "consolidated_parent", "2025-12-31") in anchors
        parent_cash = {(row["field"], row["scope"], row["period"]): row for row in r["evidence"]
                        if row.get("parent_cash_anchor")}
        assert {("parent_cfo", "parent", "2025-12-31"),
                ("parent_investment_cash", "parent", "2025-12-31"),
                ("parent_capex", "parent", "2025-12-31")} <= set(parent_cash)
    print(symbol, "owner page", proof["compiler_page"], "statement page", page, "rows", len(r["evidence"]))
    assert before == (pdf.stat().st_mtime_ns,hashlib.sha256(pdf.read_bytes()).hexdigest())

def annual_pages():
    p = pages()
    p[0] = p[0].replace("半年度", "年度")
    p[1] = p[1].replace("2025年1—6月", "2025年1—12月").replace("年半年度", "年度")
    p[1] = p[1].replace("编制单位："+NAME+"\n", "")
    balance = (f"合并资产负债表\n编制单位：{NAME}\n单位：元 币种：人民币\n"
               "项目 2025年12月31日 2024年12月31日\n"
               "资产总计 100.00 90.00\n负债合计 40.00 35.00\n"
               "所有者权益合计 60.00 55.00\n"
               "负债和所有者权益总计 100.00 90.00")
    return [p[0], balance, p[1]]

def annual_parse(p):
    s = source()
    s["period"] = "2025-12-31"
    return m._parse(p,s)

def test_annual_group_owner_native_evidence():
    r = annual_parse(annual_pages())
    assert r["gaps"] == []
    assert len(r["evidence"]) == 18
    assert r["owner_proof"]["compiler_page"] == 2
    assert r["owner_proof"]["method"] == "SAME_ANNUAL_FINANCIAL_STATEMENT_GROUP"
    assert all(x["owner_proof"] == r["owner_proof"] for x in r["evidence"])

@pytest.mark.parametrize("mutation", ["wrong_name", "wrong_year", "parent", "too_far", "blank_direct", "conflicting_direct", "missing", "duplicate"])
def test_annual_group_cannot_substitute_unproven_owner(mutation):
    p = annual_pages()
    if mutation == "wrong_name":
        p[1] = p[1].replace(NAME,NAME+"子公司")
    elif mutation == "wrong_year":
        p[1] = p[1].replace("2025年", "2023年")
    elif mutation == "parent":
        p[1] = p[1].replace("合并资产负债表", "母公司资产负债表")
    elif mutation == "too_far":
        p[2:2] = ["页眉"] * 8
    elif mutation == "blank_direct":
        p[-1] = p[-1].replace("合并利润表", "合并利润表\n编制单位：")
    elif mutation == "conflicting_direct":
        p[-1] = p[-1].replace("合并利润表", "合并利润表\n编制单位："+NAME+"子公司")
    elif mutation == "missing":
        p.pop(1)
    elif mutation == "duplicate":
        p.insert(2,p[1])
    r = annual_parse(p)
    assert any(g["reason"] == "STATEMENT_PREPARER_NOT_EXACT_LEGAL_OWNER" for g in r["gaps"])
    assert r["evidence"] == []

def test_h1_does_not_inherit_annual_balance_owner():
    p = annual_pages()
    p[0] = pages()[0]
    p[-1] = pages()[1].replace("编制单位："+NAME+"\n","")
    r = parse(p)
    assert any(g["reason"] == "STATEMENT_PREPARER_NOT_EXACT_LEGAL_OWNER" for g in r["gaps"])

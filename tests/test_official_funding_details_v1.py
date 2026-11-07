"""TEST_ONLY text fixtures; opt-in real PDFs are never fabricated."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest
from value_investment_agent.infrastructure.screening import official_funding_details_v1 as m

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def pages():
    return ["""TEST_ONLY
公司代码：600887
公司的中文名称 测试股份有限公司
合并资产负债表
2025 年 12 月 31 日
编制单位：测试股份有限公司
单位：元 币种：人民币
项目 附注 2025 年 12 月 31 日 2024 年 12 月 31 日
资产总计 100.00 90.00
负债合计 60.00 50.00
所有者权益合计 40.00 40.00
合并利润表
""", """七、合并财务报表项目注释
34、1 年内到期的非流动负债
单位：元 币种：人民币
项目 期末数 期初数
1 年内到期的租赁负债 10.00 9.00
1 年内到期的长期借款 20.00 19.00
35、其他应付款
单位：元 币种：人民币
项目 期末余额 期初余额
财务公司吸收成员单位存款 30.00 29.00
36、其他流动负债
单位：元 币种：人民币
项目 期末余额 期初余额
短期应付债券 40.00 39.00
"""]


def pin(path, root):
    return dict(path=str(path.relative_to(root)), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def fixture(tmp_path, monkeypatch, texts=None):
    pdf = tmp_path / "TEST_ONLY.pdf"
    pdf.write_bytes(b"TEST_ONLY_NOT_A_FINANCIAL_ORIGINAL")
    source = dict(symbol="600887", period="2025-12-31", **pin(pdf, tmp_path),
        source_url="https://static.cninfo.com.cn/finalpage/2026-04-30/123.PDF",
        available_at="2026-10-30T12:00:00+00:00")
    monkeypatch.setattr(m, "validate_pdf_original", lambda p: None)
    monkeypatch.setattr(m, "extract_pages", lambda p: texts if texts is not None else pages())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(schema_version=m.VERSION, sources=[source])), encoding="utf-8")
    return manifest, source


def test_equivalent_headers_original_excerpt_and_no_write(tmp_path, monkeypatch):
    path, _ = fixture(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = m.load(tmp_path, pin(path, tmp_path), NOW)
    rows = {r["field_name"]: r for r in result["observations"]}
    assert rows["lease_liabilities_current"]["value"] == "10.00"
    assert rows["long_term_borrowings_current"]["prior_value"] == "19.00"
    assert rows["financial_member_deposits"]["value"] == "30.00"
    assert rows["short_term_bonds"]["value"] == "40.00"
    assert rows["lease_liabilities_current"]["excerpt"].startswith("1 年")
    assert rows["lease_liabilities_current"]["table_header_excerpt"] == "项目 期末数 期初数"
    assert result["status"] == "PARTIAL" and result["interest_bearing_debt"] is None
    assert not result["complete_debt_verified"]
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("old,new", [
    ("项目 期末数 期初数", "项目 期初数 期末数"),
    ("单位：元 币种：人民币", "单位：元 币种：美元"),
    ("单位：元 币种：人民币", "单位：元"),
    ("项目 期末数 期初数", "2024年12月31日\n项目 期末数 期初数"),
    ("2025 年 12 月 31 日", "2025 年 6 月 30 日"),
    ("七、合并财务报表项目注释", "七、母公司财务报表主要项目注释"),
])
def test_bad_context_not_admitted(tmp_path, monkeypatch, old, new):
    texts = [s.replace(old, new) for s in pages()]
    path, _ = fixture(tmp_path, monkeypatch, texts)
    try:
        result = m.load(tmp_path, pin(path, tmp_path), NOW)
    except ValueError:
        return
    assert not any(r["field_name"] == "lease_liabilities_current" for r in result["observations"])


def test_single_column_unknown_not_zero(tmp_path, monkeypatch):
    texts = [s.replace("10.00 9.00", "10.00") for s in pages()]
    path, _ = fixture(tmp_path, monkeypatch, texts)
    result = m.load(tmp_path, pin(path, tmp_path), NOW)
    row = next(r for r in result["observations"] if r["field_name"] == "lease_liabilities_current")
    assert row["value"] is None and row["prior_value"] is None


@pytest.mark.parametrize("key,value", [
    ("sha256", "0"*64),
    ("available_at", "2027-01-01T00:00:00+00:00"),
    ("available_at", "2026-01-01T00:00:00+00:00"),
    ("source_url", "https://example.com/finalpage/2026-04-30/123.PDF"),
    ("period", "2025-06-30"), ("path", "../outside.pdf"),
])
def test_source_guards(tmp_path, monkeypatch, key, value):
    path, source = fixture(tmp_path, monkeypatch)
    source[key] = value
    path.write_text(json.dumps(dict(schema_version=m.VERSION, sources=[source])), encoding="utf-8")
    with pytest.raises(ValueError):
        m.load(tmp_path, pin(path, tmp_path), NOW)


def test_issuer_mismatch_is_retained_as_source_error_not_admitted(tmp_path, monkeypatch):
    path, source = fixture(tmp_path, monkeypatch)
    source["symbol"] = "600519"
    path.write_text(json.dumps(dict(schema_version=m.VERSION, sources=[source])), encoding="utf-8")
    result = m.load(tmp_path, pin(path, tmp_path), NOW)
    assert result["status"] == "UNAVAILABLE"
    assert result["observations"] == []
    assert result["errors"][0]["message"] == "ISSUER_IDENTITY_MISMATCH"


def test_manifest_hash_and_duplicate(tmp_path, monkeypatch):
    path, source = fixture(tmp_path, monkeypatch)
    binding = pin(path, tmp_path)
    path.write_text(json.dumps(dict(schema_version=m.VERSION, sources=[source, source])), encoding="utf-8")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        m.load(tmp_path, binding, NOW)
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE"):
        m.load(tmp_path, pin(path, tmp_path), NOW)


def test_one_unparseable_original_does_not_discard_other_bound_sources(tmp_path, monkeypatch):
    path, source = fixture(tmp_path, monkeypatch)
    second = tmp_path / "SECOND.pdf"
    second.write_bytes(b"TEST_ONLY_SECOND")
    rejected = dict(source, symbol="600888", path="SECOND.pdf",
                    sha256=hashlib.sha256(second.read_bytes()).hexdigest(),
                    source_url="https://static.cninfo.com.cn/finalpage/2026-04-30/124.PDF")
    path.write_text(json.dumps(dict(schema_version=m.VERSION, sources=[source, rejected])), encoding="utf-8")
    original_extract = m.extract_pages
    monkeypatch.setattr(m, "extract_pages", lambda value: (_ for _ in ()).throw(ValueError("PDF_LAYOUT_UNSUPPORTED"))
                        if Path(value).name == "SECOND.pdf" else original_extract(value))
    result = m.load(tmp_path, pin(path, tmp_path), NOW)
    assert result["status"] == "PARTIAL"
    assert result["observations"]
    assert result["errors"] == [dict(symbol="600888", period="2025-12-31", error_type="ValueError",
                                       message="PDF_LAYOUT_UNSUPPORTED",
                                       source_url=rejected["source_url"], sha256=rejected["sha256"])]


def test_bounded_annual_collection_archives_exact_period_only(tmp_path, monkeypatch):
    original = tmp_path / "downloaded.pdf"
    original.write_bytes(b"%PDF-TEST-ONLY")
    fetched = datetime(2026, 11, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(m, "collect_latest_reports", lambda symbols, directory: [
        dict(symbol="600887", report_kind="annual", report_period="2025-12-31",
             source_url="https://static.cninfo.com.cn/finalpage/2026-04-30/123.PDF",
             local_path=str(original), fetched_at=fetched),
        dict(symbol="600888", report_kind="annual", report_period="2024-12-31",
             source_url="https://static.cninfo.com.cn/finalpage/2025-04-30/124.PDF",
             local_path=str(original), fetched_at=fetched),
    ])
    binding = m.collect_annual_sources(tmp_path, "runtime/annual", symbols=["600887", "600888"],
                                       period="2025-12-31", allow_network=True)
    manifest = json.loads((tmp_path / binding["path"]).read_text(encoding="utf-8"))
    assert manifest["collection"]["status"] == "PARTIAL"
    assert [row["symbol"] for row in manifest["sources"]] == ["600887"]
    assert manifest["sources"][0]["path"] == "downloaded.pdf"
    assert manifest["collection"]["failures"][0]["symbol"] == "600888"


@pytest.mark.parametrize("symbols", [[], ["600887"] * 2, ["600887"] * 6, ["not-a-code"]])
def test_bounded_annual_collection_rejects_invalid_budget(tmp_path, symbols):
    with pytest.raises(ValueError):
        m.collect_annual_sources(tmp_path, "runtime/annual", symbols=symbols,
                                 period="2025-12-31", allow_network=True)


def test_real_cached_official_pdfs(tmp_path):
    raw_root = os.environ.get("OFFICIAL_FUNDING_REAL_ROOT")
    if not raw_root:
        if os.environ.get("OFFICIAL_FUNDING_REAL_REQUIRED") == "1":
            pytest.fail("OFFICIAL_FUNDING_REAL_ROOT required")
        pytest.skip("explicit public-original root opt-in")
    root = Path(raw_root)
    originals = [
        ("600519", "0", "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288", "2026-04-17/1225114741.PDF"),
        ("600887", "1", "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac", "2026-04-30/1225259562.PDF"),
    ]
    sources = []
    for symbol, index, digest, url in originals:
        original = root / ("runtime/public-evidence/20261030-a-first/"+index+"/acquisition/original.pdf")
        assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
        # Copies only into isolated TEST output root; originals stay read-only.
        target = tmp_path / (symbol+".pdf")
        target.write_bytes(original.read_bytes())
        sources.append(dict(symbol=symbol, period="2025-12-31", **pin(target, tmp_path),
            source_url="https://static.cninfo.com.cn/finalpage/"+url,
            available_at="2026-10-30T12:00:00+00:00"))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(schema_version=m.VERSION, sources=sources)), encoding="utf-8")
    result = m.load(tmp_path, pin(manifest, tmp_path), NOW)
    rows = {(r["symbol"], r["field_name"]): r for r in result["observations"]}
    for symbol, field, value in [
        ("600519", "financial_deposits_and_interbank", "18038383776.30"),
        ("600519", "lease_liabilities_current", "44206237.05"),
        ("600887", "financial_member_deposits", "908486765.87"),
        ("600887", "short_term_bonds", "9043394520.53"),
        ("600887", "long_term_borrowings_current", "4263076679.33"),
        ("600887", "lease_liabilities_current", "151630797.19"),
    ]:
        assert rows[symbol, field]["value"] == value
    financial = {(r["symbol"], r["field_name"]): r for r in result["financial_observations"]}
    for symbol, field, value in [
        ("600519", "cash", "51690610946.50"),
        ("600887", "cash", "19494920358.00"),
        ("600519", "group_net_profit", "85310324833.67"),
        ("600887", "group_net_profit", "11513910754.00"),
        ("600519", "operating_cash_flow", "61522204989.35"),
        ("600887", "operating_cash_flow", "14343920490.32"),
        ("600519", "total_assets", "303834844021.44"),
        ("600887", "total_assets", "152098516632.34"),
        ("600519", "total_liabilities", "49875590112.37"),
        ("600887", "total_liabilities", "93554239954.18"),
    ]:
        assert financial[symbol, field]["value"] == value
        assert financial[symbol, field]["prior_value"] is not None
    assert not result["complete_debt_verified"]
    (tmp_path / "actual-output.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.parametrize("mutation", ["reverse", "foreign", "blank", "parent", "three_columns"])
def test_financial_cash_requires_original_two_columns(mutation):
    text = pages()[0].replace("资产总计", "货币资金 10.00 9.00\n资产总计")
    if mutation == "reverse":
        text = text.replace("项目 附注 2025 年 12 月 31 日 2024 年 12 月 31 日",
                            "项目 附注 2024 年 12 月 31 日 2025 年 12 月 31 日")
    elif mutation == "foreign":
        text = text.replace("人民币", "美元")
    elif mutation == "blank":
        text = text.replace("货币资金 10.00 9.00", "货币资金 10.00")
    elif mutation == "parent":
        text = text.replace("合并资产负债表", "母公司资产负债表")
    elif mutation == "three_columns":
        text = text.replace("货币资金 10.00 9.00", "货币资金 10.00 9.00 8.00")
    source = dict(symbol="600887", period="2025-12-31", sha256="a"*64)
    assert not any(r["field_name"] == "cash" for r in m._financial_rows([text], source))


def test_group_profit_not_parent_or_attributable_profit():
    text = """合并利润表
单位：元 币种：人民币
项目 附注 2025 年度 2024 年度
一、营业总收入 100.00 90.00
五、净利润（净亏损以“－”号填列） 30.00 20.00
归属于母公司股东的净利润 25.00 15.00
母公司利润表
单位：元 币种：人民币
项目 附注 2025 年度 2024 年度
一、营业收入 80.00 70.00
四、净利润（净亏损以“－”号填列） 28.00 18.00
"""
    source = dict(symbol="600887", period="2025-12-31", sha256="a"*64)
    rows = m._financial_rows([text], source)
    group = [r for r in rows if r["field_name"] == "group_net_profit"]
    assert len(group) == 1 and group[0]["value"] == "30.00"


def test_continuation_foreign_currency_not_inherited():
    texts = ["""合并利润表
单位：元 币种：人民币
项目 附注 2025 年度 2024 年度
一、营业总收入 100.00 90.00
""", """单位：元 币种：美元
五、净利润（净亏损以“－”号填列） 30.00 20.00
"""]
    source = dict(symbol="600887", period="2025-12-31", sha256="a"*64)
    assert not any(r["field_name"] == "group_net_profit" for r in m._financial_rows(texts, source))


def test_merge_annual_manifests_preserves_old_sources_and_rejects_conflict(tmp_path):
    def manifest(name, sources):
        path = tmp_path / name
        path.write_text(json.dumps({"schema_version": m.VERSION, "action": "no_order", "sources": sources,
                                    "collection": {"requested_symbols": [row["symbol"] for row in sources],
                                                   "period": "2025-12-31", "failures": []}}), encoding="utf-8")
        return pin(path, tmp_path)
    common = dict(period="2025-12-31", path="original.pdf", sha256="a" * 64,
                  source_url="https://static.cninfo.com.cn/finalpage/2026-03-01/a.PDF",
                  available_at="2026-03-01T00:00:00+00:00")
    old = manifest("old.json", [dict(common, symbol="600001")])
    new = manifest("new.json", [dict(common, symbol="600002")])
    merged = m.merge_annual_source_manifests(tmp_path, "runtime/merged", existing_binding=old, new_binding=new)
    assert [row["symbol"] for row in m.manifest_sources(tmp_path, merged)] == ["600001", "600002"]
    conflict = manifest("conflict.json", [dict(common, symbol="600001", sha256="b" * 64)])
    with pytest.raises(ValueError, match="ARCHIVED_SYMBOL_SOURCE_CONFLICT"):
        m.merge_annual_source_manifests(tmp_path, "runtime/conflict", existing_binding=old, new_binding=conflict)


def test_manifest_collection_failures_survive_without_creating_source_rows(tmp_path):
    path = tmp_path / "failed.json"
    path.write_text(json.dumps({"schema_version": m.VERSION, "action": "no_order", "sources": [],
                                "collection": {"requested_symbols": ["600003"], "period": "2025-12-31",
                                               "failures": [{"symbol": "600003", "reason": "NOT_FOUND"}]}}), encoding="utf-8")
    result = m.load(tmp_path, pin(path, tmp_path), NOW)
    assert result["source_count"] == 0
    assert result["collection_failures"] == [{"symbol": "600003", "reason": "NOT_FOUND"}]


def test_empty_manifest_without_retained_collection_failure_is_rejected(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"schema_version": m.VERSION, "action": "no_order", "sources": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_MANIFEST"):
        m.load(tmp_path, pin(path, tmp_path), NOW)


def test_manifest_failed_symbols_are_a_valid_continuation_cursor(tmp_path):
    path = tmp_path / "failed.json"
    path.write_text(json.dumps({"schema_version": m.VERSION, "action": "no_order", "sources": [],
                                "collection": {"failures": [{"symbol": "600003", "reason": "NOT_FOUND"}]}}), encoding="utf-8")
    assert m.manifest_failed_symbols(tmp_path, pin(path, tmp_path)) == {"600003"}

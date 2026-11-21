"""TEST_ONLY SSE layouts plus opt-in retained exact-page acceptance."""
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.sse_capital_checkpoint_v1 import (
    parse_sse_capital_checkpoint as parse,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.application.product.common import sha256_file


def sample(symbol="600888"):
    issuer = "测试样本股份有限公司"
    h1 = {
        "1": f"公司代码：{symbol} 公司简称：测试\n{issuer}\n{symbol}\n2026 年半年度报告",
        "6": f"{issuer}2026 年半年度报告\n公司股票简况\n股票种类 股票上市交易所 股票简称 股票代码 变更前股票简称\nA股 上海证券交易所 测试 {symbol} /",
        "42": f"{issuer}2026 年半年度报告\n第六节 股份变动及股东情况\n一、股本变动情况\n(一)股份变动情况表\n1、股份变动情况表\n报告期内，公司股份总数及股本结构未发生变化。\n二、股东情况",
    }
    proposal = {
        "1": f"证券代码：{symbol} 证券简称：测试 公告编号：临 2026-081\n{issuer}\n关于 2026 年中期利润分配预案的公告\n本次利润分配以实施权益分派股权登记日登记的总股本扣除回购专户股份数为基数。\n公司拟向全体股东每股派发现金红利 0.42 元（含税），截至 2026 年 10 月 22 日，公司总股本 6,325,360,667 股，扣除公司回购专户股份 1,800,200 股，以此计算合计拟派发现金红利总额为 2,655,895,396.14 元。",
        "2": f"{issuer}\n董 事 会\n二○二六年十月三十日",
    }
    q3 = {
        "1": f"证券代码：{symbol} 证券简称：测试\n{issuer}\n2026 年第三季度报告",
        "6": (f"{issuer}2026 年第三季度报告\n合并资产负债表\n"
              f"编制单位：{issuer}\n"
              "单位：元 币种：人民币 审计类型：未经审计\n"
              "项目 2026年9月30日 2025年12月31日\n"
              "实收资本（或股本） 6,325,360,667.00 6,325,360,667.00\n"
              "资本公积 12,218,240,548.46 12,262,344,222.29"),
    }
    return h1, proposal, q3


def test_h1_total_structure_statement_has_no_share_quantity():
    h1, _, _ = sample()
    result = parse(h1, symbol="600888", published_date="2026-08-15")
    assert result["kind"] == "H1_REPORT_UNCHANGED"
    assert (result["period_start"], result["period_end"]) == ("2026-01-01", "2026-06-30")
    assert result["unchanged_report_period"] is True
    assert result["ordinary_shares"] is result["issued_shares"] is None
    assert result["ordinary_share_type_continuity_proven"] is False
    assert result["share_scope"] == "TOTAL_ISSUED_SHARES"
    assert result["term_pages"]["unchanged"] == [42]
    assert all(row["excerpt"] in h1[str(row["physical_page"])] for row in result["evidence_refs"])


def test_h1_complete_layout_ignores_contents_and_blank_but_rejects_second_body():
    h1, _, _ = sample()
    h1["2"] = "目录\n第六节 股份变动及股东情况 39"
    h1["3"] = ""
    assert parse(h1, symbol="600888", published_date="2026-08-15")["term_pages"]["unchanged"] == [42]
    h1["43"] = h1["42"]
    with pytest.raises(ValueError, match="SHARE_CHAPTER_REQUIRED"):
        parse(h1, symbol="600888", published_date="2026-08-15")


def test_h1_conflicting_body_statement_rejected():
    h1, _, _ = sample()
    h1["42"] = h1["42"].replace("二、股东情况",
        "报告期内，公司股份总数及股本结构发生变化。\n二、股东情况")
    with pytest.raises(ValueError, match="SHARE_CHANGE_OR_CONFLICT"):
        parse(h1, symbol="600888", published_date="2026-08-15")


def test_proposal_total_issued_not_ordinary_or_implemented():
    _, proposal, _ = sample()
    proposal["1"] += "\n具体财务数据见公司2026年第三季度报告。"
    result = parse(proposal, symbol="600888", published_date="2026-10-30")
    assert result["period_end"] == "2026-10-22"
    assert result["issued_shares"] == "6325360667"
    assert result["treasury_shares"] == "1800200"
    assert result["ordinary_shares"] is None
    assert result["share_scope"] == "TOTAL_ISSUED_SHARES"
    assert result["proposal_only"] is True and result["ordinary_share_type_continuity_proven"] is False
    assert result["action"] == "no_order"
    assert all(row["excerpt"] in proposal[str(row["physical_page"])] for row in result["evidence_refs"])


def test_zero_treasury_is_valid_total_issued_basis():
    _, proposal, _ = sample()
    proposal["1"] = proposal["1"].replace("1,800,200 股", "0 股").replace(
        "2,655,895,396.14 元", "2,656,651,480.14 元")
    result = parse(proposal, symbol="600888", published_date="2026-10-30")
    assert result["treasury_shares"] == "0" and result["ordinary_shares"] is None


@pytest.mark.parametrize("change", [
    lambda p: p.__setitem__("42", p["42"].replace("未发生变化", "发生变化")),
    lambda p: p.__setitem__("42", p["42"] + "\n报告期内，公司股份总数及股本结构未发生变化。"),
    lambda p: p.__setitem__("6", p["6"].replace("上海证券交易所", "深圳证券交易所")),
    lambda p: p.__setitem__("1", p["1"].replace("600888", "600887")),
    lambda p: p.__setitem__("1", p["1"].replace("半年度报告", "半年度报告摘要")),
])
def test_h1_changed_conflicting_wrong_exchange_issuer_or_summary_rejected(change):
    h1, _, _ = sample()
    change(h1)
    with pytest.raises(ValueError):
        parse(h1, symbol="600888", published_date="2026-08-15")


@pytest.mark.parametrize("change", [
    lambda p: p.__setitem__("1", p["1"].replace("6,325,360,667 股", "6,325,360,667 元")),
    lambda p: p.__setitem__("1", p["1"].replace("2,655,895,396.14", "2,655,895,396.15")),
    lambda p: p.__setitem__("1", p["1"].replace("600888", "600887")),
    lambda p: p.__setitem__("1", p["1"] + "\n" + p["1"].split("公司拟向全体股东", 1)[1].join(["公司拟向全体股东", ""])),
])
def test_proposal_wrong_unit_amount_issuer_or_repeated_terms_rejected(change):
    _, proposal, _ = sample()
    change(proposal)
    with pytest.raises(ValueError):
        parse(proposal, symbol="600888", published_date="2026-10-30")


def test_future_report_or_observation_rejected():
    h1, proposal, q3 = sample()
    with pytest.raises(ValueError):
        parse(h1, symbol="600888", published_date="2026-06-29")
    with pytest.raises(ValueError):
        parse(proposal, symbol="600888", published_date="2026-10-21")
    with pytest.raises(ValueError):
        parse(q3, symbol="600888", published_date="2026-09-29")


def test_q3_share_capital_amount_does_not_infer_issued_shares_or_current_continuity():
    _, _, q3 = sample()
    result = parse(q3, symbol="600888", published_date="2026-10-30")
    assert result["kind"] == "Q3_REPORT_EXACT_SHARE_CAPITAL_CNY"
    assert result["period_end"] == "2026-09-30"
    assert result["issued_shares"] is None
    assert result["share_capital_cny"] == "6325360667.00"
    assert result["share_scope"] == "PAID_IN_CAPITAL_AMOUNT_NOT_SHARE_COUNT"
    assert result["statement_scope"] == "CONSOLIDATED_BALANCE_SHEET"
    assert (result["source_currency"], result["source_unit"]) == ("CNY", "CNY")
    assert result["ordinary_shares"] is None and result["exact_share_count"] is False
    assert result["ordinary_share_type_continuity_proven"] is False
    assert result["continuity_after_period_end"] is False
    assert result["proposal_only"] is False and result["action"] == "no_order"
    assert all(row["excerpt"] in q3[str(row["physical_page"])]
               for row in result["evidence_refs"])


@pytest.mark.parametrize("change", [
    lambda p: p.__setitem__("1", p["1"].replace("600888", "600887")),
    lambda p: p.__setitem__("1", p["1"].replace("第三季度报告", "第三季度报告摘要")),
    lambda p: p.__setitem__("6", p["6"].replace("测试样本股份有限公司", "另一测试股份有限公司")),
    lambda p: p.__setitem__("6", p["6"].replace("单位：元", "单位：千元")),
    lambda p: p.__setitem__("6", p["6"].replace("币种：人民币", "币种：美元")),
    lambda p: p.__setitem__("6", p["6"].replace("2026年9月30日", "2026年6月30日")),
    lambda p: p.__setitem__("6", p["6"].replace("实收资本（或股本）", "股本附注")),
    lambda p: p.__setitem__("6", p["6"] + "\n实收资本（或股本） 6,325,360,667.00 6,325,360,667.00"),
])
def test_q3_wrong_issuer_kind_unit_currency_period_field_or_duplicate_rejected(change):
    _, _, q3 = sample()
    change(q3)
    with pytest.raises(ValueError):
        parse(q3, symbol="600888", published_date="2026-10-30")


def test_retained_exact_pages_only_when_explicitly_enabled():
    location = os.environ.get("SSE_CAPITAL_CHECKPOINT_REAL_PAGES")
    if not location:
        pytest.skip("Set SSE_CAPITAL_CHECKPOINT_REAL_PAGES for retained-page acceptance")
    pages = json.loads(Path(location).read_text(encoding="utf-8"))
    h1 = parse(pages["h1"], symbol="600887", published_date="2026-08-15")
    proposal = parse(pages["proposal"], symbol="600887", published_date="2026-10-30")
    assert h1["period_end"] == "2026-06-30" and h1["ordinary_shares"] is None
    assert proposal["period_end"] == "2026-10-22"
    assert proposal["issued_shares"] == "6325360667" and proposal["treasury_shares"] == "1800200"
    assert proposal["ordinary_shares"] is None and proposal["proposal_only"] is True
    assert proposal["proposed_cash_per_share_cny"] == "0.42"


def test_retained_complete_pdfs_only_when_explicitly_enabled():
    h1_path = os.environ.get("SSE_CAPITAL_CHECKPOINT_REAL_H1_PDF")
    proposal_path = os.environ.get("SSE_CAPITAL_CHECKPOINT_REAL_PROPOSAL_PDF")
    if not h1_path or not proposal_path:
        pytest.skip("Set both SSE_CAPITAL_CHECKPOINT_REAL_*_PDF for full-original acceptance")
    assert sha256_file(Path(h1_path)) == "423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2"
    assert sha256_file(Path(proposal_path)) == "e32dfd4a2f8bf61d77d3bc61052ad0ff489b822fcc188ae4e4717933c22609d7"
    h1 = parse(extract_pages(Path(h1_path)), symbol="600887", published_date="2026-08-27")
    proposal = parse(extract_pages(Path(proposal_path)), symbol="600887", published_date="2026-10-30")
    assert h1["term_pages"]["unchanged"] == [42]
    assert h1["ordinary_shares"] is None and h1["unchanged_report_period"] is True
    assert proposal["issued_shares"] == "6325360667"
    assert proposal["treasury_shares"] == "1800200"
    assert proposal["ordinary_shares"] is None and proposal["proposal_only"] is True
    assert proposal["proposed_cash_per_share_cny"] == "0.42"

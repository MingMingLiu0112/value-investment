"""Synthetic source/identity tests; retained originals are replayed separately."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import localcontext
from hashlib import sha256
import json

import pytest

from value_investment_agent.application.research import parent_direct_owner_cash_sources as subject


NOW = datetime(2027, 11, 16, tzinfo=timezone.utc)
ISSUER = "示例股份有限公司"


@pytest.mark.parametrize("change", [None, "unit", "capital_only", "wrong_class", "count", "reconcile", "hash", "duplicate"])
def test_ordinary_share_original_table_and_class_binding(case, change):
    source = case["source"]("2025-12-31")
    table = (f"{ISSUER}2025年年度报告\n股份变动情况表\n单位：股\n"
             "本次变动前 本次变动增减 本次变动后\n三、股份总数 1,000 100 -100 -100 900 100")
    if change == "unit":
        table = table.replace("单位：股", "单位：元")
    if change == "capital_only":
        table = "实收资本（或股本） 900.00 1000.00"
    if change == "reconcile":
        table = table.replace("-100 -100", "-99 -99")
    case["originals"]["2025-12-31.pdf"].append(table)
    if change == "duplicate":
        case["originals"]["2025-12-31.pdf"].append(table)
    path = case["root"] / "runtime/charter.pdf"
    path.write_bytes(b"charter")
    charter = dict(path="runtime/charter.pdf", sha256=sha256(b"charter").hexdigest(),
                   available_at="2027-01-01T00:00:00+00:00")
    text = ISSUER + "\n公司已发行的股份数为900股，均为普通股。"
    if change == "wrong_class":
        text = text.replace("普通股", "优先股")
    if change == "count":
        text = text.replace("900", "901")
    if change == "hash":
        charter["sha256"] = "0" * 64
    case["originals"]["charter.pdf"] = [text]
    def run():
        return subject._ordinary_shares(case["root"], dict(source_binding=source, period_end="2025-12-31"),
                                        charter, ISSUER, NOW)
    if change in {"wrong_class", "count", "reconcile", "hash", "duplicate"}:
        with pytest.raises(ValueError):
            run()
    elif change in {"unit", "capital_only"}:
        assert run() is None
    else:
        result = run()
        assert result["count"] == "900"
        assert result["unit"] == "shares"
        assert result["scope"] == "TOTAL_ISSUED_ORDINARY_SHARES"
        assert result["classification"] == "FACT"
        assert result["period_end"] == "2025-12-31"
        assert len(result["source_refs"]) == 2


def pages_for(period):
    year, month = int(period[:4]), int(period[5:7])
    suffix = {12: "年度", 6: "半年度", 9: "第三季度"}[month]
    report = f"{ISSUER}{year}年{suffix}报告"
    current = f"{year}年{month}月{int(period[-2:])}日"
    income_columns = (f"{year}年度 {year-1}年度" if month == 12 else
                      f"{year}年半年度 {year-1}年半年度" if month == 6 else
                      f"{year}年前三季度（1-9月） {year-1}年前三季度（1-9月）")
    note = "附注 " if month != 9 else ""
    title = lambda name: (f"{report}\n{name}\n{year}年1—{month}月\n"
                          f"编制单位：{ISSUER}\n单位：元 币种：人民币\n项目 {note}{income_columns}\n")
    balance = (f"{report}\n母公司资产负债表\n{current}\n编制单位：{ISSUER}\n单位：元 币种：人民币\n"
               f"项目 {note}{current} {year-1}年12月31日\n货币资金 54.00 41.00\n"
               "资产总计 200.00 150.00\n负债合计 120.00 90.00\n"
               "所有者权益（或股东权益）合计 80.00 60.00\n实收资本（或股本） 20.00 20.00\n"
               "盈余公积 12.00 11.00\n未分配利润 48.00 29.00\n"
               "短期借款 50.00 40.00\n长期借款 10.00 8.00\n"
               "一年内到期的非流动负债 5.00 4.00\n应付债券\n租赁负债 3.00 2.00\n"
               "其他流动负债 4.00 3.00\n公司负责人：某人")
    income = (title("母公司利润表") + "一、营业收入 十九（4） 100.00 90.00\n"
              "减：营业成本 十九（4） 60.00 55.00\n"
              "财务费用 -2.00 -1.00\n其中：利息费用 十九（4） 3.00 4.00\n"
              "利息收入 5.00 5.00\n"
              "四、净利润（净亏损以亏损号填列） 10.00 8.00\n公司负责人：某人")
    cash = (title("母公司现金流量表") + "一、经营活动产生的现金流量：\n"
            "销售商品、提供劳务收到的现金 80.00 70.00\n购买商品、接受劳务支付的现金 50.00 45.00\n"
            "经营活动产生的现金流量净额 20.00 15.00\n二、投资活动产生的现金流量：\n"
            "取得投资收益收到的现金 4.00 3.00\n购建固定资产、无形资产和其他长期资产支付的现金 9.00 6.00\n"
            "收回投资收到的现金 100.00 80.00\n投资支付的现金 100.00 80.00\n"
            "取得子公司及其他营业单位支付的现金净额 1.00\n"
            "投资活动产生的现金流量净额 -5.00 -3.00\n三、筹资活动产生的现金流量：\n"
            "取得借款收到的现金 50.00 30.00\n偿还债务支付的现金 51.00 30.00\n"
            "分配股利、利润或偿付利息支付的现金 1.00 1.00\n筹资活动产生的现金流量净额 -2.00 -1.00\n"
            "四、汇率变动对现金及现金等价物的影响 0.00 0.00\n"
            "五、现金及现金等价物净增加额 13.00 11.00\n加：期初现金及现金等价物余额 40.00 29.00\n"
            "六、期末现金及现金等价物余额 53.00 40.00\n公司负责人：某人")
    return [f"证券代码：600123\n{report}", balance, income, cash,
            f"{report}\n合并所有者权益变动表"]


@pytest.fixture
def case(tmp_path, monkeypatch):
    (tmp_path / "runtime").mkdir()
    originals = {}

    def source(period):
        relative = "runtime/" + period + ".pdf"
        path = tmp_path / relative
        path.write_bytes(period.encode())
        originals[path.name] = pages_for(period)
        return dict(path=relative, sha256=sha256(path.read_bytes()).hexdigest(), period_end=period,
                    available_at="2027-10-30T00:00:00+00:00")

    monkeypatch.setattr(subject, "extract_pages", lambda path: deepcopy(originals[path.name]))
    return dict(root=tmp_path, originals=originals, source=source)


def read(case, sources, **kwargs):
    return subject.read_parent_direct_owner_cash_sources(root=case["root"], symbol="600123",
        issuer_name=ISSUER, sources=sources, evaluated_at=NOW, **kwargs)


@pytest.mark.parametrize("period", ["2025-12-31", "2026-06-30", "2026-09-30"])
def test_real_readers_reconcile_and_preserve_periods_and_unknowns(case, period):
    result = read(case, [case["source"](period)])
    statement, = result["statements"]
    assert statement["scope"] == "ISSUER_PARENT_STANDALONE"
    assert statement["classification"] == "FACT"
    assert all(statement["checks"].values())
    assert statement["cash_flow"]["investment_income_cash_cny"]["current"] == "4.00"
    assert statement["balance_sheet"]["book_equity_cny"]["current"] == "80.00"
    assert statement["income"]["parent_net_profit_cny"]["current"] == "10.00"
    assert statement["income"]["revenue"]["current"] == "100.00"
    assert statement["income"]["revenue"]["comparative"] == "90.00"
    assert statement["income"]["cost"]["current"] == "60.00"
    assert statement["income"]["cost"]["comparative"] == "55.00"
    assert statement["income"]["revenue"]["source_refs"]["physical_page"] == 3
    assert statement["income"]["cost"]["classification"] == "FACT"
    interest = statement["income"]["interest_expense_cny"]
    assert (interest["current"], interest["comparative"]) == ("3.00", "4.00")
    assert interest["accounting_basis"] == "ACCRUAL"
    assert interest["establishes_cash_interest_paid"] is False
    assert interest["source_refs"]["physical_page"] == 3
    assert statement["cash_flow"]["opening_cash_and_equivalents_cny"]["current"] == "40.00"
    assert statement["balance_sheet"]["monetary_funds_cny"]["comparative"] == "41.00"
    assert statement["cash_flow"]["cfo_cny"]["source_refs"]["physical_page"] == 4
    assert {gap["field"] for gap in statement["gaps"]} == {"bonds_payable_cny", "acquisitions_cash_cny"}
    assert result["owner_cash_cny"] is None and result["distribution_capacity_cny"] is None
    assert result["working_capital_cash_component"] is None and result["action"] == "no_order"
    assert result["formal_eligibility"] is False
    if period.endswith("09-30"):
        assert statement["period_basis"] == "YTD_9M"
        assert statement["comparative_flow_end"] == "2025-09-30"
        assert statement["opening_balance_as_of"] == "2025-12-31"


@pytest.mark.parametrize("change", ["issuer", "period", "unit", "consolidated", "columns", "hash", "clock"])
def test_reject_changed_source_identity(case, change):
    source = case["source"]("2025-12-31")
    pages = case["originals"]["2025-12-31.pdf"]
    if change == "issuer":
        pages[1] = pages[1].replace(ISSUER, "别家公司")
    elif change == "period":
        source["period_end"] = "2024-12-31"
    elif change == "unit":
        pages[1] = pages[1].replace("单位：元", "单位：万元")
    elif change == "consolidated":
        pages[1] = pages[1].replace("母公司资产负债表", "合并资产负债表")
    elif change == "columns":
        pages[1] = pages[1].replace("项目 附注 2025年12月31日 2024年12月31日", "项目 附注 2024年12月31日 2025年12月31日")
    elif change == "hash":
        source["sha256"] = "0" * 64
    else:
        source["available_at"] = "2028-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        read(case, [source])


@pytest.mark.parametrize("field", ["balance", "cash"])
def test_reconciliation_rejects_changed_amount(case, field):
    source = case["source"]("2025-12-31")
    pages = case["originals"]["2025-12-31.pdf"]
    if field == "balance":
        pages[1] = pages[1].replace("资产总计 200.00", "资产总计 201.00")
    else:
        pages[3] = pages[3].replace("现金及现金等价物净增加额 13.00", "现金及现金等价物净增加额 14.00")
    with pytest.raises(ValueError, match="RECONCILIATION_CHANGED|BALANCE_EQUATION_CHANGED"):
        read(case, [source])


def test_cross_table_row_is_not_parent_profit(case):
    source = case["source"]("2025-12-31")
    pages = case["originals"]["2025-12-31.pdf"]
    pages[2] = pages[2].replace("四、净利润", "合并利润表\n四、净利润")
    statement = read(case, [source])["statements"][0]
    assert "parent_net_profit_cny" not in statement["income"]
    assert any(g["field"] == "parent_net_profit_cny" for g in statement["gaps"])


@pytest.mark.parametrize("period", ["2025-12-31", "2026-06-30", "2026-09-30"])
@pytest.mark.parametrize("field,label,amounts", [
    ("revenue", "一、营业收入", "100.00 90.00"),
    ("cost", "减：营业成本", "60.00 55.00"),
    ("interest_expense_cny", "其中：利息费用", "3.00 4.00"),
])
@pytest.mark.parametrize("failure", ["single_column", "missing", "duplicate", "after_boundary"])
def test_income_driver_requires_unique_two_column_parent_row(case, period, field, label, amounts, failure):
    source = case["source"](period)
    pages = case["originals"][period + ".pdf"]
    line = label + " 十九（4） " + amounts
    if failure == "single_column":
        pages[2] = pages[2].replace(line, label + " 十九（4） " + amounts.split()[0])
    elif failure == "missing":
        pages[2] = pages[2].replace(line, "")
    elif failure == "duplicate":
        pages[2] = pages[2].replace(line, line + "\n" + line)
    else:
        pages[2] = pages[2].replace(line, "") + "\n合并利润表\n" + line
    statement = read(case, [source])["statements"][0]
    assert field not in statement["income"]
    gap, = [g for g in statement["gaps"] if g["field"] == field]
    assert gap["table"] == "income" and gap["value"] is None
    assert gap["reason"] == ("TWO_PRINTED_COLUMNS_NOT_PROVEN" if failure == "single_column" else "ROW_MISSING_OR_AMBIGUOUS")


def test_low_ambient_precision_is_isolated(case):
    source = case["source"]("2026-09-30")
    expected = read(case, [source])
    with localcontext() as context:
        context.prec = 6
        assert read(case, [source]) == expected
        assert context.prec == 6


def test_duplicate_and_inconsistent_annual_interim_rejected(case):
    annual = case["source"]("2025-12-31")
    with pytest.raises(ValueError, match="DUPLICATE_PERIOD"):
        read(case, [annual, annual])
    interim = case["source"]("2026-06-30")
    with pytest.raises(ValueError, match="CONTINUITY_CHANGED"):
        read(case, [annual, interim])


def test_original_rechecked_after_extraction(case, monkeypatch):
    source = case["source"]("2025-12-31")
    def mutate(path):
        path.write_bytes(b"changed")
        return case["originals"][path.name]
    monkeypatch.setattr(subject, "extract_pages", mutate)
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        read(case, [source])


def test_constraint_replay_does_not_promote_reserve_or_settlement(case, monkeypatch):
    def bound(name, pages):
        path = case["root"] / "runtime" / name
        path.write_bytes(name.encode())
        case["originals"][name] = pages
        return dict(path="runtime/" + name, sha256=sha256(path.read_bytes()).hexdigest(),
                    available_at="2027-10-30T00:00:00+00:00")
    charter = bound("charter.pdf", [ISSUER + "\n第一百五十五条提取规则第一百五十六条\n"
                                    "1、实施现金分配条件条件正文2、利润分配期间间隔"])
    financing = bound("financing.pdf", ["证券代码：600123\n" + ISSUER])
    packet = dict(charter=charter, financing_source=financing,
                  issuer_financing=[dict(code="012345678", principal_cny="100.00", maturity="2027-12-30", physical_page=1)],
                  legal_reserve=dict(fy_pdf="runtime/note.pdf", fy_pdf_sha256="0"*64, fy_page=3))
    path = case["root"] / "runtime/constraint.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    binding = dict(path="runtime/constraint.json", sha256=sha256(path.read_bytes()).hexdigest())
    calls = []
    def replay(**kwargs):
        calls.append(kwargs)
        return [dict(scope="ISSUER_FINANCING_DISCLOSURE", id="test:012345678", period="2027-10-12"),
                dict(scope="ISSUER_ARTICLES_RULE_TEXT", id="wrong-parent-reserve-claim", text="Must not forward")]
    monkeypatch.setattr(subject, "replay_parent_cash_constraint_evidence", replay)
    result = subject._constraints(case["root"], binding, "600123", ISSUER, NOW)
    assert len(calls) == 1 and len(result["charter_rules"]) == 2
    assert result["issued_financing"][0]["outstanding_at_evaluation_cny"] is None
    assert result["issued_financing"][0]["actual_settlement_verified"] is False
    assert result["excluded_parent_claims"][0]["value"] is None
    assert "Must not forward" not in json.dumps(result)


def test_fund_replay_retains_undated_conditional_scope(case, monkeypatch):
    selection = {"receipt": {"path": "runtime/fund.json", "sha256": "0" * 64}}
    evidence = dict(scope="ISSUER_PARENT_UNDATED_COMMITMENT_BOUND",
                    kind="CONDITIONAL_BALANCE_BOUND_NOT_TIMED_CASH_FLOW", text="Conditional unpaid bound, not a dated payment")
    calls = []
    def replay(**kwargs):
        calls.append(kwargs)
        return evidence
    monkeypatch.setattr(subject, "replay_parent_fund_evidence", replay)
    result = read(case, [case["source"]("2025-12-31")], fund_selection=selection)
    assert calls[0]["context"] == dict(symbol="600123", issuer_name=ISSUER)
    assert calls[0]["cutoff"] == NOW
    assert result["fund_commitment_evidence"] == evidence
    assert result["fund_selection"] == selection
    assert result["owner_cash_cny"] is None

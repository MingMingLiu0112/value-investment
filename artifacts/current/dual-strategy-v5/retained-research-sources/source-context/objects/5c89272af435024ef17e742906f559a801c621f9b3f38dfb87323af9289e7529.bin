"""Bounded retained-original Yili factual review; no valuation or admission."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages

VERSION = "yili-current-fact-review-v1"
DEFAULT_OUTPUT = ROOT / "runtime/d2-real-admission-20261011/600887-current-facts-v1"
FY = "runtime/company-research/m1-valuation-filings-20260923/600887/2025-12-31-annual-ef988688acf64ebeafd5ad3da4721c9f3390ae9c204038cd4e1e3ae3b5ec8451.pdf"
H1 = "runtime/company-research/m1-valuation-filings-20260923/600887/2026-06-30-interim-6c456d8e5f19ba114b2cac48595f997612f66b337d294265975ed5eb7c3499ab.pdf"
LIFECYCLE = "runtime/company-research/m1-dividend-lifecycles/20260923T052056Z/600887/"
SOURCES = {
    "fy": ("1225259562", "2026-04-30", FY, "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac"),
    "h1": ("1225511409", "2026-08-27", H1, "423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2"),
    "final": ("1225335436", "2026-05-29", "runtime/company-research/m1-dividend-followup-20260928/600887/yili-fy2025-final-dividend-implementation.pdf", "c8cd69e0a195ec9daa702306a2ba1ebf7cb8b53b1f5cae5d872cd590b0ba3c70"),
    "interim": ("1224859455", "2025-12-09", LIFECYCLE + "yili_fy2025_interim_implementation.pdf", "cb0f2870dd2ed48799ec5c3403c402dc09129270b030b533818ba7b9662f0322"),
    "prior_final": ("1223718270", "2025-05-30", LIFECYCLE + "yili_fy2024_final_implementation.pdf", "94999a4f3f922ab372895488f872b8be864e1f3d5f8c9c78e34d3c3dc6ae0b3f"),
    "approval": ("1225321219", "2026-05-21", "runtime/company-research/yili-dividend-approval-202605/1225321219.pdf", "bda5690cbb6f81b591c7b731f9091d157071abed3054269000b8c690d68a8934"),
    "settlement": ("1225591152", "2026-10-01", "runtime/public-event-followup-20261002/1225591152.pdf", "f59267675689f0d77cc142d91e910e2e839adfc0282a260483e0858cc82a1ba3"),
}
MONEY = re.compile(r"-?\d{1,3}(?:,\d{3})+\.\d{2}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def build() -> dict:
    observed = datetime.now(timezone.utc).isoformat()
    pages, sources, facts = {}, {}, {}
    for key, (ident, published, path, digest) in SOURCES.items():
        original = ROOT / path
        if sha(original) != digest:
            raise ValueError(f"Original hash mismatch: {path}")
        pages[key] = extract_pages(original)
        if "伊利" not in pages[key][0] or "600887" not in compact("".join(pages[key][:7])):
            raise ValueError(f"Issuer mismatch: {path}")
        available = datetime.fromisoformat(published).date().toordinal() + 1
        sources[key] = {
            "id": "cninfo:" + ident, "path": original.as_posix(), "sha256": digest,
            "source_url": f"https://static.cninfo.com.cn/finalpage/{published}/{ident}.PDF",
            "published_date": published,
            "available_at_conservative": datetime.fromordinal(available).strftime("%Y-%m-%dT00:00:00+08:00"),
            "availability_basis": "date_only_next_day_bound_not_intraday_timestamp",
            "current_local_verified_at": observed, "original_retrieved_at": None,
            "parser_version": "existing_infrastructure.filings.pdf_text/PDFium",
        }

    def row(key, source, page, label, expected, periods, scope):
        if len(periods) != len(expected):
            raise ValueError(f"Column-period cardinality mismatch: {key}")
        text = compact(pages[source][page - 1])
        candidates = []
        for match in re.finditer(re.escape(compact(label)), text):
            tail = text[match.end():match.end() + 500]
            numbers = list(MONEY.finditer(tail))[:len(expected)]
            values = [x.group().replace(",", "") for x in numbers]
            if values == expected:
                candidates.append((values, text[match.start():match.end() + numbers[-1].end()]))
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous/wrong original row: {key}, {source}, p{page}")
        values, excerpt = candidates[0]
        facts[key] = {
            "id": key, "label": label, "source_id": sources[source]["id"],
            "source_binding": sources[source], "physical_page": page,
            "statement_scope": scope, "unit": "CNY", "currency": "CNY",
            "columns": [dict(period=period, value=value) for period, value in zip(periods, values)],
            "evidence_excerpt": excerpt,
            "verification": "ORIGINAL_LABEL_ORDERED_CURRENT_AND_COMPARATIVE_COLUMNS_MATCH",
        }
        return [D(v) for v in values]

    fy_periods, h1_periods = ["FY2025", "FY2024"], ["H12026", "H12025"]
    for source, page, periods in [("fy", 7, fy_periods), ("h1", 6, h1_periods)]:
        for key, label, expected in [
            ("revenue", "营业收入", ["115636231250.05", "115393310976.69"] if source == "fy" else ["64330936547.38", "61776746682.68"]),
            ("parent_profit", "归属于上市公司股东的净利润", ["11565166497.81", "8452859993.18"] if source == "fy" else ["5758628097.79", "7200477611.91"]),
            ("ex_nonrecurring_parent_profit", "归属于上市公司股东的扣除非经常性损益的净利润", ["11068321695.12", "6011274945.92"] if source == "fy" else ["5595762517.76", "7016349502.87"]),
        ]:
            row(source + "_" + key, source, page, label, expected, periods, "consolidated_parent_attributable" if "profit" in key else "consolidated")
    row("fy_nonrecurring", "fy", 9, "合计", ["496844802.69", "2441585047.26"], fy_periods, "consolidated_parent_attributable")
    row("h1_nonrecurring", "h1", 7, "合计", ["162865580.03"], ["H12026"], "consolidated_parent_attributable")
    quarters = ["2025Q1", "2025Q2", "2025Q3", "2025Q4"]
    row("fy_quarter_profit", "fy", 8, "归属于上市公司股东的净利润", ["4874104242.93", "2326373368.98", "3225625005.13", "1139063880.77"], quarters, "consolidated_parent_attributable")
    row("fy_quarter_ex_profit", "fy", 8, "归属于上市公司股东的扣除非经常性损益后的净利润", ["4629303049.44", "2387046453.43", "3086431987.78", "965540204.47"], quarters, "consolidated_parent_attributable")
    row("fy_single_parent_profit", "fy", 88, "四、净利润", ["11200348776.89", "13325341479.69"], fy_periods, "listed_parent_only")
    row("h1_single_parent_profit", "h1", 54, "四、净利润", ["9246690145.31", "8554645339.60"], h1_periods, "listed_parent_only")

    cash_values = {
        "fy_consolidated": ("fy", 89, 90, fy_periods, ["14343920490.32", "21739740393.38"], ["3036644156.68", "3978318320.96"], ["-7796324355.55", "-32709427280.73"], ["-13472893729.48", "-7277915908.33"], ["56365507.71", "-17957048.45"], ["-6868932087.00", "-18265559844.13"], ["24546520007.54", "42812079851.67"], ["17677587920.54", "24546520007.54"]),
        "h1_consolidated": ("h1", 55, 56, h1_periods, ["9759147483.18", "2964215363.27"], ["1304262044.68", "1452716041.52"], ["-13195068088.81", "-7482038254.51"], ["-241598720.31", "-3894225979.78"], ["-85791022.96", "86434720.96"], ["-3763310348.90", "-8325614150.06"], ["17677587920.54", "24546520007.54"], ["13914277571.64", "16220905857.48"]),
        "fy_parent": ("fy", 91, 91, fy_periods, ["7150459122.43", "17916866506.69"], ["631984543.41", "775497717.02"], ["6936945467.12", "-26710795490.24"], ["-9154464812.27", "-6247691096.85"], ["65113.83", "158057.52"], ["4933004891.11", "-15041462022.88"], ["8471582485.64", "23513044508.52"], ["13404587376.75", "8471582485.64"]),
        "h1_parent": ("h1", 57, 57, h1_periods, ["35551654301.69", "-2890913995.51"], ["1235902972.58", "237582482.91"], ["-9125896231.66", "1544381443.71"], ["-24890894675.89", "1623504544.86"], ["-22976.75", "51410.90"], ["1534840417.39", "277023403.96"], ["13404587376.75", "8471582485.64"], ["14939427794.14", "8748605889.60"]),
    }
    labels = ["经营活动产生的现金流量净额", "购建固定资产、无形资产和其他长期资产支付的现金", "投资活动产生的现金流量净额", "筹资活动产生的现金流量净额", "汇率变动对现金及现金等价物的影响", "现金及现金等价物净增加额", "期初现金及现金等价物余额", "期末现金及现金等价物余额"]
    fields = ["cfo", "capex", "cfi", "cff", "fx", "movement", "opening_cash_equivalents", "closing_cash_equivalents"]
    calculations = {}

    def value(key, column=0):
        return D(facts[key]["columns"][column]["value"])

    def calculation(key, formula, inputs, result, scope, columns=None):
        calculations[key] = dict(formula=formula, input_fact_ids=inputs, value=str(result), unit="CNY", scope=scope,
                                 input_column_indices=columns or [0] * len(inputs))

    for prefix, specification in cash_values.items():
        source, cfo_page, other_page, periods, *arrays = specification
        scope = "listed_parent_only" if prefix.endswith("parent") else "consolidated"
        for field, label, expected in zip(fields, labels, arrays):
            row(prefix + "_" + field, source, cfo_page if field == "cfo" else other_page, label, expected, periods, scope)
        for col, period in enumerate(periods):
            ids = [prefix + "_" + field for field in ["cfo", "cfi", "cff", "fx", "movement", "opening_cash_equivalents", "closing_cash_equivalents"]]
            cfo, cfi, cff, fx, movement, opening, closing = [value(k, col) for k in ids]
            if cfo + cfi + cff + fx != movement or opening + movement != closing:
                raise ValueError(f"Cash bridge fails: {prefix}, {period}")
            calculation(prefix + "_" + period + "_cash_residual", "opening+CFO+CFI+CFF+FX-closing", ids, opening + cfo + cfi + cff + fx - closing, scope)
            calculation(prefix + "_" + period + "_cash_capex_proxy", "CFO-gross_long_lived_asset_cash_purchases", [prefix + "_cfo", prefix + "_capex"], cfo - value(prefix + "_capex", col), scope + "_not_FCFF_FCFE_or_distributable_cash")
            calculations[prefix + "_" + period + "_cash_residual"]["input_column_indices"] = [col] * len(ids)
            calculations[prefix + "_" + period + "_cash_capex_proxy"]["input_column_indices"] = [col, col]
    for scope in ["consolidated", "parent"]:
        if value("fy_" + scope + "_closing_cash_equivalents") != value("h1_" + scope + "_opening_cash_equivalents"):
            raise ValueError("Cash continuity failed")
    for field in ["parent_profit", "ex_nonrecurring_parent_profit", "single_parent_profit"]:
        ids = ["fy_" + field, "h1_" + field, "h1_" + field]
        calculation("ttm_" + field, "FY2025+H12026-H12025; 2025-07-01..2026-06-30", ids, value(ids[0]) + value(ids[1]) - value(ids[2], 1), facts[ids[0]]["statement_scope"], [0, 0, 1])
    for source in ["fy", "h1"]:
        delta = value(source + "_parent_profit") - value(source + "_ex_nonrecurring_parent_profit")
        if delta != value(source + "_nonrecurring"):
            raise ValueError("Nonrecurring parent reconciliation failed")
        calculation(source + "_profit_minus_ex_profit", "reported_parent_profit-ex_nonrecurring_parent_profit", [source + "_parent_profit", source + "_ex_nonrecurring_parent_profit", source + "_nonrecurring"], delta, "consolidated_parent_attributable")
    for qkey, hkey in [("fy_quarter_profit", "h1_parent_profit"), ("fy_quarter_ex_profit", "h1_ex_nonrecurring_parent_profit")]:
        if value(qkey) + value(qkey, 1) != value(hkey, 1):
            raise ValueError("FY quarterly H1 and later comparative mismatch")
        annual = "fy_parent_profit" if qkey.endswith("quarter_profit") else "fy_ex_nonrecurring_parent_profit"
        if sum(value(qkey, i) for i in range(4)) != value(annual):
            raise ValueError("Quarterly annual sum mismatch")
    for scope in ["consolidated", "parent"]:
        for field in ["cfo", "capex"]:
            ids = ["fy_" + scope + "_" + field, "h1_" + scope + "_" + field]
            calculation("ttm_" + scope + "_" + field, "FY2025+H12026-H12025; same statement scope", ids + [ids[1]], value(ids[0]) + value(ids[1]) - value(ids[1], 1), scope, [0, 0, 1])

    row("h1_monetary_cash", "h1", 48, "货币资金", ["16616742290.33", "19494920358.00"], ["2026-06-30", "2025-12-31"], "consolidated")
    row("h1_parent_monetary_cash", "h1", 50, "货币资金", ["14941770919.14", "13406727376.75"], ["2026-06-30", "2025-12-31"], "listed_parent_only")
    row("short_debt", "h1", 49, "短期借款", ["64677193034.15", "45630626027.83"], ["2026-06-30", "2025-12-31"], "consolidated")
    row("bill_discount_debt", "h1", 148, "票据贴现借款", ["48141014262.49", "36614614803.03"], ["2026-06-30", "2025-12-31"], "consolidated_external_bank_obligation")
    row("h1_asset_impairment", "h1", 52, "资产减值损失", ["-2455875173.02", "-337447486.85"], h1_periods, "consolidated_pre_tax")
    row("h1_inventory_impairment", "h1", 167, "存货跌价损失及合同履约成本减值损失", ["-907520836.34", "-315591928.82"], h1_periods, "consolidated_pre_tax")
    row("h1_goodwill_impairment", "h1", 167, "商誉减值损失", ["-1546544866.49"], ["H12026"], "consolidated_pre_tax")
    row("h1_prior_tax_adjustment", "h1", 169, "调整以前期间所得税的影响", ["450448607.55"], ["H12026"], "consolidated_tax_expense_not_parent_adjustment")
    row("h1_parent_sales_cash", "h1", 57, "销售商品、提供劳务收到的现金", ["58600086377.25", "51741383133.15"], h1_periods, "listed_parent_only")
    row("h1_parent_purchase_cash", "h1", 57, "购买商品、接受劳务支付的现金", ["16440348197.41", "47876131225.54"], h1_periods, "listed_parent_only")
    row("h1_consolidated_purchase_cash", "h1", 55, "购买商品、接受劳务支付的现金", ["42391803459.23", "45485531733.20"], h1_periods, "consolidated")
    row("h1_mixed_distribution_interest", "h1", 56, "分配股利、利润或偿付利息支付的现金", ["6287065552.99", "8142842953.25"], h1_periods, "consolidated_mixed_category")
    row("h1_parent_mixed_distribution_interest", "h1", 57, "分配股利、利润或偿付利息支付的现金", ["6186835910.21", "8155287516.89"], h1_periods, "listed_parent_mixed_category")
    row("fy_parent_investment_income_cash", "fy", 91, "取得投资收益收到的现金", ["5034946747.60", "8502296479.35"], fy_periods, "listed_parent_only")
    row("h1_parent_investment_income_cash", "h1", 57, "取得投资收益收到的现金", ["4783985308.29", "4131426485.74"], h1_periods, "listed_parent_only")
    for key, source, amount, period in [("final_dividend", "final", "5692824600.30", "FY2025_final_paid_2026-06-05"), ("interim_dividend", "interim", "3036173120.16", "FY2025_interim_paid_2025-12-17"), ("prior_final_dividend", "prior_final", "7716940013.74", "FY2024_final_paid_2025-06-06")]:
        row(key, source, 1, "共计派发现金红利", [amount], [period], "listed_parent_external_shareholders_gross_tax")
    row("h1_parent_equity_distribution", "h1", 62, "对所有者（或股东）的分配", ["-5692824600.30"], ["H12026"], "listed_parent_only")
    if value("final_dividend") + value("h1_parent_equity_distribution") != 0:
        raise ValueError("Dividend implementation and parent equity differ")
    calculation("fy2025_plan_dividends", "FY2025_interim+FY2025_final; different payment calendar years", ["interim_dividend", "final_dividend"], value("interim_dividend") + value("final_dividend"), "listed_parent_external_shareholders")
    calculation("calendar2025_paid_dividends", "FY2024_final+FY2025_interim", ["prior_final_dividend", "interim_dividend"], value("prior_final_dividend") + value("interim_dividend"), "listed_parent_external_shareholders")
    calculation("calendar2025_parent_partial_cash_proxy", "parent_CFO+investment_income_cash-gross_capex", ["fy_parent_cfo", "fy_parent_investment_income_cash", "fy_parent_capex"], value("fy_parent_cfo") + value("fy_parent_investment_income_cash") - value("fy_parent_capex"), "partial_cash_proxy_not_distributable_cash")
    calculation("h1_parent_vs_consolidated_cfo_gap", "listed_parent_CFO-consolidated_CFO; not incremental external cash", ["h1_parent_cfo", "h1_consolidated_cfo"], value("h1_parent_cfo") - value("h1_consolidated_cfo"), "cross_scope_difference_not_cash_entitlement")
    calculation("h1_parent_purchase_cash_change", "H12026-H12025; not a complete explanation of CFO", ["h1_parent_purchase_cash", "h1_parent_purchase_cash"], value("h1_parent_purchase_cash") - value("h1_parent_purchase_cash", 1), "listed_parent_only", [0, 1])
    calculation("ttm_reported_minus_ex_parent_profit", "TTM_reported-TTM_ex_nonrecurring", ["fy_parent_profit", "h1_parent_profit", "h1_parent_profit", "fy_ex_nonrecurring_parent_profit", "h1_ex_nonrecurring_parent_profit", "h1_ex_nonrecurring_parent_profit"], D(calculations["ttm_parent_profit"]["value"]) - D(calculations["ttm_ex_nonrecurring_parent_profit"]["value"]), "consolidated_parent_attributable", [0, 0, 1, 0, 0, 1])
    row("settlement_two_issue_amounts", "settlement", 1, "本息兑付总额分别为人民币", ["10031454794.52", "10031454794.52"], ["SCP010_paid_2026-09-29", "SCP011_paid_2026-09-29"], "issuer_disclosed_completed_not_bank_statement")

    text_checks = []
    for source, page, phrases in [
        ("fy", 49, ["不低于75%", "1.22元", "尚需提交"]),
        ("approval", 2, ["股东回报规划", "审议结果：通过"]),
        ("h1", 148, ["公司合并范围内企业之间开具", "向银行贴现取得的款项"]),
        ("final", 1, ["0.90元", "2026/6/5"]),
        ("interim", 1, ["0.48元", "2025/12/17"]),
        ("settlement", 1, ["2026年9月29日", "完成了", "代理划付"]),
    ]:
        text = compact(pages[source][page - 1])
        for phrase in phrases:
            index = text.find(compact(phrase))
            if index < 0:
                raise ValueError(f"Missing semantic source anchor: {source}, {phrase}")
            text_checks.append(dict(source_binding=sources[source], physical_page=page, anchor=phrase, excerpt=text[max(0, index - 80):index + 160]))

    old_path = ROOT / "runtime/yili-cash-capex-review-20261001/result.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    if old.get("schema_version") != "observed-workbench-cutoff-replay-v1":
        raise ValueError("Old review wrapper changed; inspect rather than silently adapt")
    ratios = {
        "h1_ex_profit_yoy": dict(value=str(value("h1_ex_nonrecurring_parent_profit") / value("h1_ex_nonrecurring_parent_profit", 1) - 1), formula="H12026/H12025-1", input_fact_ids=["h1_ex_nonrecurring_parent_profit"], input_column_indices=[0, 1]),
        "discounted_bills_share_of_short_debt": dict(value=str(value("bill_discount_debt") / value("short_debt")), formula="bill_discount_borrowings/short_borrowings; 2026-06-30", input_fact_ids=["bill_discount_debt", "short_debt"], input_column_indices=[0, 0]),
        "fy2025_plan_cash_payout": dict(value=str(D(calculations["fy2025_plan_dividends"]["value"]) / value("fy_parent_profit")), formula="FY2025_interim_and_final/ FY2025_reported_parent_profit", input_fact_ids=["interim_dividend", "final_dividend", "fy_parent_profit"]),
        "calendar2025_parent_partial_proxy_coverage": dict(value=str(D(calculations["calendar2025_parent_partial_cash_proxy"]["value"]) / D(calculations["calendar2025_paid_dividends"]["value"])), formula="(parent_CFO+investment_income_cash-capex)/(FY2024_final+FY2025_interim)", input_fact_ids=["fy_parent_cfo", "fy_parent_investment_income_cash", "fy_parent_capex", "prior_final_dividend", "interim_dividend"]),
    }
    return {
        "schema_version": VERSION, "symbol": "600887", "generated_at": observed,
        "financial_period_end": "2026-06-30", "ttm_period": ["2025-07-01", "2026-06-30"],
        "scope": "CURRENT_REVIEW_OF_RETAINED_DISCLOSURES_NOT_CURRENT_VALUATION_OR_PIT_ADMISSION",
        "source_bindings": list(sources.values()), "facts": list(facts.values()),
        "semantic_source_checks": text_checks, "calculations": calculations, "descriptive_ratios": ratios,
        "old_review_inspected": dict(path=old_path.as_posix(), sha256=sha(old_path), schema_version=old["schema_version"], nested_numeric_keys=[k for k in ["disclosed_metric_review", "reported_cash_proxy"] if k in old], consumed_as_fact_object=False),
        "normalized_parent_profit_cny": None,
        "limitations": [
            "历史扣非不是正常化盈利；商誉/存货减值及税费不直接按税前数加回归母利润。",
            "母公司与合并CFO差异可观察，具体内部结算/融资及现金可取性贡献未建立归属桥。",
            "货币资金与现金等价物差额不全部解释为受限现金；资产负债表现金不净掉外部银行义务。",
            "实施公告与权益减少支持披露层已执行股息，未获得逐笔银行到账凭证；普通/特别分类未知。",
            "75%/1.22元政策已获股东会通过，不是未来可分配现金证明。",
            "6/30余额不能减9/29兑付金额推算期末现金；资金来源和兑付后债务/现金仍未知。",
            "原件可用日与今天核验时点分开；不证明完整事件覆盖或历史同期运行。",
            "未消费旧8%盈利增长/ROE路径，未产生新估值、报价、模型审批或仓位。",
        ],
        "financial_judgment": "PARTIAL_WITH_UNCERTAINTY",
        "model_approved": False, "strict_pit_admitted": False, "price_admitted": False,
        "recommendation": "NO_ACTION", "position_guidance": None, "action": "no_order",
    }


def chinese_report(payload: dict) -> str:
    facts = {f["id"]: f for f in payload["facts"]}
    lines = ["# 伊利600887保留原件当前财务核读", "", "这是今天核验6/30历史披露的事实包，不是10/11新财报或估值准入。action=no_order。", "", "## 原件逐行数据", "", "|事实|范围|期间及金额（元）|官方来源/物理页|", "|---|---|---|---|"]
    for fact in payload["facts"]:
        columns = "；".join(f"{c['period']}={c['value']}" for c in fact["columns"])
        lines.append(f"|{fact['id']}：{fact['label']}|{fact['statement_scope']}|{columns}|{fact['source_id']} p{fact['physical_page']}|")
    lines += ["", "## 确定性计算", "", "|计算|结果（元）|公式|", "|---|---:|---|"]
    for key, calculation in payload["calculations"].items():
        lines.append(f"|{key}|{calculation['value']}|{calculation['formula']}|")
    profit = D(payload["calculations"]["ttm_parent_profit"]["value"])
    ex_profit = D(payload["calculations"]["ttm_ex_nonrecurring_parent_profit"]["value"])
    h1_profit = D(facts["h1_parent_profit"]["columns"][0]["value"])
    h1_ex = D(facts["h1_ex_nonrecurring_parent_profit"]["columns"][0]["value"])
    lines += ["", "## 经济解释", "",
        f"TTM归母利润{profit}元，扣非归母{ex_profit}元；H1报告归母与扣非差仅{h1_profit-h1_ex}元，扣非仍同比下降，不能将下滑全部归为非经常项目。",
        "H1合并CFO增加同时母公司CFO远高于合并；各主体现金桥都对平，但内部现金流不能相加当外部股东新增现金。",
        "短借中存在大量合并内开票、向外部银行贴现融资。合并内部交易抵销不等于银行义务消失，不能剔除这笔负债制造净现金。",
        "商誉减值与存货减值应分别理解：前者挑战历史并购资本回报，后者涉及库存可回收价值；非现金不等于无经济损失。",
        "利润分配政策、实施公告、权益减少与混合股利利息现金行分别列示；FY2025计划分红跨两个支付日历年，不能与日历2025派息混比。",
        "兑付完成已由留存公告核读；资金来源、再融资及兑付后余额未证明，不能沿用缺公告说法，也不能解除流动性/模型门禁。",
        "", "## 限制与下一复核条件", ""]
    lines += ["- " + text for text in payload["limitations"]]
    lines += ["", "下一复核只针对改变扣非/资产回收、母公司与合并现金归属、票据融资到期及兑付后流动性的事实。模型/重大性/价格准入分别审核；本包未签署任何审批。", "", "## 来源绑定", ""]
    lines += [f"- {s['id']}：[官方PDF]({s['source_url']})；{s['path']}；SHA-256 `{s['sha256']}`。" for s in payload["source_bindings"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Verify originals and arithmetic without writing.")
    args = parser.parse_args()
    payload = build()
    if not args.check_only:
        DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=False)
        for name, content in [("facts.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n"), ("report.md", chinese_report(payload))]:
            (DEFAULT_OUTPUT / name).write_text(content, encoding="utf-8")
        manifest = dict(schema_version=VERSION + "-manifest", script=dict(path=Path(__file__).as_posix(), sha256=sha(Path(__file__))), source_bindings=payload["source_bindings"], outputs={name: sha(DEFAULT_OUTPUT / name) for name in ["facts.json", "report.md"]}, action="no_order")
        (DEFAULT_OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status="VERIFIED_RETAINED_FACTS_NOT_ADMITTED", fact_rows=len(payload["facts"]), calculations=len(payload["calculations"]), output=None if args.check_only else DEFAULT_OUTPUT.as_posix(), action="no_order"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

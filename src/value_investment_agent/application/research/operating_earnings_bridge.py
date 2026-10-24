"""Retained-statement operating earnings bridges, not normalized-profit approval."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

from ...infrastructure.filings.pdf_text import extract_pages


SCHEMA = "operating-earnings-quality-bridge-v1"
LABELS = {
    "total_revenue": "一、营业总收入", "total_cost": "二、营业总成本",
    "operating_revenue": "其中：营业收入", "interest_income": "利息收入",
    "cost_of_sales": "其中：营业成本", "taxes_surcharges": "税金及附加",
    "selling": "销售费用", "administration": "管理费用", "research": "研发费用",
    "finance": "财务费用", "interest_expense": "利息支出",
    "commission_expense": "手续费及佣金支出", "other_income": "加：其他收益",
    "investment": "投资收益（", "fair_value": "公允价值变动收益（",
    "credit_impairment": "信用减值损失（", "asset_impairment": "资产减值损失（",
    "disposal": "资产处置收益（", "operating_profit": "三、营业利润",
    "nonoperating_income": "加：营业外收入", "nonoperating_expense": "减：营业外支出",
    "profit_before_tax": "四、利润总额", "income_tax": "减：所得税费用",
    "net_profit": "五、净利润", "parent_profit": "1.归属于母公司股东的净利润",
    "minority_profit": "2.少数股东损益",
    "ex_parent_profit": "归属于上市公司股东的扣除非经常性损益的净利润",
}
COSTS = ("cost_of_sales", "interest_expense", "commission_expense", "taxes_surcharges",
         "selling", "administration", "research", "finance")
GAINS = ("other_income", "investment", "fair_value", "credit_impairment", "asset_impairment", "disposal")
REQUIRED = {"total_revenue", "total_cost", "operating_profit", "nonoperating_income",
            "nonoperating_expense", "profit_before_tax", "income_tax", "net_profit",
            "parent_profit", "minority_profit", "ex_parent_profit", "operating_revenue", "interest_income",
            "cost_of_sales", "taxes_surcharges", "selling", "administration", "research", "finance"}
MONEY = re.compile(r"(?<![\d.])-?\d{1,3}(?:,\d{3})+\.\d{2}(?!\d)")
REPORT_CONTRACTS = {
    ("FY2025", "FY2024"): dict(report_type="ANNUAL", columns=["2025年度", "2024年度"],
        title="2025年年度报告", statement_period="2025年1-12月",
        summary_columns="主要会计数据2025年2024年本期比上年同期增减(%)2023年", monetary_columns=3),
    ("H12026", "H12025"): dict(report_type="INTERIM", columns=["2026年半年度", "2025年半年度"],
        title="2026年半年度报告", statement_period="2026年1-6月",
        summary_columns="主要会计数据本报告期(1-6月)上年同期本报告期比上年同期增减(%)", monetary_columns=2),
}


def _compact(text):
    text = text.replace("－", "-")
    # Preserve numeric column boundaries while joining wrapped Chinese labels.
    text = re.sub(r"(?<=\d)\s+(?=-?\d)", "|", text)
    return re.sub(r"\s+", "", text)


def _number(value):
    if not isinstance(value, str):
        raise ValueError("Amounts must be explicit decimal strings, never missing or booleans")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid statement amount") from error
    if not number.is_finite():
        raise ValueError("Nonfinite statement amount")
    return number


def _source_path(root, binding):
    relative = Path(binding["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Source must be root relative")
    root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
        raise ValueError("Original source drift")
    return path


def _report_contract(spec):
    contract = REPORT_CONTRACTS.get(tuple(spec["periods"]))
    if (contract is None or spec["column_labels"] != contract["columns"]
            or spec.get("report_type", contract["report_type"]) != contract["report_type"]):
        raise ValueError("Report type/period/column contract mismatch")
    return contract


def _summary_profit_row(summary, contract):
    text = summary.replace("（", "(").replace("）", ")")
    start, end = "(一)主要会计数据", "(二)主要财务指标"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Missing/ambiguous summary table boundary")
    table = text.split(start, 1)[1].split(end, 1)[0]
    label, next_row = LABELS["ex_parent_profit"], "经营活动产生的现金流量净额"
    if table.count(label) != 1 or table.count(next_row) != 1 or table.index(label) >= table.index(next_row):
        raise ValueError("Missing/ambiguous complete summary row boundary")
    if contract["summary_columns"] not in table[:table.index(label)]:
        raise ValueError("Summary period/column header mismatch")
    # Match the complete row, including the intervening percentage column and
    # annual third-year amount. Never scan ahead for a second money token.
    body = table.split(label, 1)[1].split(next_row, 1)[0]
    pattern = MONEY.pattern+r"\|"+MONEY.pattern+r"\|[+-]?\d+(?:\.\d+)?"
    if contract["monetary_columns"] == 3:
        pattern += r"\|"+MONEY.pattern
    if re.fullmatch(pattern, body) is None:
        raise ValueError("Incomplete summary profit row")
    return label+body


def extract_statement(*, root: Path, spec: dict) -> dict:
    """Read actual retained PDF amounts, checking issuer, table, columns and scope."""
    contract = _report_contract(spec)
    path = _source_path(root, spec)
    pages = extract_pages(path)
    header = _compact("".join(pages[:8]))
    if spec["symbol"] not in header or spec["issuer"] not in header:
        raise ValueError("Original issuer mismatch")
    if contract["title"] not in header:
        raise ValueError("Original report type/year mismatch")
    statement = _compact("".join(pages[p-1] for p in spec["statement_pages"]))
    if "合并利润表" not in statement:
        raise ValueError("Missing consolidated statement heading")
    statement = statement.split("合并利润表", 1)[1].split("母公司利润表", 1)[0]
    if "单位：元币种：人民币" not in statement:
        raise ValueError("Unsupported statement unit/currency")
    first_label = statement.index("一、营业总收入")
    column_header = statement[:first_label]
    if contract["statement_period"] not in column_header.replace("—", "-").replace("–", "-"):
        raise ValueError("Original statement reporting period mismatch")
    current_label, previous_label = spec["column_labels"]
    if current_label not in column_header or previous_label not in column_header or column_header.index(current_label) >= column_header.index(previous_label):
        raise ValueError("Statement column order mismatch")
    summary = _compact(pages[spec["summary_page"]-1])
    if "ex_parent_profit" in spec["fields"]:
        if contract["title"] not in summary:
            raise ValueError("Original summary report type/year mismatch")
        summary = _summary_profit_row(summary, contract)
    if len(spec["fields"]) != len(set(spec["fields"])) or set(spec["fields"])-set(LABELS):
        raise ValueError("Unknown/duplicate statement field")
    rows = {}
    for field in spec["fields"]:
        text = summary if field == "ex_parent_profit" else statement
        label = LABELS[field]
        if field == "interest_income":
            text = text.split("一、营业总收入", 1)[1].split("二、营业总成本", 1)[0]
        matches = list(re.finditer(re.escape(label), text))
        if len(matches) != 1:
            raise ValueError("Ambiguous/missing original row: " + field)
        match = matches[0]
        tail = text[match.end():]
        # Stop before any subsequent recognized row; blank cells cannot borrow its numbers.
        stops = [tail.find(other) for other in LABELS.values() if other != label and tail.find(other) >= 0]
        tail = tail[:min(stops)] if stops else tail
        values = list(MONEY.finditer(tail))
        if len(values) < 2:
            raise ValueError("Missing explicit comparative amount: " + field)
        values = values[:2]
        excerpt = text[match.start():match.end()+values[-1].end()]
        physical_page = spec["summary_page"] if field == "ex_parent_profit" else next(
            p for p in spec["statement_pages"] if _compact(label) in _compact(pages[p-1]))
        rows[field] = dict(values=[v.group().replace(",", "") for v in values],
            label=label, source_id=spec["source_id"], path=spec["path"], sha256=spec["sha256"],
            source_url=spec["source_url"], physical_page=physical_page, excerpt=excerpt,
            periods=spec["periods"], currency="CNY", unit="CNY",
            scope="CONSOLIDATED_AFTER_TAX_PARENT" if field in {"parent_profit", "ex_parent_profit"} else
                  "CONSOLIDATED_AFTER_TAX_MINORITY" if field == "minority_profit" else
                  "CONSOLIDATED_AFTER_TAX" if field == "net_profit" else "CONSOLIDATED_STATEMENT_LINE",
            original_acquired_at=spec["original_acquired_at"], published_date=spec["published_date"],
            availability_scope="RETAINED_ORIGINAL_RESEARCH_NOT_CONTEMPORANEOUS_PIT_PROOF")
    _source_path(root, spec)
    return dict(symbol=spec["symbol"], periods=spec["periods"], rows=rows)


def build_operating_earnings_bridge(*, annual: dict, interim: dict) -> dict:
    """Use the same contract across issuers; residuals are not assumed missing zeros."""
    if annual["symbol"] != interim["symbol"] or annual["periods"] != ["FY2025", "FY2024"] or interim["periods"] != ["H12026", "H12025"]:
        raise ValueError("Issuer/period mismatch")
    for statement in (annual, interim):
        if not REQUIRED.issubset(statement["rows"]):
            raise ValueError("Missing required original facts")
        for key, row in statement["rows"].items():
            expected_scope = ("CONSOLIDATED_AFTER_TAX_PARENT" if key in {"parent_profit", "ex_parent_profit"} else
                              "CONSOLIDATED_AFTER_TAX_MINORITY" if key == "minority_profit" else
                              "CONSOLIDATED_AFTER_TAX" if key == "net_profit" else "CONSOLIDATED_STATEMENT_LINE")
            if (row["periods"] != statement["periods"] or len(row["values"]) != 2 or row["currency"] != "CNY"
                    or row["unit"] != "CNY" or row["scope"] != expected_scope
                    or not row.get("source_id") or not row.get("sha256") or not row.get("physical_page")):
                raise ValueError("Fact period/unit/scope/source mismatch")
            for value in row["values"]:
                _number(value)
    with localcontext() as context:
        context.prec = 48
        def values(statement, column):
            result = {key: _number(row["values"][column]) for key, row in statement["rows"].items()}
            checks = {
                "profit_before_tax": result["operating_profit"]+result["nonoperating_income"]-result["nonoperating_expense"],
                "net_profit": result["profit_before_tax"]-result["income_tax"],
                "parent_profit": result["net_profit"]-result["minority_profit"],
            }
            if any(result[key] != computed for key, computed in checks.items()):
                raise ValueError("Original statement does not reconcile")
            result["revenue_unallocated"] = result["total_revenue"]-result["operating_revenue"]-result["interest_income"]
            result["cost_unallocated"] = result["total_cost"]-sum(result[key] for key in COSTS if key in result)
            result["operating_unallocated"] = result["operating_profit"]-(result["total_revenue"]-result["total_cost"]+sum(result[key] for key in GAINS if key in result))
            result["nonrecurring_parent_difference"] = result["parent_profit"]-result["ex_parent_profit"]
            return result
        fy, prior_fy, current, prior = values(annual, 0), values(annual, 1), values(interim, 0), values(interim, 1)
        def bridge(left, right, period, statement):
            keys = [("operating_revenue", 1), ("interest_income", 1), ("revenue_unallocated", 1)]
            keys += [(key, -1) for key in COSTS if key in left and key in right]
            keys += [("cost_unallocated", -1)]
            keys += [(key, 1) for key in GAINS if key in left and key in right]
            keys += [("operating_unallocated", 1), ("nonoperating_income", 1), ("nonoperating_expense", -1),
                     ("income_tax", -1), ("minority_profit", -1), ("nonrecurring_parent_difference", -1)]
            dependencies = {
                "revenue_unallocated": ["total_revenue", "operating_revenue", "interest_income"],
                "cost_unallocated": ["total_cost", *[key for key in COSTS if key in left]],
                "operating_unallocated": ["operating_profit", "total_revenue", "total_cost", *[key for key in GAINS if key in left]],
                "nonrecurring_parent_difference": ["parent_profit", "ex_parent_profit"],
            }
            rows = [dict(field=key, current_cny=str(left[key]), comparative_cny=str(right[key]),
                         profit_effect_sign=sign, contribution_cny=str(sign*(left[key]-right[key])),
                         fact_refs=[dict(field=field, **statement["rows"][field]) for field in dependencies.get(key, [key])],
                         classification="EXPLICIT_UNALLOCATED_RESIDUAL_NOT_NORMALIZATION" if "unallocated" in key else
                         "PARENT_NET_NONRECURRING_RECONCILIATION_NOT_PRETAX_ITEM_ALLOCATION" if key == "nonrecurring_parent_difference" else
                         "HISTORICAL_REPORTED_CHANGE_NOT_RECURRING_PARENT_ADJUSTMENT") for key, sign in keys]
            total = sum(Decimal(row["contribution_cny"]) for row in rows)
            actual = left["ex_parent_profit"]-right["ex_parent_profit"]
            if total != actual:
                raise ValueError("Driver bridge residual: inconsistent component coverage")
            return dict(period=period, rows=rows, computed_change_cny=str(total), reported_change_cny=str(actual),
                        arithmetic_residual_cny=str(actual-total),
                        base_ex_parent_profit_cny=str(right["ex_parent_profit"]), current_ex_parent_profit_cny=str(left["ex_parent_profit"]))
        ttm = {key: fy[key]+current[key]-prior[key] for key in fy.keys() & current.keys() & prior.keys()}
        residual_fields = ("revenue_unallocated", "cost_unallocated", "operating_unallocated")
        residual_balances = {name: {key: str(values[key]) for key in residual_fields}
            for name, values in (("FY2025", fy), ("FY2024", prior_fy), ("H12026", current), ("H12025", prior))}
        commercial_fields = ("cost_of_sales", "taxes_surcharges", "selling", "administration", "research")
        commercial = lambda value: value["operating_revenue"]-sum(value[key] for key in commercial_fields)
        return dict(schema_version=SCHEMA, symbol=annual["symbol"], action="no_order",
            scope="HISTORICAL_EARNINGS_DRIVERS_NOT_FORWARD_NORMALIZED_EARNINGS",
            breakdown_status="RECONCILED_WITH_UNALLOCATED_RESIDUALS" if any(
                values[key] != 0 for values in (fy, prior_fy, current, prior) for key in residual_fields)
                else "LISTED_LINES_RECONCILE_NOT_ECONOMIC_COMPLETENESS",
            unallocated_balances_cny=residual_balances,
            h1_change=bridge(current, prior, "H12026_VS_H12025", interim),
            annual_change=bridge(fy, prior_fy, "FY2025_VS_FY2024", annual),
            commercial_subtotal=dict(scope="STATEMENT_SUBTOTAL_BEFORE_FINANCE_IMPAIRMENT_AND_INCOME_TAX_NOT_NORMALIZED",
                formula="operating_revenue-cost_of_sales-taxes_surcharges-selling-administration-research",
                current_cny=str(commercial(current)), comparative_cny=str(commercial(prior)),
                change_cny=str(commercial(current)-commercial(prior)),
                caveat="Not a business-segment result, recurring parent profit, EBIT certification or distributable cash."),
            ttm=dict(period="2025-07-01/2026-06-30", formula="FY2025+H12026-H12025",
                     lines_cny={key: str(value) for key, value in sorted(ttm.items())}),
            original_statements=[annual, interim], normalized_parent_profit_cny=None,
            tax_rate_assumption=None, parent_attribution_assumption=None, normalized_range=None,
            normalization_open_items=[dict(field=key, historical_current_cny=str(current[key]),
                after_tax_parent_adjustment_cny=None, overlap_with_ex_nonrecurring=None,
                recurrence="NOT_ESTABLISHED", proposed_addback_cny=None)
                for key in ("finance", "interest_income", *[key for key in GAINS if key in current], "income_tax")],
            interpretation_limits=["Historical accounting identity is not a sustainable earnings forecast.",
                "Impairment, tax and finance rows have no inferred item-specific after-tax parent attribution.",
                "Unallocated residual zero does not certify blank rows as explicit zero or complete economic disclosure.",
                "Parent-attributable consolidated profit is not parent legal-entity distributable cash.",
                "No impairment addback, equity restoration or change to any valuation/approval is performed."],
            g3_changed=False, price_admitted=False, strategy_admitted=False, normalized_earnings_admitted=False)


def research_from_retained_sources(*, root: Path, specs: list[dict], now: datetime | None = None) -> dict:
    """Read/recompute/final-recheck; return only data, never write current pointers."""
    if len(specs) != 2:
        raise ValueError("Exactly one annual and one interim original required")
    clock = now or datetime.now(timezone.utc)
    if clock.utcoffset() is None:
        raise ValueError("Timezone-aware research observation required")
    for spec in specs:
        # Publication date is not actual acquisition; a date-only conservative
        # bound permits retrospective research, never contemporaneous PIT proof.
        boundary = datetime.fromisoformat(spec["published_date"]+"T00:00:00+08:00")+timedelta(days=1)
        acquired = spec["original_acquired_at"]
        if boundary > clock or (acquired is not None and (
                datetime.fromisoformat(acquired).utcoffset() is None or datetime.fromisoformat(acquired) > clock)):
            raise ValueError("Source unavailable at requested observation")
    statements = [extract_statement(root=root, spec=spec) for spec in specs]
    annual = next(item for item in statements if item["periods"] == ["FY2025", "FY2024"])
    interim = next(item for item in statements if item["periods"] == ["H12026", "H12025"])
    result = build_operating_earnings_bridge(annual=annual, interim=interim)
    result["observed_at"] = clock.isoformat()
    result["source_bindings"] = [{key: spec[key] for key in
        ("source_id", "path", "sha256", "source_url", "published_date", "original_acquired_at")} for spec in specs]
    for spec in specs:
        _source_path(root, spec)
    return result

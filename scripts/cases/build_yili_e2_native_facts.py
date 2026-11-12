from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages

root = Path(__file__).resolve().parents[2]
review = json.loads((root / "runtime/d2-real-admission-20261011/600887-current-facts-v1/facts.json").read_text(encoding="utf-8"))
review_sources = {row["id"]: row for row in review["source_bindings"]}
original = next((root / "runtime/company-research/m1-valuation-filings-20260923/600887").glob("2026-06-30-interim-*.pdf"))
annual = next((root / "runtime/company-research/m1-valuation-filings-20260923/600887").glob("2025-12-31-annual-*.pdf"))
relative = original.relative_to(root).as_posix()
source_hash = hashlib.sha256(original.read_bytes()).hexdigest()
annual_hash = hashlib.sha256(annual.read_bytes()).hexdigest()
assert source_hash == "423af4d63f2b620a03ed9d0080adbb063f3ef14d874abeca8097d0e0d1441ac2"
assert annual_hash == "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac"
assert review_sources["cninfo:1225511409"]["sha256"] == source_hash
assert review_sources["cninfo:1225259562"]["sha256"] == annual_hash
created_at = datetime.now(timezone.utc)
manifest = {
    "schema_version": "first-research-native-facts-v1",
    "symbol": "600887",
    "issuer_name": "内蒙古伊利实业集团股份有限公司",
    "financial_basis": "2026-06-30",
    "generated_at": created_at.isoformat(),
    "action": "no_order",
    "sources": [{
        "id": "cninfo:1225511409",
        "path": relative,
        "sha256": source_hash,
        "symbol": "600887",
        "issuer_name": "内蒙古伊利实业集团股份有限公司",
        "report_period": "2026-06-30",
        "published_date": "2026-08-27",
        "available_at": review_sources["cninfo:1225511409"]["current_local_verified_at"],
        "availability_basis": "CURRENT_LOCAL_VERIFICATION_NOT_HISTORICAL_PIT",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-27/1225511409.PDF",
        "report_title": "2026年半年度报告",
    }, {
        "id": "cninfo:1225259562",
        "path": annual.relative_to(root).as_posix(),
        "sha256": annual_hash,
        "symbol": "600887",
        "issuer_name": "内蒙古伊利实业集团股份有限公司",
        "report_period": "2025-12-31",
        "published_date": "2026-04-30",
        "available_at": review_sources["cninfo:1225259562"]["current_local_verified_at"],
        "availability_basis": "CURRENT_LOCAL_VERIFICATION_NOT_HISTORICAL_PIT",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1225259562.PDF",
        "report_title": "2025年年度报告",
    }],
    "facts": [{
        "id": "revenue-2026-06-30-1225511409",
        "field": "revenue",
        "source_id": "cninfo:1225511409",
        "physical_page": 52,
        "label": "其中：营业收入",
        "excerpt": "其中：营业收入 七（61） 64,330,936,547.38 61,776,746,682.68",
        "value": "64330936547.38",
        "unit": "CNY",
        "scope": "consolidated",
        "period_end": "2026-06-30",
        "column_index": 0,
        "column_periods": ["2026-06-30", "2025-06-30"],
        "column_header": "2026 年半年度 2025 年半年度",
        "header_pages": [52],
        "scope_marker": "合并利润表",
        "number_kind": "money",
    }, {
        "id": "revenue-2025-06-30-1225511409",
        "field": "revenue",
        "source_id": "cninfo:1225511409",
        "physical_page": 52,
        "label": "其中：营业收入",
        "excerpt": "其中：营业收入 七（61） 64,330,936,547.38 61,776,746,682.68",
        "value": "61776746682.68",
        "unit": "CNY",
        "scope": "consolidated",
        "period_end": "2025-06-30",
        "column_index": 1,
        "column_periods": ["2026-06-30", "2025-06-30"],
        "column_header": "2026 年半年度 2025 年半年度",
        "header_pages": [52],
        "scope_marker": "合并利润表",
        "number_kind": "money",
    }, {
        "id": "revenue-2025-12-31-1225259562",
        "field": "revenue",
        "source_id": "cninfo:1225259562",
        "physical_page": 86,
        "label": "其中：营业收入",
        "excerpt": "其中：营业收入 七（61） 115,636,231,250.05 115,393,310,976.69",
        "value": "115636231250.05",
        "unit": "CNY",
        "scope": "consolidated",
        "period_end": "2025-12-31",
        "column_index": 0,
        "column_periods": ["2025-12-31", "2024-12-31"],
        "column_header": "2025 年度 2024 年度",
        "header_pages": [86],
        "scope_marker": "合并利润表",
        "number_kind": "money",
    }],
}
field_labels = {
    "cost": "其中：营业成本",
    "surcharges": "税金及附加",
    "selling": "销售费用",
    "admin": "管理费用",
    "research": "研发费用",
    "pre_tax_profit": "四、利润总额",
    "tax": "减：所得税费用",
    "parent_profit": "1.归属于母公司股东的净利润",
}
for source_id, pdf, first_page, header, periods in (
    ("cninfo:1225511409", original, 52, "2026 年半年度 2025 年半年度", ("2026-06-30", "2025-06-30")),
    ("cninfo:1225259562", annual, 86, "2025 年度 2024 年度", ("2025-12-31", "2024-12-31")),
):
    pages = extract_pages(pdf)
    for field, prefix in field_labels.items():
        matching = []
        for page in (first_page, first_page + 1):
            matching.extend((page, line.strip()) for line in pages[page-1].splitlines()
                if line.strip().startswith(prefix))
        if len(matching) != 1:
            raise ValueError((source_id, field, matching))
        page, line = matching[0]
        values = re.findall(r"(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)", line)
        if len(values) != 2:
            raise ValueError((source_id, field, line, values))
        for column, period in enumerate(periods[:2 if source_id.endswith("11409") else 1]):
            manifest["facts"].append({
                "id": f"{field}-{period}-{source_id.split(':')[1]}",
                "field": field,
                "source_id": source_id,
                "physical_page": page,
                "label": prefix,
                "excerpt": line,
                "value": values[column].replace(",", ""),
                "unit": "CNY",
                "scope": "consolidated_parent" if field == "parent_profit" else "consolidated",
                "period_end": period,
                "column_index": column,
                "column_periods": list(periods),
                "column_header": header,
                "header_pages": list(range(first_page, page + 1)),
                "scope_marker": "合并利润表",
                "number_kind": "money",
            })
manifest["facts"].extend([
    {
        "id": "start_book_equity-2026-06-30-1225511409",
        "field": "start_book_equity",
        "source_id": "cninfo:1225511409",
        "physical_page": 49,
        "label": "归属于母公司所有者权益（或股东权益）合计",
        "excerpt": "归属于母公司所有者权益（或股东权益）合计 53,711,364,981.99 54,655,690,475.89",
        "value": "53711364981.99",
        "unit": "CNY",
        "scope": "consolidated_parent_equity",
        "period_end": "2026-06-30",
        "column_index": 0,
        "column_periods": ["2026-06-30", "2025-12-31"],
        "column_header": "2026 年 6 月 30 日 2025 年 12 月 31 日",
        "header_pages": [48, 49],
        "scope_marker": "合并资产负债表",
        "number_kind": "money",
    },
    {
        "id": "ordinary_shares-2026-06-30-1225511409",
        "field": "ordinary_shares",
        "source_id": "cninfo:1225511409",
        "physical_page": 66,
        "label": "总股本",
        "excerpt": "总股本变为\n6,325,360,667 股。",
        "value": "6325360667",
        "unit": "shares",
        "scope": "issued_ordinary_shares",
        "period_end": "2026-06-30",
        "column_index": 0,
        "column_periods": ["2026-06-30"],
        "column_header": "2026 年半年度报告",
        "header_pages": [66],
        "scope_marker": "2025 年，公司根据",
        "number_kind": "shares",
    },
])
for source_id, pdf, page, periods in (
    ("cninfo:1225511409", original, 173, ("2026-06-30", "2025-06-30")),
    ("cninfo:1225259562", annual, 210, ("2025-12-31", "2024-12-31")),
):
    text = extract_pages(pdf)[page - 1]
    for field, label in (
        ("depreciation", "固定资产折旧、油气资产折耗、生产性生物资产折旧"),
        ("amortization", "使用权资产摊销"),
        ("amortization", "无形资产摊销"),
        ("amortization", "长期待摊费用摊销"),
    ):
        matching = [line.strip() for line in text.splitlines() if line.strip().startswith(label)]
        if len(matching) != 1:
            raise ValueError((source_id, label, matching))
        line = matching[0]
        values = re.findall(r"(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)", line)
        if len(values) != 2:
            raise ValueError((source_id, label, line, values))
        for column, period in enumerate(periods[:2 if source_id.endswith("11409") else 1]):
            manifest["facts"].append({
                "id": f"{field}-{label[:4]}-{period}-{source_id.split(':')[1]}",
                "field": field,
                "source_id": source_id,
                "physical_page": page,
                "label": label,
                "excerpt": line,
                "value": values[column].replace(",", ""),
                "unit": "CNY",
                "scope": "consolidated",
                "period_end": period,
                "column_index": column,
                "column_periods": list(periods),
                "column_header": "补充资料 本期金额 上期金额",
                "header_pages": [page],
                "scope_marker": "现金流量表补充资料",
                "number_kind": "money",
            })
for source_id, page, label, excerpt, header, periods, values in (
    ("cninfo:1225511409", 6,
        "归属于上市公司股东的扣除非经常性损益的净利润",
        "归属于上市公司股东的扣除非经常性损益的净利润 5,595,762,517.76 7,016,349,502.87",
        "本报告期（1－6月） 上年同期",
        ("2026-06-30", "2025-06-30"), ("5595762517.76", "7016349502.87")),
    ("cninfo:1225259562", 7,
        "归属于上市公司股东的扣除非\n经常性损益的净利润",
        "归属于上市公司股东的扣除非\n经常性损益的净利润\n11,068,321,695.12 6,011,274,945.92",
        "2025年 2024年",
        ("2025-12-31", "2024-12-31"), ("11068321695.12", "6011274945.92")),
):
    for column, period in enumerate(periods[:2 if source_id.endswith("11409") else 1]):
        manifest["facts"].append({
            "id": f"ex_parent_profit-{period}-{source_id.split(':')[1]}",
            "field": "ex_parent_profit",
            "source_id": source_id,
            "physical_page": page,
            "label": label,
            "excerpt": excerpt,
            "value": values[column],
            "unit": "CNY",
            "scope": "consolidated_parent",
            "period_end": period,
            "column_index": column,
            "column_periods": list(periods),
            "column_header": header,
            "header_pages": [page],
            "scope_marker": "七、公司主要会计数据和财务指标" if page == 6 else "七、近三年主要会计数据和财务指标",
            "number_kind": "money",
        })
output = root / "runtime/e2-first-input-600887-20261112" / f"native-facts-{created_at.strftime('%Y%m%dT%H%M%S%fZ')}.json"
output.parent.mkdir(parents=True, exist_ok=True)
with output.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(output.relative_to(root).as_posix(), hashlib.sha256(output.read_bytes()).hexdigest())

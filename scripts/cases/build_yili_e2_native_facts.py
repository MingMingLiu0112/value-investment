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
output = root / "runtime/e2-first-input-600887-20261112" / f"native-facts-{created_at.strftime('%Y%m%dT%H%M%S%fZ')}.json"
output.parent.mkdir(parents=True, exist_ok=True)
with output.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(output.relative_to(root).as_posix(), hashlib.sha256(output.read_bytes()).hexdigest())

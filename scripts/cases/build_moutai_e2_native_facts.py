"""Build source-bound 600519 E2 facts from retained official reports, or fail closed."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.infrastructure.filings.first_research_fact_replay_v2 import replay_first_research_facts

REPORTS = (
    ("cninfo:1225114741", "runtime/public-evidence/20261030-a-first/0/acquisition", "original.pdf", "2025-12-31", "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288", 61, 115, ("2025-12-31", "2024-12-31")),
    ("cninfo:1225475868", "runtime/value-d2-600519-20261110/h12026-20261110T131035Z", "original-retry-2.pdf", "2026-06-30", "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6", 30, 81, ("2026-06-30", "2025-06-30")),
)
MONEY = re.compile(r"(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)")
FIELDS = {"revenue": "其中：营业收入", "cost": "其中：营业成本", "surcharges": "税金及附加", "selling": "销售费用", "admin": "管理费用", "research": "研发费用", "pre_tax_profit": "四、利润总额", "tax": "减：所得税费用", "parent_profit": "1.归属于母公司股东的净利润"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(pages: list[str], page_numbers: tuple[int, ...], label: str) -> tuple[int, str, list[str]]:
    hits = []
    for page in page_numbers:
        lines = pages[page - 1].splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith(label):
                excerpt = "\n".join(lines[i:i + 3])
                numbers = MONEY.findall(line)
                if len(numbers) != 2:
                    numbers = MONEY.findall(excerpt)
                hits.append((page, line.strip() if len(MONEY.findall(line)) == 2 else excerpt.strip(), numbers[:2]))
    if len(hits) != 1 or len(hits[0][2]) != 2:
        raise ValueError(f"missing/ambiguous {label} on physical pages {page_numbers}: {hits}")
    return hits[0]


def main() -> None:
    now = datetime.now(timezone.utc)
    manifest = {"schema_version": "first-research-native-facts-v2", "symbol": "600519", "issuer_name": "贵州茅台酒股份有限公司", "financial_basis": "2026-06-30", "generated_at": now.isoformat(), "action": "no_order", "sources": [], "facts": []}
    missing = []

    def add(field, source_id, pages, page_numbers, label, periods, header, scope="consolidated", unit="CNY", kind="money", marker="合并利润表", columns=None):
        try:
            page, excerpt, values = row(pages, page_numbers, label)
            for column in (columns if columns is not None else range(2)):
                manifest["facts"].append({"id": f"{field}-{label[:4]}-{periods[column]}-{source_id.split(':')[1]}", "field": field, "source_id": source_id, "physical_page": page, "label": label, "excerpt": excerpt, "value": values[column].replace(",", ""), "unit": unit, "scope": scope, "period_end": periods[column], "column_index": column, "column_periods": list(periods), "column_header": header, "header_pages": list(range(page_numbers[0], page + 1)), "scope_marker": marker, "number_kind": kind})
        except ValueError as exc:
            missing.append(f"{source_id} {field}: {exc}")

    for source_id, directory, filename, period, expected_hash, profit_page, cash_page, periods in REPORTS:
        base = ROOT / directory
        pdf = base / filename
        receipt = json.loads((base / "receipt.json").read_text(encoding="utf-8"))
        source = receipt["source"]
        if digest(pdf) != expected_hash or source["sha256"] != expected_hash or source["symbol"] != "600519" or source["period"] != period or receipt["source_id"] != source_id or not source.get("available_at") or not receipt.get("fetched_at"):
            raise ValueError(f"source/hash/period/retrieval mismatch: {source_id}")
        index_bindings = receipt.get("index_bindings", [])
        if not index_bindings:
            raise ValueError(f"missing issuer identity index: {source_id}")
        identity_found = False
        for binding in index_bindings:
            index_path = ROOT / binding["path"]
            if digest(index_path) != binding["sha256"]:
                raise ValueError(f"index hash mismatch: {index_path}")
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for item in index.get("announcements", []):
                if item.get("announcementId") == source_id.split(":")[1] and item.get("secCode") == "600519" and item.get("orgId") == "gssh0600519":
                    identity_found = True
        if not identity_found:
            raise ValueError(f"issuer identity not verified: {source_id}")
        pages = extract_pages(pdf)
        cover = pages[0]
        if "贵州茅台酒股份有限公司" not in cover or "600519" not in cover or ("2025 年年度报告" if period == "2025-12-31" else "2026 年半年度报告") not in cover:
            raise ValueError(f"PDF cover issuer/period mismatch: {source_id}")
        manifest["sources"].append({"id": source_id, "kind": "official_issuer_filing", "path": source["path"], "sha256": expected_hash, "symbol": "600519", "issuer_name": "贵州茅台酒股份有限公司", "issuer_short_name": "贵州茅台", "issuer_identity": {"venue": "CNINFO", "security_code": "600519", "organization_id": "gssh0600519"}, "report_period": period, "published_date": receipt["published_date"], "available_at": source["available_at"], "retrieved_at": receipt["fetched_at"], "availability_basis": "CURRENT_LOCAL_VERIFICATION_NOT_HISTORICAL_PIT", "source_url": source["source_url"], "report_title": "2025年年度报告" if period == "2025-12-31" else "2026年半年度报告", "organization_id": "gssh0600519", "identity_index_binding": {"path": index_bindings[0]["path"], "sha256": index_bindings[0]["sha256"]}, "identity_available_at": index_bindings[0]["metadata"]["acquired_at"]})
        header = "2025 年度 2024 年度" if period == "2025-12-31" else "2026 年半年度 2025 年半年度"
        columns = (0,) if period == "2025-12-31" else (0, 1)
        for field, label in FIELDS.items():
            add(field, source_id, pages, (profit_page, profit_page + 1), label, periods, header, "consolidated_parent" if field == "parent_profit" else "consolidated", columns=columns)
        for field, label in (("depreciation", "固定资产折旧、油气资产折耗"), ("amortization", "使用权资产摊销"), ("amortization", "无形资产摊销"), ("amortization", "长期待摊费用摊销")):
            add(field, source_id, pages, (cash_page - 1, cash_page), label, periods, "补充资料 本期金额 上期金额", marker="现金流量表补充资料", columns=columns)
        add("ex_parent_profit", source_id, pages, (6 if period == "2025-12-31" else 5,), "归属于上市公司股东的扣除非", periods, header, "consolidated_parent", marker="主要会计数据和财务指标", columns=columns)
        for fact in manifest["facts"]:
            if fact["source_id"] == source_id and fact["field"] == "ex_parent_profit":
                fact["label"] = "\n".join(fact["excerpt"].splitlines()[:2])
                amount_line = fact["excerpt"].splitlines()[2]
                amount_matches = list(MONEY.finditer(amount_line))
                if len(amount_matches) < 2:
                    missing.append(f"{source_id} ex_parent_profit: two monetary comparative columns absent")
                else:
                    fact["excerpt"] = fact["label"] + "\n" + amount_line[:amount_matches[1].end()]
                fact["column_header"] = "2025年 2024年" if period == "2025-12-31" else "本报告期 （1－6月） 上年同期"
        if period == "2026-06-30":
            add("start_book_equity", source_id, pages, (25, 26, 27, 28), "归属于母公司所有者权益", (period, "2025-12-31"), "2026 年 6 月 30 日 2025 年 12 月 31 日", "consolidated_parent_equity", marker="合并资产负债表", columns=(0,))
            share_line = "公司股份总数由 1,252,270,215 股减少至 1,250,081,601 股。"
            share_label = "股份总数由 1,252,270,215 股减少至"
            p5 = "期末总股本 1,250,081,601.00 1,252,270,215.00 -0.17"
            p22 = "三、股份总\n数\n1,252,270,215 100 -2,188,614 -2,188,614 1,250,081,601 100"
            if (share_line not in pages[22] or p5 not in pages[4] or p22 not in "\n".join(pages[21].splitlines())
                    or "截至 2026 年 6 月\n30 日，公司总股本为 125,008.16 万股" not in "\n".join(pages[40].splitlines())
                    or "减：库存股 38 120,112,601.53" not in pages[26]):
                missing.append("cninfo:1225475868 ordinary_shares: p5/p22/p23/p27/p41 period, cancellation, issued-total, or treasury cross-check failed")
            else:
                manifest["facts"].append({"id": "ordinary_shares-2026-06-30-1225475868", "field": "ordinary_shares", "source_id": source_id, "physical_page": 23, "label": share_label, "excerpt": share_line, "value": "1250081601", "unit": "shares", "scope": "issued_ordinary_shares", "period_end": period, "column_index": 0, "column_periods": [period], "column_header": "2026 年半年度报告", "header_pages": [23], "scope_marker": "完成注销", "number_kind": "shares"})
    required = {(field, period) for field in FIELDS | {"depreciation": "", "amortization": "", "ex_parent_profit": ""} for period in ("2025-12-31", "2026-06-30", "2025-06-30")}
    actual = {(fact["field"], fact["period_end"]) for fact in manifest["facts"]}
    missing.extend(f"missing {field} {period}" for field, period in sorted(required - actual))
    # The native replay contract checks semantic labels, not just extracted amounts.
    # The report splits the adjusted-profit label across lines, and its balance
    # sheet calls issued capital 实收资本（或股本） rather than a share-total label.
    for fact in manifest["facts"]:
        if fact["field"] == "ex_parent_profit" and "扣除非经常性损益" not in re.sub(r"\s+", "", fact["label"]):
            missing.append(f"{fact['source_id']} ex_parent_profit {fact['period_end']}: full adjusted-profit label is split across PDF lines; native replay label is incomplete")
    for field, scope, unit in (("start_book_equity", "consolidated_parent_equity", "CNY"), ("ordinary_shares", "issued_ordinary_shares", "shares")):
        matches = [f for f in manifest["facts"] if f["field"] == field and f["period_end"] == "2026-06-30" and f["scope"] == scope and f["unit"] == unit]
        if len(matches) != 1:
            missing.append(f"capital contract {field} at valuation_date 2026-06-30 scope={scope} unit={unit}")
    if missing:
        raise ValueError("E2 facts incomplete; no artifact written:\n" + "\n".join(missing))
    output = ROOT / "runtime/e2-first-input-600519-20261117" / f"native-facts-{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(".pending")
    try:
        with pending.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        try:
            replay_first_research_facts(root=ROOT, binding={"path": pending.relative_to(ROOT).as_posix(), "sha256": digest(pending)}, now=now)
        except ValueError as error:
            low, high = 1, len(manifest["facts"])
            while low < high:
                middle = (low + high) // 2
                probe = dict(manifest, facts=manifest["facts"][:middle])
                pending.write_text(json.dumps(probe, ensure_ascii=False), encoding="utf-8")
                try:
                    replay_first_research_facts(root=ROOT, binding={"path": pending.relative_to(ROOT).as_posix(), "sha256": digest(pending)}, now=now)
                    low = middle + 1
                except ValueError:
                    high = middle
            raise ValueError(f"native replay failed at {manifest['facts'][low-1]['id']}: {error}") from error
        pending.rename(output)
    finally:
        pending.unlink(missing_ok=True)
    print(output.relative_to(ROOT).as_posix(), digest(output))


if __name__ == "__main__":
    main()

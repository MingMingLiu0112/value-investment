#!/usr/bin/env python3
"""Build a bounded debt and liquidity review for 600519 from issuer-report facts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "runtime/company-research"
SOURCES = {
    "balance_scope": (RESEARCH / "600519-balance-scope-20260909T124526091284Z/evidence.json", "42aeeabedb74c3d89e579b804d41ebf8060171b01b20cc91146133a9a7ad10f8"),
    "financial_assets": (RESEARCH / "600519-financial-asset-inventory-20260909T114226391473Z/evidence.json", "e19a31fb54ecd711ee9b7f82eac1880a692aca3dfdf786f006beae0ee2091116"),
    "lease": (RESEARCH / "600519-lease-model-20260909T122451598326Z/evidence.json", "96ae938f9028f1a1286055f582a2a28d75c486fb57799a0e06c1b56aa98ac361"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pinned(name: str) -> tuple[dict, dict]:
    path, expected = SOURCES[name]
    if digest(path) != expected:
        raise ValueError(f"Pinned evidence changed: {path}")
    return json.loads(path.read_text(encoding="utf-8")), {"path": str(path.relative_to(ROOT)), "sha256": expected}


def build() -> dict:
    balance, balance_ref = read_pinned("balance_scope")
    assets, assets_ref = read_pinned("financial_assets")
    lease, lease_ref = read_pinned("lease")
    totals = balance["book_control_totals"]
    groups = balance["group_subtotals"]
    if (totals["liabilities"] != "46954432394.95"
            or groups["liability:financial_external_claim"] != "25426316668.17"
            or groups["liability:lease_debt"] != "243684868.06"):
        raise ValueError("Balance-sheet classification changed")
    if (assets["totals"]["closing"]["selected_financial_assets"] != "204662945136.77"
            or assets["restricted_cash_subset"] != "8358830124.37"):
        raise ValueError("Financial-asset inventory changed")
    if lease["liability_rollforward"]["closing"] != "243684868.06":
        raise ValueError("Lease liability extract changed")
    nonblank_liability_ids = {row["id"] for row in balance["rows"] if row["side"] == "liability"}
    if {"current_lease", "noncurrent_lease"} - nonblank_liability_ids:
        raise ValueError("Lease rows are missing")

    return {
        "symbol": "600519",
        "review_version": "moutai-resilience-review-v1",
        "as_of": "2026-09-18",
        "period_end": "2026-06-30",
        "scope": "Consolidated reported balance-sheet classification, lease liabilities and financial-asset constraints; not a debt-free certification or liquidity stress test.",
        "evidence": {"balance_scope": balance_ref, "financial_assets": assets_ref, "lease": lease_ref},
        "facts": {
            "consolidated_liabilities_cny": totals["liabilities"],
            "financial_subsidiary_external_deposits_cny": groups["liability:financial_external_claim"],
            "reported_lease_liabilities_cny": groups["liability:lease_debt"],
            "selected_financial_assets_cny": assets["totals"]["closing"]["selected_financial_assets"],
            "disclosed_restricted_cash_subset_cny": assets["restricted_cash_subset"],
        },
        "conclusions": {
            "resilience": "截至2026年6月30日，已勾稽的合并负债为469.54亿元，其中254.26亿元是金融子公司的吸收存款及同业存放，已披露租赁负债约2.44亿元。该口径中没有非零短期借款、长期借款或应付债券行被列入已勾稽的非空负债表项目，因此当前资料未显示重大已识别的公司借款压力。",
            "liquidity_boundary": "已选金融资产约2,046.63亿元，但其中包括受限准备金、信贷资产及投资资产；已披露受限资金子集约83.59亿元。它们不能直接等同于工业经营可自由支配现金或普通股可分配现金。",
            "counterevidence": "非空报表行的缺失不是对表外承诺、担保、未披露融资或未来现金压力的零值证明；金融子公司存款的流动性与工业经营现金也不能混用。当前未完成担保、债务到期表和压力现金流的全量审查，因此不据此给出“无债”或低谷安全结论。",
        },
        "next_event": "下一份定期报告、担保/融资/重大承诺公告，以及金融子公司负债和受限资金变动披露。",
        "resilience_approved": False,
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = RESEARCH / f"600519-resilience-review-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = RESEARCH / "600519-resilience-review-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "review_version": result["review_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

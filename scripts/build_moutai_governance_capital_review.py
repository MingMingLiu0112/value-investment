#!/usr/bin/env python3
"""Build a bounded capital-allocation and governance review for 600519."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "runtime/company-research"
TIMELINE = ROOT / "runtime/strategy-validation/moutai-repurchase-timeline-20260909T095306550689Z/evidence.json"
TIMELINE_SHA256 = "ecedd2581bcc153837d7ddd499b46d5740355e4fe321bb707a8ed157678bbe0c"
RELATED = RESEARCH / "600519-daily-related-transactions-scope-20260911T074640Z/evidence.json"
RELATED_SHA256 = "794cd4eefe9301b8b27a3c15046966f8f2b020a8213766864da577675b08324b"
BRIDGE = RESEARCH / "600519-current-capital-bridge-20260917T084546Z/evidence.json"
BRIDGE_SHA256 = "929fbaad28a0fd3d5bf57efb5ac98a648106de7727896c95e0819a05bd4e5b27"
CANCELLATION = RESEARCH / "600519-cancellation-2025-20260909T094442562176Z/original.pdf"
CANCELLATION_TEXT = RESEARCH / "600519-cancellation-2025-20260909T094442562176Z/text.txt"
CANCELLATION_SHA256 = "9ad8dda3c43bbc19bf9926394ddf4a030543455910f7ef1b1bb736bd4385215b"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pinned(path: Path, expected: str) -> tuple[dict, dict]:
    if digest(path) != expected:
        raise ValueError(f"Pinned evidence changed: {path}")
    return json.loads(path.read_text(encoding="utf-8")), {
        "path": str(path.relative_to(ROOT)), "sha256": expected,
    }


def build() -> dict:
    timeline, timeline_ref = read_pinned(TIMELINE, TIMELINE_SHA256)
    related, related_ref = read_pinned(RELATED, RELATED_SHA256)
    bridge, bridge_ref = read_pinned(BRIDGE, BRIDGE_SHA256)
    if digest(CANCELLATION) != CANCELLATION_SHA256:
        raise ValueError("Pinned repurchase completion PDF changed")
    cancellation_text = CANCELLATION_TEXT.read_text(encoding="utf-8")
    if not all(token in cancellation_text for token in (
        "实际回购股数 3,927,585股", "实际回购金额 5,999,985,966.95元",
        "实际回购价格区间 1,408.29元/股～1,639.99元/股", "用于注销",
    )):
        raise ValueError("Repurchase completion extract changed")
    completed = next(row for row in timeline["snapshots"] if row.get("source_id") == "cninfo:1224625694")
    if completed["repurchase_complete"] is not True or completed["cumulative_shares"] != 3927585:
        raise ValueError("Completed repurchase timeline changed")
    if related["total_cny_100million"] != "92.06" or related["scope_approved"] is not False:
        raise ValueError("Related-party scope changed")
    if bridge["passed"] is not True or bridge["ordinary_share_basis"]["issued_shares"] != "1250081601":
        raise ValueError("Capital bridge changed")

    return {
        "symbol": "600519",
        "review_version": "moutai-governance-capital-review-v1",
        "as_of": "2026-09-18",
        "scope": "Observed capital return, repurchase mechanics and disclosed related-party controls; not a governance rating or valuation approval.",
        "evidence": {
            "repurchase_timeline": timeline_ref,
            "related_party_scope": related_ref,
            "current_capital_bridge": bridge_ref,
            "repurchase_completion_text": {
                "path": str(CANCELLATION.relative_to(ROOT)), "sha256": CANCELLATION_SHA256,
            },
        },
        "facts": {
            "completed_2024_program_shares": "3927585",
            "completed_2024_program_cash_excluding_fees_cny": "5999985966.95",
            "completed_2024_program_price_low_cny": "1408.29",
            "completed_2024_program_price_high_cny": "1639.99",
            "reported_2026_h1_ordinary_shares": bridge["ordinary_share_basis"]["issued_shares"],
            "related_party_2026_expected_cap_cny": str(Decimal(related["total_cny_100million"]) * Decimal("100000000")),
            "related_party_moutai_sales_cap_cny": "5917000000",
        },
        "conclusions": {
            "capital_allocation": "2024年回购计划在2025年完成：回购3,927,585股、金额约60.00亿元、价格区间1,408.29至1,639.99元/股，公告用途为注销并减少注册资本。已披露股份数随后下降，资本回报和每股分母下降是可观察事实。",
            "governance": "2026年日常关联交易预计上限92.06亿元，公告披露四名关联董事回避、其余三名非关联董事表决及独立董事专门会议审议，并列明关联销售与非关联经销商同价/同原则等定价规则。这说明存在已披露的程序与规则，但预计额度、公司陈述和表决程序不证明实际交易价格公允或治理质量优秀。",
            "counterevidence": "回购是否增厚普通股价值取决于回购时的内在价值，当前正式估值未获批准，不能仅因回购和注销就认定增厚。关联交易公告是2026年预计额，仍须用后续实际发生额、毛利/现金影响、定价样本及独立审计信息复核；激励、质押、减持和其他治理事项在本轮未形成完整审查。",
        },
        "next_event": "2026年关联交易实际发生额披露、后续回购/注销进展、年度报告中的关联交易和管理层激励披露。",
        "governance_approved": False,
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = RESEARCH / f"600519-governance-capital-review-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = RESEARCH / "600519-governance-capital-review-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "review_version": result["review_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build one immutable, non-trading research case for Kweichow Moutai (600519).

This intentionally composes already-reviewed research outputs.  It is not a
valuation engine and never produces an order, a target price, or an approved
fair value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "integrated_conditional_valuation": (
        "runtime/company-research/600519-integrated-conditional-equity-20260909T142721122559Z/evidence.json",
        "67e908b43a33700442267796e71a75e91b93430cd749de9fe1392e3d01eff6bc",
    ),
    "separated_discount_rate_sensitivity": (
        "runtime/company-research/600519-separated-rates-20260909T165254638416Z/evidence.json",
        "d53ab67705671c685acbae261ed7f427d6e5c0285d07874b8c6850085cac1106",
    ),
    "historical_account_replay": (
        "runtime/strategy-validation/moutai-account-comparison-20260909T145827486266Z/result.json",
        None,
    ),
    "official_benchmark_comparison": (
        "runtime/strategy-validation/moutai-official-benchmark-comparison-20260909T162649301451Z/evidence.json",
        "b93c0d0bce6dc40519b6cc965688a5e92c8cce9683e636e5db057e707661b3f8",
    ),
    "latest_ttm_snapshot": (
        "runtime/company-research/600519-ttm-scope-20260909T072356118039Z/evidence.json",
        "2d518b72fc2c9b8a60663c1f64121bfa45247de6262668db44ab656f27b6c57e",
    ),
}

LATEST_RESEARCH_ONLY = {
    "historical_conditional_inputs": ("runtime/strategy-validation/moutai-historical-conditional-inputs-latest.json", "evidence.json"),
    "historical_input_timeline": ("runtime/strategy-validation/moutai-historical-input-timeline-latest.json", "summary.json"),
    "historical_conditional_replay": ("runtime/strategy-validation/moutai-historical-conditional-replay-latest.json", "summary.json"),
    "blocked_paper_ledger": ("runtime/strategy-validation/moutai-blocked-paper-ledger-latest.json", "summary.json"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    data, provenance = {}, {}
    for name, (relative, expected) in INPUTS.items():
        path = root / relative
        actual = sha256(path)
        if expected and actual != expected:
            raise ValueError(f"Pinned input changed: {name}")
        value = json.loads(path.read_text(encoding="utf-8"))
        data[name] = value
        provenance[name] = {"path": relative, "sha256": actual}
    account_dir = root / "runtime/strategy-validation/moutai-account-comparison-20260909T145827486266Z"
    manifest = account_dir / "manifest.json"
    manifest_hash = sha256(manifest)
    if manifest_hash != "36d1a7053283de31d151e39bc60755ec98bdc63a71ba98811b4eac885ea49d5a":
        raise ValueError("Pinned account-replay manifest changed")
    provenance["historical_account_replay"]["manifest_path"] = str(manifest.relative_to(root))
    provenance["historical_account_replay"]["manifest_sha256"] = manifest_hash
    for name, (pointer_relative, filename) in LATEST_RESEARCH_ONLY.items():
        pointer = root / pointer_relative
        reference = json.loads(pointer.read_text(encoding="utf-8"))
        path = (root / reference["path"] / filename).resolve()
        expected_hash = reference.get("sha256") or reference.get("summary_sha256")
        if not path.is_relative_to(root.resolve()) or not expected_hash or sha256(path) != expected_hash:
            raise ValueError(f"Pinned research-only evidence changed: {name}")
        data[name] = json.loads(path.read_text(encoding="utf-8"))
        provenance[name] = {"pointer_path": pointer_relative, "path": str(path.relative_to(root)), "sha256": expected_hash}
    return data, provenance


def build_case(data: dict[str, dict], provenance: dict[str, dict]) -> dict:
    valuation = data["integrated_conditional_valuation"]
    sensitivity = data["separated_discount_rate_sensitivity"]
    replay = data["historical_account_replay"]
    benchmark = data["official_benchmark_comparison"]
    latest = data["latest_ttm_snapshot"]
    conditional_inputs = data["historical_conditional_inputs"]
    timeline = data["historical_input_timeline"]
    conditional_replay = data["historical_conditional_replay"]
    blocked_ledger = data["blocked_paper_ledger"]
    if any(item.get("trade_approved") for item in valuation["results"]):
        raise ValueError("Conditional valuation unexpectedly allows trading")
    if valuation.get("valuation_approved") is not False or replay.get("strategy_approved") is not False:
        raise ValueError("Research approval scope changed")
    if (conditional_inputs.get("case_count") != 12 or conditional_inputs.get("formal_fair_value") is not None
            or conditional_inputs.get("trade_approved") is not False
            or timeline.get("sessions") != 2674 or timeline.get("point_in_time_violations") != 0
            or timeline.get("formal_fair_value") is not None or timeline.get("trade_approved") is not False
            or conditional_replay.get("sessions") != 2674 or conditional_replay.get("sessions_with_experimental_range") != 2603
            or conditional_replay.get("formal_fair_value") is not None or conditional_replay.get("trade_approved") is not False
            or blocked_ledger.get("sessions") != 2674 or blocked_ledger.get("orders") != 0
            or blocked_ledger.get("executions") != 0 or blocked_ledger.get("performance_available") is not False):
        raise ValueError("Point-in-time research-only scope changed")
    scenarios = {row["scenario"]: row["conditional_value_per_disclosed_share"]
                 for row in valuation["representative_scenarios"]}
    return {
        "case_id": "600519-end-to-end-research-simulation",
        "symbol": "600519",
        "company": "贵州茅台",
        "run_type": "research_simulation",
        "trade_approved": False,
        "decision": {
            "state": "research_only",
            "action": "不生成买入、卖出、加仓或减仓指令",
            "blockers": [
                "条件估值不是已批准的内在价值或交易阈值",
                "历史旧规则六个情景均为零交易，未验证价值策略",
                "未接入经复核的当日市场价格与持仓记录",
                "共享费用、税资本、资产范围及资本成本尚未完成验收",
            ],
        },
        "data_snapshot": {
            "period_end": latest["period_end"],
            "ttm": {key: value["value"] for key, value in latest["ttm"].items()},
            "source_status": "披露口径TTM已做原件一致性检查；不等于实时行情。",
        },
        "conditional_valuation": {
            "currency": valuation["currency"],
            "representative_per_share": scenarios,
            "case_count": len(valuation["results"]),
            "status": "实验条件试算，不是合理价、目标价或交易价格。",
        },
        "sensitivity": {
            "case_count": len(sensitivity["results"]),
            "mean_per_share_spans": {key: value["mean_span"]
                                     for key, value in sensitivity["rate_comparisons"].items()},
            "status": "6%/8%/10%是比较实验，不是已批准资本成本。",
        },
        "historical_replay": {
            "period": "2015-01-05 to 2025-12-31",
            "hold_ending_equity_cny": replay["independent_ending_hold_equity_cny"],
            "legacy_order_counts": {row["scenario"]: row["legacy_orders"] for row in replay["summary"]},
            "status": "仅持有对照；旧规则无成交，不能证明价值交易策略有效。",
        },
        "point_in_time_research_chain": {
            "annual_input_cases": conditional_inputs["case_count"],
            "decision_sessions": timeline["sessions"],
            "input_timing_violations": timeline["point_in_time_violations"],
            "experimental_valuation_sessions": conditional_replay["sessions_with_experimental_range"],
            "blocked_ledger_sessions": blocked_ledger["sessions"],
            "blocked_ledger_orders": blocked_ledger["orders"],
            "status": "年报输入、实验范围和逐日账本均为研究证据；没有正式历史价值、账户资金、成交或策略绩效。",
        },
        "benchmarks": {
            "full": benchmark["metrics"]["full"],
            "recent_2023_2025": benchmark["metrics"]["2023-2025"],
            "status": "指数为全收益口径，持有账户分红留现金，不构成净超额收益证明。",
        },
        "provenance": provenance,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    data, provenance = load_inputs(ROOT)
    case = build_case(data, provenance)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or ROOT / "runtime/company-research" / f"600519-end-to-end-case-{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"outputs": {"evidence.json": sha256(evidence)}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = ROOT / "runtime/company-research/600519-end-to-end-case-latest.json"
    latest.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": sha256(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_dir": str(output), "evidence_sha256": sha256(evidence), "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

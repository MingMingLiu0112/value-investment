#!/usr/bin/env python3
"""Build the read-only M7 daily workbench candidate.

The command verifies every input SHA-256, assembles a presentation-only packet
from existing runtime read models and writes one candidate workbook plus a
manifest. It never publishes the WPS canonical workbook, reads a private
portfolio, creates a scheduler/notification target or emits an order.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m7_daily_workbench import (  # noqa: E402
    ACTION_NO_ORDER,
    SCHEMA_VERSION,
    write_daily_workbench,
)


DEFAULT_OUTPUT = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v2_20260924.xlsx"
)
DEFAULT_GENERATED_AT = datetime(2026, 9, 24, 2, 0, 0, tzinfo=timezone.utc)

M2_REPORT = ROOT / "runtime" / "m2-channel-verification-20260924-v1" / "report.json"
M2_MANIFEST = ROOT / "runtime" / "m2-channel-verification-20260924-v1" / "manifest.json"
M2_LIVE_MANIFEST = ROOT / "runtime" / "m2-live-20260923-v3" / "manifest.json"
M3_AUDIT_POINTER = ROOT / "runtime" / "m3-decision-acceptance-audit-latest.json"
M3_AUDIT_RECEIPT = (
    ROOT
    / "runtime"
    / "m3-decision-acceptance-audit-20260923T190024Z"
    / "receipt.json"
)
M3_DECISION_WORKBOOK = ROOT / "A股价值投资_M3决策卡候选_20260924.xlsx"
M3_DECISION_MANIFEST = ROOT / "A股价值投资_M3决策卡候选_20260924.manifest.json"
M3_HISTORY_MANIFEST = ROOT / "A股价值投资_M3历史链候选_20260924.manifest.json"
M3_INTEGRATED_RUNS = (
    ROOT / "runtime" / "m1-post-review-20260923T114228Z" / "integrated-runs.json"
)
M3_REPLAY = (
    ROOT
    / "runtime"
    / "m3-historical-research-replay-20260924-v1"
    / "replay.json"
)
M4_RISK_MANIFEST = ROOT / "A股价值投资_M4组合风险候选_20260924.manifest.json"
M4_GUIDANCE_MANIFEST = ROOT / "A股价值投资_M4仓位与股息候选_20260924.manifest.json"
M4_M5_MANIFEST = ROOT / "A股价值投资_M4M5联合检查点候选_20260924.manifest.json"
M5_MANIFEST = (
    ROOT
    / "runtime"
    / "m5-human-review-reconciliation-20260924-v1"
    / "manifest.json"
)
M5_RECONCILIATION = (
    ROOT
    / "runtime"
    / "m5-human-review-reconciliation-20260924-v1"
    / "reconciliation.json"
)
M5_PENDING = (
    ROOT
    / "runtime"
    / "m5-human-review-reconciliation-20260924-v1"
    / "pending-queue.json"
)
M6_POINTER = ROOT / "runtime" / "m6-operational-preflight-latest.json"
M6_RECEIPT = (
    ROOT
    / "runtime"
    / "m6-operational-preflight-20260924T000810Z"
    / "receipt.json"
)
AUDIT_WORKBOOK = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx"
)
CANONICAL_WORKBOOK = ROOT / "A股价值投资_Agent前端智能跟踪模板.xlsx"

PINNED_SHA256 = {
    M2_REPORT: "193e2cd9e398de625e5851d0f5d91cb3485b3ef660caa9ed8d22203e85c37ccf",
    M2_MANIFEST: "454bd22c98244a4f2bd70af6a6179cda5dbed486d57b13cd11ef5e93096d5fd4",
    M2_LIVE_MANIFEST: "69bd1b4a134fcdf67e4cd15454373b4441783ffe24a2446daa375ea260b844a1",
    M3_AUDIT_POINTER: "72ecc186b612ecc51e5d6b4e44e2dfdef02f5c0e719a7fe632e698a00e6b15f3",
    M3_AUDIT_RECEIPT: "2bb49e94df6740330d2713dee03eec1c44bb2be753f3afbbd40b1560797c8259",
    M3_DECISION_WORKBOOK: "589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d",
    M3_DECISION_MANIFEST: "c2b69ea02a0b5bdb0734b41c416ee03147ffad0eea8c78febc37ebf6b0ea2cc6",
    M3_HISTORY_MANIFEST: "8370c565f5253e2b8d4b4d5d2020dc25e35b197add46c686f1bcdbe0fbd77ece",
    M3_INTEGRATED_RUNS: "b1123333f2b4caa6beae16102bdca613b0894ad7fb72aa17329e838cd32b0459",
    M3_REPLAY: "2822dd786a40433ed03eac1e741a82a219cc9c76196b267e3a76290e53a141b9",
    M4_RISK_MANIFEST: "fd99b755718a033393c5ea02d5eaf591e2c8383c3f6bdc494c94ff057c1da648",
    M4_GUIDANCE_MANIFEST: "937c2d14b5e16b6f4cf3453054ef7a56a83446d255ee02ced2b7271d669f7591",
    M4_M5_MANIFEST: "cfdbbb090c9167e5da5e49f0d253896e133131c2ad80766b79033dbc2501d30d",
    M5_MANIFEST: "ebe71545f98bf68f5bb9f42df40a305810ef211b79bd3d84c0a709e631c1ee3d",
    M5_RECONCILIATION: "0cc01a1c6258754578ce87e4d01845aa2942bdf6457c803587db307d8a082e18",
    M5_PENDING: "3372ea05dc915f7611b5cf779692cb234f95a30de4f937f20a1e10942d17b282",
    M6_POINTER: "442e09db732b57a2b1f8d817bf5c07b3f8661fd61b385ee04f8a64e6a1afd6c0",
    M6_RECEIPT: "9dadc9bdf3b7dcfb319ce35b5d7003827799a32c9dd4fe67fca74fceaba07dc3",
    AUDIT_WORKBOOK: "d00c3363767d96010d9f6b429525cc0b35633160d1bfae967a286ea87c5130dc",
    CANONICAL_WORKBOOK: "64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911",
}

M3_NAMES = {
    "000651": "格力电器",
    "600741": "华域汽车",
    "600887": "伊利股份",
}

VALUE_DISCLAIMER = (
    "市场估值线索：PE/PB/隐含 ROE 初筛。"
    "尚未验证 FCF Yield、EV/EBIT、正常化盈利和资产负债表质量。"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_pinned(path: Path) -> None:
    expected = PINNED_SHA256[path]
    actual = digest(path)
    if actual != expected:
        raise ValueError(
            f"{path.relative_to(ROOT)} changed: expected {expected}, got {actual}"
        )


def _load_json(path: Path) -> dict[str, Any]:
    _verify_pinned(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    if "action" in payload and payload.get("action") != ACTION_NO_ORDER:
        raise ValueError(f"{path.relative_to(ROOT)} is not no_order")
    return payload


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    _verify_pinned(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array: {path}")
    return payload


def _audit_artifact(label: str, path: Path) -> dict[str, str]:
    return {
        "label": label,
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "action": ACTION_NO_ORDER,
    }


def _m2_packet() -> dict[str, Any]:
    report = _load_json(M2_REPORT)
    manifest = _load_json(M2_MANIFEST)
    live_manifest = _load_json(M2_LIVE_MANIFEST)
    if manifest["report_sha256"] != digest(M2_REPORT):
        raise ValueError("M2 report hash disagrees with M2 manifest")
    summary = report["human_review_packet"]["summary"]
    live_summary = live_manifest["summary"]
    coverage = live_summary["coverage_counts"]
    quality = live_summary["data_health"]
    channel_counts = live_summary["channel_counts"]
    budget_by_channel = {
        channel: coverage[channel]["budget_excluded_count"]
        for channel in coverage
    }
    rows = report["human_review_packet"]["rows"]
    return {
        "status": "PENDING_HUMAN_REVIEW",
        "acceptance_status": report["acceptance_status"],
        "lead_count": summary["lead_count"],
        "verified_count": summary["verified_for_deep_research"],
        "rejected_count": summary["rejected_after_verification"],
        "insufficient_count": summary["insufficient_evidence"],
        "unsupported_count": summary["unsupported"],
        "verified_symbols": list(summary["verified_symbols"]),
        "verified_channels": list(summary["verified_channels"]),
        "channel_counts": dict(channel_counts),
        "budget_by_channel": budget_by_channel,
        "budget_excluded_count": sum(budget_by_channel.values()),
        "quality": {
            "universe_count": quality["universe_count"],
            "evidence_count": quality["financial_evidence_count"],
            "pass_count": coverage["quality"]["pass_count"],
            "data_gap_count": coverage["quality"]["data_gap_count"],
            "coverage_status": "COVERAGE_LIMITED",
        },
        "value_disclaimer": VALUE_DISCLAIMER,
        "rows": [
            {
                "symbol": row["symbol"],
                "name": row["name"],
                "channel": row["channel"],
                "status": row["status"],
                "reason": _m2_reason(report, row),
                "evidence_count": row["evidence_count"],
            }
            for row in rows
        ],
    }


def _m2_reason(report: dict[str, Any], row: dict[str, Any]) -> str:
    for item in report["results"]:
        if item["symbol"] == row["symbol"] and item["channel"] == row["channel"]:
            return item["reason"]
    return ""


def _m3_packet() -> dict[str, Any]:
    pointer = _load_json(M3_AUDIT_POINTER)
    receipt_path = ROOT / pointer["path"] / "receipt.json"
    if receipt_path not in PINNED_SHA256:
        raise ValueError(f"M3 audit receipt is not pinned: {receipt_path}")
    _verify_pinned(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    decision_manifest = _load_json(M3_DECISION_MANIFEST)
    history_manifest = _load_json(M3_HISTORY_MANIFEST)
    integrated = _load_json_array(M3_INTEGRATED_RUNS)
    replay = _load_json(M3_REPLAY)
    cards = []
    for item in integrated:
        symbol = str(item["symbol"])
        pre = item.get("pre_decision_eligibility") or {}
        cards.append(
            {
                "symbol": symbol,
                "name": M3_NAMES[symbol],
                "status": "INSUFFICIENT_RESEARCH",
                "reason_kind": "RESEARCH_INCOMPLETE",
                "blockers": list(pre.get("blockers") or []),
            }
        )
    return {
        "status": "PARTIAL",
        "checkpoint_b_status": "NOT_APPROVED_YET",
        "positive_price_safety": (
            "已修复：只有 RESEARCH_ATTRACTIVE 可形成正向价格复核；"
            "NOT_ASSESSABLE / WAITING_FOR_BETTER_PRICE / KEY_OBSERVATION 不得产生 BUY/ADD。"
        ),
        "negative_cards": cards,
        "simulated_history_status": (
            "SIMULATED / PASS_AS_STRUCTURE_ONLY；不冒充真实历史收益或真实决策。"
        ),
        "historical_replay": replay,
        "decision_workbook": {
            "path": str(M3_DECISION_WORKBOOK.relative_to(ROOT)),
            "sha256": digest(M3_DECISION_WORKBOOK),
        },
        "decision_manifest": decision_manifest,
        "history_manifest": history_manifest,
        "audit_receipt": {
            "path": str(receipt_path.relative_to(ROOT)),
            "sha256": digest(receipt_path),
            "status": receipt.get("status"),
        },
    }


def _m4_packet() -> dict[str, Any]:
    risk = _load_json(M4_RISK_MANIFEST)
    guidance = _load_json(M4_GUIDANCE_MANIFEST)
    joint = _load_json(M4_M5_MANIFEST)
    return {
        "status": "ENGINEERING_DONE_SIMULATED",
        "decision_binding_status": (
            "ENGINEERING_DONE：PositionGuidance 绑定 typed InvestmentDecisionReview / "
            "decision_review_id + decision_review_sha256 + decision_status。"
        ),
        "private_input_status": "PENDING_USER_PRIVATE_INPUT",
        "new_capacity_available": False,
        "required_inputs": [
            "真实 IPS（期限、风险约束、现金与流动性需求、股息目标）",
            "真实 Portfolio Snapshot（持仓、成本、当前价格）",
            "真实现金与单只证券上限",
            "行业上限与周期仓位上限",
            "最小确认容量与人工签收边界",
        ],
        "simulated_engineering_status": (
            f"风险候选 {risk.get('assessment_namespace')}；"
            f"仓位/股息候选 {guidance.get('assessment_namespace')}；"
            f"联合检查点 {joint.get('namespace')}。均为模拟，不用于个人结论。"
        ),
    }


def _m5_packet() -> dict[str, Any]:
    manifest = _load_json(M5_MANIFEST)
    reconciliation = _load_json(M5_RECONCILIATION)
    pending = _load_json(M5_PENDING)
    return {
        "status": "ENGINEERING_DONE_OFFLINE",
        "continuous_ops_status": "NOT_READY",
        "current_candidates": manifest["counts"]["current_candidates"],
        "carried_forward": manifest["counts"]["carried_forward"],
        "pending_human_review": manifest["counts"]["pending_human_review"],
        "hash_conflicts": manifest["counts"]["hash_conflicts"],
        "superseded_pending": manifest["counts"]["superseded_pending"],
        "pending_items": list(pending["items"]),
        "reconciliation_id": reconciliation["reconciliation_id"],
    }


def _m6_packet() -> dict[str, Any]:
    pointer = _load_json(M6_POINTER)
    receipt_path = ROOT / pointer["path"] / "receipt.json"
    if receipt_path not in PINNED_SHA256:
        raise ValueError(f"M6 preflight receipt is not pinned: {receipt_path}")
    _verify_pinned(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return {
        "status": "PREFLIGHT_DONE",
        "engineering_status": receipt["engineering_status"],
        "operational_status": receipt["operational_acceptance_status"],
        "blockers": list(receipt["summary"].get("blockers") or []),
    }


def _audit_packet() -> dict[str, Any]:
    _verify_pinned(AUDIT_WORKBOOK)
    _verify_pinned(CANONICAL_WORKBOOK)
    return {
        "action": ACTION_NO_ORDER,
        "audit_workbook": str(AUDIT_WORKBOOK.relative_to(ROOT)),
        "audit_workbook_sha256": digest(AUDIT_WORKBOOK),
        "canonical_workbook": str(CANONICAL_WORKBOOK.relative_to(ROOT)),
        "canonical_workbook_sha256": digest(CANONICAL_WORKBOOK),
        "production_actions": "NONE",
        "artifacts": [
            _audit_artifact("M2 通道验证报告", M2_REPORT),
            _audit_artifact("M2 全市场 manifest", M2_LIVE_MANIFEST),
            _audit_artifact("M3 决策审计收据", ROOT / "runtime/m3-decision-acceptance-audit-20260923T190024Z/receipt.json"),
            _audit_artifact("M3 集成运行输入", M3_INTEGRATED_RUNS),
            _audit_artifact("M3 历史研究重放（事实/行情 PIT；规则非当时版本）", M3_REPLAY),
            _audit_artifact("M4 组合风险模拟 manifest", M4_RISK_MANIFEST),
            _audit_artifact("M4 仓位/股息模拟 manifest", M4_GUIDANCE_MANIFEST),
            _audit_artifact("M4/M5 联合模拟 manifest", M4_M5_MANIFEST),
            _audit_artifact("M5 复核 reconciliation", M5_RECONCILIATION),
            _audit_artifact("M5 新增待复核队列", M5_PENDING),
            _audit_artifact("M6 运营预检收据", M6_RECEIPT),
            _audit_artifact("90 页统一工作台", AUDIT_WORKBOOK),
            _audit_artifact("WPS Canonical Excel", CANONICAL_WORKBOOK),
        ],
    }


def build_packet(generated_at: datetime) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "as_of": "2026-09-24",
        "action": ACTION_NO_ORDER,
        "m2": _m2_packet(),
        "m3": _m3_packet(),
        "m4": _m4_packet(),
        "m5": _m5_packet(),
        "m6": _m6_packet(),
        "audit": _audit_packet(),
        "stage_statuses": {
            "m1": ["M1", "DONE", "DONE as Research Workbench", "已完成人工 G3 初审"],
            "m2": ["M2", "ENGINEERING_DONE", "PARTIAL", "PENDING_HUMAN_REVIEW"],
            "m3": ["M3", "ENGINEERING_PARTIAL_PLUS", "PARTIAL", "PENDING_HUMAN_REVIEW"],
            "m4": ["M4", "ENGINEERING_DONE_SIMULATED", "PARTIAL", "PENDING_PRIVATE_INPUT"],
            "m5": ["M5", "ENGINEERING_DONE_OFFLINE", "PARTIAL", "PENDING_RECONCILIATION / OPERATIONS"],
            "m6": ["M6", "PREFLIGHT_DONE", "NOT_STARTED operationally", "PENDING_AUTHORIZATION / SHADOW"],
            "m7": ["M7", "DISPLAY_ENGINEERING_DONE", "PARTIAL", "PENDING_USER_ACCEPTANCE"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
        default=DEFAULT_GENERATED_AT,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    receipt = write_daily_workbench(
        build_packet(args.generated_at),
        output=args.output,
        root=ROOT,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

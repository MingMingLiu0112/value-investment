from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ACTION_NO_ORDER = "no_order"
EVIDENCE_PATHS = (
    "evidence/m2-channel-verification-20260924-v2/report.json",
    "evidence/m2-live-20260923-v3/manifest.json",
    "evidence/m3-decision-acceptance-audit-20260924T062947Z/receipt.json",
    "evidence/m1-post-review-20260923T114228Z/integrated-runs.json",
    "evidence/m5-human-review-reconciliation-20260924-v1/pending-queue.json",
    "evidence/m6-operational-preflight-20260924T050357Z/receipt.json",
    "evidence/m3-historical-research-replay-20260924-v1/replay.json",
    "evidence/m4/risk-manifest.json",
    "evidence/m4/guidance-manifest.json",
    "evidence/m4/joint-manifest.json",
    "evidence/m5-human-review-reconciliation-20260924-v1/reconciliation.json",
    "evidence/workbooks/unified-workbench.json",
    "evidence/workbooks/canonical.json",
)


def fixture_bytes(path: str) -> bytes:
    return json.dumps(
        {"fixture_path": path, "synthetic": True},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _artifact(label: str, path: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": path,
        "sha256": hashlib.sha256(fixture_bytes(path)).hexdigest(),
        "action": ACTION_NO_ORDER,
    }


def _m2_rows() -> list[dict[str, Any]]:
    channels = ("quality", "value", "cyclical", "dividend_cash_return")
    rows: list[dict[str, Any]] = []
    initial = (
        ("600519", "贵州茅台", "quality", "INSUFFICIENT_EVIDENCE"),
        ("000333", "美的集团", "value", "INSUFFICIENT_EVIDENCE"),
        ("601088", "中国神华", "cyclical", "INSUFFICIENT_EVIDENCE"),
        ("600887", "伊利股份", "dividend_cash_return", "INSUFFICIENT_EVIDENCE"),
        ("600741", "华域汽车", "value", "INSUFFICIENT_EVIDENCE"),
    )
    for index, (symbol, name, channel, status) in enumerate(initial):
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "channel": channel,
                "status": status,
                "reason": "关键经营证据尚未补齐。",
                "evidence_count": index + 1,
            }
        )
    for index in range(6, 19):
        rows.append(
            {
                "symbol": f"{600000 + index:06d}",
                "name": f"合成样例公司 {index}",
                "channel": channels[(index - 1) % len(channels)],
                "status": "REJECTED_AFTER_VERIFICATION",
                "reason": "二阶段验证后未达到深入研究条件。",
                "evidence_count": index,
            }
        )
    return rows


def synthetic_legacy_packet(
    generated_at: str = "2026-09-26T03:00:00+00:00",
) -> dict[str, Any]:
    artifacts = [
        _artifact(f"synthetic evidence {index}", path)
        for index, path in enumerate(EVIDENCE_PATHS, 1)
    ]
    cards = [
        {
            "symbol": symbol,
            "name": name,
            "status": "INSUFFICIENT_RESEARCH",
            "reason_kind": "RESEARCH_INCOMPLETE",
            "blockers": ["关键证据尚未完成人工复核。"],
        }
        for symbol, name in (
            ("600519", "贵州茅台"),
            ("000333", "美的集团"),
            ("601088", "中国神华"),
        )
    ]
    return {
        "schema_version": "m7-daily-workbench-v1",
        "generated_at": generated_at,
        "as_of": "2026-09-25",
        "action": ACTION_NO_ORDER,
        "m2": {
            "status": "DONE",
            "checkpoint_a_status": "HUMAN_PASS",
            "acceptance_status": "HUMAN_PASS",
            "lead_count": 18,
            "verified_count": 0,
            "rejected_count": 13,
            "insufficient_count": 5,
            "unsupported_count": 0,
            "rows": _m2_rows(),
        },
        "m3": {
            "status": "PARTIAL",
            "checkpoint_b_status": "NOT_APPROVED_YET",
            "negative_cards": cards,
        },
        "m4": {
            "status": "ENGINEERING_DONE_SIMULATED",
            "private_input_status": "PENDING_USER_PRIVATE_INPUT",
            "new_capacity_available": False,
        },
        "m5": {
            "status": "ENGINEERING_DONE_OFFLINE",
            "continuous_ops_status": "NOT_READY",
            "pending_items": [
                {
                    "symbol": "600519",
                    "announcement_id": "synthetic-announcement-1",
                    "title": "合成公告等待人工复核。",
                    "disposition": "PENDING_HUMAN_REVIEW",
                }
            ],
        },
        "m6": {
            "status": "PREFLIGHT_DONE",
            "engineering_status": "DONE",
            "operational_status": "OPERATIONAL_NOT_STARTED",
            "blockers": [
                "真实运营授权尚未完成。",
                "shadow 监控尚未开始。",
                "恢复演练尚未完成。",
                "通知通道尚未验证。",
                "调度器尚未启用。",
            ],
        },
        "audit": {
            "action": ACTION_NO_ORDER,
            "artifacts": artifacts,
        },
    }


def materialize_synthetic_legacy_packet(root: Path, packet: dict[str, Any]) -> None:
    for artifact in packet["audit"]["artifacts"]:
        target = root / Path(artifact["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fixture_bytes(artifact["path"]))


__all__ = [
    "EVIDENCE_PATHS",
    "materialize_synthetic_legacy_packet",
    "synthetic_legacy_packet",
]

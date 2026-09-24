"""Build a versioned, read-only M3 Checkpoint B human-review packet.

This command only assembles hash-pinned M3 evidence. It does not write a human
receipt, does not mark Checkpoint B as passed, and does not create an Entry,
Journal, personal portfolio, position or order.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402


PACKET_SCHEMA = "m3-checkpoint-b-human-review-packet-v1"
DEFAULT_OUTPUT = ROOT / "runtime" / "m3-checkpoint-b-human-review-20260924-v1"
DEFAULT_GENERATED_AT = datetime(
    2026,
    9,
    24,
    20,
    30,
    0,
    tzinfo=timezone(timedelta(hours=8)),
)

DECISION_WORKBOOK = ROOT / "A股价值投资_M3决策卡候选_20260924.xlsx"
DECISION_MANIFEST = ROOT / "A股价值投资_M3决策卡候选_20260924.manifest.json"
ORIGINAL_WORKBOOK = (
    ROOT / "A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx"
)
ORIGINAL_MANIFEST = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.candidate.manifest.json"
)
HISTORY_WORKBOOK = (
    ROOT / "A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx"
)
HISTORY_MANIFEST = (
    ROOT
    / "A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.candidate.manifest.json"
)
HISTORY_ADDON_WORKBOOK = ROOT / "A股价值投资_M3历史链候选_20260924.xlsx"
HISTORY_ADDON_MANIFEST = ROOT / "A股价值投资_M3历史链候选_20260924.manifest.json"
CANONICAL_WORKBOOK = ROOT / "A股价值投资_Agent前端智能跟踪模板.xlsx"

DECISION_AUDIT_RECEIPT = (
    ROOT
    / "runtime"
    / "m3-decision-acceptance-audit-20260924T062947Z"
    / "receipt.json"
)
ORIGINAL_AUDIT_RECEIPT = (
    ROOT
    / "runtime"
    / "m3-original-workbook-audit-20260924T063010Z"
    / "receipt.json"
)
HISTORY_AUDIT_RECEIPT = (
    ROOT
    / "runtime"
    / "m3-history-original-workbook-audit-20260924T063017Z"
    / "receipt.json"
)
STRICT_PIT_RECEIPT = (
    ROOT
    / "runtime"
    / "m3-strict-pit-evidence-audit-20260924T080000Z"
    / "receipt.json"
)
M2_ACCEPTANCE_RECEIPT = (
    ROOT
    / "runtime"
    / "m2-checkpoint-a-human-acceptance-20260924-v3"
    / "receipt.json"
)

PINNED_SHA256 = {
    DECISION_WORKBOOK: "589f19ef9e3d235401814e98450475d657c3e981b33637337ab5da9d33fb307d",
    DECISION_MANIFEST: "c2b69ea02a0b5bdb0734b41c416ee03147ffad0eea8c78febc37ebf6b0ea2cc6",
    ORIGINAL_WORKBOOK: "ac3e67e6b9c5eb65812fab7c82cfa73e2ee2336c530b30f1d77fbc6383b1a7a3",
    ORIGINAL_MANIFEST: "192dd480b7aa8ef6299e7095014d2ca5a6becca04b4c5a42c1c6c95b375b41b4",
    HISTORY_WORKBOOK: "67e720f2326443bb3d36003db707a86169483bcd2f2be10a97dbda6d3bfacd4d",
    HISTORY_MANIFEST: "d8da5fc558847e36b2b76f9faf0a008bfac9c8c3b80ccb7a187eb46d0cb4b3ab",
    HISTORY_ADDON_WORKBOOK: "5ca99c128be065c836fa00a521b5aaade2f2826cba09dbf6249fd4e9ba926bc0",
    HISTORY_ADDON_MANIFEST: "8370c565f5253e2b8d4b4d5d2020dc25e35b197add46c686f1bcdbe0fbd77ece",
    CANONICAL_WORKBOOK: "64c8deff1a237076d2ba0b00afc8905d23bd9d117cb132dfc6757071b5659911",
    DECISION_AUDIT_RECEIPT: "755c2ec01a21cf357de212014c9d3e11cf35f0595802814d24182c7a77069429",
    ORIGINAL_AUDIT_RECEIPT: "9a083e943685cdb5c29802b430f414b5b11b15764314e7f230b09acdc421fef6",
    HISTORY_AUDIT_RECEIPT: "5e56c6e18668e9b5c345a839f85d22afc5e548c9a855ecce09f9ffcf1fee508c",
    STRICT_PIT_RECEIPT: "9d161d6e7a52e0c061c7129510933f7b3701245bd6c65a444450b50002dbdf3c",
    M2_ACCEPTANCE_RECEIPT: "9a18b7fcb08b4ba4196a989f88561939b0e9257982b03198b650669b378e6f20",
}

CARD_ROWS = (
    {
        "symbol": "000651",
        "name": "格力电器",
        "system_status": "INSUFFICIENT_RESEARCH",
        "reason_category": "RESEARCH_INCOMPLETE",
        "decision_intent": "未提交",
        "portfolio_input": "缺失",
        "entry": "本卡不需要",
        "action": ACTION_NO_ORDER,
    },
    {
        "symbol": "600741",
        "name": "华域汽车",
        "system_status": "INSUFFICIENT_RESEARCH",
        "reason_category": "RESEARCH_INCOMPLETE",
        "decision_intent": "未提交",
        "portfolio_input": "缺失",
        "entry": "本卡不需要",
        "action": ACTION_NO_ORDER,
    },
    {
        "symbol": "600887",
        "name": "伊利股份",
        "system_status": "INSUFFICIENT_RESEARCH",
        "reason_category": "RESEARCH_INCOMPLETE",
        "decision_intent": "未提交",
        "portfolio_input": "缺失",
        "entry": "本卡不需要",
        "action": ACTION_NO_ORDER,
    },
)

MACHINE_GATE_EXPECTATIONS = {
    "decision_card": {
        "done": ["m3c1", "m3c2", "m3c3", "m3c4", "m3c5", "m3c6"],
        "pending_human": ["m3c7"],
    },
    "original_workbook": {
        "done": ["owc1", "owc2", "owc3", "owc4", "owc5", "owc6"],
        "pending_human": ["owc7"],
    },
    "history_overlay": {
        "done": ["hoc1", "hoc2", "hoc3", "hoc4", "hoc5", "hoc6"],
        "pending_human": ["hoc7"],
    },
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(path: Path) -> str:
    actual = _digest(path)
    expected = PINNED_SHA256[path]
    if actual != expected:
        raise ValueError(
            f"{path.relative_to(ROOT)} changed: expected {expected}, got {actual}"
        )
    return actual


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError(f"{path.relative_to(ROOT)} is not action=no_order")
    return payload


def _artifact(path: Path, *, available: bool) -> dict[str, str | bool]:
    digest = _verify(path) if available else PINNED_SHA256[path]
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest,
        "available_in_current_clone": available,
    }


def _optional_receipt(path: Path) -> dict[str, str | bool]:
    available = path.is_file()
    if available:
        payload = _load_json(path)
        if payload.get("status") not in {
            "PENDING_HUMAN_REVIEW",
            "NOT_PROVEN",
            "DONE",
        }:
            raise ValueError(f"Unexpected receipt status: {path}")
    return _artifact(path, available=available)


def _validate_manifests() -> None:
    decision = _load_json(DECISION_MANIFEST)
    if decision["workbook_sha256"] != _verify(DECISION_WORKBOOK):
        raise ValueError("M3 decision-card manifest does not bind its workbook")
    if decision.get("positive_review_count") != 0:
        raise ValueError("M3 decision-card manifest has a positive review")

    original = _load_json(ORIGINAL_MANIFEST)
    if original["candidate_sha256"] != _verify(ORIGINAL_WORKBOOK):
        raise ValueError("M3 original-workbook manifest does not bind its candidate")
    if original.get("positive_review_count") != 0:
        raise ValueError("M3 original-workbook manifest has a positive review")
    if original.get("status") != "candidate_verified_not_published":
        raise ValueError("M3 original-workbook candidate was published")

    history = _load_json(HISTORY_MANIFEST)
    if history["candidate_sha256"] != _verify(HISTORY_WORKBOOK):
        raise ValueError("M3 history overlay manifest does not bind its candidate")
    if history.get("namespace") != "simulated":
        raise ValueError("M3 history overlay is not namespace=simulated")
    if history.get("status") != "candidate_verified_not_published":
        raise ValueError("M3 history overlay candidate was published")

    history_addon = _load_json(HISTORY_ADDON_MANIFEST)
    if history_addon["workbook_sha256"] != _verify(HISTORY_ADDON_WORKBOOK):
        raise ValueError("M3 history addon manifest does not bind its workbook")
    if history_addon.get("namespace") != "simulated":
        raise ValueError("M3 history addon is not namespace=simulated")


def _m2_governance_binding() -> dict[str, Any]:
    available = M2_ACCEPTANCE_RECEIPT.is_file()
    artifact = _artifact(M2_ACCEPTANCE_RECEIPT, available=available)
    if available:
        payload = _load_json(M2_ACCEPTANCE_RECEIPT)
        if payload.get("decisions", {}).get("M2_CHECKPOINT_A") != "HUMAN_PASS":
            raise ValueError("M2 acceptance receipt does not record HUMAN_PASS")
        if payload.get("sequence") != 2:
            raise ValueError("M2 acceptance receipt is not sequence 2")
    return {
        "status": "HUMAN_PASS",
        "receipt": artifact,
        "available_in_current_clone": available,
    }


def build_packet(*, generated_at: datetime) -> dict[str, Any]:
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    _validate_manifests()
    _verify(CANONICAL_WORKBOOK)
    _verify(HISTORY_ADDON_WORKBOOK)

    return {
        "schema_version": PACKET_SCHEMA,
        "packet_id": "m3-checkpoint-b-review-20260924-v1",
        "generated_at": generated_at.isoformat(),
        "goal_id": "VALUE-INVESTMENT-M2-M7-INITIAL_ASSISTED-USE",
        "action": ACTION_NO_ORDER,
        "checkpoint_b_status": "PENDING_HUMAN_REVIEW",
        "overall_product_status": "PARTIAL",
        "m2_governance": _m2_governance_binding(),
        "strict_contemporaneous_rule_pit": "NOT_PROVEN",
        "machine_gates": {
            name: {
                "status": "PENDING_HUMAN_REVIEW",
                "machine_criteria": value["done"],
                "human_criteria": value["pending_human"],
            }
            for name, value in MACHINE_GATE_EXPECTATIONS.items()
        },
        "evidence": {
            "decision_card": {
                "workbook": _artifact(DECISION_WORKBOOK, available=True),
                "manifest": _artifact(DECISION_MANIFEST, available=True),
                "audit_receipt": _optional_receipt(DECISION_AUDIT_RECEIPT),
            },
            "original_workbook": {
                "workbook": _artifact(ORIGINAL_WORKBOOK, available=True),
                "manifest": _artifact(ORIGINAL_MANIFEST, available=True),
                "audit_receipt": _optional_receipt(ORIGINAL_AUDIT_RECEIPT),
            },
            "history_overlay": {
                "workbook": _artifact(HISTORY_WORKBOOK, available=True),
                "manifest": _artifact(HISTORY_MANIFEST, available=True),
                "addon_workbook": _artifact(HISTORY_ADDON_WORKBOOK, available=True),
                "addon_manifest": _artifact(HISTORY_ADDON_MANIFEST, available=True),
                "audit_receipt": _optional_receipt(HISTORY_AUDIT_RECEIPT),
            },
            "strict_pit_audit": _optional_receipt(STRICT_PIT_RECEIPT),
            "canonical_workbook": _artifact(CANONICAL_WORKBOOK, available=True),
        },
        "cards": [dict(row) for row in CARD_ROWS],
        "human_review_steps": [
            "打开三份候选，确认格力、华域、伊利的当前系统状态均为研究证据不足。",
            "逐卡检查缺失的研究、组合输入或原始 Entry 为什么阻断正向决策。",
            "至少抽查一条来源 Hash，并打开至少一条证据引用链接。",
            "确认全文没有买入、加仓、减仓、目标仓位或订单列。",
            "在历史链页面确认 namespace=simulated，不接受为真实交易或收益证据。",
            "确认 strict contemporaneous-rule Historical PIT 仍为 NOT_PROVEN，不伪造历史规则证据。",
            "确认 canonical 工作簿未被任何 M3 候选覆盖，三份候选均为未发布状态。",
            "能逐卡复述最强阻断、反证和重新打开研究的触发条件后才可记录 M3_CHECKPOINT_B=HUMAN_PASS。",
        ],
        "required_user_confirmation": [
            "000651、600741、600887 均为 INSUFFICIENT_RESEARCH 或等价研究不足状态",
            "没有任何公司因看起来便宜而生成买入、加仓、目标仓位或订单",
            "历史链页面明确标注模拟，不是真实交易或收益证据",
            "能够逐卡复述阻断、反证和重新打开研究的条件",
            "strict contemporaneous-rule PIT 保持 NOT_PROVEN，没有伪造可验证历史规则证据",
        ],
        "forbidden_interpretations": [
            "M3_CHECKPOINT_B=PASS",
            "研究证据不足=可交易",
            "模拟历史链=真实收益",
            "strict PIT 未证明=可忽略",
            "三份候选已发布或覆盖 canonical",
            "本复核包可代替用户实际操作",
        ],
        "next_action": "WAIT_FOR_HUMAN_CHECKPOINT_B_REVIEW",
        "post_review_sequence": [
            "用户实际阅读三份候选并完成人工复核",
            "仅当用户明确给出 M3_CHECKPOINT_B=HUMAN_PASS 时，新增 append-only 人工收据",
            "继续 M4 私有 IPS/组合输入、M5 事件工程、M6 授权与 shadow、M7 交付",
        ],
    }


def render_markdown(packet: dict[str, Any]) -> str:
    cards = "\n".join(
        f"| {row['symbol']} | {row['name']} | {row['system_status']} | "
        f"{row['reason_category']} | {row['portfolio_input']} | {row['action']} |"
        for row in packet["cards"]
    )
    evidence = packet["evidence"]
    steps = "\n".join(f"{index}. {item}" for index, item in enumerate(packet["human_review_steps"], 1))
    required = "\n".join(f"- [ ] {item}" for item in packet["required_user_confirmation"])
    return f"""# M3 Checkpoint B 人工复核包：2026-09-24

本文件由 `scripts/build_m3_checkpoint_b_review_packet.py` 只读生成。
当前状态为 `PENDING_HUMAN_REVIEW`；代理不能替用户签收 Checkpoint B。

```text
goal_id={packet["goal_id"]}
action={packet["action"]}
checkpoint_b_status={packet["checkpoint_b_status"]}
strict_contemporaneous_rule_pit={packet["strict_contemporaneous_rule_pit"]}
M2_CHECKPOINT_A={packet["m2_governance"]["status"]}
```

## 三张负向决策卡

| 证券 | 名称 | 系统状态 | 原因类别 | 组合输入 | 动作 |
| --- | --- | --- | --- | --- | --- |
{cards}

## 复核步骤

{steps}

## 用户逐项确认

{required}

## 证据 Hash

| 产物 | SHA-256 |
| --- | --- |
| M3 决策卡候选 | `{evidence["decision_card"]["workbook"]["sha256"]}` |
| M3 原工作簿候选 | `{evidence["original_workbook"]["workbook"]["sha256"]}` |
| M3 历史链叠加候选 | `{evidence["history_overlay"]["workbook"]["sha256"]}` |
| canonical 工作簿 | `{evidence["canonical_workbook"]["sha256"]}` |

Checkpoint B 未通过前，系统不生成个人化 BUY/ADD、Entry、Journal、仓位或订单。
"""


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path.resolve()), "sha256": _digest(path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(),
        default=DEFAULT_GENERATED_AT,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("M3 Checkpoint B review packet output escapes project root")
    if output_dir.exists():
        raise ValueError(f"M3 Checkpoint B review packet output already exists: {output_dir}")
    packet = build_packet(generated_at=args.generated_at)
    output_dir.mkdir(parents=True)
    packet_output = _write_json(output_dir / "checkpoint-b-packet.json", packet)
    markdown_path = output_dir / "checkpoint-b-review.md"
    markdown_path.write_text(render_markdown(packet), encoding="utf-8")
    manifest = {
        "schema_version": "m3-checkpoint-b-human-review-packet-manifest-v1",
        "generated_at": args.generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "checkpoint_b_status": "PENDING_HUMAN_REVIEW",
        "outputs": {
            "packet": packet_output,
            "markdown": {
                "path": str(markdown_path.resolve()),
                "sha256": _digest(markdown_path),
            },
        },
    }
    manifest_output = _write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest_output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

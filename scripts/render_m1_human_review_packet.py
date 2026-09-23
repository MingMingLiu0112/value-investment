"""Render a hash-pinned M1 deferred-review ledger from frozen local evidence.

This command is read-only against the current M1 runtime/config/WPS evidence.
It does not grant G3, does not decide announcement materiality, does not touch
the WPS workbook, and never emits an order or position instruction. These
decision-stage checks are explicit M1 outputs but are not M1 exit blockers.
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

from value_investment_agent.m1_valuation_package_builder import (  # noqa: E402
    build_package_descriptor_attempts,
)


APPLICATION_POINTER = "runtime/m1-research-application-latest.json"
DEFAULT_OUTPUT = "docs/m1-human-review-packet-20260923.md"
APPLICATION_SYMBOLS = ("000651", "600741", "600887")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _require_pinned(root: Path, pointer: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    relative = str(pointer["path"])
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Pointer escapes project root: {relative}")
    evidence = target / "evidence.json"
    actual = _digest(evidence)
    expected = str(pointer.get("sha256") or "").lower()
    if actual != expected:
        raise ValueError(f"Pointer hash changed: {relative}")
    return evidence, _load_json(evidence)


def _package_specs(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "config" / "m1-valuation-packages-v1").glob("*.json")):
        payload = _load_json(path)
        symbol = str(payload.get("symbol") or "")
        if symbol in APPLICATION_SYMBOLS:
            result[symbol] = payload
    return result


def _md_link(text: str, target: str) -> str:
    return f"[{text}]({target})"


def _announcement_rows(symbol: str, spec: dict[str, Any], root: Path) -> tuple[list[str], int]:
    scan_ref = ((spec.get("model_validity_input") or {}).get("event_scan_ref") or {})
    path = root_relative(scan_ref.get("path"))
    expected = str(scan_ref.get("sha256") or "").lower()
    evidence_path = root / path if path else None
    if not evidence_path or not evidence_path.exists():
        raise ValueError(f"Missing event-scan evidence for {symbol}")
    if expected and _digest(evidence_path) != expected:
        raise ValueError(f"Event-scan hash changed for {symbol}")
    scan = _load_json(evidence_path)
    rows: list[str] = []
    for item in scan.get("announcements") or []:
        if not item.get("materiality_candidate") or not item.get("pre_model"):
            continue
        refs = item.get("evidence_refs") or []
        ref = refs[0] if refs else {}
        local = str(ref.get("path") or "")
        source_url = str(ref.get("source_url") or "")
        sha256 = str(ref.get("sha256") or "")
        title = (
            str(item.get("title") or "")
            .strip()
            .replace("|", "/")
            .replace("\r", " ")
            .replace("\n", " ")
        )
        published = str(item.get("published_at") or "")
        local_target = f"../{Path(local).as_posix()}" if local else ""
        local_file = root / Path(local) if local else None
        local_ok = bool(local_file and local_file.exists() and sha256 and _digest(local_file) == sha256)
        local_label = "本地原件" if local_ok else "本地原件(Hash不符)"
        local_text = _md_link(local_label, local_target) if local_target else "无"
        source_text = _md_link("CNINFO 原件", source_url) if source_url else "无"
        rows.append(
            f"| {item.get('announcement_id')} | {published} | {title} | "
            f"{local_text} / {source_text} | `{sha256[:12]}...` | 待填写 | 待填写 | 待填写 |"
        )
    return rows, len(rows)


def root_relative(value: object) -> Path:
    return Path(str(value or ""))


def _valuation_rows(results: dict[str, dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for symbol in APPLICATION_SYMBOLS:
        item = results.get(symbol) or {}
        valuation = item.get("valuation") or {}
        gate = item.get("gate") or {}
        g3 = (gate.get("results") or {}).get("G3_估值门")
        def fmt(value: Any) -> str:
            try:
                return f"{float(value):.4f}"
            except (TypeError, ValueError):
                return str(value)

        rows.append(
            f"| {symbol} | {valuation.get('model_type') or '-'} | "
            f"{fmt(valuation.get('bear_value'))} / {fmt(valuation.get('base_value'))} / "
            f"{fmt(valuation.get('bull_value'))} | `{g3}` | 待填写 | 待填写 |"
        )
    return rows


def _blocker_list(symbol: str, spec: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for blocker in spec.get("blockers") or []:
        lines.append(f"- `{blocker}`")
    return lines


def _render(root: Path) -> tuple[str, dict[str, Any]]:
    specs = _package_specs(root)
    if set(specs) != set(APPLICATION_SYMBOLS):
        raise ValueError("Required M1 application package is missing")
    attempts = build_package_descriptor_attempts(root)
    descriptors = {
        item.descriptor.symbol: item.descriptor
        for item in attempts
        if item.descriptor and item.descriptor.symbol in APPLICATION_SYMBOLS
    }
    if set(descriptors) != set(APPLICATION_SYMBOLS):
        raise ValueError("Required M1 descriptor is missing")
    pointer = _load_json(root / APPLICATION_POINTER)
    application_evidence_path, application = _require_pinned(root, pointer)
    results = {
        str(item.get("symbol")): item for item in application.get("results") or []
        if str(item.get("symbol") or "") in APPLICATION_SYMBOLS
    }

    parts = [
        "# M1 后续里程碑复核台账",
        "",
        "更新：2026-09-23。本文件由 `scripts/render_m1_human_review_packet.py` 从当前冻结 runtime/config 证据生成，只读、不批准、不改变原 Excel，`action=no_order`。M1 研究工作台验收已通过；以下项目延后到 M3/M5/M6，不是 M1 的完成条件。",
        "",
        "进入对应里程碑前，请把结论回复给 Codex，不要直接修改本文件冒充人工记录。任何 G3 批准、事件重要性判断或 Excel 确认都应由 Codex 写入新的可追溯收据。",
        "",
        "## A. M3：G3 条件估值批准",
        "",
        "以下数值仍是 `conditional_research_only`。后续人工批准只表示“模型基础可作为条件研究继续使用”，不是合理价、价格吸引力、仓位或买入建议。",
        "",
        "| 公司 | 模型 | Bear / Base / Bull | G3 当前值 | 批准 | 补充条件 |",
        "| --- | --- | ---: | --- | --- | --- |",
        *_valuation_rows(results),
        "",
        "对每家公司核对：",
        "",
        "1. 官方原件、反证、thesis breaker 与 `assumption_bindings` 是否一致。",
        "2. 2026H1 未经审计、ROIC/WACC/增量 ROIC、法人层级现金与股本动作等 blocker 是否仍成立。",
        "3. 事件复核结果是否要求调整输入或让模型 `STALE`。",
        "4. 回复格式：`000651 G3 批准 / 不批准`，并附一句依据或仍需补的数据。",
        "",
    ]

    for symbol in APPLICATION_SYMBOLS:
        descriptor = descriptors[symbol]
        spec = specs[symbol]
        model = spec.get("requested_model") or descriptor.dependencies.model_id
        scan = descriptor.model_validity_input.event_scan
        parts.extend(
            [
                f"### {symbol}",
                "",
                f"- 模型：`{model}`",
                f"- 事件扫描：`{scan.status}`，pre-model 状态：`{scan.pre_model_review_status}`",
                f"- 研究 blocker：",
                *_blocker_list(symbol, spec),
                "",
            ]
        )

    parts.extend(
        [
            "## B. M5：模型前公告重要性阅读",
            "",
            "下表只包含 `pre_model=true` 且 `materiality_candidate=true` 的公告。请逐项打开本地原件或 CNINFO 链接，判断：不重要 / 重要 / 需要拆分。",
            "",
            "| 公告 ID | 发布日期 | 标题 | 原件 | SHA-256 前 12 位 | 判断 | 影响字段 | 备注 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    pending_event_count = 0
    for symbol in APPLICATION_SYMBOLS:
        rows, count = _announcement_rows(symbol, specs[symbol], root)
        pending_event_count += count
        parts.extend(rows)
    parts.extend(
        [
            "",
            "若某条判断为“重要”，当前 `VALID`/`READY` 不能自动保留；需要先登记新事实/假设并重算。若全部为“不重要”，可以进入 M5 的下一步。",
            "",
            "## C. M6：Excel 人工可用性确认",
            "",
            "打开 `A股价值投资_Agent前端智能跟踪模板.xlsx`，确认：",
            "",
            "1. 前 6 个 M1 页名称和顺序正确。",
            "2. 内部链接没有错误页面或死链接。",
            "3. `00_M1应用总览` 仍显示“完成，有阻断”、`action=no_order`。",
            "4. 估值、股利、反向估值、阻断/证据、样本页没有写成 BUY/ADD/仓位。",
            "",
            "## D. 禁止事项",
            "",
            "- 不把 G3 批准解释为买入信号。",
            "- 不把 `READY` 价格桥解释为价格吸引力。",
            "- 不把 LOW 股息可持续性解释为股息可维持。",
            "",
            "## 证据摘要",
            "",
            f"- Application 指针：`{APPLICATION_POINTER}`",
            f"- Application evidence SHA-256：`{_digest(application_evidence_path)}`",
            f"- 生成时间：`{datetime.now(timezone.utc).isoformat()}`",
            "",
        ]
    )
    text = "\n".join(parts)
    summary = {
        "action": "no_order",
        "symbols": list(APPLICATION_SYMBOLS),
        "application_pointer": APPLICATION_POINTER,
        "pending_announcements": pending_event_count,
    }
    return text, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text, summary = _render(args.root.resolve())
    output = args.out if args.out.is_absolute() else args.root.resolve() / args.out
    if not args.dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"packet: {output.relative_to(args.root.resolve())}")
    print(f"action: {summary['action']}")
    print(f"pending announcements: {summary['pending_announcements']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

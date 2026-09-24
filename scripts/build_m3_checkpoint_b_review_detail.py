"""Build a read-only detail aid for the M3 Checkpoint B human review.

The detail aid binds the already frozen M3 review packet to the matching
immutable company dossiers.  It exposes counter-evidence, thesis breakers,
next events and research gaps that the reviewer must understand before
recording a human decision.  It never creates a receipt, Entry, Journal,
portfolio, position or order.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402


DETAIL_SCHEMA = "m3-checkpoint-b-review-detail-v1"
DEFAULT_OUTPUT = ROOT / "runtime" / "m3-checkpoint-b-review-detail-20260924-v2"
DEFAULT_GENERATED_AT = datetime(
    2026,
    9,
    24,
    21,
    30,
    0,
    tzinfo=timezone(timedelta(hours=8)),
)

BASE_PACKET = (
    ROOT
    / "runtime"
    / "m3-checkpoint-b-human-review-20260924-v1"
    / "checkpoint-b-packet.json"
)
DOSSIERS = {
    "000651": ROOT
    / "runtime"
    / "company-research"
    / "000651-m1-dossier-20260923T004117Z"
    / "evidence.json",
    "600741": ROOT
    / "runtime"
    / "company-research"
    / "600741-m1-dossier-20260923T004123Z"
    / "evidence.json",
    "600887": ROOT
    / "runtime"
    / "company-research"
    / "600887-m1-dossier-20260923T004120Z"
    / "evidence.json",
}

PINNED_SHA256 = {
    BASE_PACKET: "fab538fb283b55b449d6c52be908216cbe2df06880a2c66848901371a15c7eb4",
    DOSSIERS["000651"]: "be20b1686aea0219b52602ece96b7e240147e679890d7f28966ae82a60702c56",
    DOSSIERS["600741"]: "d162721de48b530720917c8c154159b9ed0e260a84c4592a084b7d2069fb6864",
    DOSSIERS["600887"]: "84368e78db5bad449b5f6183f3bb3d3ee30a4aa0a35af48552a403b090fd6435",
}

SECTION_KEYS = ("counter_evidence", "thesis_breakers", "next_events", "research_gaps")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(path: Path) -> str:
    expected = PINNED_SHA256.get(path)
    if expected is None:
        raise ValueError(f"No pinned SHA-256 for {path}")
    actual = _digest(path)
    if actual != expected:
        raise ValueError(f"{path.relative_to(ROOT)} changed: expected {expected}, got {actual}")
    return actual


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _finding_rows(section: object, field: str) -> list[dict[str, Any]]:
    if not isinstance(section, Mapping):
        raise ValueError(f"{field} must be an object")
    rows = section.get("findings")
    if not isinstance(rows, list):
        raise ValueError(f"{field}.findings must be a list")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{field}.findings[{index}] must be an object")
        text = _text(row.get("text"), f"{field}.findings[{index}].text")
        refs = row.get("evidence_refs") or []
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ValueError(f"{field}.findings[{index}].evidence_refs must be strings")
        result.append(
            {
                "kind": str(row.get("kind") or "unknown"),
                "text": text,
                "evidence_refs": refs,
            }
        )
    return result


def _blockers(section: object, field: str) -> list[str]:
    if not isinstance(section, Mapping):
        raise ValueError(f"{field} must be an object")
    blockers = section.get("blockers") or []
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item.strip() for item in blockers
    ):
        raise ValueError(f"{field}.blockers must be non-empty strings")
    return [item.strip() for item in blockers]


def _evidence_sources(payload: Mapping[str, Any], symbol: str) -> list[dict[str, Any]]:
    raw = payload.get("evidence_refs")
    if not isinstance(raw, list):
        raise ValueError(f"{symbol} dossier evidence_refs must be a list")
    sources: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"{symbol} dossier evidence_refs[{index}] must be an object")
        source_id = _text(item.get("id"), f"{symbol}.evidence_refs[{index}].id")
        source_url = str(item.get("source_url") or "").strip()
        source_hash = str(item.get("sha256") or "").strip().lower()
        if len(source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in source_hash):
            raise ValueError(f"{symbol} dossier evidence source {source_id} has invalid SHA-256")
        sources.append(
            {
                "id": source_id,
                "kind": str(item.get("kind") or ""),
                "source_url": source_url,
                "sha256": source_hash,
                "description": str(item.get("description") or ""),
            }
        )
    return sources


def _build_card(symbol: str, base_card: Mapping[str, Any], dossier_path: Path) -> dict[str, Any]:
    _verify(dossier_path)
    dossier = _load_json(dossier_path)
    if dossier.get("symbol") != symbol:
        raise ValueError(f"Dossier symbol mismatch for {symbol}")
    if dossier.get("action") != ACTION_NO_ORDER:
        raise ValueError(f"Dossier {symbol} must remain action=no_order")

    sections = {key: _finding_rows(dossier.get(key), key) for key in SECTION_KEYS}
    blockers = _blockers(dossier.get("research_gaps"), "research_gaps")
    research_gaps = sections["research_gaps"] or [
        {"kind": "gap", "text": blocker, "evidence_refs": []} for blocker in blockers
    ]
    next_events = sections["next_events"]
    return {
        "symbol": symbol,
        "name": str(base_card.get("name") or ""),
        "system_status": str(base_card.get("system_status") or ""),
        "reason_category": str(base_card.get("reason_category") or ""),
        "decision_intent": str(base_card.get("decision_intent") or ""),
        "portfolio_input": str(base_card.get("portfolio_input") or ""),
        "entry": str(base_card.get("entry") or ""),
        "action": ACTION_NO_ORDER,
        "strongest_blocker": blockers[0] if blockers else "未登记阻断项，必须保持研究不足。",
        "research_blockers": blockers,
        "counter_evidence": sections["counter_evidence"],
        "thesis_breakers": sections["thesis_breakers"],
        "next_events": next_events,
        "reopen_condition": (
            next_events[0]["text"]
            if next_events
            else "未登记下一事件；不得据此形成正向复核。"
        ),
        "research_gaps": research_gaps,
        "evidence_sources": _evidence_sources(dossier, symbol),
        "dossier": {
            "path": str(dossier_path.relative_to(ROOT)),
            "sha256": _verify(dossier_path),
        },
    }


def build_detail_packet(*, generated_at: datetime) -> dict[str, Any]:
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    _verify(BASE_PACKET)
    base = _load_json(BASE_PACKET)
    if base.get("action") != ACTION_NO_ORDER:
        raise ValueError("Base M3 review packet must remain action=no_order")
    if base.get("checkpoint_b_status") != "PENDING_HUMAN_REVIEW":
        raise ValueError("Base M3 review packet must remain pending human review")
    base_cards = base.get("cards")
    if not isinstance(base_cards, list):
        raise ValueError("Base M3 review packet cards must be a list")
    by_symbol = {}
    for row in base_cards:
        if not isinstance(row, Mapping):
            raise ValueError("Base M3 review packet card must be an object")
        symbol = str(row.get("symbol") or "")
        by_symbol[symbol] = row
    if set(by_symbol) != set(DOSSIERS):
        raise ValueError("Base M3 review packet symbols do not match pinned dossiers")

    cards = [
        _build_card(symbol, by_symbol[symbol], DOSSIERS[symbol])
        for symbol in ("000651", "600741", "600887")
    ]
    return {
        "schema_version": DETAIL_SCHEMA,
        "packet_id": "m3-checkpoint-b-review-detail-20260924-v2",
        "generated_at": generated_at.isoformat(),
        "goal_id": "VALUE-INVESTMENT-M2-M7-INITIAL-ASSISTED-USE",
        "action": ACTION_NO_ORDER,
        "checkpoint_b_status": "PENDING_HUMAN_REVIEW",
        "supersedes": {
            "packet_id": "m3-checkpoint-b-review-detail-20260924-v1",
            "reason": "v1 Markdown rendered research-gap rows incorrectly; JSON review inputs remain hash-pinned.",
        },
        "purpose": "为 Checkpoint B 人工复核提供冻结研究档案中的动因、反证、破坏条件和下一次事件，不代替用户签收。",
        "base_packet": {
            "path": str(BASE_PACKET.relative_to(ROOT)),
            "sha256": _verify(BASE_PACKET),
            "checkpoint_b_status": "PENDING_HUMAN_REVIEW",
        },
        "cards": cards,
        "forbidden_interpretations": [
            "复核明细=Checkpoint B 通过",
            "反证列表=交易建议",
            "下一次事件=已发生事实",
            "研究不足=公司无价值",
            "本包可代替用户阅读原候选",
        ],
        "required_user_confirmation": [
            "逐卡能复述最强阻断、至少一条反证和重新打开研究的条件",
            "确认三张卡仍为研究证据不足且没有 BUY/ADD/仓位/订单",
            "确认本明细只引用冻结档案，不把旧事实改写为当前结论",
            "确认 strict contemporaneous-rule PIT 仍为 NOT_PROVEN",
        ],
    }


def render_markdown(packet: Mapping[str, Any]) -> str:
    sections: list[str] = []
    for card in packet["cards"]:
        counter_evidence = "\n".join(
            f"- [{row['kind']}] {row['text']}" for row in card["counter_evidence"]
        ) or "- 未登记反证；研究状态不得升级。"
        breakers = "\n".join(
            f"- [{row['kind']}] {row['text']}" for row in card["thesis_breakers"]
        ) or "- 未登记论点破坏条件；研究状态不得升级。"
        next_events = "\n".join(
            f"- [{row['kind']}] {row['text']}" for row in card["next_events"]
        ) or "- 未登记下一次事件；不得据此形成正向复核。"
        gaps = "\n".join(
            f"- [{row['kind']}] {row['text']}" for row in card["research_gaps"]
        ) or "- 未登记研究缺口。"
        sources = "\n".join(
            f"- `{row['id']}`：`{row['sha256']}`"
            + (f"；{row['source_url']}" if row["source_url"] else "")
            for row in card["evidence_sources"]
        )
        sections.append(
            f"""## {card['symbol']} {card['name']}

```text
system_status={card['system_status']}
reason_category={card['reason_category']}
decision_intent={card['decision_intent']}
portfolio_input={card['portfolio_input']}
entry={card['entry']}
action={card['action']}
strongest_blocker={card['strongest_blocker']}
reopen_condition={card['reopen_condition']}
```

### 反证

{counter_evidence}

### 论点破坏条件

{breakers}

### 下一次复核事件

{next_events}

### 研究缺口

{gaps}

### 来源绑定

{sources}
"""
        )
    confirmation = "\n".join(
        f"- [ ] {item}" for item in packet["required_user_confirmation"]
    )
    return f"""# M3 Checkpoint B 复核明细：2026-09-24

本文件由 `scripts/build_m3_checkpoint_b_review_detail.py` 只读生成，绑定基础复核包
`{packet['base_packet']['sha256']}`。它只帮助用户理解冻结档案，不签收
Checkpoint B，不生成 Entry、Journal、仓位或订单。

```text
action={packet['action']}
checkpoint_b_status={packet['checkpoint_b_status']}
base_packet_sha256={packet['base_packet']['sha256']}
```

## 人工确认

{confirmation}

{'\n\n'.join(sections)}
## 边界

细节来源均为冻结研究档案；旧事实、反证和下一次事件不因本文件而变成当前结论。
只有用户实际阅读原候选并明确给出 `M3_CHECKPOINT_B=HUMAN_PASS` 后，才可新增
append-only 人工收据。
"""


def _write_json(path: Path, payload: Mapping[str, Any]) -> dict[str, str]:
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
        raise ValueError("M3 review detail output escapes project root")
    if output_dir.exists():
        raise ValueError(f"M3 review detail output already exists: {output_dir}")
    packet = build_detail_packet(generated_at=args.generated_at)
    output_dir.mkdir(parents=True)
    packet_output = _write_json(output_dir / "review-detail.json", packet)
    markdown_path = output_dir / "review-detail.md"
    markdown_path.write_text(render_markdown(packet), encoding="utf-8")
    manifest = {
        "schema_version": "m3-checkpoint-b-review-detail-manifest-v1",
        "generated_at": args.generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "checkpoint_b_status": "PENDING_HUMAN_REVIEW",
        "outputs": {
            "detail": packet_output,
            "markdown": {"path": str(markdown_path.resolve()), "sha256": _digest(markdown_path)},
        },
    }
    manifest_output = _write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest_output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

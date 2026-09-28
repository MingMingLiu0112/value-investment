"""Compose bounded public-event research for the three registered cases."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
YILI_SOURCES = (
    {
        "evidence_id": "yili-1225578520-completion",
        "title": "伊利股份2023年持股计划（第三期）完成股票购买公告",
        "path": "runtime/prospective-public-event-20260927/20260927T004835372Z/600887-1225578520.pdf",
        "sha256": "7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c",
        "available_at": "2026-09-25",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-09-24/1225578520.PDF",
    },
    {
        "evidence_id": "yili-1225259570-plan-transfer",
        "title": "伊利股份2026年第三期持股计划董事会决议",
        "path": "runtime/prospective-event-support/600887/1225259570-2026-board-resolution.pdf",
        "sha256": "7369a05f737a7c786b226237a5149d59b0a243619bc005a5a94e660bae94f697",
        "available_at": "2026-05-01",
        "source_url": None,
    },
)


def _verify_source(root: Path, source: dict[str, Any]):
    from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord

    path = (root / source["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Missing Yili evidence source: {source['evidence_id']}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != source["sha256"]:
        raise ValueError(f"Yili evidence SHA-256 mismatch: {source['evidence_id']}")
    return EvidenceRecord(
        evidence_id=source["evidence_id"],
        title=source["title"],
        artifact_type="cninfo_original_pdf",
        path=source["path"],
        sha256=actual,
        available_at=date.fromisoformat(source["available_at"]),
        source_url=source["source_url"],
    )


def build_projection_payload(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Verify pinned inputs and combine issuer-specific, no-order projections."""
    root = Path(repository_root).resolve()
    sys.path[:0] = [str(root), str(root / "src")]
    from scripts.cases.build_midea_public_event_projection import build_projection_payload as build_midea
    from scripts.cases.build_shenhua_public_event_projection import build_projection_payload as build_shenhua
    from value_investment_agent.presentation.read_models.m5_event_state_projection import (
        EventStateInput,
        project_m5_event_states,
    )

    midea = build_midea(root)
    shenhua = build_shenhua(root)
    yili_evidence = tuple(_verify_source(root, source) for source in YILI_SOURCES)
    yili = project_m5_event_states((EventStateInput(
        state="insufficient_evidence",
        event_id="cninfo-600887-1225578520-third-phase-share-purchase",
        company_name="伊利股份",
        what_happened=(
            "2023年持股计划第三期于2026年9月22日完成股票购买，公告金额"
            "224,997,098.71元（不含费用）；购买的是现有股份，不是新发行。"
        ),
        impact_area="员工激励、费用及股本口径",
        evidence=yili_evidence,
        missing_evidence=(
            "实际资金来源构成、计划账户转入225,018,899.80元与购股金额之间"
            "21,801.09元差额的去向、股份支付费用确认期间及相关股份权利口径"
        ),
        reopen_condition=(
            "取得持股计划资金结算及后续正式财报披露，逐项核对资金、费用、"
            "股份权利和股本口径后再评估其研究影响"
        ),
        action="no_order",
    ),))
    inputs = (midea["projection"], yili.as_payload(), shenhua["projection"])
    keys = ("events", "audit_evidence", "audit_decisions")
    projection = {"action": "no_order"}
    for key in keys:
        rows = [row for item in inputs for row in item[key]]
        identities = [row.get("event_id") if key != "audit_evidence" else row.get("evidence_id") for row in rows]
        if len(identities) != len(set(identities)):
            raise ValueError(f"Duplicate identity in composite M5 {key}")
        projection[key] = rows
    if any(row.get("action") != "no_order" for key in ("events", "audit_decisions") for row in projection[key]):
        raise ValueError("Composite M5 projection must remain no_order")
    return {
        "action": "no_order",
        "report": {
            "schema_version": "registered-public-event-projection-v1",
            "scope": ["000333", "600887", "601088"],
            "classification": "PRE_REGISTRATION_PUBLIC_HISTORICAL_MATERIAL",
            "strict_pit_proven": False,
            "source_time_independently_certified": False,
            "valuation_or_trade_conclusion_changed": False,
            "prospective_observation_written": False,
            "subprojection_schemas": [
                midea["report"]["schema_version"], "yili-event-gap-v1",
                shenhua["report"]["schema_version"],
            ],
            "limitations": [
                "这些公告均为注册起点前已公开的历史材料，不构成新的前瞻发现或严格PIT证明。",
                "美的与神华投影保留各自来源限制；伊利持股计划事项的材料性仍未定，资金、差额、费用及股份权利口径尚未闭合。",
                "事件卡仅供研究跟踪；不自动改变估值、盈利预测、仓位或交易结论。",
            ],
            "action": "no_order",
        },
        "projection": projection,
    }


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(f"Refusing to overwrite existing output: {target}") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        write_new_json(args.output, build_projection_payload())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

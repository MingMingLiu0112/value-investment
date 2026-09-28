"""Build an append-only, bounded historical public-event projection for Shenhua."""
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
OUTPUT_SCHEMA_VERSION = "shenhua-public-event-projection-v1"

EVIDENCE_SOURCES = (
    {
        "evidence_id": "shenhua-1225546779-meeting-materials",
        "title": "中国神华2026年第三次临时股东会会议资料（方案金额）",
        "path": "runtime/prospective-public-event-20260927/shenhua-indexed-originals-20260927T154222Z/1225546779.pdf",
        "sha256": "93c49e799e4e2767f78c74c10b36484fa746f6b8aa945e6f1fb7293150275311",
        "available_at": "2026-09-05",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-09-04/1225546779.PDF",
    },
    {
        "evidence_id": "shenhua-1225579981-resolution",
        "title": "中国神华2026年第三次临时股东会决议公告（方案通过）",
        "path": "runtime/prospective-public-event-20260927/shenhua-gapfill-originals-20260927T130000Z/1225579981.pdf",
        "sha256": "a30578712ce65e62c379ad4ca271693aa9819f45d15f8cf21850bfdc19dc8940",
        "available_at": "2026-09-25",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-09-24/1225579981.PDF",
    },
    {
        "evidence_id": "shenhua-1225565223-operations",
        "title": "中国神华2026年8月份主要运营数据公告（发行人自报、比较期已重述）",
        "path": "runtime/prospective-public-event-20260927/shenhua-indexed-originals-20260927T154222Z/1225565223.pdf",
        "sha256": "9d458791200e6b47096859d58d825e5b9c1e619c82c90bf6cf05479eba9b0685",
        "available_at": "2026-09-17",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-09-16/1225565223.PDF",
    },
    {
        "evidence_id": "pdf-1225185584",
        "title": "国家能源集团财务有限公司风险评估报告（发行人自评）",
        "path": "runtime/prospective-public-event-20260927/shenhua-finance-risk/1225185584.PDF",
        "sha256": "6fce900be4fa9ea2a169513f01911d4bb47bb4f4dff9914873601a8f0d1f02af",
        "available_at": "2026-04-25",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-25/1225185584.PDF",
    },
    {
        "evidence_id": "shenhua-1225579956-restricted-share-unlock",
        "title": "中国神华部分限售股解除限售上市流通公告",
        "path": "runtime/prospective-public-event-20260927/shenhua-major-transaction-1225579956.pdf",
        "sha256": "f7d78ed7a7270069f112060bd90cd2779b9fa81c774a522f826174f0fdb38cd2",
        "available_at": "2026-09-25",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-09-24/1225579956.PDF",
    },
)

EVENT_SOURCES = (
    {
        "event_id": "cninfo-601088-1225546779-1225579981-interim-distribution",
        "state": "material_supporting_evidence",
        "evidence_ids": ("shenhua-1225546779-meeting-materials", "shenhua-1225579981-resolution"),
        "what_happened": (
            "2026年中期利润分配方案提出税前每股0.98元、合计约212.56亿元；"
            "2026年9月23日股东会决议通过。A股实施公告、股权登记日和支付日期尚未见，不能视为已支付。"
        ),
        "impact_area": "资本配置与股东回报",
        "reopen_condition": "等待A股利润分配实施公告，并核实登记日、支付日、实际每股金额及现金覆盖",
    },
    {
        "event_id": "cninfo-601088-1225565223-2026-08-operations",
        "state": "material_risk_monitor",
        "evidence_ids": ("shenhua-1225565223-operations",),
        "what_happened": (
            "发行人披露2026年8月主要运营数据；公告说明比较期数据已重述，且口径纳入2026年4月并入的资产。"
            "该表属于发行人运营统计，不等同于经审计财务事实。"
        ),
        "impact_area": "经营趋势与可比口径",
        "reopen_condition": "与后续季度报告中的分部经营数据和合并范围核对后再评估盈利预测依赖",
    },
    {
        "event_id": "cninfo-601088-1225185584",
        "state": "material_risk_monitor",
        "evidence_ids": ("pdf-1225185584",),
        "what_happened": (
            "发行人风险评估报告披露关联方国家能源集团财务公司的股权关系及金融服务；"
            "报告称截至2025年末未发生不良贷款，该资产质量表述为发行人自评，并非独立信用验证。"
        ),
        "impact_area": "关联方资金与现金质量",
        "reopen_condition": "核验期后存款余额、期限、可动用性及后续信用质量披露",
    },
    {
        "event_id": "cninfo-601088-1225579956",
        "state": "material_risk_monitor",
        "evidence_ids": ("shenhua-1225579956-restricted-share-unlock",),
        "what_happened": (
            "公告称2026-10-08有457,665,903股限售股上市流通，占总股本2.11%。"
            "这是既有股份限售状态变化，不是新增发行或总股本增加；也不是卖出信号。"
        ),
        "impact_area": "潜在流通供给",
        "reopen_condition": "跟踪实际上市流通及后续股本披露；不得仅据解禁事件推导卖出结论",
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verified_path(root: Path, source: dict[str, Any]) -> Path:
    path = (root / source["path"]).resolve()
    if root not in path.parents:
        raise ValueError("Evidence path escapes the repository")
    if not path.is_file():
        raise ValueError(f"Missing source PDF {source['evidence_id']}: {path}")
    actual = _sha256(path)
    if actual.lower() != source["sha256"]:
        raise ValueError(
            f"Source PDF SHA-256 mismatch for {source['evidence_id']}: "
            f"expected {source['sha256']}, got {actual}"
        )
    return path


def build_projection_payload(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Verify pinned original PDFs, then project four explicitly bounded events."""
    root = Path(repository_root).resolve()
    from value_investment_agent.presentation.read_models.m5_event_state_projection import (
        EventStateInput,
        project_m5_event_states,
    )
    from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord

    evidence_by_id = {}
    for source in EVIDENCE_SOURCES:
        _verified_path(root, source)
        record = EvidenceRecord(
            evidence_id=source["evidence_id"],
            title=source["title"],
            artifact_type="cninfo_original_pdf",
            path=source["path"],
            sha256=source["sha256"],
            available_at=date.fromisoformat(source["available_at"]),
            source_url=source["source_url"],
        )
        evidence_by_id[record.evidence_id] = record

    projection = project_m5_event_states(tuple(
        EventStateInput(
            state=source["state"],
            event_id=source["event_id"],
            company_name="中国神华",
            what_happened=source["what_happened"],
            impact_area=source["impact_area"],
            evidence=tuple(evidence_by_id[key] for key in source["evidence_ids"]),
            reopen_condition=source["reopen_condition"],
            action="no_order",
        )
        for source in EVENT_SOURCES
    ))
    if projection.action != "no_order":
        raise ValueError("M5 projection action must remain no_order")

    return {
        "action": "no_order",
        "report": {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "company": "中国神华",
            "symbol": "601088",
            "scope": "BOUNDED_PUBLIC_EVENT_PROJECTION_FROM_RETAINED_CNINFO_ORIGINALS",
            "classification": "PRE_REGISTRATION_PUBLIC_HISTORICAL_MATERIAL",
            "source_time_independently_certified": False,
            "strict_pit_proven": False,
            "valuation_or_trade_conclusion_changed": False,
            "prospective_observation_written": False,
            "action": "no_order",
            "limitations": [
                "原件来源时间未获独立时间戳证明；本投影是预登记前已公开历史材料的事后整理，不证明严格PIT。",
                "财务公司风险评估中的资产质量结论为发行人自评；不据此推断违约、损失或资金受限。",
                "运营统计为发行人披露且比较期已重述；不等同于经审计财务数据。",
                "限售股解禁改变可流通状态，不改变总股本；不是新增发行或自动卖出信号。",
                "本投影不改变估值、盈利预测、组合或交易结论。",
            ],
            "evidence_source_urls": {
                source["evidence_id"]: source["source_url"] for source in EVIDENCE_SOURCES
            },
        },
        "projection": projection.as_payload(),
    }


def write_new_json(path: Path, payload: dict[str, Any]) -> None:
    """Create output atomically and exclusively; never replace existing bytes."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"Refusing to overwrite existing output: {target}") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New JSON output path")
    args = parser.parse_args(argv)
    try:
        payload = build_projection_payload()
        write_new_json(args.output, payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

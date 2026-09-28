"""Build a bounded, retrospective Midea public-event projection from CNINFO archives."""
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
INDEX_RELATIVE_PATH = Path(
    "runtime/prospective-public-event-20260927/"
    "gapfill-000333-20260927T114140840633Z/index.json"
)
INDEX_SHA256 = "6c04cd73eeb3e3d79e9589b80398b96eafa34d36f7f49d317300a630e5ea1dab"
ARCHIVE_RELATIVE_DIR = Path(
    "runtime/prospective-public-event-20260927/midea-gapfill-originals-20260927T114140Z"
)
ARCHIVE_RELATIVE_BASELINE_DIR = Path(
    "runtime/prospective-public-event-20260927/midea-baseline-originals-20260927T112500Z"
)

EVENT_SOURCES = (
    {
        "event_id": "midea-2026-interim-dividend-proposal-1225531406",
        "announcement_id": "1225531406",
        "announcement_date": "2026-08-29",
        "available_at": date(2026, 8, 30),
        "relative_pdf_path": ARCHIVE_RELATIVE_BASELINE_DIR / "1225531406.pdf",
        "sha256": "89337c66647fc1758eadc1f7c7d5a7308cf54b62ab1c92781d9dcf12c3b3b5b9",
        "url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531406.PDF",
        "title": "2026年中期利润分配方案公告",
        "what_happened": (
            "登记起点前已公开的历史材料：公司提出2026年中期利润分配方案；"
            "该公告仅证明提案，不证明后续审议、实施或现金覆盖。"
        ),
        "impact_area": "资本分配研究",
        "state": "material_supporting_evidence",
        "reopen_condition": "取得股东会审批及利润分配实施公告，并核对分红股本基数与支付日",
    },
    {
        "event_id": "midea-2026-buyback-change-progress-1225544342",
        "announcement_id": "1225544342",
        "announcement_date": "2026-09-03",
        "available_at": date(2026, 9, 4),
        "relative_pdf_path": ARCHIVE_RELATIVE_DIR / "1225544342.pdf",
        "sha256": "24900692f953f24bff8464e27e3383e91b2a272984e38bff21ca628b3d7cc50b",
        "url": "https://static.cninfo.com.cn/finalpage/2026-09-03/1225544342.PDF",
        "title": "以集中竞价交易方式回购A股股份进展公告",
        "what_happened": (
            "登记起点前已公开的历史材料：披露2026年回购计划用途变更及截至"
            "2026-08-31的回购进展；不证明股份已完成注销或股本处理。"
        ),
        "impact_area": "资本配置与股本风险研究",
        "state": "material_risk_monitor",
        "reopen_condition": "取得股份注销完成公告与更新后的总股本资料，再判断每股口径是否需重算",
    },
    {
        "event_id": "midea-2026-employee-plan-transfer-compensation-1225544482",
        "announcement_id": "1225544482",
        "announcement_date": "2026-09-03",
        "available_at": date(2026, 9, 4),
        "relative_pdf_path": ARCHIVE_RELATIVE_DIR / "1225544482.pdf",
        "sha256": "d93bfd07da79f6b5e11b1c7bbdb151a4fe021690a2a307c0fc3c1047b4716365",
        "url": "https://static.cninfo.com.cn/finalpage/2026-09-03/1225544482.PDF",
        "title": "2026年A股持股计划非交易过户完成公告",
        "what_happened": (
            "登记起点前已公开的历史材料：披露员工持股计划非交易过户及股份支付"
            "会计安排；公告未量化股份支付费用，股份来源于2025年回购。"
        ),
        "impact_area": "员工激励与股份支付监测",
        "state": "material_risk_monitor",
        "reopen_condition": "取得覆盖过户后期间的正式财报或结算披露，核对费用确认及相关股份权利",
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"Missing {label}: {path}")
    actual = _sha256(path)
    if actual.lower() != expected.lower():
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def build_projection_payload(
    repository_root: Path = REPOSITORY_ROOT,
    *,
    index_sha256: str = INDEX_SHA256,
    pdf_sha256s: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate pinned archives and build the existing bounded M5 projection."""
    root = Path(repository_root).resolve()
    index_path = root / INDEX_RELATIVE_PATH
    _require_hash(index_path, index_sha256, "CNINFO index")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if (
        index.get("symbol") != "000333"
        or index.get("issuer_name") != "美的集团"
        or index.get("schema_version") != "prospective-cninfo-window-index-v1"
    ):
        raise ValueError("CNINFO index identity or schema is unexpected")

    announcements = {
        str(row.get("announcementId")): row
        for row in index.get("announcements", [])
        if isinstance(row, dict)
    }
    expected_ids = {source["announcement_id"] for source in EVENT_SOURCES}
    if not expected_ids.issubset(announcements):
        raise ValueError("CNINFO index is missing one or more required announcements")

    hashes = pdf_sha256s or {
        source["announcement_id"]: source["sha256"] for source in EVENT_SOURCES
    }
    evidence_records = []
    event_inputs = []
    for source in EVENT_SOURCES:
        announcement = announcements[source["announcement_id"]]
        if announcement.get("secCode") != "000333":
            raise ValueError(f"Announcement issuer mismatch: {source['announcement_id']}")
        expected_url_path = source["url"].split("cninfo.com.cn/")[-1]
        if announcement.get("adjunctUrl") != expected_url_path:
            raise ValueError(f"Announcement URL mismatch: {source['announcement_id']}")

        relative_path = source["relative_pdf_path"]
        pdf_path = (root / relative_path).resolve()
        if root not in pdf_path.parents:
            raise ValueError("PDF path escapes the repository")
        expected_pdf_hash = hashes.get(source["announcement_id"])
        if not expected_pdf_hash:
            raise ValueError(f"No recorded PDF hash for {source['announcement_id']}")
        _require_hash(pdf_path, expected_pdf_hash, f"CNINFO PDF {source['announcement_id']}")

        from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord

        evidence_records.append(EvidenceRecord(
            evidence_id=f"cninfo-{source['announcement_id']}",
            title=source["title"],
            artifact_type="cninfo_original_pdf",
            path=relative_path.as_posix(),
            sha256=expected_pdf_hash,
            available_at=source["available_at"],
            source_url=source["url"],
        ))
        event_inputs.append((source, evidence_records[-1]))

    from value_investment_agent.presentation.read_models.m5_event_state_projection import (
        EventStateInput,
        project_m5_event_states,
    )

    projection = project_m5_event_states(tuple(
        EventStateInput(
            state=source["state"],
            event_id=source["event_id"],
            company_name="美的集团",
            what_happened=source["what_happened"],
            impact_area=source["impact_area"],
            evidence=(evidence,),
            reopen_condition=source["reopen_condition"],
        )
        for source, evidence in event_inputs
    ))
    if projection.action != "no_order":
        raise ValueError("M5 projection action must remain no_order")

    return {
        "action": "no_order",
        "report": {
            "schema_version": "midea-public-event-projection-v1",
            "company": "美的集团",
            "symbol": "000333",
            "registration_start": "2026-09-27T08:45:00+08:00",
            "classification": "PRE_REGISTRATION_PUBLIC_HISTORICAL_MATERIAL",
            "prospective_observation_written": False,
            "prospective_ledger_written": False,
            "valuation_or_trade_conclusion_changed": False,
            "action": "no_order",
            "evidence_source_urls": {
                source["announcement_id"]: source["url"] for source in EVENT_SOURCES
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

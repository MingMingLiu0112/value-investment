"""Collect and hash-pin CNINFO event-scan evidence for the three M1 companies.

This command archives the complete announcement index and every disclosure PDF
for the window ending at each valuation date. It attaches the result to the
versioned valuation packages and never opens PostgreSQL, WPS or an order path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import (  # noqa: E402
    PDF_BASE_URL,
    download_disclosure_pdf,
    search_announcement_window,
)
from value_investment_agent.event_scan import (  # noqa: E402
    COVERAGE_COMPLETE,
    EVENT_SCAN_SCHEMA,
    PRE_MODEL_NONE,
    PRE_MODEL_PENDING_HUMAN_REVIEW,
    PRE_MODEL_REVIEWED_NO_CANDIDATES,
    REVIEW_PENDING_HUMAN_REVIEW,
    REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
    SCAN_COMPLETE_MATERIAL_EVENTS,
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    AnnouncementReview,
    EventScanResult,
    event_scan_from_payload,
)


PACKAGE_DIR = ROOT / "config" / "m1-valuation-packages-v1"
EVIDENCE_ROOT = ROOT / "runtime" / "company-research" / "m1-event-scans"
ISSUER_NAMES = {
    "000651": "格力电器",
    "600741": "华域汽车",
    "600887": "伊利股份",
}
SCAN_START_OVERRIDE = {
    "000651": "2026-08-27",
    "600741": "2026-08-27",
    "600887": "2026-08-27",
}
PARSER_VERSION = "cninfo-announcement-window-v1"

_NON_CANDIDATE_KINDS = {
    "governance",
    "investor_relations",
    "routine",
}


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    return date.fromisoformat(value)


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _rule_kind(title: str) -> str:
    normalized = title.replace(" ", "")
    if any(word in normalized for word in ("半年度报告", "年度报告", "季度报告")):
        return "financial_statement"
    if "回购" in normalized:
        return "buyback"
    if any(word in normalized for word in ("减资", "注册资本", "股本变动")):
        return "capital_structure"
    if "资产减值" in normalized:
        return "asset_impairment"
    if "会计政策" in normalized:
        return "accounting_policy"
    if any(word in normalized for word in ("提供担保", "对外担保")):
        return "guarantee"
    if "经营数据" in normalized:
        return "operating_data"
    if any(word in normalized for word in ("股东会", "董事会", "监事会")):
        return "governance"
    if any(word in normalized for word in ("业绩说明会", "投资者关系", "接待日")):
        return "investor_relations"
    if any(word in normalized for word in ("管理制度", "登记管理", "法律意见书")):
        return "governance"
    return "unknown"


def _review(
    item: dict[str, Any],
    validity_from: date,
    symbol: str,
    archive_dir: Path,
) -> AnnouncementReview:
    published_at = _datetime(
        datetime.fromtimestamp(
            int(item["announcementTime"]) / 1000,
            timezone(timedelta(hours=8)),
        ).isoformat(),
        "announcementTime",
    )
    announcement_id = str(item["announcementId"])
    source_url = PDF_BASE_URL + str(item["adjunctUrl"]).lstrip("/")
    rule_kind = _rule_kind(str(item.get("announcementTitle") or ""))
    candidate = rule_kind not in _NON_CANDIDATE_KINDS
    review_status = (
        REVIEW_PENDING_HUMAN_REVIEW
        if candidate else REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE
    )
    pdf_path = (
        archive_dir
        / "announcements"
        / published_at.date().isoformat()
        / f"{announcement_id}.pdf"
    )
    sha256 = download_disclosure_pdf(source_url, pdf_path)
    ref = {
        "id": f"{symbol}-announcement-{announcement_id}",
        "path": _relative(pdf_path),
        "sha256": sha256,
        "source_url": source_url,
    }
    return AnnouncementReview(
        announcement_id=announcement_id,
        published_at=published_at,
        title=str(item.get("announcementTitle") or ""),
        source_url=source_url,
        rule_kind=rule_kind,
        review_status=review_status,
        materiality_candidate=candidate,
        pre_model=published_at.date() < validity_from,
        evidence_refs=(ref,),
        notes=(
            "Rule classification from announcement title only; "
            "not an independent materiality determination."
        ),
    )


def _index_ref(index_path: Path, symbol: str) -> dict[str, str]:
    return {
        "id": f"{symbol}-cninfo-event-index",
        "path": _relative(index_path),
        "sha256": _digest(index_path),
    }


def _scan_from(package: dict[str, Any], symbol: str) -> date:
    return date.fromisoformat(SCAN_START_OVERRIDE[symbol])


def _package_payloads() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(PACKAGE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = str(payload["symbol"])
        if symbol not in ISSUER_NAMES:
            continue
        result[symbol] = payload
    if set(result) != set(ISSUER_NAMES):
        raise ValueError("One or more M1 valuation packages are missing")
    return result


def collect(packages: dict[str, dict[str, Any]], run_id: str) -> dict[str, Any]:
    collected = datetime.now(timezone.utc)
    run_dir = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    receipts: dict[str, dict[str, Any]] = {}

    for symbol, package in sorted(packages.items()):
        symbol_dir = run_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=False)
        validity = package["model_validity_input"]
        validity_from = _date(validity["valid_from"], "validity.valid_from")
        pit = package["point_in_time"]
        validity_to = _date(pit["valuation_date"], "valuation_date")
        scan_from = _scan_from(package, symbol)
        scan_to = max(validity_to, validity_from)

        index_payload = search_announcement_window(
            symbol,
            scan_from.isoformat(),
            scan_to.isoformat(),
            ISSUER_NAMES[symbol],
        )
        index_path = symbol_dir / "cninfo-index.json"
        index_path.write_text(
            json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        announcements_raw = index_payload["announcements"]
        if len(announcements_raw) != index_payload["total_announcements"]:
            raise ValueError(
                f"CNINFO announcement count mismatch for {symbol}"
            )
        reviews = tuple(
            _review(item, validity_from, symbol, symbol_dir)
            for item in announcements_raw
        )
        candidates = [item for item in reviews if item.materiality_candidate]
        validity_candidates = [
            item for item in candidates if not item.pre_model
        ]
        pre_model_candidates = [item for item in candidates if item.pre_model]
        pre_model_status = (
            PRE_MODEL_PENDING_HUMAN_REVIEW
            if pre_model_candidates else PRE_MODEL_REVIEWED_NO_CANDIDATES
        )
        blockers = (
            ["pre-model disclosures require human review before the model basis is complete"]
            if pre_model_candidates else []
        )
        evidence_refs = [
            _index_ref(index_path, symbol),
            *(
                ref
                for review in reviews
                for ref in review.evidence_refs
            ),
        ]
        scan = EventScanResult(
            schema_version=EVENT_SCAN_SCHEMA,
            symbol=symbol,
            provider="cninfo",
            scan_from=scan_from,
            scan_to=scan_to,
            validity_from=validity_from,
            validity_to=validity_to,
            status=(
                SCAN_COMPLETE_MATERIAL_EVENTS
                if validity_candidates else SCAN_COMPLETE_NO_MATERIAL_EVENT
            ),
            coverage_status=COVERAGE_COMPLETE,
            pre_model_review_status=pre_model_status,
            announcements=reviews,
            blockers=tuple(blockers),
            evidence_refs=tuple(evidence_refs),
            retrieved_at=collected,
            parser_version=PARSER_VERSION,
        )
        round_trip = event_scan_from_payload(scan.as_policy())
        if round_trip.as_policy() != scan.as_policy():
            raise ValueError(f"Event scan round trip changed for {symbol}")
        evidence_path = symbol_dir / "evidence.json"
        evidence_path.write_text(
            json.dumps(scan.as_policy(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        receipts[symbol] = {
            "symbol": symbol,
            "path": _relative(evidence_path),
            "sha256": _digest(evidence_path),
            "scan_from": scan_from.isoformat(),
            "scan_to": scan_to.isoformat(),
            "validity_from": validity_from.isoformat(),
            "validity_to": validity_to.isoformat(),
            "status": scan.status,
            "coverage_status": scan.coverage_status,
            "pre_model_review_status": scan.pre_model_review_status,
            "announcement_count": len(reviews),
            "pre_model_candidate_count": len(pre_model_candidates),
            "validity_candidate_count": len(validity_candidates),
        }
    return {
        "schema_version": "m1-event-scan-run-v1",
        "run_id": run_id,
        "generated_at": collected.isoformat(),
        "action": "no_order",
        "receipts": receipts,
    }


def _attach(packages: dict[str, dict[str, Any]], receipts: dict[str, Any]) -> None:
    for symbol, receipt in receipts["receipts"].items():
        package = packages[symbol]
        reference = {
            "id": f"{symbol}-event-scan-{receipts['run_id']}",
            "symbol": symbol,
            "path": receipt["path"],
            "sha256": receipt["sha256"],
        }
        validity = package["model_validity_input"]
        validity["event_scan_ref"] = reference
        validity["event_scan_evidence_refs"] = [reference]
        validity["events"] = []
        package["dependencies"]["scan_watermark"] = (
            f"m1-cninfo-event-scan-v1:{receipt['sha256'][:16]}"
        )
        blockers = list(package.get("blockers") or [])
        pre_model_blocker = (
            "pre-model event-scan disclosures require human review"
        )
        if not any(blocker.startswith("pre-model event-scan") for blocker in blockers):
            blockers.append(pre_model_blocker)
        package["blockers"] = blockers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-attach", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    packages = _package_payloads()
    receipt = collect(packages, run_id)
    if not args.no_attach:
        _attach(packages, receipt)
        for symbol, payload in packages.items():
            target = next(
                path for path in PACKAGE_DIR.glob(f"{symbol}-*.json")
            )
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    run_path = EVIDENCE_ROOT / run_id / "manifest.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.json_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

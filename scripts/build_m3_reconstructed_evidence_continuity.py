"""Build one real-source reconstructed M3 evidence continuity candidate.

The command is local and offline.  It verifies the already archived CNINFO
PDFs, Tencent price file, reviewed distribution registry and two prior runtime
evidence packages, then writes a standalone no-order workbook.  It does not
claim a contemporaneous rule, actual entry, human decision or valuation.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m3_reconstructed_evidence_continuity import (  # noqa: E402
    ACTION_NO_ORDER,
    DIRECTION_DOWN,
    DIRECTION_NOT_COMPARABLE,
    DIRECTION_UP,
    IMPACT_NOT_COMPARABLE,
    IMPACT_STRENGTHENED,
    IMPACT_WEAKENED,
    METRIC_BASIC_EPS,
    METRIC_CASH_PER_SHARE,
    METRIC_CLOSE_PRICE,
    METRIC_ENDING_SHARES,
    METRIC_PARENT_EQUITY,
    METRIC_PARENT_PROFIT,
    PERIOD_BASIS_BASELINE,
    PERIOD_BASIS_FY,
    PERIOD_BASIS_YTD,
    TRACE_NAMESPACE,
    TRACE_SCHEMA,
    from_payload,
)
from value_investment_agent.m3_reconstructed_evidence_workbook import (  # noqa: E402
    write_reconstructed_evidence_workbook,
)


CN_TZ = timezone(timedelta(hours=8))

DEFAULT_REPLAY = (
    ROOT
    / "runtime"
    / "m3-historical-research-replay-20260924-v1"
    / "replay.json"
)
DEFAULT_EQUITY_EVIDENCE = (
    ROOT
    / "runtime"
    / "company-research"
    / "600519-consolidated-parent-equity-inputs-20260914T115049Z"
    / "evidence.json"
)
DEFAULT_LATEST_EVIDENCE = (
    ROOT
    / "runtime"
    / "company-research"
    / "600519-latest-20260909T033748190833Z"
    / "evidence.json"
)
DEFAULT_DISTRIBUTIONS = ROOT / "docs" / "reviewed-cash-distributions.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--equity-evidence", type=Path, default=DEFAULT_EQUITY_EVIDENCE)
    parser.add_argument("--latest-evidence", type=Path, default=DEFAULT_LATEST_EVIDENCE)
    parser.add_argument("--distributions", type=Path, default=DEFAULT_DISTRIBUTIONS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--as-of",
        type=lambda value: datetime.fromisoformat(value),
        default=None,
    )
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Artifact path is required")
    return (root / value.strip().replace("\\", "/")).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _verify(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    actual = _digest(path)
    if actual.lower() != str(expected).lower():
        raise ValueError(
            f"{label} hash mismatch: expected {str(expected).lower()}, got {actual}"
        )
    return actual


def _metric(
    *,
    key: str,
    period: str,
    basis: str,
    current: object,
    comparative: object | None,
    unit: str,
    ref: str,
    status: str,
) -> dict[str, Any]:
    return {
        "metric": key,
        "period_end": period,
        "period_basis": basis,
        "current_value": str(current),
        "comparative_value": str(comparative) if comparative is not None else None,
        "unit": unit,
        "reference_id": ref,
        "validation_status": status,
        "source_label": key,
    }


def _annual_ref(
    entry: Mapping[str, Any],
    *,
    ref_id: str,
    root: Path,
) -> tuple[dict[str, Any], Path]:
    # Chain entries do not contain a local path; derive the archived PDF by id.
    pdf_path = next(
        (root / "runtime" / "historical-filing-index").rglob(
            f"600519-{str(entry['source_id']).split(':', 1)[-1]}.pdf"
        ),
        None,
    )
    if pdf_path is None:
        raise ValueError(f"Archived PDF not found for {entry.get('source_id')}")
    actual = _verify(
        pdf_path.resolve(),
        str(entry["raw_file_hash"]),
        f"{ref_id} PDF",
    )
    return (
        {
            "ref_id": ref_id,
            "kind": "filing",
            "path": str(pdf_path.resolve().relative_to(ROOT)),
            "sha256": actual,
            "source_url": str(entry["source_url"]),
            "available_at": str(entry["available_at"]),
            "role": str(entry["source_id"]),
            "notes": "verified local PDF hash",
        },
        pdf_path.resolve(),
    )


def _row(path: Path, field: str, period: str) -> Mapping[str, Any]:
    for item in _load_json(path).get("rows") or ():
        if item.get("field") == field and item.get("period_end") == period:
            return item
    raise ValueError(f"{field} row not found for {period}: {path}")


def build_payload(
    *,
    replay_path: Path,
    equity_path: Path,
    latest_path: Path,
    distributions_path: Path,
    generated_at: datetime,
    root: Path = ROOT,
) -> dict[str, Any]:
    replay = _load_json(replay_path)
    if replay.get("schema_version") != "m3-historical-research-replay-v1":
        raise ValueError("Unsupported historical replay schema")
    if replay.get("namespace") != "HISTORICAL_RESEARCH_REPLAY":
        raise ValueError("Historical replay namespace is required")
    if replay.get("action") != ACTION_NO_ORDER:
        raise ValueError("Historical replay must remain no_order")
    if replay.get("symbol") != "600519":
        raise ValueError("Only the frozen 600519 replay is supported")
    if replay.get("replay_date") != "2024-06-21":
        raise ValueError("Unexpected historical replay date")

    facts = replay["then_known_facts"]
    annual_ref_payload = facts["source_ref"]
    annual_path = _as_path(root, annual_ref_payload["path"])
    _verify(
        annual_path,
        annual_ref_payload["sha256"],
        "2023 annual PDF",
    )
    distribution_ref = next(
        item
        for item in replay.get("then_known_filings") or ()
        if item.get("id") == "cninfo:1220324741"
    )
    distribution_path = _as_path(root, distribution_ref["path"])
    _verify(
        distribution_path,
        distribution_ref["sha256"],
        "distribution PDF",
    )
    quote_ref = replay["then_known_quote"]["source_ref"]
    price_path = _as_path(root, quote_ref["path"])
    _verify(price_path, quote_ref["sha256"], "price file")

    replay_hash = _verify(replay_path.resolve(), _digest(replay_path), "frozen replay")
    equity_hash = _verify(
        equity_path.resolve(), _digest(equity_path), "equity evidence package"
    )
    latest_hash = _verify(
        latest_path.resolve(), _digest(latest_path), "latest evidence package"
    )
    distributions_hash = _verify(
        distributions_path.resolve(),
        _digest(distributions_path),
        "reviewed distributions registry",
    )

    equity = _load_json(equity_path)
    chain = {
        item["period_end"]: item
        for item in equity.get("chain") or ()
        if item.get("period_end") in {"2023-12-31", "2024-12-31", "2025-12-31"}
    }
    if set(chain) != {"2023-12-31", "2024-12-31", "2025-12-31"}:
        raise ValueError("Equity evidence is missing required annual periods")
    annual_refs: dict[str, dict[str, Any]] = {}
    for ref_id, period in (
        ("annual-2023", "2023-12-31"),
        ("annual-2024", "2024-12-31"),
        ("annual-2025", "2025-12-31"),
    ):
        annual_refs[ref_id], _ = _annual_ref(chain[period], ref_id=ref_id, root=root)

    interim_path = _as_path(
        root,
        "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf",
    )
    interim_hash = _verify(interim_path, "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6", "2026 interim PDF")
    interim_row = _row(latest_path, "parent_profit", "2026-06-30")
    if interim_row.get("sha256") != interim_hash:
        raise ValueError("2026 interim row hash does not match the archived PDF")

    distribution_entry = next(
        item
        for item in _load_json(distributions_path).get("events") or ()
        if any(
            ref.get("url", "").endswith("/1220324741.PDF")
            for ref in item.get("evidence") or ()
        )
    )

    evidence_references = [
        annual_refs["annual-2023"],
        annual_refs["annual-2024"],
        annual_refs["annual-2025"],
        {
            "ref_id": "interim-2026-h1",
            "kind": "filing",
            "path": str(interim_path.relative_to(ROOT)),
            "sha256": interim_hash,
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF",
            "available_at": "2026-08-16T00:00:00+08:00",
            "role": "cninfo:1225475868",
            "notes": "verified local PDF hash",
        },
        {
            "ref_id": "distribution-2024",
            "kind": "filing",
            "path": str(distribution_path.relative_to(ROOT)),
            "sha256": str(distribution_ref["sha256"]).lower(),
            "source_url": str(distribution_ref["source_url"]),
            "available_at": str(distribution_ref["available_at"]),
            "role": "2024 distribution filing",
            "notes": "verified local PDF hash",
        },
        {
            "ref_id": "price-2024",
            "kind": "price_file",
            "path": str(price_path.relative_to(ROOT)),
            "sha256": str(quote_ref["sha256"]).lower(),
            "source_url": str(quote_ref["source_url"]),
            "available_at": str(quote_ref["available_at"]),
            "role": "authenticated 2024 price file",
            "notes": "verified local file hash",
        },
        {
            "ref_id": "frozen-replay",
            "kind": "frozen_replay",
            "path": str(replay_path.resolve().relative_to(ROOT)),
            "sha256": replay_hash,
            "source_url": "",
            "available_at": replay.get("generated_at"),
            "role": "frozen historical research replay",
            "notes": "retrospective rule only",
        },
        {
            "ref_id": "equity-evidence",
            "kind": "facts_evidence",
            "path": str(equity_path.resolve().relative_to(ROOT)),
            "sha256": equity_hash,
            "source_url": "",
            "available_at": generated_at.isoformat(),
            "role": "verified consolidated parent equity chain",
            "notes": "runtime package, not a public data origin",
        },
        {
            "ref_id": "latest-evidence",
            "kind": "facts_evidence",
            "path": str(latest_path.resolve().relative_to(ROOT)),
            "sha256": latest_hash,
            "source_url": "",
            "available_at": generated_at.isoformat(),
            "role": "2026 interim extraction",
            "notes": "two-decoder issuer original, no independent source",
        },
        {
            "ref_id": "reviewed-distributions",
            "kind": "facts_evidence",
            "path": str(distributions_path.resolve().relative_to(ROOT)),
            "sha256": distributions_hash,
            "source_url": "",
            "available_at": generated_at.isoformat(),
            "role": "reviewed cash distribution registry",
            "notes": "tracked review registry",
        },
    ]

    baseline_facts = [
        _metric(
            key=METRIC_PARENT_PROFIT,
            period="2023-12-31",
            basis=PERIOD_BASIS_BASELINE,
            current=chain["2023-12-31"]["parent_profit_cny"],
            comparative=None,
            unit="CNY",
            ref="annual-2023",
            status=str(chain["2023-12-31"]["validation_status"]),
        ),
        _metric(
            key=METRIC_PARENT_EQUITY,
            period="2023-12-31",
            basis=PERIOD_BASIS_BASELINE,
            current=chain["2023-12-31"]["parent_equity_cny"],
            comparative=None,
            unit="CNY",
            ref="annual-2023",
            status=str(chain["2023-12-31"]["validation_status"]),
        ),
        _metric(
            key=METRIC_BASIC_EPS,
            period="2023-12-31",
            basis=PERIOD_BASIS_BASELINE,
            current=chain["2023-12-31"]["reported_basic_eps"],
            comparative=None,
            unit="CNY/share",
            ref="annual-2023",
            status=str(chain["2023-12-31"]["validation_status"]),
        ),
        _metric(
            key=METRIC_ENDING_SHARES,
            period="2023-12-31",
            basis=PERIOD_BASIS_BASELINE,
            current=chain["2023-12-31"]["ending_issued_shares"],
            comparative=None,
            unit="shares",
            ref="annual-2023",
            status=str(chain["2023-12-31"]["validation_status"]),
        ),
        _metric(
            key=METRIC_CLOSE_PRICE,
            period="2024-06-21",
            basis=PERIOD_BASIS_BASELINE,
            current=replay["then_known_quote"]["close_cny"],
            comparative=None,
            unit="CNY",
            ref="price-2024",
            status="authenticated_historical_price_file",
        ),
        _metric(
            key=METRIC_CASH_PER_SHARE,
            period="2023-12-31",
            basis=PERIOD_BASIS_BASELINE,
            current=distribution_entry["cash_per_share"],
            comparative=None,
            unit="CNY/share",
            ref="distribution-2024",
            status="reviewed_distribution_registry",
        ),
    ]

    # The chain already includes current and prior values through the original
    # report's comparative columns, so bind those instead of guessing priors.
    fy2023 = chain["2023-12-31"]
    fy2024 = chain["2024-12-31"]
    fy2025 = chain["2025-12-31"]
    disclosures = [
        {
            "observation_id": "600519-2024-annual",
            "disclosure_id": str(fy2024["source_id"]),
            "title": "贵州茅台2024年年度报告",
            "report_period": "2024-12-31",
            "period_basis": PERIOD_BASIS_FY,
            "available_at": str(fy2024["available_at"]),
            "evidence_quality": str(fy2024["validation_status"]),
            "metrics": [
                _metric(
                    key=METRIC_PARENT_PROFIT,
                    period="2024-12-31",
                    basis=PERIOD_BASIS_FY,
                    current=fy2024["parent_profit_cny"],
                    comparative=fy2023["parent_profit_cny"],
                    unit="CNY",
                    ref="annual-2024",
                    status=str(fy2024["validation_status"]),
                ),
                _metric(
                    key=METRIC_PARENT_EQUITY,
                    period="2024-12-31",
                    basis=PERIOD_BASIS_FY,
                    current=fy2024["parent_equity_cny"],
                    comparative=fy2023["parent_equity_cny"],
                    unit="CNY",
                    ref="annual-2024",
                    status=str(fy2024["validation_status"]),
                ),
                _metric(
                    key=METRIC_BASIC_EPS,
                    period="2024-12-31",
                    basis=PERIOD_BASIS_FY,
                    current=fy2024["reported_basic_eps"],
                    comparative=fy2023["reported_basic_eps"],
                    unit="CNY/share",
                    ref="annual-2024",
                    status=str(fy2024["validation_status"]),
                ),
            ],
        },
        {
            "observation_id": "600519-2025-annual",
            "disclosure_id": str(fy2025["source_id"]),
            "title": "贵州茅台2025年年度报告",
            "report_period": "2025-12-31",
            "period_basis": PERIOD_BASIS_FY,
            "available_at": str(fy2025["available_at"]),
            "evidence_quality": str(fy2025["validation_status"]),
            "metrics": [
                _metric(
                    key=METRIC_PARENT_PROFIT,
                    period="2025-12-31",
                    basis=PERIOD_BASIS_FY,
                    current=fy2025["parent_profit_cny"],
                    comparative=fy2024["parent_profit_cny"],
                    unit="CNY",
                    ref="annual-2025",
                    status=str(fy2025["validation_status"]),
                ),
                _metric(
                    key=METRIC_PARENT_EQUITY,
                    period="2025-12-31",
                    basis=PERIOD_BASIS_FY,
                    current=fy2025["parent_equity_cny"],
                    comparative=fy2024["parent_equity_cny"],
                    unit="CNY",
                    ref="annual-2025",
                    status=str(fy2025["validation_status"]),
                ),
                _metric(
                    key=METRIC_BASIC_EPS,
                    period="2025-12-31",
                    basis=PERIOD_BASIS_FY,
                    current=fy2025["reported_basic_eps"],
                    comparative=fy2024["reported_basic_eps"],
                    unit="CNY/share",
                    ref="annual-2025",
                    status=str(fy2025["validation_status"]),
                ),
            ],
        },
        {
            "observation_id": "600519-2026-h1",
            "disclosure_id": "cninfo:1225475868",
            "title": "贵州茅台2026年半年度报告",
            "report_period": "2026-06-30",
            "period_basis": PERIOD_BASIS_YTD,
            "available_at": "2026-08-16T00:00:00+08:00",
            "evidence_quality": "issuer_original_two_decoder_no_independent_source",
            "metrics": [
                _metric(
                    key=METRIC_PARENT_PROFIT,
                    period="2026-06-30",
                    basis=PERIOD_BASIS_YTD,
                    current=interim_row["current"],
                    comparative=interim_row["comparative_from_current_report"],
                    unit="CNY",
                    ref="interim-2026-h1",
                    status="issuer_original_two_decoder_no_independent_source",
                )
            ],
        },
    ]

    comparisons = [
        {
            "dimension": METRIC_PARENT_PROFIT,
            "baseline_value": fy2023["parent_profit_cny"],
            "observation_id": "600519-2024-annual",
            "observation_value": fy2024["parent_profit_cny"],
            "change_direction": DIRECTION_UP,
            "impact": IMPACT_STRENGTHENED,
            "arithmetic_note": "FY2024 归母净利润高于 FY2023 基准",
            "evidence_ref_ids": ["annual-2023", "annual-2024"],
        },
        {
            "dimension": METRIC_PARENT_PROFIT,
            "baseline_value": fy2023["parent_profit_cny"],
            "observation_id": "600519-2025-annual",
            "observation_value": fy2025["parent_profit_cny"],
            "change_direction": DIRECTION_UP,
            "impact": IMPACT_STRENGTHENED,
            "arithmetic_note": "FY2025 归母净利润高于 FY2023 基准，但低于 FY2024",
            "evidence_ref_ids": ["annual-2023", "annual-2025"],
        },
        {
            "dimension": METRIC_PARENT_PROFIT,
            "baseline_value": interim_row["comparative_from_current_report"],
            "observation_id": "600519-2026-h1",
            "observation_value": interim_row["current"],
            "change_direction": DIRECTION_DOWN,
            "impact": IMPACT_WEAKENED,
            "arithmetic_note": "2026H1 对 2025H1 的可比归母净利润下降；这是披露口径算术，不是论点裁决",
            "evidence_ref_ids": ["interim-2026-h1", "latest-evidence"],
        },
        {
            "dimension": METRIC_PARENT_EQUITY,
            "baseline_value": fy2023["parent_equity_cny"],
            "observation_id": "600519-2024-annual",
            "observation_value": fy2024["parent_equity_cny"],
            "change_direction": DIRECTION_UP,
            "impact": IMPACT_STRENGTHENED,
            "arithmetic_note": "FY2024 归母净资产高于 FY2023 基准",
            "evidence_ref_ids": ["annual-2023", "annual-2024"],
        },
        {
            "dimension": METRIC_PARENT_EQUITY,
            "baseline_value": fy2023["parent_equity_cny"],
            "observation_id": "600519-2025-annual",
            "observation_value": fy2025["parent_equity_cny"],
            "change_direction": DIRECTION_UP,
            "impact": IMPACT_STRENGTHENED,
            "arithmetic_note": "FY2025 归母净资产继续高于 FY2023 基准",
            "evidence_ref_ids": ["annual-2023", "annual-2025"],
        },
        {
            "dimension": METRIC_BASIC_EPS,
            "baseline_value": fy2023["reported_basic_eps"],
            "observation_id": "600519-2024-annual",
            "observation_value": fy2024["reported_basic_eps"],
            "change_direction": DIRECTION_UP,
            "impact": IMPACT_STRENGTHENED,
            "arithmetic_note": "FY2024 EPS 高于 FY2023 基准",
            "evidence_ref_ids": ["annual-2023", "annual-2024"],
        },
        {
            "dimension": METRIC_BASIC_EPS,
            "baseline_value": fy2023["reported_basic_eps"],
            "observation_id": "600519-2025-annual",
            "observation_value": fy2025["reported_basic_eps"],
            "change_direction": DIRECTION_UP,
            "impact": IMPACT_STRENGTHENED,
            "arithmetic_note": "FY2025 EPS 高于 FY2023 基准，但低于 FY2024",
            "evidence_ref_ids": ["annual-2023", "annual-2025"],
        },
        {
            "dimension": METRIC_CLOSE_PRICE,
            "baseline_value": replay["then_known_quote"]["close_cny"],
            "observation_id": "600519-2026-h1",
            "observation_value": replay["then_known_quote"]["close_cny"],
            "change_direction": DIRECTION_NOT_COMPARABLE,
            "impact": IMPACT_NOT_COMPARABLE,
            "arithmetic_note": "当前追踪不引入未经该观察日验证的新行情，因此不比较",
            "evidence_ref_ids": ["price-2024"],
        },
    ]

    return {
        "trace_id": "600519-reconstructed-evidence-continuity-2024-06-21-v1",
        "schema_version": TRACE_SCHEMA,
        "namespace": TRACE_NAMESPACE,
        "symbol": "600519",
        "generated_at": generated_at.isoformat(),
        "baseline": {
            "baseline_date": "2024-06-21",
            "source_replay_id": str(replay["replay_id"]),
            "rule_version": str(replay["rule"]["rule_version"]),
            "rule_registered_at": str(replay["rule"]["registered_at"]),
            "rule_registration_status": str(replay["rule"]["rule_registration_status"]),
            "future_rule_version_used": bool(replay["future_rule_version_used"]),
            "strict_contemporaneous_rule_pit": False,
            "facts": baseline_facts,
            "note": "由冻结历史重放绑定的事实与报价；规则是事后登记，不构成同期 PIT。",
        },
        "disclosures": disclosures,
        "comparisons": comparisons,
        "evidence_references": evidence_references,
        "conclusion_status": "RECONSTRUCTED_EVIDENCE_ONLY",
        "actual_entry_present": False,
        "human_decision": None,
        "requires_human_review": True,
        "blockers": [
            "strict_contemporaneous_rule_pit_not_proven",
            "retrospective_rule_version_used",
            "reconstructed_not_actual_entry",
            "arithmetic_trend_requires_human_research_review",
            "action_no_order",
        ],
        "action": ACTION_NO_ORDER,
    }


def main() -> int:
    args = parse_args()
    generated_at = args.as_of or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    payload = build_payload(
        replay_path=args.replay,
        equity_path=args.equity_evidence,
        latest_path=args.latest_evidence,
        distributions_path=args.distributions,
        generated_at=generated_at,
    )
    trace = from_payload(payload)
    output_dir = args.output_dir or (
        ROOT / "runtime" / f"m3-reconstructed-continuity-{generated_at:%Y%m%dT%H%M%SZ}"
    )
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Reconstructed continuity output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    workbook_path = (
        output_dir / "A股价值投资_M3重建证据连续性候选_20260924.xlsx"
    )
    workbook_receipt = write_reconstructed_evidence_workbook(
        trace,
        output=workbook_path,
        root=output_dir,
    )
    trace_path = output_dir / "trace.json"
    trace_path.write_text(trace.to_json() + "\n", encoding="utf-8")
    input_path = output_dir / "input-payload.json"
    input_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": TRACE_SCHEMA,
        "namespace": TRACE_NAMESPACE,
        "trace_id": trace.trace_id,
        "trace_sha256": trace.trace_sha256,
        "workbook": workbook_receipt,
        "input_payload_sha256": _digest(input_path),
        "generated_at": generated_at.isoformat(),
        "strict_contemporaneous_rule_pit": "NOT_PROVEN",
        "action": ACTION_NO_ORDER,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

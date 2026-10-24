"""Run one real M2 opportunity-discovery snapshot and publish an Excel board.

This script is read-only with respect to the existing WPS workbook, production
PostgreSQL, scheduler and server projects. It writes only a runtime preview;
the existing Canonical WPS workbook remains the sole formal user workbook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m2_discovery_engine import (
    M2ScreeningPolicy,
    build_discovery_receipt,
)
from value_investment_agent.m2_discovery_workbook import write_discovery_workbook
from value_investment_agent.m2_market_data import (
    fetch_eastmoney_dividends,
    fetch_sina_industry_quotes,
    fetch_tencent_board_rank,
)
from value_investment_agent.m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    EvidenceReference,
    discovery_receipt_from_payload,
)
from value_investment_agent.application.discovery.official_universe_collection import (
    collect_official_m2_input, screening_quote_date, verify_retained_official_input,
    read_receipt_bound_official_input,
)
from value_investment_agent.application.product.value_discovery_surface import publish_value_discovery_report
from value_investment_agent.infrastructure.screening.evidence_screen_v3 import (
    VERSION as EVIDENCE_SCREEN_VERSION,
    build_discovery_receipt as build_evidence_receipt,
)
from value_investment_agent.infrastructure.screening.financial_export_v2 import (
    financial_fetched_at as _financial_fetched_at,
    retained_run_clock as _retained_run_clock,
)
from value_investment_agent.application.discovery.public_financial_input import (
    build_financial_input, verify_public_supplement,
)


CHINA = timezone(timedelta(hours=8))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(output_dir: Path, name: str, data: bytes) -> Path:
    target = output_dir / name
    target.write_bytes(data)
    return target


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _reference(
    ref_id: str,
    path: Path,
    *,
    root: Path,
    source_name: str,
    source_url: str,
    fetched_at: datetime,
) -> EvidenceReference:
    return EvidenceReference(
        id=ref_id,
        path=str(path.relative_to(root)),
        sha256=_sha(path.read_bytes()),
        source_name=source_name,
        source_url=source_url,
        fetched_at=fetched_at,
    )


def _payload_fetched_at(payload: Mapping[str, object], name: str) -> datetime:
    value = payload.get("fetched_at")
    if not value:
        raise RuntimeError(f"{name} payload has no fetched_at and cannot be replay-restamped")
    return datetime.fromisoformat(str(value))


def _collect_official(output_dir: Path, root: Path) -> tuple[dict, EvidenceReference]:
    return collect_official_m2_input(output_dir, root)


def run_once(
    *,
    root: Path,
    output_dir: Path,
    wps_dir: Path | None,
    max_per_channel: int,
    skip_dividend: bool,
    reuse_inputs: bool,
    project_leads: bool = False,
    skip_workbook: bool = False,
    collect_public_financials: bool = False,
) -> dict:
    if reuse_inputs and collect_public_financials:
        raise ValueError('historical replay cannot collect current financial observations')
    if wps_dir is not None:
        raise ValueError("M2 may not create a second WPS workbook; use the runtime preview")
    if reuse_inputs and (output_dir / "m2-opportunity-discovery.xlsx").exists():
        raise ValueError("reuse requires an input-only directory; existing workbook must remain immutable")
    if reuse_inputs and project_leads and (output_dir / 'value-discovery-report.json').exists():
        raise ValueError('reuse requires an input-only directory; existing research report must remain immutable')
    wall_now = datetime.now(timezone.utc)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = M2ScreeningPolicy(max_per_channel=max_per_channel)
    receipt_builder = build_evidence_receipt

    if reuse_inputs:
        retained_generated_at, quote_date, retained_run_id = _retained_run_clock(output_dir)
        generated_at = retained_generated_at
        run_id = f"m2-replay-{wall_now.astimezone(CHINA).strftime('%Y%m%dT%H%M%S')}Z"
        replay_of_run_id = retained_run_id
        original = json.loads((output_dir / 'receipt.json').read_text(encoding='utf-8'))
        if original['rule_version'] == EVIDENCE_SCREEN_VERSION:
            receipt_builder = build_evidence_receipt
        elif original['rule_version'] == policy.rule_version:
            receipt_builder = build_discovery_receipt
        else:
            raise ValueError('unsupported retained M2 rule version')
    else:
        if any((output_dir / name).exists() for name in (
            'receipt.json', 'official-universe.json', 'tencent-market.json',
            'sina-industry-quotes.json', 'eastmoney-dividends.json', 'retained-financial-points.json')):
            raise ValueError('fresh M2 collection requires a new input directory; use --reuse-inputs for history')
        generated_at = wall_now
        quote_date = wall_now.astimezone(CHINA).date().isoformat()
        run_id = f"m2-{wall_now.astimezone(CHINA).strftime('%Y%m%dT%H%M%S')}Z"
        replay_of_run_id = None

    required_inputs = {
        "official": output_dir / "official-universe.json",
        "tencent": output_dir / "tencent-market.json",
        "sina": output_dir / "sina-industry-quotes.json",
        "dividend": output_dir / "eastmoney-dividends.json",
        "financial": output_dir / "retained-financial-points.json",
    }
    if reuse_inputs:
        missing_inputs = [name for name, path in required_inputs.items() if not path.exists()]
        if missing_inputs:
            raise RuntimeError(
                "--reuse-inputs requires every retained input: " + ", ".join(missing_inputs)
            )
        official_path = required_inputs["official"]
        official_bytes = read_receipt_bound_official_input(official_path, root=root, receipt=original)
        official_payload = json.loads(official_bytes.decode('utf-8'))
        verify_retained_official_input(official_payload, root=root)
        official_fetched = _payload_fetched_at(official_payload, "official")
        official_ref = _reference(
            "official", official_path, root=root,
            source_name="沪深北交易所官方证券清单",
            source_url="https://www.szse.cn | https://query.sse.com.cn | https://www.bse.cn",
            fetched_at=official_fetched,
        )
        tencent_path = required_inputs["tencent"]
        tencent_payload = json.loads(tencent_path.read_text(encoding="utf-8"))
        tencent_ref = _reference(
            "tencent", tencent_path, root=root,
            source_name="AkShare / Tencent all-A market snapshot",
            source_url="https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj",
            fetched_at=_payload_fetched_at(tencent_payload, "tencent"),
        )
        sina_path = required_inputs["sina"]
        sina_payload = json.loads(sina_path.read_text(encoding="utf-8"))
        sina_ref = _reference(
            "sina", sina_path, root=root,
            source_name="AkShare / Sina Shenwan level-1 industry and quote snapshot",
            source_url="https://vip.stock.finance.sina.com.cn/mkt/#hs_a",
            fetched_at=_payload_fetched_at(sina_payload, "sina"),
        )
        dividend_path = required_inputs["dividend"]
        dividend_payload = json.loads(dividend_path.read_text(encoding="utf-8"))
        dividend_ref = _reference(
            "dividend", dividend_path, root=root,
            source_name="AkShare / Eastmoney annual cash dividend plan snapshot",
            source_url="https://data.eastmoney.com/yjfp/",
            fetched_at=_payload_fetched_at(dividend_payload, "dividend"),
        )
        financial_path = required_inputs["financial"]
        financial_payload = json.loads(financial_path.read_text(encoding="utf-8"))
        financial_points = financial_payload.get("points") or []
    else:
        # Financial evidence is independent of security-list and quote availability.
        # Retain it even when a later market provider fails; do not publish a scan.
        financial_payload = build_financial_input(root=root, output_dir=output_dir,
                                                 collect_public=collect_public_financials)
        financial_points = financial_payload['points']
        financial_path = _write(output_dir, "retained-financial-points.json", _json_bytes(financial_payload))
        official_payload, official_ref = _collect_official(output_dir, root)

        tencent_raw, tencent_payload = fetch_tencent_board_rank()
        tencent_path = _write(output_dir, "tencent-market.json", tencent_raw)
        tencent_ref = _reference(
            "tencent",
            tencent_path,
            root=root,
            source_name="AkShare / Tencent all-A market snapshot",
            source_url="https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj",
            fetched_at=_payload_fetched_at(tencent_payload, "tencent"),
        )

        sina_raw, sina_payload = fetch_sina_industry_quotes()
        sina_path = _write(output_dir, "sina-industry-quotes.json", sina_raw)
        sina_ref = _reference(
            "sina",
            sina_path,
            root=root,
            source_name="AkShare / Sina Shenwan level-1 industry and quote snapshot",
            source_url="https://vip.stock.finance.sina.com.cn/mkt/#hs_a",
            fetched_at=_payload_fetched_at(sina_payload, "sina"),
        )

        dividend_payload: dict = {"fiscal_year": "2025", "rows": []}
        if not skip_dividend:
            dividend_raw, dividend_payload = fetch_eastmoney_dividends(fiscal_year=2025)
            dividend_path = _write(output_dir, "eastmoney-dividends.json", dividend_raw)
            dividend_ref = _reference(
                "dividend",
                dividend_path,
                root=root,
                source_name="AkShare / Eastmoney annual cash dividend plan snapshot",
                source_url="https://data.eastmoney.com/yjfp/",
                fetched_at=_payload_fetched_at(dividend_payload, "dividend"),
            )
        else:
            dividend_raw = _json_bytes(dividend_payload)
            dividend_path = _write(output_dir, "eastmoney-dividends.json", dividend_raw)
            dividend_ref = _reference(
                "dividend",
                dividend_path,
                root=root,
                source_name="M2 dividend adapter skipped by operator",
                source_url="internal://m2/dividend-skipped",
                fetched_at=generated_at,
            )

    verify_public_supplement(root=root, payload=financial_payload,
                             evaluation_at=generated_at if reuse_inputs else datetime.now(timezone.utc))
    missing_financial = financial_payload.get("status") == "NOT_AVAILABLE"
    if missing_financial and financial_points:
        raise ValueError("NOT_AVAILABLE financial input cannot contain financial facts")
    # Absence is a gap, not evidence fetched at the collection clock.
    financial_ref = None if missing_financial else _reference(
        "financial", financial_path, root=root,
        source_name="Retained financial evidence and E1 public observations" if financial_payload.get('public_financial_input') else "Retained point-in-time financial evidence export",
        source_url="internal://m2/retained-financial-points" if financial_payload.get('public_financial_input') else "internal://runtime/server-export-payload",
        fetched_at=_financial_fetched_at(financial_payload))

    if not reuse_inputs:
        generated_at = datetime.now(timezone.utc)
    quote_date = screening_quote_date(official_payload, generated_at,
        retained_quote_date=quote_date if reuse_inputs else None)
    run_refs = {
        "official": official_ref,
        "tencent": tencent_ref,
        "sina": sina_ref,
        "dividend": dividend_ref,
    }
    if financial_ref is not None:
        run_refs["financial"] = financial_ref
    receipt = receipt_builder(
        run_id=run_id,
        generated_at=generated_at,
        official_payload=official_payload,
        tencent_payload=tencent_payload,
        sina_payload=sina_payload,
        dividend_payload=dividend_payload,
        financial_points=financial_points,
        quote_date=quote_date,
        run_refs=run_refs,
        policy=policy,
        quote_date_verified=False,
    )
    receipt_bytes = _json_bytes(receipt.as_policy())
    receipt_path = _write(output_dir, "receipt.json", receipt_bytes)
    lead_report_path = None
    if project_leads:
        lead_report_path = output_dir / "value-discovery-report.json"
        publish_value_discovery_report(root=root, receipt_path=receipt_path,
            receipt_sha256=_sha(receipt_bytes), output_path=lead_report_path)
    policy_path = _write(output_dir, "policy.json", _json_bytes(policy.as_policy()))

    workbook_path = output_dir / "m2-opportunity-discovery.xlsx"
    workbook_info = None if skip_workbook else write_discovery_workbook(
        receipt,
        policy,
        output=workbook_path,
        root=root,
    )

    # These equalities prove deterministic reconstruction from retained JSON,
    # not independent original-source verification or historical quote/PIT validity.
    # V2 official raw replay and original receipt binding are separate checks above.
    replay = discovery_receipt_from_payload(json.loads(receipt_bytes.decode("utf-8")))
    replay_matches_receipt = (
        replay == receipt
        and replay.candidate_signature == receipt.candidate_signature
        and replay.coverage_signature == receipt.coverage_signature
    )
    replay_build = receipt_builder(
        run_id=run_id,
        generated_at=generated_at,
        official_payload=json.loads((output_dir / "official-universe.json").read_text(encoding="utf-8")),
        tencent_payload=json.loads((output_dir / "tencent-market.json").read_text(encoding="utf-8")),
        sina_payload=json.loads((output_dir / "sina-industry-quotes.json").read_text(encoding="utf-8")),
        dividend_payload=json.loads((output_dir / "eastmoney-dividends.json").read_text(encoding="utf-8")),
        financial_points=json.loads((output_dir / "retained-financial-points.json").read_text(encoding="utf-8"))["points"],
        quote_date=quote_date,
        run_refs=run_refs,
        policy=policy,
        quote_date_verified=False,
    )
    replay_matches_inputs = (
        replay_build == receipt
        and replay_build.candidate_signature == receipt.candidate_signature
        and replay_build.coverage_signature == receipt.coverage_signature
    )

    counts = {
        channel: len(result.candidates)
        for channel, result in receipt.channel_results.items()
    }
    retained_financial_input = json.loads(financial_path.read_text(encoding='utf-8'))
    summary = {
        "run_id": run_id,
        "action": ACTION_NO_ORDER,
        "generated_at": receipt.generated_at.isoformat(),
        "as_of": receipt.as_of.isoformat(),
        "quote_date": receipt.quote_date,
        "quote_date_verification": "UNVERIFIED_PROVIDER_TRADE_DATE",
        "replay_of_run_id": replay_of_run_id,
        "input_mode": "HISTORICAL_REPLAY" if reuse_inputs else "LIVE_COLLECTION",
        "current_publication_eligible": False,
        "financial_input": {
            key: retained_financial_input.get(key)
            for key in ('status', 'gap_reason', 'input_adapter_version', 'annual_evidence_adoption', 'retained_generated_at', 'public_financial_input')
        },
        "rule_version": receipt.rule_version,
        "data_health": receipt.data_health.as_policy(),
        "channel_counts": counts,
        "legacy_comparison": receipt.legacy_comparison.as_policy(),
        "coverage_signature": receipt.coverage_signature,
        "candidate_signature": receipt.candidate_signature,
        "coverage_counts": {
            channel: result.as_policy()["coverage"]
            for channel, result in receipt.channel_results.items()
        },
        "receipt_path": str(receipt_path.relative_to(root)),
        "lead_report_path": str(lead_report_path.relative_to(root)) if lead_report_path else None,
        "workbook": workbook_info,
        "wps_workbook": None,
        "replay": {
            "receipt_bytes_match": replay_matches_receipt,
            "raw_inputs_match": replay_matches_inputs,
        },
    }
    manifest = {
        "schema_version": "m2-run-manifest-v1",
        "summary": summary,
        "files": {
            name: {
                "path": str(path.relative_to(root)),
                "sha256": _sha(path.read_bytes()),
            }
            for name, path in (
                ("official", output_dir / "official-universe.json"),
                ("tencent", output_dir / "tencent-market.json"),
                ("sina", output_dir / "sina-industry-quotes.json"),
                ("dividend", output_dir / "eastmoney-dividends.json"),
                ("financial", output_dir / "retained-financial-points.json"),
                ("receipt", receipt_path),
                *(((("lead_report", lead_report_path),) if lead_report_path else ())),
                ("policy", policy_path),
                *(((("workbook", workbook_path),) if not skip_workbook else ())),
            )
        },
    }
    _write(output_dir, "manifest.json", _json_bytes(manifest))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--wps-dir", type=Path)
    parser.add_argument("--no-wps", action="store_true")
    parser.add_argument("--max-per-channel", type=int, default=50)
    parser.add_argument("--skip-dividend", action="store_true")
    parser.add_argument("--reuse-inputs", action="store_true")
    parser.add_argument("--no-workbook", action="store_true", help="Write evidence JSON only; preserve Excel-frozen scope")
    parser.add_argument('--collect-public-financials', action='store_true', help='Collect public annual E1 observations; never financial admission')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or (
        ROOT
        / "runtime"
        / f"m2-opportunity-discovery-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    summary = run_once(
        root=ROOT,
        output_dir=output_dir,
        wps_dir=None if args.no_wps else args.wps_dir,
        max_per_channel=args.max_per_channel,
        skip_dividend=args.skip_dividend,
        reuse_inputs=args.reuse_inputs,
        project_leads=True,
        skip_workbook=args.no_workbook,
        collect_public_financials=args.collect_public_financials,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

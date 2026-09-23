"""Run one real M2 opportunity-discovery snapshot and publish an Excel board.

This script is read-only with respect to the existing WPS workbook, production
PostgreSQL, scheduler and server projects.  It writes only a new timestamped
runtime directory and, when requested, a new workbook in the WPS cloud folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
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
from value_investment_agent.official_universe import collect_security_lists


CHINA = timezone(timedelta(hours=8))
WPS_WORKBOOK_NAME = "A股价值投资_M2机会发现_{date}.xlsx"
DEFAULT_WPS_DIR = Path(
    r"C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪"
)


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


def _load_retained_financial_export(path: Path) -> tuple[list[dict], dict]:
    if not path.exists():
        return [], {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    points = payload.get("points") or []
    return points, payload


def _payload_fetched_at(payload: Mapping[str, object], name: str) -> datetime:
    value = payload.get("fetched_at")
    if not value:
        raise RuntimeError(f"{name} payload has no fetched_at and cannot be replay-restamped")
    return datetime.fromisoformat(str(value))


def _financial_fetched_at(payload: Mapping[str, object]) -> datetime:
    generated_at = payload.get("retained_generated_at") or payload.get("generated_at")
    if generated_at:
        return datetime.fromisoformat(str(generated_at))
    point_times = [
        str(point.get("fetched_at") or point.get("created_at") or "")
        for point in payload.get("points") or []
        if point.get("fetched_at") or point.get("created_at")
    ]
    if point_times:
        return datetime.fromisoformat(max(point_times))
    raise RuntimeError("Retained financial export has no generated_at or point timestamp")


def _collect_official(output_dir: Path, root: Path) -> tuple[dict, EvidenceReference]:
    retained = root / "runtime" / "exchange-lists" / "official-universe.json"
    live_error: str | None = None
    try:
        raw_dir = output_dir / "official-raw"
        payload = collect_security_lists(raw_dir)
        raw = _json_bytes(payload)
        path = _write(output_dir, "official-universe.json", raw)
        live_error = None
    except Exception as error:
        live_error = str(error)
        if not retained.exists():
            raise RuntimeError("Official universe collection failed and no retained fallback exists") from error
        payload = json.loads(retained.read_text(encoding="utf-8"))
        path = _write(output_dir, "official-universe.json", _json_bytes(payload))
    if live_error:
        payload = dict(payload)
        payload["m2_live_collection_error"] = live_error
    fetched_at = payload.get("fetched_at")
    if not fetched_at:
        raise RuntimeError("Official universe payload has no fetched_at")
    reference = _reference(
        "official",
        path,
        root=root,
        source_name="沪深北交易所官方证券清单",
        source_url="https://www.szse.cn | https://query.sse.com.cn | https://www.bse.cn",
        fetched_at=datetime.fromisoformat(fetched_at),
    )
    return payload, reference


def _retained_run_clock(output_dir: Path) -> tuple[datetime, str, str]:
    """Recover the original PIT clock before replaying retained inputs."""
    receipt_path = output_dir / "receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError(
            "--reuse-inputs requires an existing receipt.json; refusing to relabel "
            "retained inputs with the current clock"
        )
    receipt = discovery_receipt_from_payload(
        json.loads(receipt_path.read_text(encoding="utf-8"))
    )
    return receipt.generated_at, receipt.quote_date or receipt.as_of.isoformat(), receipt.run_id


def run_once(
    *,
    root: Path,
    output_dir: Path,
    wps_dir: Path | None,
    max_per_channel: int,
    skip_dividend: bool,
    reuse_inputs: bool,
) -> dict:
    wall_now = datetime.now(timezone.utc)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = M2ScreeningPolicy(max_per_channel=max_per_channel)

    if reuse_inputs:
        retained_generated_at, quote_date, retained_run_id = _retained_run_clock(output_dir)
        generated_at = retained_generated_at
        run_id = f"m2-replay-{wall_now.astimezone(CHINA).strftime('%Y%m%dT%H%M%S')}Z"
        replay_of_run_id = retained_run_id
    else:
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
        official_payload = json.loads(official_path.read_text(encoding="utf-8"))
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
        financial_ref = _reference(
            "financial", financial_path, root=root,
            source_name="Retained point-in-time financial evidence export",
            source_url="internal://runtime/server-export-payload",
            fetched_at=_financial_fetched_at(financial_payload),
        )
    else:
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

        financial_points, financial_export = _load_retained_financial_export(
            root / "runtime" / "server-export-payload.json"
        )
        financial_path = _write(output_dir, "retained-financial-points.json", _json_bytes({
            "points": financial_points,
            "retained_generated_at": financial_export.get("generated_at"),
        }))
        financial_fetched = _financial_fetched_at({
            "points": financial_points,
            "generated_at": financial_export.get("generated_at"),
        })
        financial_ref = _reference(
            "financial",
            financial_path,
            root=root,
            source_name="Retained point-in-time financial evidence export",
            source_url="internal://runtime/server-export-payload",
            fetched_at=financial_fetched,
        )

    run_refs = {
        "official": official_ref,
        "tencent": tencent_ref,
        "sina": sina_ref,
        "dividend": dividend_ref,
        "financial": financial_ref,
    }
    receipt = build_discovery_receipt(
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
    )
    receipt_bytes = _json_bytes(receipt.as_policy())
    receipt_path = _write(output_dir, "receipt.json", receipt_bytes)
    policy_path = _write(output_dir, "policy.json", _json_bytes(policy.as_policy()))

    workbook_path = output_dir / "m2-opportunity-discovery.xlsx"
    workbook_info = write_discovery_workbook(
        receipt,
        policy,
        output=workbook_path,
        root=root,
    )

    # Replay from the exact receipt bytes and from the retained raw inputs.
    replay = discovery_receipt_from_payload(json.loads(receipt_bytes.decode("utf-8")))
    replay_matches_receipt = (
        replay == receipt
        and replay.candidate_signature == receipt.candidate_signature
        and replay.coverage_signature == receipt.coverage_signature
    )
    replay_build = build_discovery_receipt(
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
    )
    replay_matches_inputs = (
        replay_build == receipt
        and replay_build.candidate_signature == receipt.candidate_signature
        and replay_build.coverage_signature == receipt.coverage_signature
    )

    wps_result = None
    if wps_dir is not None:
        wps_dir.mkdir(parents=True, exist_ok=True)
        wps_name = WPS_WORKBOOK_NAME.format(
            date=generated_at.astimezone(CHINA).strftime("%Y%m%d")
        )
        wps_target = wps_dir / wps_name
        counter = 2
        while wps_target.exists():
            wps_target = wps_dir / f"{wps_name[:-5]}_{counter}.xlsx"
            counter += 1
        shutil.copy2(workbook_path, wps_target)
        wps_result = {
            "path": str(wps_target),
            "sha256": _sha(wps_target.read_bytes()),
        }

    counts = {
        channel: len(result.candidates)
        for channel, result in receipt.channel_results.items()
    }
    summary = {
        "run_id": run_id,
        "action": ACTION_NO_ORDER,
        "generated_at": receipt.generated_at.isoformat(),
        "as_of": receipt.as_of.isoformat(),
        "quote_date": receipt.quote_date,
        "replay_of_run_id": replay_of_run_id,
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
        "workbook": workbook_info,
        "wps_workbook": wps_result,
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
                ("policy", policy_path),
                ("workbook", workbook_path),
            )
        },
    }
    _write(output_dir, "manifest.json", _json_bytes(manifest))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--wps-dir", type=Path, default=DEFAULT_WPS_DIR)
    parser.add_argument("--no-wps", action="store_true")
    parser.add_argument("--max-per-channel", type=int, default=50)
    parser.add_argument("--skip-dividend", action="store_true")
    parser.add_argument("--reuse-inputs", action="store_true")
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
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

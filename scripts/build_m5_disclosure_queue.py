"""Build a real CNINFO pending-materiality queue and a standalone workbook.

The command archives raw CNINFO indexes and candidate PDFs under runtime/,
creates a presentation-only Excel candidate, and optionally copies it to WPS
Cloud. It never decides materiality, writes PostgreSQL, schedules work or
orders.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import shutil
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import SYMBOL_NAMES, search_announcement_window  # noqa: E402
from value_investment_agent.m5_disclosure_queue import (  # noqa: E402
    ACTION_NO_ORDER,
    DISCLOSURE_QUEUE_SCHEMA,
    PARSER_VERSION,
    PROVIDER_CNINFO,
    DisclosureReviewQueue,
    build_cninfo_event_scan,
    disclosure_review_queue_from_payload,
    source_failure_event_scan,
)
from value_investment_agent.m5_disclosure_queue_workbook import (  # noqa: E402
    write_m5_disclosure_queue_workbook,
)


DEFAULT_SYMBOLS = ("600887", "600741", "000651")
DEFAULT_START = date(2026, 8, 27)
DEFAULT_WPS_DIR = Path(
    "C:/Users/we/WPSDrive/197617831/WPS云盘/价投跟踪"
)
DEFAULT_OUTPUT = ROOT / "A股价值投资_M5真实披露待复核队列_20260924.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--wps-dir", type=Path, default=DEFAULT_WPS_DIR)
    parser.add_argument("--no-wps", action="store_true")
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(item.strip() for item in value.split(",") if item.strip())
    if not symbols:
        raise ValueError("At least one symbol is required")
    if any(len(item) != 6 or not item.isdigit() for item in symbols):
        raise ValueError("Symbols must be comma-separated six-digit codes")
    return tuple(dict.fromkeys(symbols))


def collect_queue(
    symbols: tuple[str, ...],
    *,
    scan_from: date,
    scan_to: date,
    runtime_root: Path,
    retrieved_at: datetime,
) -> DisclosureReviewQueue:
    runtime_root.mkdir(parents=True, exist_ok=True)
    scans = []
    for symbol in symbols:
        try:
            payload = search_announcement_window(
                symbol,
                scan_from.isoformat(),
                scan_to.isoformat(),
                SYMBOL_NAMES.get(symbol),
            )
            scan = build_cninfo_event_scan(
                payload,
                symbol=symbol,
                scan_from=scan_from,
                scan_to=scan_to,
                retrieved_at=retrieved_at,
                evidence_dir=runtime_root / symbol,
                root=ROOT,
            )
        except Exception as error:
            scan = source_failure_event_scan(
                symbol=symbol,
                scan_from=scan_from,
                scan_to=scan_to,
                retrieved_at=retrieved_at,
                error=error,
            )
        scans.append(scan)
    return DisclosureReviewQueue(
        queue_id=f"cninfo-review-{scan_from.isoformat()}-{retrieved_at:%Y%m%dT%H%M%SZ}",
        schema_version=DISCLOSURE_QUEUE_SCHEMA,
        provider=PROVIDER_CNINFO,
        parser_version=PARSER_VERSION,
        scan_from=scan_from,
        scan_to=scan_to,
        retrieved_at=retrieved_at,
        scans=tuple(scans),
        action=ACTION_NO_ORDER,
    )


def _write_runtime(queue: DisclosureReviewQueue, runtime_root: Path) -> dict:
    queue_path = runtime_root / "queue.json"
    if queue_path.exists():
        raise ValueError(f"Disclosure queue runtime already exists: {queue_path}")
    queue_path.write_text(queue.to_json() + "\n", encoding="utf-8")
    return {
        "path": str(queue_path.resolve()),
        "sha256": _digest(queue_path),
    }


def _copy_wps(
    workbook: Path,
    wps_dir: Path | None,
) -> dict | None:
    if wps_dir is None or not wps_dir.exists():
        return None
    wps_dir.mkdir(parents=True, exist_ok=True)
    target = wps_dir / workbook.name
    counter = 1
    while target.exists():
        target = wps_dir / f"{workbook.stem}_{counter}{workbook.suffix}"
        counter += 1
    shutil.copy2(workbook, target)
    return {
        "path": str(target.resolve()),
        "sha256": _digest(target),
    }


def main() -> int:
    args = parse_args()
    symbols = _parse_symbols(args.symbols)
    scan_from = args.start_date
    scan_to = args.end_date or date.today()
    retrieved_at = datetime.now(timezone.utc)
    run_stamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    if args.runtime_root is None:
        runtime_root = ROOT / "runtime" / f"m5-disclosure-review-{run_stamp}"
    else:
        runtime_root = args.runtime_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"Disclosure queue workbook already exists: {output}")

    queue = collect_queue(
        symbols,
        scan_from=scan_from,
        scan_to=scan_to,
        runtime_root=runtime_root,
        retrieved_at=retrieved_at,
    )
    runtime_receipt = _write_runtime(queue, runtime_root)
    round_trip = disclosure_review_queue_from_payload(
        json.loads(Path(runtime_receipt["path"]).read_text(encoding="utf-8"))
    )
    if round_trip.as_policy() != queue.as_policy():
        raise ValueError("Disclosure review queue round trip changed")

    workbook_result = write_m5_disclosure_queue_workbook(
        queue,
        output=output,
        root=ROOT,
        security_names=SYMBOL_NAMES,
    )
    wps_result = None if args.no_wps else _copy_wps(output, args.wps_dir)
    manifest = {
        **workbook_result,
        "schema_version": DISCLOSURE_QUEUE_SCHEMA,
        "queue_id": queue.queue_id,
        "provider": PROVIDER_CNINFO,
        "parser_version": PARSER_VERSION,
        "scan_from": scan_from.isoformat(),
        "scan_to": scan_to.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "runtime_queue": runtime_receipt,
        "wps_workbook": wps_result,
        "action": ACTION_NO_ORDER,
        "symbols": list(symbols),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

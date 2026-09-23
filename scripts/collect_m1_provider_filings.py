"""Collect the next M1 provider statutory reports into local evidence only.

This command never opens PostgreSQL, the WPS workbook or a trading interface.
It uses the existing CNINFO collector and writes a source manifest so later
provider dossiers can pin every PDF to its issuer, period, URL and hash.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from value_investment_agent.disclosures import collect_latest_reports


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "runtime" / "company-research" / "m1-official-filings-20260923"
ISSUERS = {
    "600887": "伊利股份",
    "600690": "海尔智家",
    "600741": "华域汽车",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _preferred(records: list[dict]) -> dict | None:
    for kind in ("interim", "annual"):
        candidates = [record for record in records if record["report_kind"] == kind]
        if candidates:
            return max(
                candidates,
                key=lambda record: (
                    record["report_period"],
                    record["published_at"],
                ),
            )
    return None


def main() -> int:
    all_records: list[dict] = []
    for symbol, issuer_name in ISSUERS.items():
        records = collect_latest_reports([symbol], TARGET, {symbol: issuer_name})
        selected = _preferred(records)
        if selected is None:
            raise ValueError(f"No annual or interim filing was found for {symbol}")
        all_records.append(selected)

    manifest = _jsonable({
        "purpose": "M1 provider research evidence, local runtime only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "action": "no_order",
        "selected_records": all_records,
        "all_downloaded_records_count": len(all_records),
    })
    manifest_path = TARGET / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

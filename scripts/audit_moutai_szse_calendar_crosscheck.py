#!/usr/bin/env python3
"""Compare pinned Moutai daily bars with SZSE's official historical calendar.

SZSE is not the listing exchange for 600519.  This is deliberately a
cross-market official calendar check only: it cannot prove an SSE-specific
suspension or next-open execution.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CALENDAR_URL = "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def month_keys() -> list[str]:
    return [f"{year}-{month:02d}" for year in range(2015, 2026) for month in range(1, 13)]


def load_moutai_dates() -> set[str]:
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from replay_moutai_distributions import load_inputs
    bars, _, _, _ = load_inputs(ROOT)
    return {row["date"] for row in bars}


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/exchange-calendar-probes" / f"moutai-szse-calendar-crosscheck-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    open_dates: set[str] = set()
    archives = []
    with requests.Session() as session:
        session.trust_env = False
        for month in month_keys():
            response = session.get(CALENDAR_URL, params={"month": month}, headers={"Referer": "https://www.szse.cn/"}, timeout=(10, 15))
            response.raise_for_status()
            raw_path = output / f"{month}.json"
            raw_path.write_bytes(response.content)
            rows = response.json().get("data")
            if not isinstance(rows, list) or not rows or any(str(row.get("jybz")) not in {"0", "1"} or not row.get("jyrq") for row in rows):
                raise ValueError(f"Invalid official calendar response: {month}")
            dates = {str(row["jyrq"]) for row in rows}
            if not all(date.startswith(month) for date in dates):
                raise ValueError(f"Calendar month mismatch: {month}")
            open_dates.update(str(row["jyrq"]) for row in rows if str(row["jybz"]) == "1")
            archives.append({"month": month, "url": response.url, "path": raw_path.name, "sha256": sha(raw_path), "rows": len(rows)})
    moutai_dates = load_moutai_dates()
    payload = {
        "symbol": "600519", "period": "2015-01-01..2025-12-31",
        "calendar_exchange": "SZSE", "calendar_url": CALENDAR_URL,
        "months": archives, "szse_open_dates": len(open_dates), "moutai_bar_dates": len(moutai_dates),
        "missing_from_moutai": sorted(open_dates - moutai_dates), "extra_moutai_dates": sorted(moutai_dates - open_dates),
        "matched": open_dates == moutai_dates,
        "scope": "Official SZSE calendar crosscheck only; it is not an SSE calendar, suspension record, order-book record, or execution approval.",
        "execution_approved": False,
    }
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": sha(Path(__file__)), "evidence_sha256": sha(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "matched": payload["matched"], "missing": len(payload["missing_from_moutai"]), "extra": len(payload["extra_moutai_dates"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

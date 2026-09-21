#!/usr/bin/env python3
"""Build a hash-pinned SSE calendar evidence record for the Moutai replay.

The holiday intervals are deliberately transcribed from archived SSE notices,
instead of inferred from the price series.  Later SSE amendments override the
annual notice they explicitly adjust.  This validates session dates only;
daily bars still cannot establish executable liquidity or a fill.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from replay_moutai_distributions import load_inputs


NOTICE_DIR = ROOT / "runtime/exchange-calendar-probes/sse-annual-notices-20260913"
NOTICE_MANIFEST = NOTICE_DIR / "manifest.json"
SZSE_EVIDENCE = ROOT / "runtime/exchange-calendar-probes/moutai-szse-calendar-crosscheck-20260913T015511Z/evidence.json"
SZSE_EVIDENCE_SHA256 = "2ce1219d6dba8ac5c11eeacbb720a2ebe90d9b622a2b0c99b8cd71d76dd13499"

# Every interval is taken from the named, hash-pinned SSE notice.  Weekends are
# calculated separately, so this table records only the official holiday spans.
HOLIDAY_INTERVALS = {
    2015: (("2015-01-01", "2015-01-03"), ("2015-02-18", "2015-02-24"), ("2015-04-05", "2015-04-06"), ("2015-05-01", "2015-05-03"), ("2015-06-20", "2015-06-22"), ("2015-09-03", "2015-09-05"), ("2015-09-27", "2015-09-27"), ("2015-10-01", "2015-10-07")),
    2016: (("2016-01-01", "2016-01-03"), ("2016-02-07", "2016-02-13"), ("2016-04-02", "2016-04-04"), ("2016-04-30", "2016-05-02"), ("2016-06-09", "2016-06-11"), ("2016-09-15", "2016-09-17"), ("2016-10-01", "2016-10-07")),
    2017: (("2017-01-01", "2017-01-02"), ("2017-01-27", "2017-02-02"), ("2017-04-02", "2017-04-04"), ("2017-04-29", "2017-05-01"), ("2017-05-28", "2017-05-30"), ("2017-10-01", "2017-10-08")),
    2018: (("2018-01-01", "2018-01-01"), ("2018-02-15", "2018-02-21"), ("2018-04-05", "2018-04-07"), ("2018-04-29", "2018-05-01"), ("2018-06-16", "2018-06-18"), ("2018-09-22", "2018-09-24"), ("2018-10-01", "2018-10-07"), ("2018-12-30", "2019-01-01")),
    2019: (("2019-01-01", "2019-01-01"), ("2019-02-04", "2019-02-10"), ("2019-04-05", "2019-04-07"), ("2019-05-01", "2019-05-04"), ("2019-06-07", "2019-06-09"), ("2019-09-13", "2019-09-15"), ("2019-10-01", "2019-10-07")),
    2020: (("2020-01-01", "2020-01-01"), ("2020-01-24", "2020-02-02"), ("2020-04-04", "2020-04-06"), ("2020-05-01", "2020-05-05"), ("2020-06-25", "2020-06-27"), ("2020-10-01", "2020-10-08")),
    2021: (("2021-01-01", "2021-01-03"), ("2021-02-11", "2021-02-17"), ("2021-04-03", "2021-04-05"), ("2021-05-01", "2021-05-05"), ("2021-06-12", "2021-06-14"), ("2021-09-19", "2021-09-21"), ("2021-10-01", "2021-10-07")),
    2022: (("2022-01-01", "2022-01-03"), ("2022-01-31", "2022-02-06"), ("2022-04-03", "2022-04-05"), ("2022-04-30", "2022-05-04"), ("2022-06-03", "2022-06-05"), ("2022-09-10", "2022-09-12"), ("2022-10-01", "2022-10-07")),
    2023: (("2023-01-01", "2023-01-02"), ("2023-01-21", "2023-01-27"), ("2023-04-05", "2023-04-05"), ("2023-04-29", "2023-05-03"), ("2023-06-22", "2023-06-24"), ("2023-09-29", "2023-10-06")),
    2024: (("2024-01-01", "2024-01-01"), ("2024-02-09", "2024-02-17"), ("2024-04-04", "2024-04-06"), ("2024-05-01", "2024-05-05"), ("2024-06-10", "2024-06-10"), ("2024-09-15", "2024-09-17"), ("2024-10-01", "2024-10-07")),
    2025: (("2025-01-01", "2025-01-01"), ("2025-01-28", "2025-02-04"), ("2025-04-04", "2025-04-06"), ("2025-05-01", "2025-05-05"), ("2025-05-31", "2025-06-02"), ("2025-10-01", "2025-10-08")),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def date_range(start: str, end: str) -> set[str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return {(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)}


def expected_open_dates() -> set[str]:
    all_dates = date_range("2015-01-01", "2025-12-31")
    holidays = set().union(*(date_range(start, end) for intervals in HOLIDAY_INTERVALS.values() for start, end in intervals))
    return {day for day in all_dates if date.fromisoformat(day).weekday() < 5 and day not in holidays}


def load_notices() -> list[dict]:
    manifest = json.loads(NOTICE_MANIFEST.read_text(encoding="utf-8"))
    notices = []
    for row in manifest:
        path = NOTICE_DIR / row["path"]
        if sha256(path) != row["sha256"]:
            raise ValueError(f"Pinned SSE notice changed: {row['name']}")
        notices.append({**row, "verified": True})
    victory_day = next(row for row in notices if row["name"] == "2015-victory-day-amendment")
    amendment = next(row for row in notices if row["name"] == "2019-labor-amendment")
    emergency = next(row for row in notices if row["name"] == "2020-spring-festival-amendment")
    if "9月3日" not in (NOTICE_DIR / victory_day["path"]).read_text(encoding="utf-8"):
        raise ValueError("2015 victory-day amendment text is incomplete")
    if "5月1日" not in (NOTICE_DIR / amendment["path"]).read_text(encoding="utf-8"):
        raise ValueError("2019 amendment text is incomplete")
    if "2月3日" not in (NOTICE_DIR / emergency["path"]).read_text(encoding="utf-8"):
        raise ValueError("2020 emergency amendment text is incomplete")
    return notices


def build_audit() -> dict:
    notices = load_notices()
    if sha256(SZSE_EVIDENCE) != SZSE_EVIDENCE_SHA256:
        raise ValueError("Pinned SZSE crosscheck changed")
    szse = json.loads(SZSE_EVIDENCE.read_text(encoding="utf-8"))
    if not szse["matched"] or szse["szse_open_dates"] != 2674:
        raise ValueError("Unexpected SZSE official calendar result")
    bars, _, _, _ = load_inputs(ROOT)
    bar_dates = {row["date"] for row in bars}
    sse_dates = expected_open_dates()
    return {
        "symbol": "600519",
        "period": "2015-01-01..2025-12-31",
        "calendar_exchange": "SSE",
        "notices": notices,
        "amendments_applied": [{"notice": "2015-victory-day-amendment", "adds_closed_interval": ["2015-09-03", "2015-09-05"], "next_open_date": "2015-09-07"}, {"notice": "2019-labor-amendment", "overrides": "2019 annual notice labor-day interval", "effective_closed_interval": ["2019-05-01", "2019-05-04"], "next_open_date": "2019-05-06"}, {"notice": "2020-spring-festival-amendment", "overrides": "2020 annual notice spring-festival reopening", "effective_closed_interval": ["2020-01-24", "2020-02-02"], "next_open_date": "2020-02-03"}],
        "transcription_scope": "Weekdays minus holiday intervals explicitly transcribed from hash-pinned SSE annual notices and the two overriding SSE amendments.",
        "sse_open_dates": len(sse_dates),
        "moutai_bar_dates": len(bar_dates),
        "szse_official_open_dates": szse["szse_open_dates"],
        "missing_from_moutai": sorted(sse_dates - bar_dates),
        "extra_moutai_dates": sorted(bar_dates - sse_dates),
        "sse_matches_moutai": sse_dates == bar_dates,
        "sse_matches_szse_crosscheck": len(sse_dates) == szse["szse_open_dates"] and sse_dates == bar_dates,
        "calendar_approved": sse_dates == bar_dates,
        "execution_approved": False,
        "limitation": "The calendar validates date membership only. It cannot prove a 600519 suspension state, order-book liquidity, queue priority, transaction cost, or next-open fill.",
    }


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/exchange-calendar-probes" / f"moutai-sse-calendar-audit-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = build_audit()
    evidence_path = output / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": sha256(Path(__file__)), "evidence_sha256": sha256(evidence_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "calendar_approved": evidence["calendar_approved"], "execution_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

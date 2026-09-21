"""Inspect a pinned official ChinaBond 2014 government-curve workbook.

This is source-identity and date-coverage evidence only. It never supplies a
risk-free rate or changes valuation/trading admission.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runtime/strategy-validation/moutai-historical-chinabond-government-2014-20260920T133600Z"
SOURCE = RUN / "chinabond-government-2014.xlsx"
EXPECTED_SHA256 = "151938bc21a8080428f0035649dec1575573772b16b688f7621121b9c790c423"
TARGET_DATE = date(2014, 12, 31)
SOURCE_PAGE = (
    "https://www.chinabond.com.cn/zzsj/zzsj_zzjgcp/zzjgcp_cpxz/cpxz_qxxz/"
    "qxxz_zzgzqx/202307/t20230716_853000155.html"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(value.strip(), pattern).date()
            except ValueError:
                continue
    return None


def build() -> dict[str, object]:
    if digest(SOURCE) != EXPECTED_SHA256:
        raise ValueError("Pinned ChinaBond workbook hash changed")

    workbook = load_workbook(SOURCE, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("ChinaBond workbook is empty")
    header = list(rows[0])
    observations = []
    for row_number, row in enumerate(rows[1:], start=2):
        observation_date = as_date(row[0] if row else None)
        if observation_date:
            observations.append({"row": row_number, "date": observation_date.isoformat(), "values": list(row)})
    if not observations:
        raise ValueError("ChinaBond workbook has no parseable observation dates")

    target_rows = [row for row in observations if row["date"] == TARGET_DATE.isoformat()]
    ten_year_rows = [row for row in target_rows if row["values"][2] == 10]
    if len(ten_year_rows) != 1:
        raise ValueError("Expected exactly one 10-year government-curve observation on target date")
    status = (
        "candidate_requires_tenor_and_publication_contract_review"
        if target_rows
        else "rejected_target_date_not_in_official_annual_file"
    )
    return {
        "source_id": "chinabond:government-curve:2014-annual-standard-tenor",
        "source_page": SOURCE_PAGE,
        "source_file": str(SOURCE.relative_to(ROOT)),
        "source_file_sha256": EXPECTED_SHA256,
        "curve_identity": "中债国债收益率曲线(到期)",
        "source_page_published_date": "2014-06-27",
        "sheet_name": sheet.title,
        "workbook_created": workbook.properties.created.isoformat() if workbook.properties.created else None,
        "workbook_modified": workbook.properties.modified.isoformat() if workbook.properties.modified else None,
        "header": header,
        "row_count": len(observations),
        "first_observation_date": observations[0]["date"],
        "last_observation_date": observations[-1]["date"],
        "target_date": TARGET_DATE.isoformat(),
        "target_date_rows": target_rows,
        "target_ten_year_yield_percent": ten_year_rows[0]["values"][3],
        "rate_input_status": status,
        "valuation_approved": False,
        "trade_approved": False,
        "limitations": [
            "A date match alone does not establish which tenor is an appropriate risk-free proxy.",
            "The annual-file publication date is not a daily historical availability/vintage contract.",
            "Workbook creation and modification properties are file metadata, not an issuer publication receipt.",
            "No yield is promoted into a valuation model by this inspection.",
        ],
    }


def main() -> int:
    result = build()
    output = RUN / "inspection.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    manifest = RUN / "manifest.json"
    manifest.write_text(json.dumps({
        "script_sha256": digest(Path(__file__)),
        "source_file_sha256": EXPECTED_SHA256,
        "inspection_sha256": digest(output),
        "inspected_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "status": result["rate_input_status"],
        "first": result["first_observation_date"],
        "last": result["last_observation_date"],
        "target_rows": len(result["target_date_rows"]),
        "target_ten_year_yield_percent": result["target_ten_year_yield_percent"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

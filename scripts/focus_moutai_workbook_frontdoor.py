#!/usr/bin/env python3
"""Focus visible research pages on the current 600519 single-company case.

The workbook retains every existing company row. This patch only hides rows
other than 600519 on the two visible research-detail sheets, so the intended
single-company case opens without hundreds of unfinished records preceding it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.hyperlink import Hyperlink


SHEETS = ("09_公司研究", "21_决策验证")
FIRST_DATA_ROW = 4
SYMBOL = "600519"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_for_symbol(sheet, symbol: str) -> int:
    matches = [row for row in range(FIRST_DATA_ROW, sheet.max_row + 1)
               if str(sheet.cell(row, 1).value).zfill(6) == symbol]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {symbol} row in {sheet.title}, found {len(matches)}")
    return matches[0]


def focus_sheet(sheet) -> dict[str, int]:
    symbol_row = row_for_symbol(sheet, SYMBOL)
    hidden = 0
    visible = 0
    for row in range(FIRST_DATA_ROW, sheet.max_row + 1):
        is_current_case = row == symbol_row
        sheet.row_dimensions[row].hidden = not is_current_case
        if is_current_case:
            visible += 1
        else:
            hidden += 1
    sheet.freeze_panes = "A4"
    return {"symbol_row": symbol_row, "hidden_rows": hidden, "visible_rows": visible}


def repair_moutai_research_link(workbook, research_row: int) -> str:
    sheet = workbook["00_待完成公司"]
    cell = sheet["G4"]
    if cell.hyperlink is None:
        raise ValueError("Expected the Moutai research navigation link")
    current_target = cell.hyperlink.location or cell.hyperlink.target or ""
    if "09_公司研究" not in current_target:
        raise ValueError("Expected G4 to target the company-research sheet")
    location = f"'09_公司研究'!N{research_row}"
    # Rebuild a pure OOXML internal link. Mutating an existing relationship
    # can leave a dangling rId when the source link was externally encoded.
    cell.hyperlink = Hyperlink(
        ref=cell.coordinate,
        location=location,
        display=str(cell.value),
        tooltip=cell.hyperlink.tooltip,
    )
    return f"00_待完成公司!{cell.coordinate}->{location}"


def build(source: Path, output: Path) -> dict[str, object]:
    source, output = source.resolve(), output.resolve()
    if source == output or source.suffix.lower() != ".xlsx" or not source.is_file():
        raise ValueError("Source must be an existing, distinct .xlsx workbook")
    shutil.copy2(source, output)
    workbook = load_workbook(output)
    details = {}
    for sheet_name in SHEETS:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Missing required sheet: {sheet_name}")
        details[sheet_name] = focus_sheet(workbook[sheet_name])
    if "00_待完成公司" not in workbook.sheetnames:
        raise ValueError("Missing required sheet: 00_待完成公司")
    details["research_navigation"] = repair_moutai_research_link(
        workbook, details["09_公司研究"]["symbol_row"]
    )
    workbook.save(output)
    return {
        "source_sha256": digest(source),
        "candidate_sha256": digest(output),
        "scope": "row_visibility_and_internal_navigation_only",
        "sheets": details,
        "preserved_data_note": "All hidden company rows remain in the workbook and can be manually unhidden.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source, args.output)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage a minimal 600519 P1/P2 status correction without rebuilding a workbook."""
from __future__ import annotations

import argparse
from copy import copy
from pathlib import Path

from openpyxl import load_workbook


STATUS = (
    "【当前操作】研究观察：不新增买入、不减仓、不卖出。\n"
    "【为什么】正式合理价、模拟准入和实盘指令均未通过；条件试算不是买卖点。\n"
    "【已完成】600519研究卡的事实与反证已整理；2014Q3至2015决策窗口公告覆盖已核验，"
    "但完整权益滚动与历史回测仍未完成。\n"
    "【2026-09-18状态修正】当前P1模型已撤回：旧资本事件刷新在标称估值时点后取得，"
    "不得驱动当前估值或纸面订单。P2下一会话执行机械证据已齐备，但不改变"
    "trade_approved=false、live_eligible=false。"
)


def header_index(sheet, header: str) -> int:
    headers = [cell.value for cell in sheet[3]]
    try:
        return headers.index(header) + 1
    except ValueError as error:
        raise ValueError(f"{sheet.title} lacks header {header!r}") from error


def symbol_row(sheet, symbol: str) -> int:
    for row in range(4, sheet.max_row + 1):
        if str(sheet.cell(row, 1).value).zfill(6) == symbol:
            return row
    raise ValueError(f"{sheet.title} lacks symbol {symbol}")


def append_status(sheet, row: int, column: int) -> None:
    cell = sheet.cell(row, column)
    existing = str(cell.value or "")
    if STATUS not in existing:
        cell.value = STATUS + ("\n\n" + existing if existing else "")
    alignment = copy(cell.alignment)
    alignment.wrap_text = True
    alignment.vertical = "top"
    cell.alignment = alignment


def stage(workbook: Path, output: Path) -> None:
    """Write the narrowly scoped status correction to a separate candidate."""
    workbook, output = workbook.resolve(), output.resolve()
    if workbook.suffix.lower() != ".xlsx" or not workbook.is_file():
        raise ValueError("Workbook must be an existing .xlsx file")
    output.parent.mkdir(parents=True, exist_ok=True)
    wb = load_workbook(workbook)
    research, decisions = wb["09_公司研究"], wb["21_决策验证"]
    # The canonical research-case verifier pins the status field to column 16.
    append_status(research, symbol_row(research, "600519"), 16)
    append_status(decisions, symbol_row(decisions, "600519"), header_index(decisions, "策略验证状态"))
    wb.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage(args.workbook, args.output)
    print(f"STAGED {args.output.resolve()}")


if __name__ == "__main__":
    main()

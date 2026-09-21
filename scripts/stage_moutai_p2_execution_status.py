#!/usr/bin/env python3
"""Stage the current 600519 P2 mechanism status without rebuilding Excel."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN, "r": DOC_REL, "p": PKG_REL}
ET.register_namespace("", MAIN)
ET.register_namespace("r", DOC_REL)

STATUS = (
    "【当前操作】研究观察：不新增买入、不减仓、不卖出。\n"
    "【P1研究范围】截至2026-09-20，五项当前研究门禁已通过；仅可输出指定日期的条件研究范围。\n"
    "【P2机制】条件到拟单、冻结限价/预算/流动性/滑点、次日开盘纸面结算、T+1、费用及幂等账本已完成合成机制验证；不是历史收益或真实成交。\n"
    "【P2日期一致零单】2026-09-16 的同日模型、论点、P1准入、双源收盘1258.00元、停牌/费用/流动性与执行合同已绑定；安全边际-163.18%，状态watch/no_order。独立账户仍为现金100万元、0股、0成交，未伪造开盘成交。\n"
    "【边界】该零单链只证明纸面研究流程可复算，不是当前行情、正式合理价、历史收益或交易指令。\n"
    "【未通过】正式合理价、R1历史策略验证、交易指令和实盘准入均未通过。\n"
    "【下一步】仅在新的完整交易会话中重建同日事实、模型和执行证据；若真实价格条件触发，再验证拟单和下一会话处理，不为制造成交调整阈值。"
)

UPDATES = {"09_公司研究": {"P743": STATUS}, "21_决策验证": {"X742": STATUS}}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sheet_part(archive: ZipFile, name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rel_id = next(sheet.get(f"{{{DOC_REL}}}id") for sheet in workbook.findall("m:sheets/m:sheet", NS)
                  if sheet.get("name") == name)
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(rel.get("Target") for rel in relationships.findall("p:Relationship", NS)
                  if rel.get("Id") == rel_id).lstrip("/")
    return target if target.startswith("xl/") else "xl/" + target


def write_inline(cell: ET.Element, value: str) -> None:
    cell.set("t", "inlineStr")
    for child in list(cell):
        cell.remove(child)
    inline = ET.SubElement(cell, f"{{{MAIN}}}is")
    text = ET.SubElement(inline, f"{{{MAIN}}}t")
    text.text = value


def stage(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if source == output or output.exists() or not source.is_file():
        raise ValueError("Source must exist and output must be a distinct new file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as archive:
        replacements: dict[str, bytes] = {}
        for sheet_name, cells_to_update in UPDATES.items():
            part = sheet_part(archive, sheet_name)
            root = ET.fromstring(archive.read(part))
            cells = {cell.get("r"): cell for cell in root.findall(".//m:c", NS)}
            missing = sorted(set(cells_to_update) - set(cells))
            if missing:
                raise ValueError(f"{sheet_name} lacks expected cells: {missing}")
            for address, value in cells_to_update.items():
                write_inline(cells[address], value)
            replacements[part] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with ZipFile(output, "w", ZIP_DEFLATED, allowZip64=True) as destination:
            for item in archive.infolist():
                destination.writestr(item, replacements.get(item.filename, archive.read(item.filename)))
    return {"source_sha256": sha256(source), "staged_sha256": sha256(output),
            "changed_cells": [f"{sheet}!{cell}" for sheet, cells in UPDATES.items() for cell in cells]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(stage(args.source, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

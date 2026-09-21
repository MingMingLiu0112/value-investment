#!/usr/bin/env python3
"""Stage the current 600519 P1 research-admission status without rebuilding Excel."""
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

UPDATES = {
    "09_公司研究": {
        "P743": "【当前操作】研究观察：不新增买入、不减仓、不卖出。\n"
                 "【当前P1】截至2026-09-20，归母权益范围、模型勾稽、资本成本、前瞻假设和股本/资本动作五项门禁已通过；"
                 "仅可输出指定日期的条件研究范围。\n"
                 "【未通过】正式合理价、模拟准入、纸面订单和实盘指令均未通过；条件范围不是买卖点。\n"
                 "【下一步】P2须把同一日期的模型、收盘决策、下一有效会话开盘、停复牌、费用、滑点、流动性、公司行动和持久化账本绑定后，才可生成纸面拟单。"
    },
    "21_决策验证": {
        "X742": "【当前操作】研究观察：不新增买入、不减仓、不卖出。\n"
                 "【当前P1】截至2026-09-20，归母权益范围、模型勾稽、资本成本、前瞻假设和股本/资本动作五项门禁已通过；"
                 "仅可输出指定日期的条件研究范围。\n"
                 "【未通过】正式合理价、模拟准入、纸面订单和实盘指令均未通过；条件范围不是买卖点。\n"
                 "【下一步】P2须把同一日期的模型、收盘决策、下一有效会话开盘、停复牌、费用、滑点、流动性、公司行动和持久化账本绑定后，才可生成纸面拟单。"
    },
}


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

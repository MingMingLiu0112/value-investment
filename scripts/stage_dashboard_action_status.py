#!/usr/bin/env python3
"""Stage one explicit, evidence-bounded action status on the Excel dashboard."""
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

HOME = "00_\u9996\u9875Dashboard"
EXPECTED_LABEL = "\u5f53\u524d\u5224\u65ad"
ACTION_LABEL = "\u5f53\u524d\u64cd\u4f5c"
ACTION_BODY = (
    "\u7814\u7a76\u89c2\u5bdf | \u4e0d\u65b0\u589e\u4e70\u5165\u3001\u4e0d\u51cf\u4ed3\u3001\u4e0d\u5356\u51fa\u3002"
    "\u6b63\u5f0f\u5408\u7406\u4ef7\u3001\u6a21\u62df\u51c6\u5165\u548c\u5b9e\u76d8\u6307\u4ee4\u5c1a\u672a\u901a\u8fc7\uff1b"
    "\u73b0\u6709\u6761\u4ef6\u8bd5\u7b97\u4e0d\u662f\u4e70\u5356\u70b9\u3002"
)


def cell_text(cell: ET.Element, shared: list[str]) -> str:
    if cell.get("t") == "s":
        value = cell.find("m:v", NS)
        return shared[int(value.text)] if value is not None and value.text else ""
    return "".join(node.text or "" for node in cell.findall(".//m:t", NS))


def inline_text(cell: ET.Element, text: str) -> None:
    cell.attrib["t"] = "inlineStr"
    for child in list(cell):
        cell.remove(child)
    inline = ET.SubElement(cell, f"{{{MAIN}}}is")
    value = ET.SubElement(inline, f"{{{MAIN}}}t")
    value.text = text


def sheet_part(archive: ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = next(
        sheet.get(f"{{{DOC_REL}}}id")
        for sheet in workbook.findall("m:sheets/m:sheet", NS)
        if sheet.get("name") == sheet_name
    )
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(rel.get("Target") for rel in relationships.findall("p:Relationship", NS)
                  if rel.get("Id") == relationship_id)
    target = target.lstrip("/")
    return target if target.startswith("xl/") else "xl/" + target


def stage(source: Path, staged: Path) -> dict:
    source, staged = source.resolve(), staged.resolve()
    if source == staged or source.suffix.lower() != ".xlsx" or not source.is_file() or staged.exists():
        raise ValueError("Source must exist and staged must be a distinct new .xlsx file")
    staged.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.findall(".//m:t", NS)) for item in root]
        part = sheet_part(archive, HOME)
        root = ET.fromstring(archive.read(part))
        cells = {cell.get("r"): cell for cell in root.findall(".//m:c", NS)}
        if cell_text(cells.get("A9"), shared) != EXPECTED_LABEL or cells.get("C9") is None:
            raise ValueError("Dashboard action-status row changed; refuse to overwrite")
        inline_text(cells["A9"], ACTION_LABEL)
        inline_text(cells["C9"], ACTION_BODY)
        replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with ZipFile(staged, "w", ZIP_DEFLATED, allowZip64=True) as destination:
            for item in archive.infolist():
                destination.writestr(item, replacement if item.filename == part else archive.read(item.filename))
    return {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "staged_sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
            "changed_cells": [f"{HOME}!A9", f"{HOME}!C9"], "action": ACTION_BODY}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("staged", type=Path)
    args = parser.parse_args()
    print(stage(args.source, args.staged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

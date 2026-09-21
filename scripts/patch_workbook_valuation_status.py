"""Low-memory, evidence-bound update of one derived research-card status.

This avoids serializing the whole WPS workbook through OpenPyXL. Only the
merged ``估值门禁`` body cell for a requested ResearchCase is changed; every
other OOXML part is copied byte-for-byte into a candidate workbook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_text(cell: ET.Element, shared: list[str]) -> str:
    if cell.get("t") == "s":
        value = cell.findtext(MAIN + "v")
        return shared[int(value)] if value is not None else ""
    return "".join(node.text or "" for node in cell.iter(MAIN + "t")) or cell.findtext(MAIN + "v", "")


def shared_strings(package: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = ET.fromstring(package.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(MAIN + "t")) for item in root]


def overview_part(package: ZipFile) -> str:
    workbook = ET.fromstring(package.read("xl/workbook.xml"))
    rels = ET.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    targets = {item.get("Id"): item.get("Target") for item in rels.findall(PKG_REL + "Relationship")}
    for sheet in workbook.findall(".//" + MAIN + "sheet"):
        if sheet.get("name") == "00_公司总览":
            target = targets[sheet.get(REL + "id")]
            target = target.lstrip("/")
            return target if target.startswith("xl/") else "xl/" + target
    raise ValueError("00_公司总览 worksheet is missing")


def row_number(reference: str) -> int:
    return int("".join(char for char in reference if char.isdigit()))


def patch_sheet(xml: bytes, *, symbol: str, name: str, status: str, shared: list[str]) -> bytes:
    root = ET.fromstring(xml)
    cells = list(root.iter(MAIN + "c"))
    heading = f"{name} {symbol} | MVP研究卡"
    starts = [row_number(cell.get("r", "A0")) for cell in cells if cell_text(cell, shared) == heading]
    if len(starts) != 1:
        raise ValueError("Target research card heading is missing or ambiguous")
    start = starts[0]
    target = None
    for cell in cells:
        row = row_number(cell.get("r", "A0"))
        if start < row <= start + 20 and cell_text(cell, shared) == "估值门禁":
            target = next((candidate for candidate in cells if candidate.get("r") == f"C{row}"), None)
            break
    if target is None:
        raise ValueError("Target valuation-gate body cell is missing")
    for child in list(target):
        target.remove(child)
    target.set("t", "inlineStr")
    inline = ET.SubElement(target, MAIN + "is")
    ET.SubElement(inline, MAIN + "t").text = status
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_candidate(*, source: Path, candidate: Path, valuation: Path) -> dict:
    payload = json.loads(valuation.read_text(encoding="utf-8"))
    value = payload["result"]
    if (value.get("symbol") != "000333" or value.get("model_type") != "FCFF"
            or value.get("status") != "not_ready" or payload.get("trade_approved") is not False):
        raise ValueError("Only a non-trading 000333 unified FCFF result may use this publisher")
    text = ("估值未就绪（统一 FCFF ValuationResult 已生成）。\n"
            "阻断：" + "；".join(value["blockers"]) + "。\n"
            "无买卖价 / 无仓位 / 无订单")
    before = digest(source)
    with ZipFile(source) as incoming:
        shared = shared_strings(incoming)
        part = overview_part(incoming)
        original = incoming.read(part)
        # Resolve shared strings before the XML is converted to inline text.
        root = ET.fromstring(original)
        heading = f"美的集团 000333 | MVP研究卡"
        if not any(cell_text(cell, shared) == heading for cell in root.iter(MAIN + "c")):
            raise ValueError("Midea research card is not present in the canonical overview")
        patched = patch_sheet(original, symbol="000333", name="美的集团", status=text, shared=shared)
        with NamedTemporaryFile(delete=False, suffix=".xlsx", dir=candidate.parent) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with ZipFile(temporary_path, "w", ZIP_DEFLATED, allowZip64=True) as outgoing:
                for info in incoming.infolist():
                    outgoing.writestr(info, patched if info.filename == part else incoming.read(info.filename))
            os.replace(temporary_path, candidate)
        finally:
            temporary_path.unlink(missing_ok=True)
    return {"source": str(source), "source_sha256": before, "candidate": str(candidate),
            "candidate_sha256": digest(candidate), "valuation_sha256": digest(valuation),
            "trade_approved": False, "status": "candidate_ready"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--valuation", type=Path, required=True)
    args = parser.parse_args()
    result = build_candidate(source=args.workbook.resolve(), candidate=args.candidate.resolve(),
                             valuation=args.valuation.resolve())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

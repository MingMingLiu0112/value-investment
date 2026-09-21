#!/usr/bin/env python3
"""Stage a minimal research-card XML update without WPS rewriting legacy sheets."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN, "r": DOC_REL, "p": PKG_REL}
ET.register_namespace("", MAIN)
ET.register_namespace("r", DOC_REL)

LABEL = "主模型 / 价格要求"
BODY = (
    "主模型：归母权益剩余收益/分配能力模型，以2026-06-30归母权益和扣非TTM为起点，检验未来五年利润-5%/0/+5%、75%研究性分配、优势回报五年衰减及不同折现率。"
    "市场对价格的要求：2026-09-18归档价1,257.12元高于0年、5年、10年优势衰减且利润增长-5%至+5%的注册组合上限，因此利润、分配、优势持续期或资本成本中至少一项需显著更强。"
    "变量有多解，这不是唯一市场预测、合理价或卖出信号；正式估值仍待指定日期审查。"
)
CAPITAL_LABEL = "资本配置 / 治理"
CAPITAL_BODY = (
    "资本配置：2024年回购计划在2025年完成，回购3,927,585股、金额约60.00亿元、价格区间1,408.29至1,639.99元/股，公告用途为注销并减少注册资本；已披露股份数随后下降。"
    "治理：2026年日常关联交易预计上限92.06亿元，公告披露四名关联董事回避、其余三名非关联董事表决、独立董事专门会议审议及定价规则。"
    "边界：回购是否增厚须与当时内在价值比较，关联交易预计额和程序不证明实际价格公允；激励、质押、减持等尚未形成完整审查。"
)
INDUSTRY_COUNTEREVIDENCE = "行业旁证：五粮液中报不能支持行业自动复苏；其现金流比例和经营结果不可直接外推到茅台。"
RESILIENCE_LABEL = "现金 / 低谷韧性"
RESILIENCE_BODY = (
    "分配：2026年上半年母公司经营现金流扣资本开支后约覆盖当期分红及利息41.1%，不能据此直接判定分红不可持续。"
    "低谷韧性：截至2026年6月30日，已勾稽合并负债469.54亿元，其中金融子公司吸收存款及同业存放254.26亿元，已披露租赁负债约2.44亿元；当前资料未显示重大已识别公司借款压力。"
    "边界：已选金融资产含受限准备金、信贷和投资资产，不能等同于自由分配现金；未完成担保、债务到期和压力现金流全量审查，因此不称无债或低谷安全。"
)
DELIVERY_LABEL = "当前交付边界"
DELIVERY_BODY = "R0研究卡与P1研究日条件估值准入已通过；正式合理价、模拟准入和实盘指令仍未通过。"


def cell_text(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "s":
        value = cell.find("m:v", NS)
        return shared[int(value.text)] if value is not None and value.text else ""
    return "".join(node.text or "" for node in cell.findall(".//m:t", NS))


def inline_text(cell: ET.Element, text: str) -> None:
    cell.attrib["t"] = "inlineStr"
    for child in list(cell):
        cell.remove(child)
    inline = ET.SubElement(cell, f"{{{MAIN}}}is")
    value = ET.SubElement(inline, f"{{{MAIN}}}t")
    if text.startswith(" ") or text.endswith(" "):
        value.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    value.text = text


def sheet_part(archive: ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rel_id = next(
        sheet.get(f"{{{DOC_REL}}}id")
        for sheet in workbook.findall("m:sheets/m:sheet", NS)
        if sheet.get("name") == sheet_name
    )
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next(
        rel.get("Target") for rel in relationships.findall("p:Relationship", NS) if rel.get("Id") == rel_id
    )
    normalized = target.lstrip("/")
    return normalized if normalized.startswith("xl/") else "xl/" + normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("staged", type=Path)
    args = parser.parse_args()
    if args.staged.exists():
        raise ValueError(f"Staged path already exists: {args.staged}")
    args.staged.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.source) as source:
        shared = []
        if "xl/sharedStrings.xml" in source.namelist():
            strings = ET.fromstring(source.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.findall(".//m:t", NS)) for item in strings]
        part = sheet_part(source, "00_公司总览")
        root = ET.fromstring(source.read(part))
        cells = {cell.get("r"): cell for cell in root.findall(".//m:c", NS)}
        label_cell = next((cell for cell in cells.values() if cell_text(cell, shared) == "主模型 / 价格要求"), None)
        if label_cell is None:
            raise ValueError("Research-card price row is missing")
        row_number = "".join(ch for ch in label_cell.get("r", "") if ch.isdigit())
        body_cell = cells.get("C" + row_number)
        if body_cell is None:
            raise ValueError("Research-card body cell is missing")
        inline_text(label_cell, LABEL)
        inline_text(body_cell, BODY)
        row = next((item for item in root.findall(".//m:row", NS) if item.get("r") == row_number), None)
        if row is not None:
            row.set("ht", "90")
            row.set("customHeight", "1")
        sales_label = next((cell for cell in cells.values() if cell_text(cell, shared) in {"量价与反证", "量价 / 行业反证"}), None)
        industry_label = next((cell for cell in cells.values() if cell_text(cell, shared) in {"行业反证", CAPITAL_LABEL}), None)
        if sales_label is None or industry_label is None:
            raise ValueError("Research-card sales or industry counterevidence row is missing")
        sales_row = "".join(ch for ch in sales_label.get("r", "") if ch.isdigit())
        industry_row = "".join(ch for ch in industry_label.get("r", "") if ch.isdigit())
        sales_body = cells.get("C" + sales_row)
        industry_body = cells.get("C" + industry_row)
        if sales_body is None or industry_body is None:
            raise ValueError("Research-card counterevidence body is missing")
        if cell_text(sales_label, shared) == "量价与反证":
            inline_text(sales_label, "量价 / 行业反证")
            inline_text(sales_body, cell_text(sales_body, shared) + " " + INDUSTRY_COUNTEREVIDENCE)
        if cell_text(industry_label, shared) == "行业反证":
            inline_text(industry_label, CAPITAL_LABEL)
            inline_text(industry_body, CAPITAL_BODY)
        industry_sheet_row = next((item for item in root.findall(".//m:row", NS) if item.get("r") == industry_row), None)
        if industry_sheet_row is not None:
            industry_sheet_row.set("ht", "130")
            industry_sheet_row.set("customHeight", "1")
        cash_label = next((cell for cell in cells.values() if cell_text(cell, shared) in {"现金与分配", RESILIENCE_LABEL}), None)
        if cash_label is None:
            raise ValueError("Research-card cash row is missing")
        cash_row = "".join(ch for ch in cash_label.get("r", "") if ch.isdigit())
        cash_body = cells.get("C" + cash_row)
        if cash_body is None:
            raise ValueError("Research-card cash body is missing")
        inline_text(cash_label, RESILIENCE_LABEL)
        inline_text(cash_body, RESILIENCE_BODY)
        cash_sheet_row = next((item for item in root.findall(".//m:row", NS) if item.get("r") == cash_row), None)
        if cash_sheet_row is not None:
            cash_sheet_row.set("ht", "150")
            cash_sheet_row.set("customHeight", "1")
        delivery_label = next((cell for cell in cells.values() if cell_text(cell, shared) == DELIVERY_LABEL), None)
        if delivery_label is None:
            raise ValueError("Research-card delivery-boundary row is missing")
        delivery_row = "".join(ch for ch in delivery_label.get("r", "") if ch.isdigit())
        delivery_body = cells.get("C" + delivery_row)
        if delivery_body is None:
            raise ValueError("Research-card delivery-boundary body is missing")
        inline_text(delivery_body, DELIVERY_BODY)
        replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        with ZipFile(args.staged, "w", ZIP_DEFLATED, allowZip64=True) as destination:
            for item in source.infolist():
                payload = replacement if item.filename == part else source.read(item.filename)
                destination.writestr(item, payload)
    print(
        "{" + ",".join((
            '"status":"staged"',
            '"changed_sheet":"00_公司总览"',
            '"changed_row":' + row_number + ',"governance_row":' + industry_row + ',"resilience_row":' + cash_row + ',"delivery_row":' + delivery_row,
            '"sha256":"' + hashlib.sha256(args.staged.read_bytes()).hexdigest() + '"',
        )) + "}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

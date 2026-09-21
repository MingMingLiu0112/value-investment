#!/usr/bin/env python3
"""Apply narrowly scoped, evidence-backed research status updates to a workbook copy."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
GREE_POINTER = ROOT / "runtime/company-research/000651-r0-research-card-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_gree_card() -> tuple[dict, dict]:
    pointer = json.loads(GREE_POINTER.read_text(encoding="utf-8"))
    evidence = (ROOT / pointer["path"] / "evidence.json").resolve()
    if not evidence.is_relative_to(ROOT.resolve()) or digest(evidence) != pointer["sha256"]:
        raise ValueError("Pinned Gree research card changed")
    card = json.loads(evidence.read_text(encoding="utf-8"))
    if (card.get("symbol") != "000651" or card.get("research_status") != "priority_for_shallow_research"
            or card.get("trade_approved") is not False or card.get("formal_fair_value") is not None):
        raise ValueError("Unexpected Gree research-card scope")
    return card, {"path": str(evidence.relative_to(ROOT)), "sha256": pointer["sha256"]}


def row_for_symbol(ws, symbol: str) -> int:
    rows = [cell.row for cell in ws["A"] if str(cell.value) == symbol]
    if len(rows) != 1:
        raise ValueError(f"Expected one {symbol} row in {ws.title}")
    return rows[0]


def build(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if source == output or source.suffix.lower() != ".xlsx" or not source.is_file():
        raise ValueError("Source must be an existing, distinct .xlsx workbook")
    card, card_ref = load_gree_card()
    shutil.copy2(source, output)
    workbook = load_workbook(output)

    pending = workbook["00_待完成公司"]
    pending_row = row_for_symbol(pending, "000651")
    pending_updates = {
        3: "重点研究候选",
        4: "R0一手事实已核验",
        5: "2026H1巨潮已核验；行情仍过期",
        6: "完成资金/融资口径和适用估值；尚无交易模拟",
    }
    for column, value in pending_updates.items():
        pending.cell(pending_row, column).value = value

    research = workbook["09_公司研究"]
    research_row = row_for_symbol(research, "000651")
    research_updates = {
        3: "消费暖通及工业装备；业务和经济性仍待分部研究",
        5: "2026H1巨潮原始半年报已核验，进入一手事实研究队列",
        6: "待验证：产品结构、渠道、海外与工业业务的长期经济性",
        7: "收入、利润、经营现金流同比下滑；现金、金融资产和融资负债口径复杂",
        8: "待完成同业与业务分部交叉研究",
        10: "仅事实核验：不能由低估值或账面现金直接推导买入",
        11: "融资/受限资金范围、现金归属或后续财报与关键经营事实推翻当前假说时暂停研究",
        12: "2026-09-17",
        13: "R0一手事实已核验；未形成公司定性结论",
        14: "H1营收893.98亿元、归母132.78亿元、经营现金流188.09亿元；均同比下降。",
        15: "合同负债下降；受限现金、金融资产及有息负债范围需先拆分。",
        16: "巨潮2026H1事实卡；无估值、仓位、交易或模拟准入。",
        17: card["issuer_filing"]["source_url"],
    }
    for column, value in research_updates.items():
        research.cell(research_row, column).value = value
    research.cell(research_row, 17).hyperlink = card["issuer_filing"]["source_url"]
    research.cell(research_row, 17).style = "Hyperlink"

    dashboard = workbook["00_首页Dashboard"]
    dashboard["C11"] = "高：execution_not_ready。下一交易日已确认，但风险警示/涨跌停、流动性与限价条款尚未绑定；这不是卖出指令。"
    workbook.save(output)

    return {
        "source_sha256": digest(source), "candidate_sha256": digest(output),
        "gree_card": card_ref,
        "changed_cells": {
            "00_待完成公司": [f"{chr(64 + column)}{pending_row}" for column in pending_updates],
            "09_公司研究": [f"{chr(64 + column)}{research_row}" for column in research_updates],
            "00_首页Dashboard": ["C11"],
        },
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

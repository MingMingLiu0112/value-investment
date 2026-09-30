"""Update only the visible quote/date display in the canonical workbook."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = Path(r"C:\Users\we\WPSDrive\197617831\WPS云盘\价投跟踪\A股价值投资_Agent前端智能跟踪模板.xlsx")
QUOTES = {"000333": "81.66", "600887": "27.24", "601088": "47.30"}
AS_OF = "2026-09-29"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def replace_quotes(value: object) -> object:
    if not isinstance(value, str):
        return value
    rendered = value.replace("2026-09-28", AS_OF)
    for symbol, price in QUOTES.items():
        rendered = re.sub(rf"(?<!\d){symbol}\s+\d+(?:\.\d+)?", f"{symbol} {price}", rendered)
    rendered = rendered.replace("双源匹配收盘价 82.00 元", "双源匹配收盘价 81.66 元")
    rendered = rendered.replace("双源匹配收盘价 27.03 元", "双源匹配收盘价 27.24 元")
    rendered = rendered.replace("双源匹配收盘价 48.39 元", "双源匹配收盘价 47.30 元")
    return rendered


def main() -> int:
    raise RuntimeError("DEPRECATED_UNSAFE_QUOTE_REWRITE_DISABLED: use publish_product_workbench_to_canonical.py with verified bindings")
    if not CANONICAL.is_file():
        raise FileNotFoundError(CANONICAL)
    before = sha256(CANONICAL)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ROOT / "runtime" / "workbook-backups" / f"canonical-before-quote-display-{stamp}.xlsx"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CANONICAL, backup)
    if sha256(backup) != before:
        raise RuntimeError("backup hash mismatch")

    staging = backup.with_name(f"{backup.stem}.staging.xlsx")
    shutil.copy2(CANONICAL, staging)
    workbook = load_workbook(staging, data_only=False, keep_links=True)
    try:
        for sheet_name in ("01_今日", "02_机会", "06_系统与审计"):
            sheet = workbook[sheet_name]
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell, MergedCell):
                        continue
                    cell.value = replace_quotes(cell.value)
        workbook.save(staging)
    finally:
        workbook.close()
    after = sha256(staging)
    shutil.copy2(staging, CANONICAL)
    staging.unlink(missing_ok=True)
    receipt = {
        "status": "QUOTE_DISPLAY_UPDATED",
        "action": "no_order",
        "canonical": str(CANONICAL),
        "before_sha256": before,
        "backup": str(backup.relative_to(ROOT)),
        "backup_sha256": sha256(backup),
        "after_sha256": sha256(CANONICAL),
        "candidate_sha256": after,
        "quote_as_of": AS_OF,
        "quotes": QUOTES,
        "research_status_unchanged": True,
        "trade_signal_created": False,
    }
    receipt_path = ROOT / "runtime" / "publication-receipts" / f"canonical-quote-display-{stamp}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

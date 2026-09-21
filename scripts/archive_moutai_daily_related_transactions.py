#!/usr/bin/env python3
"""Archive the official 2025 daily-related-transactions notice for scope review."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
URL = "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114727.PDF"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/company-research" / f"600519-daily-related-transactions-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    request = Request(URL, headers={"User-Agent": "Mozilla/5.0 ValueInvestmentAgent/1.0"})
    with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
        raw = response.read(3_000_000)
    if not raw.startswith(b"%PDF") or len(raw) >= 3_000_000:
        raise ValueError("Unexpected official related-transactions response")
    pdf = output / "600519-1225114727.pdf"
    pdf.write_bytes(raw)
    pages = [{"physical_page": number, "text": page.extract_text()} for number, page in enumerate(PdfReader(pdf).pages, start=1)]
    text = output / "extracted-pages.json"
    text.write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "symbol": "600519", "source_id": "cninfo:1225114727", "source_url": URL,
        "title": "贵州茅台关于日常关联交易的公告", "raw_file": str(pdf.relative_to(ROOT)),
        "raw_file_sha256": digest(pdf), "pages": len(pages),
        "text_extraction": str(text.relative_to(ROOT)),
        "review_status": "archived_not_yet_interpreted", "valuation_approved": False, "trade_approved": False,
    }
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"outputs": {file.name: digest(file) for file in output.iterdir()}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": evidence["raw_file_sha256"], "pages": len(pages)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

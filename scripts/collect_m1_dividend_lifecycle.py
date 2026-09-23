"""Archive CNINFO dividend-lifecycle originals for M1 distribution research.

The command only collects and hash-pins statutory PDFs plus their PDFium text.
It does not infer financial facts, open PostgreSQL, change WPS, or generate an
order.  Package updates remain a separate reviewed step so a collector cannot
silently turn a disclosure into a sustainability conclusion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import (  # noqa: E402
    PDF_BASE_URL,
    download_disclosure_pdf,
)
from value_investment_agent.pdf_text import extract_pages  # noqa: E402


EVIDENCE_ROOT = ROOT / "runtime" / "company-research" / "m1-dividend-lifecycles"
PARSER_VERSION = "pdfium-m1-dividend-lifecycle-v1"
PDF_SUFFIX = ".pdf"
TEXT_SUFFIX = ".extracted-text.json"

LifecycleSources = dict[str, list[dict[str, str]]]


SOURCES: LifecycleSources = {
    "000651": [
        {
            "id": "gree_fy2024_final_implementation",
            "role": "fy2024-final-implementation",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-08-22/1224534765.PDF",
            "published_at": "2025-08-21T16:00:00+00:00",
        },
        {
            "id": "gree_fy2025_interim_implementation",
            "role": "fy2025-interim-implementation",
            "fiscal_period": "FY2025-interim",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-01-16/1224936369.PDF",
            "published_at": "2026-01-15T16:00:00+00:00",
        },
    ],
    "600741": [
        {
            "id": "huayu_fy2024_final_proposal",
            "role": "fy2024-final-proposal",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-04-29/1223375163.PDF",
            "published_at": "2025-04-29T16:00:00+08:00",
        },
        {
            "id": "huayu_fy2024_final_agm_resolution",
            "role": "fy2024-final-approval",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-06-28/1224018822.PDF",
            "published_at": "2025-06-28T16:00:00+08:00",
        },
        {
            "id": "huayu_fy2024_final_implementation",
            "role": "fy2024-final-implementation",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-07-19/1224214626.PDF",
            "published_at": "2025-07-19T16:00:00+08:00",
        },
    ],
    "600887": [
        {
            "id": "yili_fy2024_final_proposal",
            "role": "fy2024-final-proposal",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-04-30/1223421147.PDF",
            "published_at": "2025-04-30T16:00:00+08:00",
        },
        {
            "id": "yili_fy2024_final_agm_resolution",
            "role": "fy2024-final-approval",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-05-21/1223608795.PDF",
            "published_at": "2025-05-21T16:00:00+08:00",
        },
        {
            "id": "yili_fy2024_final_total_adjustment",
            "role": "fy2024-final-total-adjustment",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-05-22/1223626923.PDF",
            "published_at": "2025-05-22T16:00:00+08:00",
        },
        {
            "id": "yili_fy2024_final_implementation",
            "role": "fy2024-final-implementation",
            "fiscal_period": "FY2024-final",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-05-30/1223718270.PDF",
            "published_at": "2025-05-30T16:00:00+08:00",
        },
        {
            "id": "yili_fy2025_interim_proposal",
            "role": "fy2025-interim-proposal",
            "fiscal_period": "FY2025-interim",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-10-31/1224774249.PDF",
            "published_at": "2025-10-31T16:00:00+08:00",
        },
        {
            "id": "yili_shareholder_return_plan_2025_2027",
            "role": "shareholder-return-policy",
            "fiscal_period": "FY2025-FY2027-policy",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-11-18/1224808850.PDF",
            "published_at": "2025-11-18T16:00:00+08:00",
        },
        {
            "id": "yili_fy2025_interim_egm_resolution",
            "role": "fy2025-interim-approval",
            "fiscal_period": "FY2025-interim",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-11-29/1224834639.PDF",
            "published_at": "2025-11-29T16:00:00+08:00",
        },
        {
            "id": "yili_fy2025_interim_implementation",
            "role": "fy2025-interim-implementation",
            "fiscal_period": "FY2025-interim",
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-12-09/1224859455.PDF",
            "published_at": "2025-12-09T16:00:00+08:00",
        },
    ],
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp requires timezone: {value}")
    return parsed


def _archive(
    symbol: str,
    definition: dict[str, str],
    symbol_dir: Path,
    retrieved_at: datetime,
) -> dict[str, Any]:
    source_id = definition["id"]
    if not source_id or not source_id.startswith(("gree_", "huayu_", "yili_")):
        raise ValueError(f"Unexpected dividend lifecycle source id: {source_id}")
    source_url = definition["source_url"]
    if not source_url.startswith(PDF_BASE_URL):
        raise ValueError(f"Unexpected CNINFO source URL: {source_url}")

    pdf_path = symbol_dir / f"{source_id}{PDF_SUFFIX}"
    if pdf_path.exists():
        pdf_sha256 = _digest(pdf_path)
    else:
        pdf_sha256 = download_disclosure_pdf(source_url, pdf_path)

    pages = extract_pages(pdf_path)
    if not pages or not any(text.strip() for text in pages):
        raise ValueError(f"Dividend lifecycle PDF has no decodable text: {source_id}")
    text_path = symbol_dir / f"{source_id}{TEXT_SUFFIX}"
    text_payload = {
        "schema_version": "m1-dividend-lifecycle-extracted-text-v1",
        "source_id": source_id,
        "symbol": symbol,
        "pdf_sha256": pdf_sha256,
        "parser_version": PARSER_VERSION,
        "pages": pages,
    }
    text_path.write_text(
        json.dumps(text_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "id": source_id,
        "kind": "official_issuer_filing",
        "role": definition["role"],
        "fiscal_period": definition["fiscal_period"],
        "location": _relative(pdf_path),
        "sha256": pdf_sha256,
        "source_url": source_url,
        "published_at": _datetime(definition["published_at"]).isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "parser_version": PARSER_VERSION,
        "extracted_text": {
            "location": _relative(text_path),
            "sha256": _digest(text_path),
        },
    }


def collect(symbols: list[str], run_id: str) -> dict[str, Any]:
    retrieved_at = datetime.now(timezone.utc)
    receipts: dict[str, Any] = {}
    run_dir = EVIDENCE_ROOT / run_id
    for symbol in symbols:
        definitions = SOURCES[symbol]
        symbol_dir = run_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        sources = [_archive(symbol, item, symbol_dir, retrieved_at) for item in definitions]
        if len({source["id"] for source in sources}) != len(sources):
            raise ValueError(f"Duplicate dividend lifecycle source ids: {symbol}")
        receipts[symbol] = {
            "symbol": symbol,
            "source_count": len(sources),
            "sources": sources,
        }
    manifest = {
        "schema_version": "m1-dividend-lifecycle-run-v1",
        "run_id": run_id,
        "generated_at": retrieved_at.isoformat(),
        "action": "no_order",
        "parser_version": PARSER_VERSION,
        "receipts": receipts,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", choices=sorted(SOURCES), default=sorted(SOURCES))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = collect(args.symbols, run_id)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

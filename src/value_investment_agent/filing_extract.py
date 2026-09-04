"""Extract review-only financial-statement candidates from statutory PDFs."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path


FIELDS = {
    "货币资金": "cash",
    "短期借款": "short_term_borrowings",
    "一年内到期的非流动负债": "current_portion_long_term_debt",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "购建固定资产、无形资产和其他长期资产所支付的现金": "capital_expenditure",
}
FIELD_STATEMENTS = {
    "cash": "balance",
    "short_term_borrowings": "balance",
    "current_portion_long_term_debt": "balance",
    "long_term_borrowings": "balance",
    "bonds_payable": "balance",
    "operating_cash_flow": "cashflow",
    "capital_expenditure": "cashflow",
}

# This issuer-disclosed annual-report summary is useful for human review, but
# candidates from it remain unverified until a reviewer confirms the page.
SUMMARY_FIELDS = {
    "营业收入": ("revenue", "reported_amount"),
    "归属于上市公司股东的净利润": ("net_income", "reported_amount"),
    "经营活动产生的现金流量净额": ("operating_cash_flow", "reported_amount"),
    "基本每股收益": ("eps_annual", "CNY/share"),
    "加权平均净资产收益率": ("roe", "percent"),
    "归属于上市公司普通股股东的每股净资产": ("bvps", "CNY/share"),
}


def _number_after_label(text: str, label: str) -> tuple[str, str] | None:
    # The PDF text layer puts an optional footnote reference between a label
    # and its amount, e.g. "货币资金 1 53,518,798,979.08".
    match = re.search(
        rf"{re.escape(label)}(?:\s+\d{{1,2}})?\s+(-?[\d,]+(?:\.\d+)?)",
        text,
    )
    if match is None:
        return None
    return match.group(1).replace(",", ""), text[max(0, match.start() - 120):match.end() + 180]


def extract_candidates_from_pages(pages: list[str]) -> list[dict]:
    """Return candidates for automated cross-source verification, never trusted facts."""
    candidates: list[dict] = []
    statement: str | None = None
    for page_index, page_text in enumerate(pages, start=1):
        if "主要会计数据和财务指标" in page_text:
            for label, (field_name, unit) in SUMMARY_FIELDS.items():
                result = _number_after_label(page_text, label)
                if result is None:
                    continue
                value, excerpt = result
                candidates.append({
                    "field_name": field_name, "source_label": label,
                    "value": value, "unit": unit, "page": page_index,
                    "excerpt": excerpt, "status": "candidate_pending_automated_verification",
                })
        if "母公司资产负债表" in page_text or "母公司现金流量表" in page_text:
            statement = None
        elif "合并资产负债表" in page_text or ("资产负债表" in page_text and "本集团" in page_text):
            statement = "balance"
        elif "合并现金流量表" in page_text or ("现金流量表" in page_text and "本集团" in page_text):
            statement = "cashflow"
        if statement is None:
            continue
        for label, field_name in FIELDS.items():
            if FIELD_STATEMENTS[field_name] != statement:
                continue
            result = _number_after_label(page_text, label)
            if result is None:
                continue
            value, excerpt = result
            candidates.append(
                {
                    "field_name": field_name,
                    "source_label": label,
                    "value": value,
                    "unit": "CNY",
                    "page": page_index,
                    "excerpt": excerpt,
                    "status": "candidate_pending_automated_verification",
                }
            )
    return candidates


def extract_candidates(pdf_path: Path) -> dict:
    """Read a statutory PDF and produce a JSON-serializable review packet."""
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("PDF extraction requires pypdf; install the project dependencies") from error
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF was not found: {pdf_path}")
    # Some issuer PDFs have recoverable xref defects. Keep those warnings out
    # of scheduled-task logs; exceptions still fail the specific disclosure.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    raw = pdf_path.read_bytes()
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return {
        "evidence_file": str(pdf_path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "page_count": len(pages),
        "candidates": extract_candidates_from_pages(pages),
        "warning": "Candidates require automatic cross-source verification before they enter verified facts.",
    }

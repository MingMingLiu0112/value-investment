"""Read the pinned issuer dividend plan as a conditional D2 policy fact.

This adapter does not revise sealed research contexts or create cash forecasts.
"""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from ....infrastructure.filings.official_pdf import validate_pdf_original
from ....infrastructure.filings.pdf_text import extract_pages
from ...product.common import require_inside


SCHEMA = "d2-issuer-dividend-plan-source-v2"
URL = "https://www.moutaichina.com/eportal/attachDir/mtgf/2024/08/2024080910064576661.pdf"


def _compact(text):
    return re.sub(r"\s+", "", text).replace("－", "-").replace("—", "-")


def read_issuer_dividend_plan(root: Path, receipt_path: Path, *, now: datetime) -> dict:
    """Replay exact local PDF bytes and extract only its disclosed 2024-26 rule."""
    if now.utcoffset() is None:
        raise ValueError("D2_PLAN_AWARE_CLOCK_REQUIRED")
    root = root.resolve()
    receipt_path = require_inside(root, receipt_path, "D2 plan receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if (receipt.get("schema_version") != SCHEMA or receipt.get("symbol") != "600519"
            or receipt.get("issuer_name") != "贵州茅台酒股份有限公司"
            or receipt.get("source_url") != URL
            or receipt.get("document_date") != "2024-08-09"
            or receipt.get("published_date_basis") != "PDF_PAGE_2_BOARD_DATE_NOT_INDEPENDENT_POSTING_TIME"):
        raise ValueError("D2_PLAN_RECEIPT_IDENTITY_INVALID")
    stamp = datetime.fromisoformat(receipt["fetched_at"].replace("Z", "+00:00"))
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("D2_PLAN_NOT_YET_ACQUIRED")
    relative = Path(receipt["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("D2_PLAN_PATH_INVALID")
    original = require_inside(root, root / relative, "D2 plan original")
    raw = original.read_bytes()
    digest = sha256(raw).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"]) or digest != receipt["sha256"]:
        raise ValueError("D2_PLAN_PDF_HASH_CHANGED")
    validate_pdf_original(original)
    pages = extract_pages(original)
    if len(pages) != 2:
        raise ValueError("D2_PLAN_PAGE_COUNT_CHANGED")
    first, second = map(_compact, pages)
    if ("证券代码：600519" not in first or "贵州茅台酒股份有限公司" not in first
            or "2024-2026年度现金分红回报规划" not in first
            or "2024-2026年度，公司每年度分配的现金红利总额不低于当年实现归属于上市公司股东的净利润的75%" not in first
            or "每年度的现金分红分两次（年度和中" not in first
            or "期分红）实施" not in second
            or "具体的现金分红方案由公司董事会拟定，经公司股东大会审议通过后实施" not in second
            or "在保证公司持续经营能力和长期发展不受影响的前提下" not in first
            or "规划由公司董事会负责解释，经公司股东大会审议通过之日起正式生效" not in second
            or "2024年8月9日" not in second):
        raise ValueError("D2_PLAN_DISCLOSURE_TEXT_CHANGED")
    # The board date is not a verified posting timestamp. The local fetch is
    # the earliest evidenced availability for this adapter.
    return dict(schema_version="d2-issuer-dividend-plan-anchor-v2", symbol="600519",
        issuer_name=receipt["issuer_name"], status="DISCLOSED_CONDITIONAL_ANNUAL_PAYOUT_PLAN",
        fiscal_years=[2024, 2025, 2026], minimum_ratios=["0.75"] * 3,
        profit_basis="consolidated_parent_attributable",
        distribution_basis="annual_total_cash_dividends",
        planned_installments=["annual", "interim"],
        approval_condition="Specific cash dividend proposal requires board formulation and shareholder approval; plan effective upon shareholder approval.",
        operating_condition="Subject to laws and articles, continuing operations, long-term development, funding needs and cash flow.",
        source_binding=dict(path=relative.as_posix(), sha256=digest, source_url=URL),
        receipt_binding=dict(path=receipt_path.relative_to(root).as_posix(),
            sha256=sha256(receipt_path.read_bytes()).hexdigest()),
        physical_pages=[1, 2], document_date="2024-08-09",
        fetched_at=stamp.isoformat(), available_at=stamp.isoformat(),
        limitation="Policy for 2024-2026 only; not parent cash capacity, declaration, paid dividend, forecast or a rule for later years.",
        action="no_order", formal_eligibility=False)

"""Versioned, source-bound Q3 income facts; never a cash or valuation input by itself."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

import pypdfium2 as pdfium

from .quarter_financial_ocr_v1 import MODELS, SUPPORTED_SYMBOL
from .quarter_financial_read_model_v1 import read_quarter_financial_ocr, _inside
from ...infrastructure.filings.pdfium_runtime import serialized_pdfium

REGISTRY = "config/quarter-income-ocr-v2.json"
FIELDS = {8: {"revenue": "其中：营业收入", "cost": "其中：营业成本",
              "surcharges": "税金及附加", "selling": "销售费用",
              "admin": "管理费用", "research": "研发费用"},
          9: {"pre_tax_profit": "四、利润总额", "tax": "减：所得税费用",
              "parent_profit": "1.归属于母公司股东的净利",
              "net_profit": "五、净利润", "minority_profit": "2.少数股东损益"}}
AMOUNT = re.compile(r"-?(?:\d{1,3},)*\d+\.\d{2}\Z")


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _box(row: dict) -> tuple[float, float]:
    b = row.get("box")
    if (not isinstance(b, list) or len(b) != 4 or
            any(not isinstance(p, list) or len(p) != 2 or
                any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in p) for p in b)):
        raise ValueError("Q3_OCR_GEOMETRY_INVALID")
    return min(p[0] for p in b), min(p[1] for p in b)


def _row_value(rows: list[dict], label: str, native: str, col: int) -> Decimal:
    labels = [r for r in rows if r.get("text", "").startswith(label) and _box(r)[0] < 800]
    if len(labels) != 1:
        raise ValueError("Q3_INCOME_LABEL_MISSING_OR_DUPLICATE:" + label)
    y = _box(labels[0])[1]
    lo, hi = ((800, 1200) if col == 2026 else (1200, 1700))
    amounts = [r for r in rows if isinstance(r.get("text"), str) and
               AMOUNT.fullmatch(r["text"]) and lo < _box(r)[0] < hi and
               abs(_box(r)[1] - y) < 38]
    if (len(amounts) != 1 or any(not isinstance(r.get("confidence"), (int, float)) or
                                 r["confidence"] < .98 for r in labels)):
        raise ValueError("Q3_INCOME_AMOUNT_UNVERIFIED:" + label + ":" + str(col))
    # Verify the complete native row, not just a number elsewhere on the page.
    number = r"-?(?:\d{1,3},)*\d+\.\d{2}"
    pattern = re.escape(label) + r"[^\d]{0,100}?(" + number + r")\s+(" + number + r")"
    pairs = re.findall(pattern, native, re.DOTALL)
    native_verified = (len(pairs) == 1 and
                       pairs[0][0 if col == 2026 else 1] == amounts[0]["text"])
    score = amounts[0].get("confidence")
    if not native_verified and (not isinstance(score, (int, float)) or score < .98):
        raise ValueError("Q3_INCOME_AMOUNT_UNVERIFIED:" + label + ":" + str(col))
    text = amounts[0]["text"]
    # Repeated net income on the continuing-operations row is legitimate.
    # Geometry selects the row; all printed occurrences must reconcile.
    if native.count(text) != sum(r.get("text") == text for r in rows):
        raise ValueError("Q3_INCOME_NATIVE_NUMBER_AMBIGUOUS:" + label)
    return Decimal(text.replace(",", ""))


@serialized_pdfium
def _render(root: Path, original: Path, entries: dict) -> dict[int, str]:
    doc = pdfium.PdfDocument(original)
    try:
        result = {}
        for n, entry in entries.items():
            page = doc[n - 1]
            try:
                bitmap = page.render(scale=3)
                try:
                    image = bitmap.to_pil()
                    pixels = sha256(image.tobytes()).hexdigest()
                    if pixels != entry["pixel_sha256"] or list(image.size) != entry["image_size"]:
                        raise ValueError("Q3_INCOME_PDF_IMAGE_MISMATCH:" + str(n))
                finally:
                    bitmap.close()
                textpage = page.get_textpage()
                try:
                    result[n] = textpage.get_text_range()
                finally:
                    textpage.close()
            finally:
                page.close()
        return result
    finally:
        doc.close()


def _reported_nonrecurring_ytd(pages: list[str], parent_profit: str) -> str:
    first, second = (" ".join(page.replace("：", ":").split()) for page in pages)
    unit = "单位:元 币种:人民币"
    if (unit not in first or "年初至报告期末" not in first
            or "非经常性损益项目和金额" not in second):
        raise ValueError("Q3_NONRECURRING_HEADERS_UNVERIFIED")
    section = second.split("非经常性损益项目和金额", 1)[1]
    section = section.split("对公司将", 1)[0]
    if unit not in section or "年初至报告期末" not in section:
        raise ValueError("Q3_NONRECURRING_HEADERS_UNVERIFIED")
    amount = r"(-?(?:\d{1,3},)*\d+\.\d{2})"
    adjusted = re.findall(
        r"归属于上市公司股东的 扣除非经常性损益的净 利润 "
        + amount + r" -?\d+\.\d{2} " + amount + r" -?\d+\.\d{2}", first)
    totals = re.findall(r"合计 " + amount + " " + amount, section)
    if len(adjusted) != 1 or len(totals) != 1:
        raise ValueError("Q3_NONRECURRING_ROWS_UNVERIFIED")
    ytd_adjusted = Decimal(adjusted[0][1].replace(",", ""))
    total = Decimal(totals[0][1].replace(",", ""))
    if Decimal(parent_profit) - ytd_adjusted != total:
        raise ValueError("Q3_NONRECURRING_PROFIT_RECONCILIATION_FAILED")
    return str(total)


def read_quarter_income_facts(root: Path, symbol: str, now: datetime) -> dict:
    result = {"schema_version": "quarter-income-facts-v2", "symbol": symbol,
              "status": "UNASSESSABLE", "action": "no_order", "formal_eligibility": False,
              "valuation_admitted": False, "facts": None}
    base = read_quarter_financial_ocr(root, symbol, now)
    if base["status"] == "NOT_SUPPORTED":
        return {**result, "status": "NOT_SUPPORTED", "reason": base.get("reason")}
    if base["status"] != "VERIFIED_OBSERVATION_ONLY":
        return {**result, "reason": "Q3_BASE_SOURCE_UNVERIFIED:" + base["status"]}
    try:
        root = Path(root).resolve()
        registry_path = _inside(root, REGISTRY)
        registry = json.loads(registry_path.read_bytes())
        if (registry.get("schema_version") != "quarter-income-ocr-registry-v2" or
                registry.get("action") != "no_order" or
                set(registry.get("cases", {})) != {SUPPORTED_SYMBOL}):
            raise ValueError("Q3_INCOME_REGISTRY_INVALID")
        case = registry["cases"][symbol]
        if (case.get("source_sha256") != base["source_bindings"]["original"]["sha256"] or
                case.get("report_period") != "2026-09-30" or
                set(case.get("pages", {})) != {"8", "9"}):
            raise ValueError("Q3_INCOME_SOURCE_IDENTITY_MISMATCH")
        original = _inside(root, base["source_bindings"]["original"]["path"])
        if _sha(original) != case["source_sha256"]:
            raise ValueError("Q3_INCOME_ORIGINAL_HASH_CHANGED")
        entries = {}
        for n in FIELDS:
            refs = case["pages"][str(n)]
            image_path, ocr_path = (_inside(root, refs[k]["path"]) for k in ("image", "ocr"))
            if _sha(image_path) != refs["image"]["sha256"] or _sha(ocr_path) != refs["ocr"]["sha256"]:
                raise ValueError("Q3_INCOME_ARTIFACT_HASH_CHANGED")
            entry = json.loads(ocr_path.read_bytes())
            generated = datetime.fromisoformat(entry["generated_at"])
            available = datetime.fromisoformat(base["source_bindings"]["original"]["available_at"])
            if (generated.utcoffset() is None or generated > now or generated < available or
                    entry.get("schema_version") != "official-quarter-income-ocr-raw-v2" or
                    entry.get("status") != "UNADMITTED_OCR_REQUIRES_RECONCILIATION" or
                    entry.get("source_sha256") != case["source_sha256"] or
                    entry.get("image_sha256") != refs["image"]["sha256"] or
                    entry.get("physical_page") != n or
                    entry.get("report_period") != "2026-09-30" or
                    entry.get("currency") != "CNY" or entry.get("unit") != "yuan" or
                    entry.get("ocr_engine") != "rapidocr-3.10.0" or
                    entry.get("model_sha256") != MODELS or
                    entry.get("render_engine") != "pypdfium2" or entry.get("render_scale") != 3):
                raise ValueError("Q3_INCOME_OCR_BINDING_INVALID")
            entries[n] = entry
        native = _render(root, original, entries)
        if not all("2026" in native[n] and "2025" in native[n] for n in (8,)):
            raise ValueError("Q3_INCOME_NATIVE_PERIOD_UNVERIFIED")
        headers = entries[8]["rows"]
        if not all(any(r.get("text") == text for r in headers) for text in
                   ("合并利润表", "2026年前三季度", "2025年前三季度",
                    "单位：元币种：人民币审计类型：未经审计")):
            raise ValueError("Q3_INCOME_HEADER_UNVERIFIED")
        facts = {str(year): {field: str(_row_value(entries[n]["rows"], label, native[n], year))
                             for n, fields in FIELDS.items() for field, label in fields.items()}
                 for year in (2026, 2025)}
        for year, row in facts.items():
            if Decimal(row["pre_tax_profit"]) - Decimal(row["tax"]) != Decimal(row["net_profit"]) or \
               Decimal(row["net_profit"]) - Decimal(row["minority_profit"]) != Decimal(row["parent_profit"]):
                raise ValueError("Q3_INCOME_PROFIT_RECONCILIATION_FAILED:" + year)
        original_pair = base["ytd_9m_observation"]["facts"]
        if (facts["2026"]["revenue"] != original_pair["revenue_ytd_cny"] or
                facts["2026"]["parent_profit"] != original_pair["attributable_profit_ytd_cny"]):
            raise ValueError("Q3_INCOME_V1_V2_FACT_CONFLICT")
        from ...infrastructure.filings.pdf_text import extract_pages

        nonrecurring = None
        try:
            nonrecurring = _reported_nonrecurring_ytd(extract_pages(original, limit=2), facts["2026"]["parent_profit"])
        except (ValueError, OSError, TypeError):
            pass
        if _sha(original) != case["source_sha256"]:
            raise ValueError("Q3_INCOME_ORIGINAL_HASH_CHANGED")
        if nonrecurring is not None:
            facts["2026"]["nonrecurring"] = nonrecurring
        comparative = None
        if prior := case.get("prior_year_original"):
            try:
                prior_path = _inside(root, prior["path"])
                acquired_at = datetime.fromisoformat(prior["available_at"])
                if (prior["report_period"] != "2025-09-30"
                        or acquired_at.utcoffset() is None or acquired_at > now
                        or not re.fullmatch(
                            r"https://static[.]cninfo[.]com[.]cn/finalpage/2025-\d{2}-\d{2}/\d+[.]PDF",
                            prior["source_url"])
                        or _sha(prior_path) != prior["sha256"]):
                    raise ValueError("Q3_COMPARATIVE_BINDING_INVALID")
                prior_pages = extract_pages(prior_path, limit=2)
                heading = "".join(prior_pages[0].split())
                if ("2025年第三季度报告" not in heading
                        or f"证券代码：{symbol}" not in heading):
                    raise ValueError("Q3_COMPARATIVE_IDENTITY_MISMATCH")
                value = _reported_nonrecurring_ytd(prior_pages, facts["2025"]["parent_profit"])
                if _sha(prior_path) != prior["sha256"]:
                    raise ValueError("Q3_COMPARATIVE_ORIGINAL_HASH_CHANGED")
                comparative = {**prior, "physical_pages": [1, 2]}
                facts["2025"]["nonrecurring"] = value
            except (ValueError, OSError, KeyError, TypeError):
                pass
        return {**result, "status": "VERIFIED_REPORTED_Q3_INCOME_FACTS_ONLY",
                "prior_year_nonrecurring_source": comparative,
                "nonrecurring_source_pages": [1, 2] if nonrecurring is not None else [],
                "report_period": "2026-09-30", "period_basis": "YTD_9M",
                "currency": "CNY", "unit": "yuan", "facts": facts,
                "source_bindings": {"original": base["source_bindings"]["original"],
                    "ocr_registry": {"path": REGISTRY, "sha256": _sha(registry_path)},
                    "pages": case["pages"]},
                "reason": "Consolidated income only; parent cash, D&A and future policy unverified."}
    except (ValueError, OSError, KeyError, TypeError, IndexError, json.JSONDecodeError) as error:
        return {**result, "reason": str(error) if isinstance(error, ValueError) else type(error).__name__}

"""Read only, source bound parent cash history for first research input."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from .parent_cash_research import LABELS, extract_parent_cash_statement
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import require_inside


SCHEMA = "first-input-parent-cash-observation-v1"
STOCKS = ("opening_cash_and_equivalents_cny", "closing_cash_and_equivalents_cny")
FLOWS = tuple(field for field in LABELS if field not in STOCKS)
FIELDS = (*FLOWS, *STOCKS)
STOCK = "closing_cash_and_equivalents_cny"
REPORTS = {"2025-12-31": ("FY2025", "FY2024", "2025年年度报告", "2025年度", "2024年度"),
           "2026-06-30": ("H12026", "H12025", "2026年半年度报告", "2026年半年度", "2025年半年度")}
LIMITATIONS = [
    "Historical parent statement flows and closing cash only; future cash is unproven.",
    "Mixed distributions, profit and interest paid are not identified ordinary dividends.",
    "Closing cash is a point-in-time stock and has no TTM value.",
    "Historical CFO or cash balance does not establish future remittance or legal distribution capacity.",
]


def _read_bound(root: Path, binding: dict) -> bytes:
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or not isinstance(binding["path"], str) or "\\" in binding["path"]
            or Path(binding["path"]).is_absolute() or ".." in Path(binding["path"]).parts
            or not isinstance(binding["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]) is None):
        raise ValueError("INVALID_SOURCE_BINDING")
    path = require_inside(root, root / binding["path"], "parent cash source")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("SOURCE_SHA256_MISMATCH")
    return raw


def _time(value: str, now: datetime) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("SOURCE_TIME_UNAVAILABLE")
    return stamp


def calculate_ttm_flows(periods: list[dict]) -> dict[str, str]:
    """FY2025 + H12026 - H12025, exclusively for named interval flows."""
    if len(periods) != 3 or {p["period"] for p in periods} != {"FY2025", "H12025", "H12026"}:
        raise ValueError("TTM_PERIODS_REQUIRED")
    by_period = {p["period"]: p for p in periods}
    result = {}
    for field in FLOWS:
        values = []
        for period in ("FY2025", "H12026", "H12025"):
            value = by_period[period]["flows"][field]
            if not isinstance(value, str):
                raise ValueError("TTM_FLOW_MISSING:" + field)
            number = Decimal(value)
            if not number.is_finite():
                raise ValueError("TTM_FLOW_NONFINITE:" + field)
            values.append(number)
        result[field] = format(values[0] + values[1] - values[2], ".2f")
    return result


def observe_first_input_parent_cash(*, root: Path, native_facts_binding: dict,
                                    now: datetime) -> dict:
    """Replay exactly two E2 native manifest originals; never write or place orders."""
    envelope = dict(schema_version=SCHEMA, status="UNASSESSABLE", symbol=None,
                    action="no_order", periods=[], ttm_flows={}, source_bindings=[],
                    limitations=list(LIMITATIONS), whole_statement_reconciled=False,
                    future_cash_proven=False,
                    formal_eligibility=False)
    try:
        root = Path(root).resolve()
        if now.utcoffset() is None:
            raise ValueError("AWARE_CUTOFF_REQUIRED")
        manifest = json.loads(_read_bound(root, native_facts_binding))
        symbol = manifest["symbol"]
        envelope["symbol"] = symbol
        if (manifest.get("schema_version") != "first-research-native-facts-v1"
                or manifest.get("action") != "no_order"
                or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(manifest.get("issuer_name"), str)
                or not manifest["issuer_name"].strip()
                or manifest.get("financial_basis") != "2026-06-30"):
            raise ValueError("E2_MANIFEST_IDENTITY_OR_BASIS_INVALID")
        _time(manifest["generated_at"], now)
        sources = manifest["sources"]
        if len(sources) != 2 or {s["report_period"] for s in sources} != set(REPORTS):
            raise ValueError("TWO_OFFICIAL_REPORTS_REQUIRED")
        found = {}
        refs = []
        for source in sources:
            report_period = source["report_period"]
            current, prior, title, current_col, prior_col = REPORTS[report_period]
            published = date.fromisoformat(source["published_date"])
            available = _time(source["available_at"], now)
            if (source.get("symbol") != symbol or source.get("issuer_name") != manifest["issuer_name"]
                    or date.fromisoformat(report_period) > published
                    or published > available.date()
                    or title not in source["report_title"]
                    or source.get("source_url") !=
                    f'https://static.cninfo.com.cn/finalpage/{published.isoformat()}/{source["id"].split(":")[-1]}.PDF'
                    or re.fullmatch(r"cninfo:[0-9]+", source["id"]) is None):
                raise ValueError("OFFICIAL_SOURCE_IDENTITY_OR_TIME_CONFLICT")
            if not isinstance(source.get("identity_index_binding"), dict):
                raise ValueError("OFFICIAL_IDENTITY_INDEX_REQUIRED")
            index = json.loads(_read_bound(root, source["identity_index_binding"]))
            matches = [row for row in index.get("announcements", [])
                       if isinstance(row, dict) and row.get("secCode") == symbol]
            if not matches or {row.get("orgId") for row in matches} != {source.get("organization_id")}:
                raise ValueError("OFFICIAL_IDENTITY_INDEX_CONFLICT")
            names = {re.sub(r"<[^>]*>", "", row.get("secName", "")).strip()
                     for row in matches}
            declared = source.get("issuer_short_name")
            if (not names or "" in names or
                    (names != {declared} if declared is not None
                     else any(name not in manifest["issuer_name"] for name in names))):
                raise ValueError("OFFICIAL_IDENTITY_INDEX_CONFLICT")
            _time(source["identity_available_at"], now)
            raw = _read_bound(root, {"path": source["path"], "sha256": source["sha256"]})
            if not raw.startswith(b"%PDF-"):
                raise ValueError("OFFICIAL_PDF_FORMAT_INVALID")
            path = require_inside(root, root / source["path"], "parent cash PDF")
            parsed = extract_parent_cash_statement(
                pages=extract_pages(path),
                spec=dict(symbol=symbol, issuer=manifest["issuer_name"],
                          periods=[current, prior], column_labels=[current_col, prior_col]),
                )
            if (parsed["statement_scope"] != "listed_parent_only"
                    or len(parsed.get("balances", [])) != 2
                    or any(balance.get("cash_residual_cny") != "0.00"
                           or balance.get("movement_residual_cny") != "0.00"
                           for balance in parsed["balances"])):
                raise ValueError("PARENT_STATEMENT_SCOPE_INVALID")
            if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("SOURCE_CHANGED_DURING_PARSE")
            for index, period in enumerate((current, prior)):
                flows = {}
                pages = {}
                for field in FIELDS:
                    row = parsed["rows"][field]
                    if (row["statement_scope"] != "listed_parent_only"
                            or row["columns"][index]["period"] != period
                            or not isinstance(row["physical_page"], int)
                            or row["physical_page"] < 1):
                        raise ValueError("PARENT_COLUMN_OR_PAGE_CONFLICT:" + field)
                    pages[field] = row["physical_page"]
                    if field in FLOWS:
                        flows[field] = row["columns"][index]["value"]
                item = dict(period=period, flows=flows,
                            opening_cash_and_equivalents_cny=parsed["rows"]["opening_cash_and_equivalents_cny"]["columns"][index]["value"],
                            closing_cash_and_equivalents_cny=parsed["rows"][STOCK]["columns"][index]["value"],
                            cash_residual_cny=parsed["balances"][index]["cash_residual_cny"],
                            movement_residual_cny=parsed["balances"][index]["movement_residual_cny"],
                            physical_pages=pages, source_sha256=source["sha256"])
                if period in found and found[period] != item:
                    raise ValueError("DUPLICATE_PERIOD_CONFLICT")
                found[period] = item
            if current == "H12026":
                interim_opening = parsed["rows"]["opening_cash_and_equivalents_cny"]["columns"][0]["value"]
            refs.append(dict(source_id=source["id"], path=source["path"], sha256=source["sha256"],
                             source_url=source["source_url"], report_period=report_period,
                             published_date=source["published_date"], available_at=source["available_at"]))
        periods = [found[p] for p in ("FY2025", "H12025", "H12026")]
        if periods[0]["closing_cash_and_equivalents_cny"] != interim_opening:
            raise ValueError("PARENT_CASH_PERIOD_CONTINUITY_CONFLICT")
        envelope.update(status="OBSERVED", whole_statement_reconciled=True, periods=periods,
                        ttm_flows=calculate_ttm_flows(periods),
                        source_bindings=[dict(native_facts_binding), *refs])
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, UnicodeError, ArithmeticError, OverflowError) as error:
        envelope.update(status="UNASSESSABLE", reason=str(error), periods=[],
                        ttm_flows={}, source_bindings=[])
    return envelope

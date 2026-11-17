"""Source-bound parent balance movements; never convert them to WC cash flow."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

import pypdfium2 as pdfium

from .pdfium_runtime import serialized_pdfium

VERSION = "parent-wc-history-600519-v1"
REGISTRY = "config/parent-wc-history-600519-v1.json"
NUMBER = r"(-?\d{1,3}(?:,\d{3})*\.\d{2})"
FIELDS = {"accounts_receivable": "应收账款", "inventory": "存货", "accounts_payable": "应付账款"}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("PARENT_WC_DUPLICATE_KEY")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique)


@serialized_pdfium
def _pages(path, numbers):
    doc = pdfium.PdfDocument(path)
    try:
        if len(doc) < max(numbers):
            raise ValueError("PARENT_WC_PAGE_MISSING")
        result = {}
        for number in numbers:
            page = doc[number - 1]
            try:
                text_page = page.get_textpage()
                try:
                    result[number] = text_page.get_text_range()
                finally:
                    text_page.close()
            finally:
                page.close()
        return result
    finally:
        doc.close()


def _row(text, label):
    matches = re.findall(r"^" + re.escape(label) + r"(?:\s+\d+)?\s+" + NUMBER + r"\s+" + NUMBER,
                         text, flags=re.M)
    if len(matches) != 1:
        raise ValueError("PARENT_WC_BALANCE_ROW_MISSING_OR_AMBIGUOUS:" + label)
    return [Decimal(value.replace(",", "")) for value in matches[0]]


def _cash(text):
    match = re.search(r"经营活动产生的现金流量净额" + NUMBER,
                      re.sub(r"\s+", "", text))
    if not match:
        raise ValueError("PARENT_WC_CFO_MISSING")
    return Decimal(match[1].replace(",", ""))


def read_parent_wc_history(root: Path, as_of: datetime) -> dict:
    """Read FY/H1 parent balances and CFO; cash WC remains UNKNOWN."""
    root = Path(root).resolve()
    result = {"schema_version": VERSION, "status": "UNASSESSABLE", "symbol": "600519",
              "operating_wc_cash_cny": "UNKNOWN", "formal_eligibility": False,
              "action": "no_order"}
    try:
        if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
            raise ValueError("PARENT_WC_AWARE_AS_OF_REQUIRED")
        registry = root / REGISTRY
        raw = registry.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("PARENT_WC_REGISTRY_TOO_LARGE")
        data = _json(raw)
        if (not isinstance(data, dict) or set(data) != {"schema_version", "action", "symbol",
                "issuer_name", "sources"} or data["schema_version"] != VERSION
                or data["action"] != "no_order" or data["symbol"] != "600519"
                or data["issuer_name"] != "贵州茅台酒股份有限公司"
                or not isinstance(data["sources"], list) or len(data["sources"]) != 2
                or [s.get("period") for s in data["sources"]] != ["2025-12-31", "2026-06-30"]):
            raise ValueError("PARENT_WC_REGISTRY_INVALID")
        observations = []
        paths = []
        for source in data["sources"]:
            if set(source) != {"period", "path", "sha256", "source_url", "published_date",
                    "available_at", "parent_balance_pages", "parent_cash_page", "group_cash_header_page", "group_cash_page",
                    "group_cash_reconciliation_page", "columns"}:
                raise ValueError("PARENT_WC_SOURCE_FIELDS_INVALID")
            name = source["path"]
            if (not isinstance(name, str) or not name.startswith("runtime/")
                    or "\\" in name or Path(name).is_absolute() or PureWindowsPath(name).drive
                    or ".." in PureWindowsPath(name).parts
                    or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])):
                raise ValueError("PARENT_WC_SOURCE_BINDING_INVALID")
            match = re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/(\d{4}-\d{2}-\d{2})/\d{10}\.PDF",
                                 source["source_url"])
            available = datetime.fromisoformat(source["available_at"])
            if (not match or date.fromisoformat(match[1]) != date.fromisoformat(source["published_date"])
                    or available.utcoffset() is None or available > as_of
                    or available.date() < date.fromisoformat(source["published_date"])):
                raise ValueError("PARENT_WC_SOURCE_NOT_AVAILABLE_AS_OF")
            path = (root / name).resolve()
            if not path.is_relative_to(root) or path.name != "original.pdf" or not path.is_file():
                raise ValueError("PARENT_WC_ORIGINAL_MISSING")
            if path.stat().st_size > 64 * 1024 * 1024 or _sha(path) != source["sha256"]:
                raise ValueError("PARENT_WC_ORIGINAL_HASH_MISMATCH")
            numbers = [*source["parent_balance_pages"], source["parent_cash_page"],
                       source["group_cash_header_page"], source["group_cash_page"],
                       source["group_cash_reconciliation_page"]]
            if len(set(numbers)) != 6 or any(type(n) is not int or n < 1 for n in numbers):
                raise ValueError("PARENT_WC_PAGES_INVALID")
            pages = _pages(path, numbers)
            balance = "\n".join(pages[n] for n in source["parent_balance_pages"])
            header = balance.split("母公司资产负债表", 1)
            if len(header) != 2:
                raise ValueError("PARENT_WC_PARENT_BALANCE_HEADER_MISSING")
            balance = header[1]
            year = source["period"][:4]
            expected_columns = [f'{year} 年 12 月 31 日', f'{int(year)-1} 年 12 月 31 日'] if source["period"].endswith("12-31") else [
                f'{year} 年 6 月 30 日', f'{int(year)-1} 年 12 月 31 日']
            if ("单位：元 币种：人民币" not in balance
                    or data["issuer_name"] not in balance
                    or any(column not in balance for column in expected_columns)
                    or source["columns"] != (["2025-12-31", "2024-12-31"]
                                             if source["period"] == "2025-12-31"
                                             else ["2026-06-30", "2025-12-31"])):
                raise ValueError("PARENT_WC_BALANCE_UNIT_OR_COLUMNS_INVALID")
            rows = {}
            for field, label in FIELDS.items():
                end, begin = _row(balance, label)
                rows[field] = {"period_end_balance_cny": str(end),
                               "period_start_balance_cny": str(begin),
                               "balance_change_cny": str(end - begin)}
            cash_page = pages[source["parent_cash_page"]]
            cash_period = ("2025 年 1—12 月" if source["period"] == "2025-12-31"
                           else "2026 年 1—6 月")
            if ("母公司现金流量表" not in cash_page
                    or cash_period not in cash_page or "单位：元 币种：人民币" not in cash_page):
                raise ValueError("PARENT_WC_PARENT_CASH_HEADER_MISSING")
            parent_cfo = _cash(cash_page.split("母公司现金流量表", 1)[1])
            group_header = pages[source["group_cash_header_page"]]
            if ("合并现金流量表" not in group_header
                    or cash_period not in group_header
                    or "单位：元 币种：人民币" not in group_header
                    or "客户存款和同业存放款项净增加额" not in re.sub(r"\s+", "", group_header)):
                raise ValueError("PARENT_WC_GROUP_CASH_HEADER_INVALID")
            group_cfo = _cash(pages[source["group_cash_page"]])
            note = pages[source["group_cash_reconciliation_page"]]
            note_cfo = _cash(note)
            if group_cfo != note_cfo or parent_cfo == note_cfo or not all(
                    label in note for label in ("存货的减少", "经营性应收项目的减少", "经营性应付项目的增加")):
                raise ValueError("PARENT_WC_NOTE_SCOPE_NOT_GROUP")
            if source["period"] not in ("2025-12-31", "2026-06-30"):
                raise ValueError("PARENT_WC_PERIOD_INVALID")
            observations.append({"period": source["period"], "columns": source["columns"],
                                 "parent_balance_pages": source["parent_balance_pages"],
                                 "parent_cash_page": source["parent_cash_page"],
                                 "group_cash_header_page": source["group_cash_header_page"],
                                 "group_note_page": source["group_cash_reconciliation_page"],
                                 "unit": "CNY", "balance_rows": rows,
                                 "parent_cfo_cny": str(parent_cfo),
                                 "excluded_group_note_cfo_cny": str(note_cfo),
                                 "source_url": source["source_url"],
                                 "original_sha256": source["sha256"],
                                 "available_at": source["available_at"]})
            paths.append((path, source["sha256"]))
        if any(observations[0]["balance_rows"][field]["period_end_balance_cny"] !=
               observations[1]["balance_rows"][field]["period_start_balance_cny"] for field in FIELDS):
            raise ValueError("PARENT_WC_OPENING_BALANCES_DO_NOT_RECONCILE")
        if registry.read_bytes() != raw or any(_sha(path) != digest for path, digest in paths):
            raise ValueError("PARENT_WC_SOURCE_CHANGED_DURING_READ")
        result.update(status="PARENT_BALANCE_MOVEMENTS_ONLY", observations=observations,
                      research_use="Historical parent balance movements may inform conditional sensitivity only; not cash WC, forecast, or capacity.",
                      missing_evidence="No parent-only indirect CFO reconciliation separating inventory, operating receivables and payables from noncash, tax, settlement and related-party effects.",
                      registry_sha256=hashlib.sha256(raw).hexdigest())
    except (ValueError, OSError, TypeError, KeyError, IndexError) as error:
        result["error_code"] = str(error) if isinstance(error, ValueError) else type(error).__name__
    return result

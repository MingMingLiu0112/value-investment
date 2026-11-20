"""Replay the exact A-share count from a paired SZSE catalog export."""

from datetime import date, datetime
from decimal import Decimal
import json
import re
from zipfile import BadZipFile

from ...quote_sessions import CHINA


def replay_szse_capital_export(*, binding, symbol: str, comparison_date: date, now: datetime, read):
    from openpyxl import load_workbook

    receipt = json.loads(read(binding).read_bytes())
    if (not re.fullmatch(r"(?:00|30)\d{4}", symbol)
            or receipt["symbol"] != symbol
            or receipt["catalog"] != "1110"
            or receipt["action"] != "no_order"
            or date.fromisoformat(receipt["catalog_metadata_date"]) != comparison_date):
        raise ValueError("SZSE_CAPITAL_EXPORT_IDENTITY_MISMATCH")
    base = "https://www.szse.cn/api/report/ShowReport"
    query = f"&CATALOGID=1110&TABKEY=tab1&txtDMorJC={symbol}"
    catalog, export = receipt["sources"]
    if (catalog["source_url"] != f"{base}/data?SHOWTYPE=JSON{query}"
            or export["source_url"] != f"{base}/?SHOWTYPE=xlsx{query}"):
        raise ValueError("SZSE_CAPITAL_EXPORT_SOURCE_MISMATCH")
    catalog_time, export_time = (datetime.fromisoformat(item["saved_at"]) for item in (catalog, export))
    if (catalog_time.utcoffset() is None or export_time.utcoffset() is None
            or not 0 <= (export_time - catalog_time).total_seconds() <= 60
            or export_time > now
            or any(time.astimezone(CHINA).date() != comparison_date for time in (catalog_time, export_time))):
        raise ValueError("SZSE_CAPITAL_EXPORT_CAPTURE_WINDOW_MISMATCH")
    catalog_ref = {key: catalog[key] for key in ("path", "sha256")}
    export_ref = {key: export[key] for key in ("path", "sha256")}
    tabs = json.loads(read(catalog_ref).read_bytes())
    tab, = [page for page in tabs if page["metadata"]["tabkey"] == "tab1"]
    meta = tab["metadata"]
    row, = tab["data"]
    if (meta["catalogid"] != "1110" or meta["subname"].strip() != comparison_date.isoformat()
            or meta["cols"]["agzgb"] != "A股总股本<br>（亿股）" or row["agdm"] != symbol):
        raise ValueError("SZSE_CAPITAL_EXPORT_CATALOG_MISMATCH")
    with read(export_ref).open("rb") as raw:
        try:
            workbook = load_workbook(raw, read_only=True)
        except BadZipFile as error:
            raise ValueError("SZSE_CAPITAL_EXPORT_INVALID_WORKBOOK") from error
        try:
            rows = workbook["A股列表"].iter_rows(min_row=1, max_row=3, max_col=8, values_only=True)
            headings, values, *extra = rows
        finally:
            workbook.close()
    if (extra or headings[4] != "A股代码" or headings[7] != "A股总股本"
            or values[4] != symbol or not isinstance(values[7], str)
            or not re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})+", values[7])):
        raise ValueError("SZSE_CAPITAL_EXPORT_ROW_MISMATCH")
    count = int(values[7].replace(",", ""))
    displayed = Decimal(row["agzgb"]) * Decimal(100_000_000)
    if not displayed.is_finite() or abs(displayed - count) >= 1_000_000:
        raise ValueError("SZSE_CAPITAL_EXPORT_CATALOG_DISAGREEMENT")
    return dict(status="SOURCE_BOUND_EXACT_EXPORT_OBSERVATION", ordinary_a_shares=str(count),
                comparison_date=comparison_date.isoformat(), date_basis="PAIRED_CATALOG_METADATA",
                evidence_binding=binding, action="no_order")

"""Replay same-period parent direct operating cash from retained issuer reports."""
from datetime import datetime
from pathlib import Path
import re

from .parent_direct_cash_research import SCOPE, _amounts, _bound, _clock, _table
from ...infrastructure.filings.official_report_acquisition import load_retained_official_report
from ...infrastructure.filings.parent_balance_basis_v1 import extract_parent_balance_facts
from ...infrastructure.filings.pdf_text import extract_pages

VERSION = "retained-parent-direct-observations-v1"


def _normalize_paginated_annual_table(pages, *, page, title, issuer, year):
    """Reorder only the exact annual header found above the parent table."""
    if type(page) is not int or not 1 <= page <= len(pages):
        return pages
    lines = [line.strip() for line in pages[page - 1].splitlines() if line.strip()]
    if len(lines) < 7 or lines[1] != "财务报告" or lines[4] != title:
        return pages
    compact = lambda text: "".join(text.split())
    date_pattern = (fr"{year}年12月31日" if title == "母公司资产负债表"
                    else fr"{year}年1[—－–-]12月")
    if (not re.fullmatch(re.escape(issuer + f"{year}年年度报告") + r"[0-9]{1,3}", compact(lines[0]))
            or not re.fullmatch(date_pattern, compact(lines[2]))
            or compact(lines[3]) != "编制单位：" + issuer):
        return pages
    normalized = list(pages)
    normalized[page - 1] = "\n".join([issuer + f"{year}年年度报告", title, *lines[2:4], *lines[5:]])
    return normalized


def _read_retained_original(*, root, symbol, issuer_name, period_end, receipt_binding, evaluated_at):
    if not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None:
        raise ValueError("RETAINED_DIRECT_OBSERVATION_CUTOFF_REQUIRED")
    root = Path(root).resolve()
    packet = load_retained_official_report(
        root=root, receipt_binding=receipt_binding, symbol=symbol, issuer_name=issuer_name, period=period_end,
    )
    source = packet["source"]
    for stamp in (packet["fetched_at"], packet["completed_at"], source["available_at"]):
        _clock(stamp, evaluated_at)
    path, raw = _bound(root, source)
    pages = extract_pages(path)
    return packet, path, raw, pages


def read_retained_parent_direct_observations(
    *, root, symbol, issuer_name, period_end, receipt_binding, income_page, cash_page, evaluated_at,
):
    """Verify the acquisition and parse two explicit physical tables in the same original."""
    packet, path, raw, pages = _read_retained_original(
        root=root, symbol=symbol, issuer_name=issuer_name, period_end=period_end,
        receipt_binding=receipt_binding, evaluated_at=evaluated_at,
    )
    source = packet["source"]
    year = int(period_end[:4])
    annual = period_end.endswith("-12-31")
    values = {}
    for page, title, fields in (
        (income_page, "母公司利润表", ("revenue", "cost")),
        (cash_page, "母公司现金流量表", ("customer_cash", "supplier_cash", "cfo")),
    ):
        issuer = "".join(issuer_name.split())
        table_pages = (
            _normalize_paginated_annual_table(pages, page=page, title=title, issuer=issuer, year=year)
            if annual else pages
        )
        _, body = _table(
            table_pages, page_number=page, title=title, year=year, issuer=issuer, annual=annual,
        )
        values.update({name: _amounts(body, name)[0] for name in fields})
    if path.read_bytes() != raw:
        raise ValueError("RETAINED_DIRECT_OBSERVATION_ORIGINAL_CHANGED")
    return [
        dict(symbol=symbol, scope=SCOPE, currency="CNY", classification="FACT",
             period_start=f"{year - column}-01-01", period_end=f"{year - column}{period_end[4:]}",
             source_refs=[dict(source, receipt_binding=receipt_binding, column=column,
                               income_page=income_page, operating_page=cash_page, reader_version=VERSION)],
             **{name: str(pair[column]) for name, pair in values.items()})
        for column in range(2)
    ]

def read_retained_parent_balance_observations(
    *, root, symbol, issuer_name, period_end, receipt_binding, evaluated_at,
):
    """Replay parent balance facts when the annual period precedes the table title."""
    packet, path, raw, pages = _read_retained_original(
        root=root, symbol=symbol, issuer_name=issuer_name, period_end=period_end,
        receipt_binding=receipt_binding, evaluated_at=evaluated_at,
    )
    issuer = "".join(issuer_name.split())
    title = "母公司资产负债表"
    locations = [i for i, page in enumerate(pages, 1)
                 for line in page.splitlines() if line.strip() == title]
    if len(locations) == 1 and period_end.endswith("-12-31"):
        pages = _normalize_paginated_annual_table(
            pages, page=locations[0], title=title, issuer=issuer, year=int(period_end[:4]),
        )
    result = extract_parent_balance_facts(
        pages=pages, source=packet["source"], source_id=packet["source_id"], issuer_name=issuer,
    )
    if path.read_bytes() != raw:
        raise ValueError("RETAINED_DIRECT_OBSERVATION_ORIGINAL_CHANGED")
    return result

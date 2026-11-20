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


def read_retained_parent_cash_statement_observations(
    *, root, symbol, issuer_name, period_end, receipt_binding, evaluated_at,
):
    """Replay verified cash rows without imputing absent borrowings or repayments."""
    from .parent_cash_research import _column_labels, _period_pair, extract_parent_cash_statement

    packet, path, raw, pages = _read_retained_original(
        root=root, symbol=symbol, issuer_name=issuer_name, period_end=period_end,
        receipt_binding=receipt_binding, evaluated_at=evaluated_at,
    )
    periods = _period_pair(period_end)
    result = extract_parent_cash_statement(
        pages=pages,
        spec=dict(symbol=symbol, issuer=issuer_name, periods=list(periods),
                  column_labels=_column_labels(periods)),
        observation_fields={
            "cfo_cny", "cfi_cny", "cff_cny", "gross_capex_cny",
            "mixed_distribution_interest_paid_cny", "opening_cash_and_equivalents_cny",
            "closing_cash_and_equivalents_cny",
        },
    )
    if path.read_bytes() != raw:
        raise ValueError("RETAINED_DIRECT_OBSERVATION_ORIGINAL_CHANGED")
    return dict(result, schema_version="retained-parent-cash-statement-observations-v1",
                source=dict(packet["source"], receipt_binding=receipt_binding),
                financing_inference_allowed=False, action="no_order")


def read_retained_year_end_ordinary_shares(
    *, root, symbol, issuer_name, period_end, receipt_binding, supporting_root,
    supporting_sources, evaluated_at,
):
    """Verify a dated issued share count against ordinary-share class originals."""
    from datetime import date

    from ...infrastructure.filings.native_capital_observation_v1 import _compact

    year = date.fromisoformat(period_end).year
    if period_end != f"{year}-12-31" or set(supporting_sources) != {"proposal", "charter", "charter_vote"}:
        raise ValueError("RETAINED_ORDINARY_SHARE_SOURCE_SET_INVALID")
    packet, annual_path, annual_raw, pages = _read_retained_original(
        root=root, symbol=symbol, issuer_name=issuer_name, period_end=period_end,
        receipt_binding=receipt_binding, evaluated_at=evaluated_at,
    )
    integer = r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
    year_end = f"截至{year}年12月31日,"
    annual = re.compile(year_end + r"本公司累计发行股份总数" + integer + r"(?:[.]00)?股")
    proposal = re.compile(year_end + r"公司总股本" + integer + r"股")
    charter = re.compile(r"公司已发行的股份数为" + integer + r"股,(?:全部|均)为普通股。")
    vote = re.compile(r"议案名称:关于修订《公司章程》及附件的议案审议结果:通过")

    def one(original, pattern, role):
        matches = [(i, m) for i, text in enumerate(original, 1) for m in pattern.finditer(_compact(text))]
        if len(matches) != 1:
            raise ValueError("RETAINED_ORDINARY_SHARE_TERM_NOT_UNIQUE:" + role)
        return matches[0]

    annual_page, annual_term = one(pages, annual, "annual")
    refs = [dict(packet["source"], receipt_binding=receipt_binding,
                 physical_page=annual_page, excerpt=annual_term[0])]
    periods = {}
    counts = [int(annual_term[1].replace(",", ""))]
    for role, pattern in (("proposal", proposal), ("charter", charter), ("charter_vote", vote)):
        ref = supporting_sources[role]
        acquired = _clock(ref["available_at"], evaluated_at)
        official = re.fullmatch(r"https://static[.]cninfo[.]com[.]cn/finalpage/([0-9-]{10})/[0-9]{10}[.]PDF", ref["source_url"])
        if not official:
            raise ValueError("RETAINED_ORDINARY_SHARE_OFFICIAL_URL_REQUIRED")
        disclosed = date.fromisoformat(official[1])
        if disclosed > acquired.date():
            raise ValueError("RETAINED_ORDINARY_SHARE_FUTURE_LABEL")
        periods[role] = disclosed
        path, raw = _bound(Path(supporting_root).resolve(), ref)
        original = extract_pages(path)
        cover = _compact(original[0])
        if _compact(issuer_name) not in cover or (role != "charter" and
                not re.search(r"证券代码:" + re.escape(symbol) + r"(?![0-9])", cover)):
            raise ValueError("RETAINED_ORDINARY_SHARE_IDENTITY_MISMATCH:" + role)
        if role == "charter" and "章程" not in cover:
            raise ValueError("RETAINED_ORDINARY_SHARE_CHARTER_TITLE_REQUIRED")
        page, term = one(original, pattern, role)
        if path.read_bytes() != raw:
            raise ValueError("RETAINED_DIRECT_OBSERVATION_ORIGINAL_CHANGED")
        if role != "charter_vote":
            counts.append(int(term[1].replace(",", "")))
        refs.append(dict(ref, physical_page=page, excerpt=term[0]))
    if not periods["charter"] < periods["charter_vote"] <= date.fromisoformat(period_end) < periods["proposal"]:
        raise ValueError("RETAINED_ORDINARY_SHARE_DISCLOSURE_ORDER_INVALID")
    if not counts[0] > 0 or len(set(counts)) != 1:
        raise ValueError("RETAINED_ORDINARY_SHARE_COUNTS_CONFLICT")
    if annual_path.read_bytes() != annual_raw:
        raise ValueError("RETAINED_DIRECT_OBSERVATION_ORIGINAL_CHANGED")
    return dict(classification="FACT", period_end=period_end, unit="shares",
                scope="TOTAL_ISSUED_ORDINARY_SHARES", count=str(counts[0]), source_refs=refs,
                treasury_excluded=False, comparison_date_capital_proven=False, action="no_order")


def read_retained_parent_d2_preflight(
    *, root, symbol, issuer_name, annual_period, annual_receipt, interim_period, interim_receipt,
    supporting_root, supporting_sources, evaluated_at,
):
    """Combine the existing parent source bridge with a dated ordinary-share anchor."""
    from .parent_direct_owner_cash_sources import read_parent_direct_owner_cash_sources

    if interim_period != f"{int(annual_period[:4]) + 1}-06-30":
        raise ValueError("RETAINED_D2_NONCONSECUTIVE_PERIODS")
    shares = read_retained_year_end_ordinary_shares(
        root=root, symbol=symbol, issuer_name=issuer_name, period_end=annual_period,
        receipt_binding=annual_receipt, supporting_root=supporting_root,
        supporting_sources=supporting_sources, evaluated_at=evaluated_at,
    )
    annual_source = shares["source_refs"][0]
    interim, _, _, _ = _read_retained_original(
        root=root, symbol=symbol, issuer_name=issuer_name, period_end=interim_period,
        receipt_binding=interim_receipt, evaluated_at=evaluated_at,
    )
    sources = [
        dict(period_end=period, **{key: source[key] for key in ("path", "sha256", "available_at")})
        for period, source in ((annual_period, annual_source), (interim_period, interim["source"]))
    ]
    cash = read_parent_direct_owner_cash_sources(
        root=root, symbol=symbol, issuer_name=issuer_name, sources=sources, evaluated_at=evaluated_at,
    )
    if any(not statement["checks"].get("cash_statement_reconciled") or
           not statement["checks"].get("balance_equation_reconciled") for statement in cash["statements"]):
        raise ValueError("RETAINED_D2_PARENT_STATEMENTS_NOT_RECONCILED")
    return dict(schema_version="retained-parent-d2-preflight-v1", symbol=symbol,
                valuation_date=annual_period, ordinary_shares=shares, cash_source_bridge=cash,
                status="SOURCE_BOUND_D2_PREFLIGHT_ONLY", model_applicability_verified=False,
                action="no_order", formal_eligibility=False)

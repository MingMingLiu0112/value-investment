"""Read-only replay of bound parent H1 income and direct-cash observations.

Accepts the retained parent-trade-accrual-countercheck-v1 receipt binding;
its source_cash_countercheck binds the second, intra-year receipt. No forecast,
annualisation, source admission, cash-policy mapping or writes occur here.
"""
from datetime import datetime
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import re

from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.stock_identity_table_v1 import labelled_security_codes

VERSION = "parent-direct-cash-research-v1"
SCOPE = "ISSUER_PARENT_STANDALONE"
LABELS = {
    "revenue": "一、营业收入", "cost": "减：营业成本",
    "customer_cash": "销售商品、提供劳务收到的现金",
    "supplier_cash": "购买商品、接受劳务支付的现金",
    "cfo": "经营活动产生的现金流量净额",
    "inflow": "经营活动现金流入小计", "outflow": "经营活动现金流出小计",
}
MONEY = re.compile(r"(?<![\d,.])-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}(?![\d,.])")
TABLE_TITLE = re.compile(
    r"^(?:(?:[0-9一二三四五六七八九十]+[、.．])|(?:[（(][0-9一二三四五六七八九十]+[）)]))?"
    r"(?:合并|母公司)(?:资产负债表|利润表|现金流量表|所有者权益变动表|股东权益变动表)"
    r"(?:[（(]续[）)])?$"
)
SIGNATURE = re.compile(r"^(?:公司负责人|法定代表人|企业负责人|主管会计工作负责人|会计机构负责人)[:：]")


def _fail(reason):
    raise ValueError("PARENT_DIRECT_CASH_" + reason)


def _compact(text):
    return "".join(text.split())


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _bound(root, ref):
    if (not isinstance(ref, dict) or not {"path", "sha256"} <= ref.keys()
            or not isinstance(ref["path"], str) or "\\" in ref["path"]
            or Path(ref["path"]).is_absolute() or PureWindowsPath(ref["path"]).drive
            or ".." in Path(ref["path"]).parts
            or not re.fullmatch(r"[0-9a-f]{64}", str(ref["sha256"]))):
        _fail("BINDING_INVALID")
    runtime = (root / "runtime").resolve()
    path = (root / ref["path"]).resolve()
    if not path.is_relative_to(runtime) or not runtime.is_relative_to(root):
        _fail("PATH_OUTSIDE_RUNTIME")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != ref["sha256"]:
        _fail("HASH_CHANGED")
    return path, raw


def _clock(value, evaluated_at):
    try:
        instant = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        _fail("AWARE_RECEIPT_TIME_REQUIRED")
    if instant.utcoffset() is None or instant > evaluated_at:
        _fail("RECEIPT_NOT_AVAILABLE")
    return instant


def _table(pages, *, page_number, title, year, issuer=None, annual=False):
    if type(page_number) is not int or not 1 <= page_number <= len(pages):
        _fail("PAGE_INVALID")
    locations = [(i + 1, j) for i, page in enumerate(pages)
                 for j, line in enumerate(page.splitlines()) if line.strip() == title]
    if len(locations) != 1 or locations[0][0] != page_number:
        _fail("PARENT_TABLE_NOT_UNIQUE_OR_PAGE_CHANGED")
    lines = [line.strip() for line in pages[page_number - 1].splitlines() if line.strip()]
    suffix = f"{year}年年度报告" if annual else f"{year}年半年度报告"
    header = _compact(lines[0])
    if not header.endswith(suffix) or not header[:-len(suffix)]:
        _fail("ISSUER_OR_REPORT_PERIOD_CHANGED")
    owner = header[:-len(suffix)]
    if issuer is not None and owner != issuer:
        _fail("ISSUER_CHANGED")
    start = lines.index(title)
    # Never borrow headers or same-named rows from a later statement. Extraction
    # remains on this physical page; missing rows are not searched on later pages.
    body = lines[start + 1:]
    stops = [i for i, line in enumerate(body)
             if TABLE_TITLE.fullmatch(_compact(line)) or SIGNATURE.match(_compact(line))]
    if stops:
        body = body[:stops[0]]
    table_header = "".join(_compact(line) for line in body[:4])
    columns = f"项目附注{year}年度{year-1}年度" if annual else f"项目附注{year}年半年度{year-1}年半年度"
    month = 12 if annual else 6
    if ("单位：元币种：人民币" not in table_header or columns not in table_header
            or not re.search(fr"{year}年1[—－–-]{month}月", table_header)):
        _fail("UNIT_OR_PERIOD_COLUMNS_CHANGED")
    if title == "母公司现金流量表":
        stops = [i for i, line in enumerate(body) if _compact(line) == "二、投资活动产生的现金流量："]
        if len(stops) != 1:
            _fail("CASH_SECTION_BOUNDARY_REQUIRED")
        body = body[:stops[0]]
    return owner, body


def _amounts(lines, field):
    label = LABELS[field]
    matches = [line for line in lines if line.split(maxsplit=1)[:1] == [label]]
    if len(matches) != 1:
        _fail("ROW_NOT_UNIQUE:" + field)
    line = matches[0]
    numbers = MONEY.findall(line)
    if len(numbers) != 2 or not line.endswith(numbers[-1]):
        _fail("TWO_PRINTED_COLUMNS_REQUIRED:" + field)
    return tuple(Decimal(number.replace(",", "")) for number in numbers), line


def read_parent_direct_cash_research(*, root, receipt_binding, evaluated_at):
    """Reverify bound parent originals using deterministic decimal arithmetic."""
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        return _read_parent_direct_cash_research(
            root=root, receipt_binding=receipt_binding, evaluated_at=evaluated_at)


def _read_parent_direct_cash_research(*, root, receipt_binding, evaluated_at):
    """Return observed rows from bound receipts and original PDFs.

    evaluated_at is an aware datetime. The receipt binding is {path, sha256},
    relative to root. Receipt computed_at is a conservative replay availability
    boundary, not proof of historical publication-time/PIT admission. source_refs
    retain both receipts, exact PDF pages, period columns and extracted row text.
    The accrual receipt links the second cash receipt and yields H1 observations.
    An official-report-acquisition-v1 annual receipt yields one FY observation.
    Unsupported layouts fail closed. FY minus H1 is left to the consumer.
    """
    if not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None:
        _fail("AWARE_EVALUATION_TIME_REQUIRED")
    root = Path(root).resolve()
    _, raw = _bound(root, receipt_binding)
    receipt = json.loads(raw, object_pairs_hook=_unique)
    if receipt.get("schema_version") == "official-report-acquisition-v1":
        return _read_annual(root, receipt_binding, receipt, evaluated_at)
    if (receipt.get("schema_version") != "parent-trade-accrual-countercheck-v1"
            or receipt.get("scope") != "actual_parent_standalone"
            or receipt.get("currency") != "CNY" or receipt.get("period_basis") != "H1"
            or receipt.get("action") != "no_order" or receipt.get("operating_wc_cash_cny") is not None):
        _fail("ACCRUAL_RECEIPT_CONTRACT_INVALID")
    _clock(receipt.get("computed_at"), evaluated_at)
    cash_binding = receipt["source_cash_countercheck"]
    _, raw = _bound(root, cash_binding)
    cash_receipt = json.loads(raw, object_pairs_hook=_unique)
    if (cash_receipt.get("schema_version") != "parent-trade-cash-intra-year-reconciliation-v1"
            or cash_receipt.get("scope") != SCOPE or cash_receipt.get("currency") != "CNY"
            or cash_receipt.get("symbol") != receipt.get("symbol")
            or cash_receipt.get("action") != "no_order"
            or cash_receipt.get("formal_eligibility") is not False
            or cash_receipt.get("operating_wc_cash_cny") is not None):
        _fail("CASH_RECEIPT_CONTRACT_INVALID")
    _clock(cash_receipt.get("computed_at"), evaluated_at)
    symbol = receipt["symbol"]
    years = sorted(receipt["observed"])
    if (not years or any(not re.fullmatch(r"[0-9]{4}", year) for year in years)
            or len(receipt["income_refs"]) != 2 * len(years)):
        _fail("RECEIPT_PERIODS_INVALID")
    refs = cash_receipt["original_bindings"]
    if len({ref["path"] for ref in refs}) != len(refs):
        _fail("DUPLICATE_ORIGINAL")
    originals = {}
    for ref in refs:
        path, _ = _bound(root, ref)
        originals[ref["path"]] = (ref, path)
    grouped = {}
    for ref in receipt["income_refs"]:
        if ref["path"] not in originals or ref["sha256"] != originals[ref["path"]][0]["sha256"]:
            _fail("INCOME_CASH_ORIGINAL_MISMATCH")
        grouped.setdefault(ref["path"], []).append(ref)
    if len(grouped) != len(years):
        _fail("INCOME_ORIGINAL_COUNT_INVALID")
    reports, issuer = {}, None
    for relative, income_refs in grouped.items():
        cash_ref, path = originals[relative]
        pages = extract_pages(path)
        _bound(root, cash_ref)  # Reject changes during extraction.
        if labelled_security_codes(pages[:8], symbol=symbol) != {symbol}:
            _fail("SECURITY_IDENTITY_CHANGED")
        if len(income_refs) != 2 or len({ref["physical_page"] for ref in income_refs}) != 1:
            _fail("INCOME_LOCATORS_INVALID")
        page = income_refs[0]["physical_page"]
        if type(page) is not int or not 1 <= page <= len(pages):
            _fail("PAGE_INVALID")
        match = re.fullmatch(r"(.+?)([0-9]{4})年半年度报告", _compact(pages[page - 1].splitlines()[0]))
        if not match or match[2] not in years or match[2] in reports:
            _fail("ORIGINAL_PERIOD_CHANGED")
        year = int(match[2])
        if datetime(year, 6, 30, tzinfo=evaluated_at.tzinfo) > evaluated_at:
            _fail("REPORT_PERIOD_IN_FUTURE")
        issuer, income_lines = _table(pages, page_number=page, title="母公司利润表", year=year, issuer=issuer)
        _, cash_lines = _table(pages, page_number=cash_ref["physical_page"], title="母公司现金流量表", year=year, issuer=issuer)
        if not any(_compact(line) == issuer for line in pages[0].splitlines()):
            _fail("COVER_ISSUER_CHANGED")
        pairs, locators = {}, []
        for field in LABELS:
            is_income = field in {"revenue", "cost"}
            pair, text = _amounts(income_lines if is_income else cash_lines, field)
            pairs[field] = pair
            if is_income and sum(_compact(ref["excerpt"]) == _compact(text) for ref in income_refs) != 1:
                _fail("INCOME_EXCERPT_CHANGED")
            locators.append(dict(path=relative, sha256=cash_ref["sha256"],
                                 physical_page=page if is_income else cash_ref["physical_page"],
                                 field=field, text=text, column="current", period_end=f"{year}-06-30"))
        for column in (0, 1):
            if pairs["inflow"][column] - pairs["outflow"][column] != pairs["cfo"][column]:
                _fail("CFO_SUBTOTAL_MISMATCH")
        observed = receipt["observed"][str(year)]
        cash_observed = cash_receipt["period_amounts"][f"{year}H1"]
        for field, key in (("revenue", "revenue"), ("cost", "cost"), ("customer_cash", "received"), ("supplier_cash", "paid")):
            if Decimal(observed[key]) != pairs[field][0]:
                _fail("ACCRUAL_AMOUNT_CHANGED:" + field)
        for field, key in (("customer_cash", "customer_cash"), ("supplier_cash", "supplier_cash"), ("cfo", "net_operating_cash")):
            if Decimal(cash_observed[key]) != pairs[field][0]:
                _fail("CASH_AMOUNT_CHANGED:" + field)
        trade = pairs["customer_cash"][0] - pairs["supplier_cash"][0]
        if (Decimal(cash_observed["net_trade_cash"]) != trade
                or Decimal(cash_observed["other_operating_cash"]) != pairs["cfo"][0] - trade):
            _fail("CASH_RECONCILIATION_CHANGED")
        reports[str(year)] = (pairs, locators)
    rows = []
    for year in years:
        pairs, locators = reports[year]
        prior = reports.get(str(int(year) - 1))
        if prior and any(pair[1] != prior[0][field][0] for field, pair in pairs.items()):
            _fail("COMPARATIVE_RESTATEMENT_REQUIRES_REVIEW")
        rows.append(dict(symbol=symbol, scope=SCOPE, currency="CNY", classification="FACT",
                         period_start=f"{year}-01-01", period_end=f"{year}-06-30",
                         **{field: str(pairs[field][0]) for field in LABELS if field not in {"inflow", "outflow"}},
                         source_refs={"receipt": dict(receipt_binding), "cash_receipt": dict(cash_binding),
                                      "originals": locators}))
    return dict(schema_version=VERSION, observed=rows, evaluated_at=evaluated_at.isoformat(),
                action="no_order", formal_eligibility=False,
                limitation="Historical parent H1 observations only; no forecast or PIT admission.")


def _read_annual(root, receipt_binding, receipt, evaluated_at):
    """Replay one retained annual acquisition; never search for additional sources."""
    source = receipt.get("source", {})
    period = source.get("period", "")
    if (receipt.get("report_kind") != "annual"
            or receipt.get("status") != "ORIGINAL_ACQUIRED_NOT_FACT_ADMITTED"
            or not re.fullmatch(r"[0-9]{4}-12-31", period)):
        _fail("ANNUAL_RECEIPT_CONTRACT_INVALID")
    available = _clock(source.get("available_at"), evaluated_at)
    fetched = _clock(receipt.get("fetched_at"), evaluated_at)
    year = int(period[:4])
    if datetime(year, 12, 31, tzinfo=evaluated_at.tzinfo) > min(available, fetched):
        _fail("ANNUAL_REPORT_PERIOD_IN_FUTURE")
    path, _ = _bound(root, source)
    pages = extract_pages(path)
    _bound(root, source)
    symbol = source.get("symbol")
    if labelled_security_codes(pages[:8], symbol=symbol) != {symbol}:
        _fail("SECURITY_IDENTITY_CHANGED")
    tables, issuer = {}, None
    for title in ("母公司利润表", "母公司现金流量表"):
        hits = [i + 1 for i, page in enumerate(pages) if title in {line.strip() for line in page.splitlines()}]
        if len(hits) != 1:
            _fail("PARENT_TABLE_NOT_UNIQUE")
        issuer, lines = _table(pages, page_number=hits[0], title=title, year=year,
                               issuer=issuer, annual=True)
        tables[title] = (hits[0], lines)
    if not any(_compact(line) == issuer for line in pages[0].splitlines()):
        _fail("COVER_ISSUER_CHANGED")
    pairs, refs = {}, []
    for field in LABELS:
        page, lines = tables["母公司利润表" if field in {"revenue", "cost"} else "母公司现金流量表"]
        pairs[field], text = _amounts(lines, field)
        refs.append(dict(path=source["path"], sha256=source["sha256"], physical_page=page,
                         field=field, text=text, column="current", period_end=period,
                         available_at=source["available_at"]))
    for column in (0, 1):
        if pairs["inflow"][column] - pairs["outflow"][column] != pairs["cfo"][column]:
            _fail("CFO_SUBTOTAL_MISMATCH")
    row = dict(symbol=symbol, scope=SCOPE, currency="CNY", classification="FACT", period_start=f"{year}-01-01",
               period_end=period,
               **{field: str(pairs[field][0]) for field in LABELS if field not in {"inflow", "outflow"}},
               source_refs={"receipt": dict(receipt_binding), "originals": refs})
    return dict(schema_version=VERSION, observed=[row], evaluated_at=evaluated_at.isoformat(),
                action="no_order", formal_eligibility=False,
                limitation="Historical parent FY observation only; no forecast or PIT admission.")

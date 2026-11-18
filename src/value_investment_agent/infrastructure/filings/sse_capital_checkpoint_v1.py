"""Narrow SSE capital observations from caller-verified original PDF pages.

This parser does not verify PDF bytes, URL, acquisition time or event coverage.
A distribution proposal is a dated share observation, never implementation.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata


VERSION = "sse-capital-checkpoint-v1"
NUMBER = r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
MONEY = r"((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]+)"


def _compact(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _one(text, pattern, label):
    found = list(re.finditer(pattern, text))
    if len(found) != 1:
        raise ValueError("SSE_CHECKPOINT_FIELD_MISSING_OR_AMBIGUOUS: " + label)
    return found[0]


def _date(year, month, day):
    return date(int(year), int(month), int(day))


def _shares(value, *, allow_zero=False):
    number = Decimal(value.replace(",", ""))
    if (number < 0 if allow_zero else number <= 0) or number != number.to_integral_value():
        raise ValueError("SSE_CHECKPOINT_SHARE_QUANTITY_INVALID")
    return number


def _excerpt(raw, matched):
    from .native_capital_observation_v1 import _raw_excerpt
    return _raw_excerpt(raw, matched)


def parse_sse_capital_checkpoint(pages, *, symbol, published_date):
    """Parse one supported full H1/Q3 report or interim proposal selection."""
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("SSE_CHECKPOINT_SYMBOL_REQUIRED")
    if isinstance(published_date, date) and type(published_date) is date:
        published = published_date
    elif isinstance(published_date, str):
        published = date.fromisoformat(published_date)
        if published.isoformat() != published_date:
            raise ValueError("SSE_CHECKPOINT_PUBLISHED_DATE_REQUIRED")
    else:
        raise ValueError("SSE_CHECKPOINT_PUBLISHED_DATE_REQUIRED")
    if isinstance(pages, (list, tuple)):
        raw = dict(enumerate(pages, 1))
    elif isinstance(pages, dict):
        raw = {}
        for key, value in pages.items():
            if (type(key) is int and key > 0) or (isinstance(key, str) and
                    re.fullmatch(r"[1-9][0-9]*", key)):
                page = int(key)
            else:
                raise ValueError("SSE_CHECKPOINT_PHYSICAL_PAGE_REQUIRED")
            if page in raw:
                raise ValueError("SSE_CHECKPOINT_DUPLICATE_PAGE")
            raw[page] = value
    else:
        raise ValueError("SSE_CHECKPOINT_PAGES_REQUIRED")
    if (not 1 <= len(raw) <= 300 or 1 not in raw or max(raw) > 500 or
            any(not isinstance(value, str) for value in raw.values()) or
            not any(value.strip() for value in raw.values()) or
            sum(map(len, raw.values())) > 2_000_000):
        raise ValueError("SSE_CHECKPOINT_BOUNDED_PAGES_REQUIRED")
    text = {page: _compact(value) for page, value in raw.items()}
    cover = text[1]
    if "摘要" in cover:
        raise ValueError("SSE_CHECKPOINT_FULL_ORIGINAL_REQUIRED")

    def evidence(field, page, matched):
        return dict(field=field, physical_page=page, excerpt=_excerpt(raw[page], matched))

    if any(re.fullmatch(r"20\d{2}年第三季度报告", _compact(line))
           for line in raw[1].splitlines()):
        code = _one(cover, r"证券代码:" + symbol + r"证券简称:", "quarter code")
        company_lines = [_compact(line) for line in raw[1].splitlines()
                         if re.fullmatch(r"[\u4e00-\u9fff]+股份有限公司", _compact(line))]
        if len(company_lines) != 1:
            raise ValueError("SSE_CHECKPOINT_FIELD_MISSING_OR_AMBIGUOUS: quarter company")
        company = company_lines[0]
        title = _one(cover, r"(20\d{2})年第三季度报告", "quarter title")
        year = int(title[1])
        end = date(year, 9, 30)
        if end > published:
            raise ValueError("SSE_CHECKPOINT_REPORT_AFTER_PUBLICATION")
        statements = []
        for page, body in text.items():
            if "合并资产负债表" not in body:
                continue
            issuer = _one(body, r"编制单位:" + re.escape(company),
                          "quarter statement issuer")
            unit = _one(body, r"单位:元币种:人民币(?:审计类型:未经审计)?",
                        "quarter statement CNY unit")
            period = _one(body, rf"项目{year}年9月30日{year - 1}年12月31日",
                          "quarter statement period")
            capital = _one(body, r"实收资本\(或股本\)" + MONEY + MONEY,
                           "quarter exact share capital")
            statements.append((page, issuer, unit, period, capital))
        if len(statements) != 1:
            raise ValueError("SSE_CHECKPOINT_Q3_CONSOLIDATED_STATEMENT_REQUIRED")
        capital_page, issuer, unit, period, capital = statements[0]
        current = _shares(capital[1])
        _shares(capital[2])
        # The balance-sheet line is a CNY paid-in-capital amount.  It must not
        # be promoted to an issued-share count unless a separate source proves
        # the applicable par value and share-class bridge.
        return dict(parser_version=VERSION, kind="Q3_REPORT_EXACT_SHARE_CAPITAL_CNY",
            symbol=symbol, period_start=date(year, 1, 1).isoformat(),
            period_end=end.isoformat(), issued_shares=None,
            share_capital_cny=format(current, "f"),
            share_scope="PAID_IN_CAPITAL_AMOUNT_NOT_SHARE_COUNT", ordinary_shares=None,
            exact_share_count=False, statement_scope="CONSOLIDATED_BALANCE_SHEET",
            source_currency="CNY", source_unit="CNY",
            exact_share_field="实收资本（或股本）",
            unchanged_report_period=False, treasury_shares=None, proposal_only=False,
            ordinary_share_type_continuity_proven=False,
            continuity_after_period_end=False,
            term_pages=dict(identity=[1], capital=[capital_page]),
            evidence_refs=[dict(field="identity", physical_page=1, excerpt=raw[1]),
                evidence("statement_issuer", capital_page, issuer[0]),
                evidence("currency_and_unit", capital_page, unit[0]),
                evidence("period_end", capital_page, period[0]),
                evidence("issued_shares", capital_page, capital[0])],
            published_date=published.isoformat(), action="no_order")

    if "半年度报告" in cover:
        code = _one(cover, r"公司代码:" + symbol + r"公司简称:", "report code")
        company = _one(cover, r"([\u4e00-\u9fff]+股份有限公司)", "report company")
        title = _one(cover, r"(20\d{2})年半年度报告", "report title")
        year = int(title[1])
        start, end = date(year, 1, 1), date(year, 6, 30)
        if end > published:
            raise ValueError("SSE_CHECKPOINT_REPORT_AFTER_PUBLICATION")
        stock_rows = [(page, m) for page, body in text.items() for m in re.finditer(
            r"A股上海证券交易所[\u4e00-\u9fff]+" + symbol + r"(?:/|无)", body)]
        if len(stock_rows) != 1 or "公司股票简况" not in text[stock_rows[0][0]]:
            raise ValueError("SSE_CHECKPOINT_SSE_STOCK_ROW_REQUIRED")
        # A complete report repeats the chapter title in its contents page.
        # Only the body page carries the share-movement and shareholder sections.
        chapters = [(page, body) for page, body in text.items()
            if "第六节股份变动及股东情况" in body
            and "一、股本变动情况" in body and "二、股东情况" in body]
        if len(chapters) != 1:
            raise ValueError("SSE_CHECKPOINT_SHARE_CHAPTER_REQUIRED")
        capital_page, chapter = chapters[0]
        section = _one(chapter, r"一、股本变动情况.*?二、股东情况", "share movement section")[0]
        unchanged = "报告期内,公司股份总数及股本结构未发生变化。"
        if (section.count(unchanged) != 1 or
                re.search(r"(?:股份总数|股本结构).{0,12}(?:发生变化|有所变化|已变化)",
                          section.replace(unchanged, ""))):
            raise ValueError("SSE_CHECKPOINT_REPORT_SHARE_CHANGE_OR_CONFLICT")
        return dict(parser_version=VERSION, kind="H1_REPORT_UNCHANGED", symbol=symbol,
            period_start=start.isoformat(), period_end=end.isoformat(), issued_shares=None,
            share_scope="TOTAL_ISSUED_SHARES", ordinary_shares=None,
            unchanged_report_period=True, treasury_shares=None, proposal_only=False,
            ordinary_share_type_continuity_proven=False,
            term_pages=dict(identity=[1], stock=[stock_rows[0][0]], unchanged=[capital_page]),
            evidence_refs=[evidence("identity", 1, code[0] + company[0] + title[0])
                if code.end() == company.start() and company.end() == title.start()
                else dict(field="identity", physical_page=1, excerpt=raw[1]),
                evidence("stock", stock_rows[0][0], stock_rows[0][1][0]),
                evidence("unchanged", capital_page, unchanged)],
            published_date=published.isoformat(), action="no_order")

    code = _one(cover, r"证券代码:" + symbol + r"证券简称:", "proposal code")
    lines = [line for line in raw[1].splitlines() if line.strip()]
    header = next((i for i, line in enumerate(lines) if "证券代码" in line), None)
    if header is None or header + 2 >= len(lines):
        raise ValueError("SSE_CHECKPOINT_PROPOSAL_HEADER_REQUIRED")
    company = _compact(lines[header + 1])
    if (not re.fullmatch(r"[\u4e00-\u9fff]+股份有限公司", company)
            or company not in cover[code.end():]
            or (2 in raw and company not in text[2])):
        raise ValueError("SSE_CHECKPOINT_PROPOSAL_ISSUER_CONFLICT")
    title = _one(cover, r"关于(20\d{2})年中期利润分配预案的公告", "proposal title")
    if int(title[1]) > published.year or "股权登记日" not in cover:
        raise ValueError("SSE_CHECKPOINT_PROPOSAL_IDENTITY_OR_STATUS_CONFLICT")
    statement = _one(cover, r"公司拟向全体股东每股派发现金红利" + MONEY +
        r"元\(含税\)[,，]截至(20\d{2})年(\d{1,2})月(\d{1,2})日[,，]公司总股本" + NUMBER +
        r"股[,，]扣除公司回购专户股份" + NUMBER +
        r"股[,，]以此计算合计拟派发现金红利总额为" + MONEY + r"元", "proposal share basis")
    observed = _date(statement[2], statement[3], statement[4])
    if observed > published or observed.year != int(title[1]):
        raise ValueError("SSE_CHECKPOINT_OBSERVATION_AFTER_PUBLICATION")
    total, treasury = _shares(statement[5]), _shares(statement[6], allow_zero=True)
    if treasury >= total:
        raise ValueError("SSE_CHECKPOINT_TREASURY_EXCEEDS_TOTAL")
    try:
        dps = Decimal(statement[1])
        gross = Decimal(statement[7].replace(",", ""))
    except InvalidOperation as error:
        raise ValueError("SSE_CHECKPOINT_PROPOSAL_AMOUNT_INVALID") from error
    if dps <= 0 or gross <= 0 or (total - treasury) * dps != gross:
        raise ValueError("SSE_CHECKPOINT_PROPOSAL_AMOUNT_MISMATCH")
    return dict(parser_version=VERSION, kind="INTERIM_PROPOSAL_DATED_SHARES", symbol=symbol,
        period_start=None, period_end=observed.isoformat(), issued_shares=str(total),
        share_scope="TOTAL_ISSUED_SHARES", ordinary_shares=None,
        unchanged_report_period=False, treasury_shares=str(treasury), proposal_only=True,
        ordinary_share_type_continuity_proven=False,
        term_pages=dict(identity=[1], share_basis=[1]),
        evidence_refs=[dict(field="identity", physical_page=1,
            excerpt=lines[header] + "\n" + lines[header + 1]),
            evidence("share_basis", 1, statement[0])],
        published_date=published.isoformat(), action="no_order")

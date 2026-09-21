"""Extract review-only financial-statement candidates from statutory PDFs."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path

ANNUAL_BACKFILL_PARSER_VERSION = 'filing-extract-v35-chinese-note-reference'

FIELDS = {
    "资产总计": "total_assets",
    "负债合计": "total_liabilities",
    "货币资金": "cash",
    "短期借款": "short_term_borrowings",
    "一年内到期的非流动负债": "current_portion_long_term_debt",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "租赁负债": "lease_liabilities_noncurrent",
    "长期应付款": "long_term_payables_noncurrent",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "购建固定资产、无形资产和其他长期资产所支付的现金": "capital_expenditure",
    "购建固定资产、无形资产和其他长期资产支付的现金": "capital_expenditure",
    "营业成本": "operating_cost",
    "归属于母公司股东的净利润": "net_income",
    "归属于母公司所有者的净利润": "net_income",
}
FIELD_STATEMENTS = {
    "total_assets": "balance",
    "total_liabilities": "balance",
    "cash": "balance",
    "short_term_borrowings": "balance",
    "current_portion_long_term_debt": "balance",
    "long_term_borrowings": "balance",
    "bonds_payable": "balance",
    "lease_liabilities_noncurrent": "balance",
    "long_term_payables_noncurrent": "balance",
    "operating_cash_flow": "cashflow",
    "capital_expenditure": "cashflow",
    "operating_cost": "income",
    "net_income": "income",
}

# This issuer-disclosed annual-report summary is useful for human review, but
# candidates from it remain unverified until a reviewer confirms the page.
SUMMARY_FIELDS = {
    "营业收入": ("revenue", "reported_amount"),
    "归属于上市公司股东的净利润": ("net_income", "reported_amount"),
    "归属于本行股东的净利润": ("net_income", "reported_amount"),
    "经营活动产生的现金流量净额": ("operating_cash_flow", "reported_amount"),
    "基本每股收益": ("eps_annual", "CNY/share"),
    "加权平均净资产收益率": ("roe", "percent"),
    "归属于上市公司普通股股东的每股净资产": ("bvps", "CNY/share"),
}
SUMMARY_AMOUNT_FIELDS = {"revenue", "net_income", "operating_cash_flow"}
SUMMARY_UNIT_MULTIPLIERS = {"元": 1, "千元": 1_000, "万元": 10_000, "百万元": 1_000_000, "亿元": 100_000_000}


def _number_after_label(text: str, label: str, *, bare_footnote: bool = True,
                        wrapped_label: bool = False, monetary: bool = False) -> tuple[str, str] | None:
    # The PDF text layer puts an optional footnote reference between a label
    # and its amount, e.g. "货币资金 1 53,518,798,979.08".
    footnote = (r'(?:\s+(?:\d{1,2}|[一二三四五六七八九十]+[（(][一二三四五六七八九十]+[）)]\d{1,3}'
                r'|[一二三四五六七八九十]+、\s*\d{1,3}(?:[（(]\d{1,3}[）)])?'
                r'|[（(](?:\s*[一二三四五六七八九十百])+\s*[）)]))?'
                if bare_footnote else r'(?:\s*[（(]\d{1,2}[）)])?')
    label_pattern = r'\s*'.join(re.escape(c) for c in label) if wrapped_label else re.escape(label)
    note_words = r'\s*'.join(map(re.escape, '净亏损以')) if wrapped_label else '净亏损以'
    note_end = r'\s*'.join(map(re.escape, '号填列')) if wrapped_label else '号填列'
    loss_note = (rf'(?:\s*[（(]\s*{note_words}\s*[“"][-—－][”"]\s*{note_end}\s*[）)])?'
                 if monetary and label == '归属于母公司股东的净利润' else '')
    match = re.search(
        rf"(?<![\u4e00-\u9fff]){label_pattern}{loss_note}{footnote}\s+(-?[\d,]+(?:\.\d+)?)",
        text,
    )
    if match is None:
        return None
    if monetary:
        # Require the same two-column wrap pattern before joining money digits.
        # A lone following number might instead be the previous-year value.
        value = match.group(1)
        tail = text[match.end():]
        if '.' not in value and tail.startswith('.'):
            spaced = re.match(r'\.\s+(\d{2})\s+-?[\d,]+\.\s+\d{2}(?=\s|$)', tail)
            if spaced is None:
                return None
            return (value + '.' + spaced.group(1)).replace(',', ''), text[
                max(0, match.start()-120):match.end()+spaced.end()+180]
        fraction = value.partition('.')[2]
        fragment = (r'(\d)' if '.' in value and len(fraction) == 1
                    else r'(\.\d{2})' if '.' not in value else None)
        if fragment and re.match(r'[ \t]*\r?\n[ \t]*' + fragment + r'[ \t]*(?:\r?\n|$)', tail):
            previous = (r'-?[\d,]+\.\d[ \t]*\r?\n[ \t]*\d'
                        if '.' in value else r'-?[\d,]+[ \t]*\r?\n[ \t]*\.\d{2}')
            continuation = re.match(r'[ \t]*\r?\n[ \t]*' + fragment
                                    + r'[ \t]*\r?\n[ \t]*' + previous + r'(?=\s|$)', tail)
            if continuation is None:
                return None
            return (value + continuation.group(1)).replace(',', ''), text[
                max(0, match.start()-120):match.end()+continuation.end()+180]
    return match.group(1).replace(",", ""), text[max(0, match.start() - 120):match.end() + 180]


def _cross_page_current_debt(page_text: str, next_page: str, next_page_number: int):
    """Recover the final label character only when the next page proves it."""
    prefix = '一年内到期的非流动负'
    lines = [line.strip() for line in next_page.splitlines() if line.strip()]
    while lines and (re.fullmatch(r'\d+\s*/\s*\d+', lines[0])
                     or re.search(r'20\d{2}\s*年\s*年度报告(?:全文)?$', lines[0])):
        lines.pop(0)
    if not lines or lines[0] != '债':
        return None
    match = re.search(r'(?m)^[ \t]*' + re.escape(prefix)
                      + r'([ \t]+[^\r\n]+)[\r\n\s]*\Z', page_text)
    if match is None:
        return None
    result = _number_after_label(prefix + '债' + match[1], prefix + '债', monetary=True)
    if result is None:
        return None
    value, _ = result
    excerpt = page_text[max(0, match.start() - 120):].rstrip()
    excerpt += f'\n标签续页依据（PDF第{next_page_number}页首个正文行）：债'
    return value, excerpt


def _disclosed_amount_unit(page_text: str) -> tuple[str, int] | None:
    """Read an issuer-disclosed table unit; absence remains deliberately unknown."""
    units = re.findall(r"单位\s*[：:]\s*(?:人民币)?\s*(亿元|百万元|万元|千元|元)", page_text)
    units.extend(re.findall(r'^[ \t]*人民币[ \t]*(亿元|百万元|万元|千元|元)[ \t\r]*$',
                            page_text, re.MULTILINE))
    # Some statutory reports declare the amount scale without the word 'unit'.
    units.extend(re.findall(r"[（(]\s*人民币\s*(亿元|百万元|万元|千元|元)\s*[，,]\s*特别注明除外\s*[）)]", page_text))
    if len(set(units)) != 1:
        return None
    return "CNY", SUMMARY_UNIT_MULTIPLIERS[units[0]]


def _scaled_amount(value: str, multiplier: int) -> str:
    return str(Decimal(value) * Decimal(multiplier))


def extract_annual_growth(page_text: str, page_index: int) -> list[dict]:
    """Parse explicit annual growth columns; ambiguous/restated layouts stay pending elsewhere."""
    if any(label in page_text for label in ('调整前', '调整后', '重述后')):
        return []
    header = re.search(r'(20\d{2})\s*年\s*(20\d{2})\s*年\s*本年比上年\s*增减', page_text)
    if not header or int(header[1]) != int(header[2]) + 1:
        return []
    number = r'(-?\d[\d,]*(?:\.\d+)?)'
    result = []
    for label, field in [('营业收入', 'revenue_yoy'), ('归属于上市公司股东的净利润', 'net_income_yoy')]:
        # PDF text often wraps a complete row label within the same page.
        label_pattern = r'\s*'.join(re.escape(character) for character in label)
        row = re.search(r'^\s*' + label_pattern + r'\s*(?:[（(](?:千元|百万元|万元|亿元|元)[）)])?\s+'
                        + number + r'\s+' + number + r'\s+' + number + r'%', page_text, re.MULTILINE)
        if not row:
            continue
        current, previous, growth = (Decimal(v.replace(',', '')) for v in row.groups())
        if previous <= 0 or abs((current / previous - 1) * 100 - growth) > Decimal('0.05'):
            continue
        result.append({'field_name':field, 'source_label':label + '同比增长率',
                       'value':str(growth), 'unit':'percent', 'page':page_index,
                       'excerpt':header.group(0) + '\n' + row.group(0),
                       'status':'candidate_pending_automated_verification'})
    return result


def _page_sections(pages: list[str]):
    # A new statement can start halfway down a page. Preserve the preceding
    # statement's scope/unit until that exact heading, and retain PDF page IDs.
    heading = re.compile(r'^[ \t]*(?:[0-9一二三四五六七八九十]+[、.．][ \t]*)?(?:合并(?:及银行)?|母公司|公司)?(?:资产负债表|现金流量表|利润表)[ \t\r]*$', re.MULTILINE)
    for page_index, page in enumerate(pages, start=1):
        matches = list(heading.finditer(page))
        if len(matches) == 1:
            title = matches[0]
            before, after = page[:title.start()], page[title.end():]
            if (title.start() > len(page) * 0.75
                    and '资产负债表' in title.group()
                    and re.search(r'期末数\s+期初数', before)
                    and _disclosed_amount_unit(before) is not None
                    and re.fullmatch(r'\s*法定代表人[^\r\n]*\s*', after)):
                # Some PDF text streams place the table title after its rows.
                page = title.group() + '\n' + before + after
        boundaries = sorted({0, len(page), *(m.start() for m in heading.finditer(page))})
        for start, end in zip(boundaries, boundaries[1:]):
            yield page_index, page[start:end]


def _ambiguous_statement_columns(text: str) -> bool:
    title = re.search(r'(?m)^[ \t]*(?:[0-9一二三四五六七八九十]+[、.．][ \t]*)?合并(?:及银行)?(?:资产负债表|利润表|现金流量表)[ \t\r]*$', text)
    continuation = re.search(r'(?m)^[ \t]*项目\s+(?:附注\s+)?20\d{2}\s*年', text)
    if title is None and continuation is None:
        return False
    header = re.split(r'流动资产|非流动资产|营业收入|资产总计|经营活动产生的现金流量',
                      text[title.end() if title else continuation.start():], maxsplit=1)[0]
    if '调整数' in header:
        return True
    years = [int(year) for year in re.findall(r'(20\d{2})\s*年', header)]
    # Statement-date repetition is harmless; ascending or multi-year columns
    # cannot be interpreted as the standard current/prior two-column layout.
    ordered = [year for index, year in enumerate(years) if not index or year != years[index - 1]]
    return len(set(ordered)) > 2 or any(a < b for a, b in zip(ordered, ordered[1:]))


def extract_candidates_from_pages(pages: list[str]) -> list[dict]:
    """Return candidates for automated cross-source verification, never trusted facts."""
    from value_investment_agent.combined_balance import extract_combined_totals
    candidates: list[dict] = extract_combined_totals(pages)
    for index in range(1, len(pages)):
        previous = pages[index - 1]
        if '主要会计数据和财务指标' not in previous:
            continue
        tail = previous.rsplit('主要会计数据和财务指标', 1)[1]
        header = re.search(r'(20\d{2})\s*年\s+(20\d{2})\s*年', tail)
        if (not header or int(header[1]) != int(header[2]) + 1
                or any(word in tail for word in ('季度', '母公司', '预测'))
                or re.search(r'(?m)^\s*[一二三四五六七八九十]+、', tail)):
            continue
        lines = [line.strip() for line in pages[index].splitlines() if line.strip()]
        while lines and (re.fullmatch(r'(?:\d+(?:\s*/\s*\d+)?|-\s*\d+\s*-)', lines[0])
                         or re.search(r'20\d{2}\s*年\s*年度报告\s*$', lines[0])):
            lines.pop(0)
        if not lines:
            continue
        starts_eps = bool(re.match(r'^基本每股收益[（(]元[/／]股[）)]', lines[0]))
        starts_roe = lines[0].startswith('加权平均净资产收益率')
        starts_deducted_eps = lines[0].startswith('扣除非经常性损益后的基本每')
        if not (starts_eps or starts_roe or starts_deducted_eps):
            continue
        body = re.split(r'20\d{2}\s*年末|截止|(?m:^[一二三四五六七八九十]+、)',
                        '\n'.join(lines), maxsplit=1)[0]
        if any(word in body for word in ('季度', '母公司', '预测')):
            continue
        context = '主要财务指标 ' + header.group() + '\n'
        for row in extract_candidates_from_pages([context + body]):
            if row['field_name'] in ({'eps_annual', 'roe'} if starts_eps else {'roe'}):
                candidates.append({**row, 'page': index + 1, 'header_page': index,
                                   'header_excerpt': header.group(),
                                   'excerpt': body,
                                   'extraction_method': 'adjacent_annual_summary_continuation'})
    statement: str | None = None
    statement_amount_unit: tuple[str, int] | None = None
    report_unit = None
    report_unit_page = None
    report_unit_excerpt = None
    statement_unit_page = None
    for page_index, page_text in _page_sections(pages):
        declaration = re.search(r'财务附注中报表的单位为\s*[：:]\s*(亿元|百万元|万元|千元|元)', page_text)
        if (declaration and '财务报告' in page_text
                and re.search(r'二\s*、\s*财务报表', page_text)):
            report_unit = ('CNY', SUMMARY_UNIT_MULTIPLIERS[declaration[1]])
            report_unit_page = page_index
            report_unit_excerpt = declaration[0]
        summary_text = re.split(r'(?m)^[^\r\n]*(?:分季度主要财务数据|第一季度)[^\r\n]*',
                                page_text, maxsplit=1)[0]
        standard_summary = "主要会计数据和财务指标" in summary_text
        section_summary = re.search(r'^\s*第[一二三四五六七八九十]+节\s+会计数据和财务指标\s*$',
                                    summary_text, re.MULTILINE)
        quarterly_only = ('季度' in summary_text and not re.search(r'20\d{2}\s*年\s+20\d{2}\s*年', summary_text))
        indicator_header = re.search(
            r'^\s*(?:[（(][一二三四五六七八九十0-9]+[）)]\s*)?主要财务指标\s+(20\d{2})\s*年\s+(20\d{2})\s*年',
            summary_text, re.MULTILINE)
        standalone_indicators = bool(indicator_header
            and int(indicator_header[1]) == int(indicator_header[2]) + 1
            and not any(word in summary_text for word in ('季度', '预测', '母公司')))
        if (standard_summary or section_summary or standalone_indicators) and not quarterly_only:
            annual_header = re.search(r'(20\d{2})\s*年\s+(20\d{2})\s*年', summary_text)
            wrapped_summary = bool(annual_header and int(annual_header[1]) == int(annual_header[2]) + 1)
            interim_wrapped = bool(re.search(
                r'本报告期\s+上年同期\s+本报告期比上年同期增减', summary_text))
            interim_ambiguous = interim_wrapped and any(
                token in summary_text for token in ('调整前', '调整后', '重述后', '预测', '母公司'))
            wrapped_summary = wrapped_summary or (interim_wrapped and not interim_ambiguous)
            # The additional layout has not been qualified for restated growth.
            if standard_summary:
                candidates.extend(extract_annual_growth(summary_text, page_index))
            for label, (field_name, unit) in SUMMARY_FIELDS.items():
                if interim_ambiguous:
                    continue
                if standalone_indicators and not (standard_summary or section_summary) and field_name not in {'eps_annual', 'roe'}:
                    continue
                # Annualized interim returns are not the unannualized ROE fact.
                # Mixed summary tables need an explicit row-level basis parser.
                if field_name == 'roe' and '\u5e74\u5316' in summary_text:
                    continue
                # Summary tables have no separate note column. A bare integer
                # is the current value, not permission to skip to last year.
                result = _number_after_label(summary_text, label, bare_footnote=False,
                                             wrapped_label=wrapped_summary,
                                             monetary=field_name in SUMMARY_AMOUNT_FIELDS)
                inline_scale = None
                if result is None:
                    inline_label = r'\s*'.join(map(re.escape, label)) if wrapped_summary else re.escape(label)
                    inline = re.search(inline_label + r'\s*[（(](千元|百万元|万元|亿元|元[/／]股|元|%)[）)]', summary_text)
                    if inline:
                        declared = inline.group(1).replace('\uff0f', '/')
                        compatible = ((field_name in SUMMARY_AMOUNT_FIELDS and declared in SUMMARY_UNIT_MULTIPLIERS)
                                      or (unit == 'CNY/share' and declared == '元/股')
                                      or (unit == 'percent' and declared == '%'))
                        if compatible:
                            result = _number_after_label(summary_text, inline.group(0), bare_footnote=False,
                                                         monetary=field_name in SUMMARY_AMOUNT_FIELDS)
                            if field_name in SUMMARY_AMOUNT_FIELDS:
                                inline_scale = ('CNY', SUMMARY_UNIT_MULTIPLIERS[declared])
                if result is None:
                    continue
                value, excerpt = result
                if field_name in SUMMARY_AMOUNT_FIELDS:
                    amount_unit = inline_scale or _disclosed_amount_unit(summary_text)
                    if amount_unit is not None:
                        unit, multiplier = amount_unit
                        value = _scaled_amount(value, multiplier)
                candidates.append({
                    "field_name": field_name, "source_label": label,
                    "value": value, "unit": unit, "page": page_index,
                    "excerpt": excerpt, "status": "candidate_pending_automated_verification",
                })
        titles = {title.replace('合并及银行', '合并') for title in re.findall(r'^[ \t]*(?:[0-9一二三四五六七八九十]+[、.．][ \t]*)?((?:合并(?:及银行)?|母公司|公司)?(?:资产负债表|现金流量表|利润表))[ \t\r]*$', page_text, re.MULTILINE)}
        if titles.intersection(("母公司资产负债表", "母公司现金流量表", "母公司利润表",
                                "公司资产负债表", "公司现金流量表", "公司利润表")) or (
                titles.intersection(('资产负债表', '现金流量表', '利润表')) and '本集团' not in page_text):
            statement = None
            statement_amount_unit = None
        elif "合并资产负债表" in titles or ("资产负债表" in titles and "本集团" in page_text):
            statement = "balance"
            statement_amount_unit = _disclosed_amount_unit(page_text)
        elif "合并现金流量表" in titles or ("现金流量表" in titles and "本集团" in page_text):
            statement = "cashflow"
            statement_amount_unit = _disclosed_amount_unit(page_text)
        elif "合并利润表" in titles or ("利润表" in titles and "本集团" in page_text):
            statement = "income"
            statement_amount_unit = _disclosed_amount_unit(page_text)
        if titles:
            statement_unit_page = None
            if (statement is not None and statement_amount_unit is None and report_unit
                    and not re.search(r'单位\s*[：:]|人民币\s*(?:亿元|百万元|万元|千元|元)', page_text)):
                statement_amount_unit = report_unit
                statement_unit_page = report_unit_page
        if _ambiguous_statement_columns(page_text):
            statement = None
            statement_amount_unit = None
        if statement is None:
            continue
        # Statement-line amounts have no safe default.  A declaration such as
        # "单位：万元" must be retained before they can be compared to the
        # structured secondary source; an unspecified amount stays out of the
        # unattended evidence path.
        if statement_amount_unit is None:
            continue
        for label, field_name in FIELDS.items():
            if FIELD_STATEMENTS[field_name] != statement:
                continue
            result = _number_after_label(page_text, label, monetary=True,
                                         wrapped_label=field_name in ('operating_cash_flow', 'net_income', 'capital_expenditure'))
            if result is None and field_name == 'current_portion_long_term_debt' and page_index < len(pages):
                result = _cross_page_current_debt(page_text, pages[page_index], page_index + 1)
            if result is None:
                continue
            value, excerpt = result
            unit, multiplier = statement_amount_unit
            candidates.append(
                {
                    "field_name": field_name,
                    "source_label": label,
                    "value": _scaled_amount(value, multiplier),
                    "unit": unit,
                    "page": page_index,
                    "excerpt": excerpt,
                    "status": "candidate_pending_automated_verification",
                    **({'unit_evidence_page': statement_unit_page,
                        'unit_evidence_excerpt': report_unit_excerpt} if statement_unit_page else {}),
                }
            )
        # A balance sheet ends at its liabilities-and-equity total. Do not
        # carry this scope into later tax, cash-payment or maturity notes.
        if statement == 'balance' and re.search(
            r'\u8d1f\u503a(?:\u548c|\u53ca|\u4e0e)(?:\u6240\u6709\u8005\u6743\u76ca|\u80a1\u4e1c\u6743\u76ca)'
            r'\s*(?:\uff08[^\uff09]*\uff09|\([^)]*\))?\s*(?:\u603b\u8ba1|\u5408\u8ba1)',
            page_text,
        ):
            statement = None
            statement_amount_unit = None
    return candidates


def extract_candidates(pdf_path: Path) -> dict:
    """Read a statutory PDF and produce a JSON-serializable review packet."""
    from .pdf_text import extract_pages

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF was not found: {pdf_path}")
    with pdf_path.open('rb') as handle:
        sha256 = hashlib.file_digest(handle, 'sha256').hexdigest()
    pages = extract_pages(pdf_path)
    return {
        "evidence_file": str(pdf_path),
        "sha256": sha256,
        "parser_version": ANNUAL_BACKFILL_PARSER_VERSION,
        "page_count": len(pages),
        "candidates": extract_candidates_from_pages(pages),
        "warning": "Candidates require automatic cross-source verification before they enter verified facts.",
    }

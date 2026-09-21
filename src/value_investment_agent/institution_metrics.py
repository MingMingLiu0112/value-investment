"""Extract explicitly dated percentage tables from official institution reports.

These are visible evidence candidates, NOT cross-source-verified facts. Neither
repeated pages in one PDF nor a hash match counts as an independent source.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import chain
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import logging
from pathlib import Path
import re
import unicodedata

FIELDS = {
    'bank': {'不良贷款率': 'npl_ratio', '拨备覆盖率': 'provision_coverage',
             '核心一级资本充足率': 'cet1_ratio', '净息差': 'net_interest_margin'},
    'broker': {'风险覆盖率': 'risk_coverage', '资本杠杆率': 'capital_leverage',
               '流动性覆盖率': 'liquidity_coverage', '净稳定资金率': 'net_stable_funding'},
    'insurer': {'核心偿付能力充足率': 'core_solvency', '综合偿付能力充足率': 'comprehensive_solvency'},
}
VERSION = 'institution-table-v14-broker-label-units'
LABEL_ALIASES = {'净息差': ('净息差','净利息收益率')}


def _bank_group_prose(text: str, page_index: int, engine: str) -> list[dict]:
    """Accept only explicit period/group assertions, never forecast fragments."""
    compact = re.sub(r'\s+', '', text)
    rows = []
    for label, field, basis, period_word in (
        ('净息差', 'net_interest_margin', 'YTD', '报告期'),
        ('核心一级资本充足率', 'cet1_ratio', 'period_end', '报告期末'),
    ):
        pattern = (rf'(?:^|[。；])(?P<claim>{period_word}[，,](?:本)?集团{label}'
                   rf'(?:为)?(?P<value>\d+(?:\.\d+)?)%[，,。；])')
        for match in re.finditer(pattern, compact):
            value = Decimal(match['value'])
            if value > 100:
                continue
            rows.append({'field_name': field, 'value': str(value), 'unit': 'percent',
                         'page_number': page_index, 'source_label': label,
                         'excerpt': match['claim'], 'statement_scope': '集团（原文明确）',
                         'scope_evidence': match['claim'], 'capital_method': None,
                         'text_engine': engine, 'period_basis': basis})
    for match in re.finditer(
            r'(?:^|。)(?P<claim>报告期末[，,]本集团不良贷款余额[^。]{1,350}。)', compact):
        claim = match['claim']
        if re.search(r'子公司|母公司|本行|预计|预测|目标|上年不良|上年拨备', claim):
            continue
        for label, field, ceiling in (('不良贷款率', 'npl_ratio', 100),
                                      ('拨备覆盖率', 'provision_coverage', 2000)):
            values = re.findall(rf'[；;]{label}(?:为)?(\d+(?:\.\d+)?)%[，,；;。]', claim)
            if len(values) != 1 or Decimal(values[0]) > ceiling:
                continue
            rows.append({'field_name': field, 'value': values[0], 'unit': 'percent',
                         'page_number': page_index, 'source_label': label, 'excerpt': claim,
                         'statement_scope': '集团（原文明确）', 'scope_evidence': claim,
                         'capital_method': None, 'text_engine': engine, 'period_basis': 'period_end'})
    for match in re.finditer(
            r'报告期末[，,]本集团(?:不良贷款余额|核心一级资本净额)[^。]{1,500}。', compact):
        claim = match.group()
        prefix = re.split(r'[。；]', compact[:match.start()])[-1]
        if (re.search(r'预计|预测|目标|假设|若|倘|上年|去年', prefix)
                or re.search(r'子公司|母公司|本行|预计|预测|目标|非并表', claim)):
            continue
        for label, field, ceiling in (
            ('不良贷款率', 'npl_ratio', 100),
            ('拨备覆盖率', 'provision_coverage', 2000),
            ('核心一级资本充足率', 'cet1_ratio', 100),
        ):
            values = re.findall(rf'[；;]{label}(?:为)?(\d+(?:\.\d+)?)%[，,；;。]', claim)
            if len(values) != 1 or Decimal(values[0]) > ceiling:
                continue
            rows.append({'field_name': field, 'value': values[0], 'unit': 'percent',
                         'page_number': page_index, 'source_label': label, 'excerpt': claim,
                         'statement_scope': '集团（原文明确）', 'scope_evidence': claim,
                         'capital_method': None, 'text_engine': engine,
                         'period_basis': 'period_end'})
    return rows


def _long_profitability_context(lines: list[str], index: int) -> list[str] | None:
    """Recognize a bounded, single-page bank summary table, not distant prose."""
    if index > 80 or not re.match(r'^\s*(?:净息差|净利息收益率)', lines[index]):
        return None
    text = '\n'.join(lines[:index + 1])
    header = re.search(
        r'20\d{2}\s*年\s*1\s*[-至]\s*\d{1,2}\s*月\s*'
        r'20\d{2}\s*年\s*1\s*[-至]\s*\d{1,2}\s*月\s*'
        r'本报告期比\s*上年同期\s*'
        r'20\d{2}\s*年\s*1\s*[-至]\s*\d{1,2}\s*月\s*'
        r'经营业绩\(人民币百万元\)[^\n]*', text)
    if not header:
        return None
    body = text[header.end():]
    if (re.search(r'20\d{2}|本报告期|监管|母公司|本行口径|^\s*[一二三四五六七八九十]+[、.]', body, re.M)
            or '盈利能力指标(%)' not in body):
        return None
    return text[header.start():].splitlines()


def parse_tables(pages: list[str], model: str, period: str, *, fallback_pages: list[str] | None = None) -> list[dict]:
    year, month, day = period.split('-')
    date_pattern = rf'{year}\s*[年./-]\s*0?{int(month)}\s*[月./-]\s*0?{int(day)}\s*日?'
    matches = defaultdict(list)
    decoded = chain(((i, text, 'PDFium') for i, text in enumerate(pages, 1)),
                    ((i, text, 'pypdf') for i, text in enumerate(fallback_pages or [], 1)))
    previous_pages = {}
    for page_index, text, engine in decoded:
        text = unicodedata.normalize('NFKC', text)
        previous = previous_pages.get(engine, '')
        previous_pages[engine] = text
        if model == 'broker':
            for fact in _continued_broker_risks(previous, text, page_index, engine):
                matches[fact['field_name']].append(fact)
            for fact in _continued_broker_label_units(previous, text, page_index, engine):
                matches[fact['field_name']].append(fact)
        if model == 'bank':
            for fact in _regulatory_bank_rows(previous, text, period, page_index, engine):
                matches[fact['field_name']].append(fact)
            continuation = _continued_bank_margin(previous, text, period, page_index, engine)
            if continuation:
                matches['net_interest_margin'].append(continuation)
            for fact in _bank_group_prose(text, page_index, engine):
                matches[fact['field_name']].append(fact)
        lines = [re.sub(r'(?<=[\u4e00-\u9fff])[^\S\n]+(?=[\u4e00-\u9fff])', '', line)
                 for line in text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            preceding = lines[max(0,i-35):i+1]
            if model == 'bank':
                extended = _long_profitability_context(lines, i)
                if extended is not None:
                    preceding = extended
            scope_headers = [heading for heading in preceding
                             if re.search(r'母公司的?净资本及(?:有关)?风险控制指标\s*$', heading)]
            scope_header = scope_headers[-1] if scope_headers and model == 'broker' else None
            unit_lines = [line_before for line_before in preceding if re.search(
                r'(?:单位\s*:|财务比率|资产质量指标|资本充足率指标|盈利能力指标\s*\(\s*%|主要指标)',line_before)]
            unit_context = unit_lines[-1] if unit_lines else ''
            # Chinese PDF text frequently collapses the space between column
            # headings. Anchor to the last header, not unrelated earlier prose.
            header_indices = [j for j,line_before in enumerate(preceding)
                if re.search(r'本报告期(?:末)?\s*上年|本报告期末\s*本报告期初', line_before) or
                (re.search(r'(?:指标|比率)\s*\(\s*%\s*\)', line_before)
                 and j + 1 < len(preceding)
                 and re.fullmatch(r'\s*20\d{2}\s*年\s*', preceding[j + 1])) or
                len(re.findall(r'20\d{2}\s*年\s*1\s*[-至]\s*\d{1,2}\s*月', line_before)) >= 2 or
                len(re.findall(r'20\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}', line_before)) >= 2]
            if header_indices:
                preceding = preceding[header_indices[-1]:]
            context = '\n'.join(preceding)
            # A dated current-period-first header is mandatory. Regulatory and
            # historical-first tables need a separate parser, not guessed columns.
            dates = re.findall(r'20\d{2}\s*[年./-]\s*\d{1,2}\s*[月./-]\s*\d{1,2}\s*日?', context)
            current_first = bool(dates and re.fullmatch(date_pattern, dates[0]))
            generic_first = bool(re.search(r'本报告期(?:末)?\s*上年|本报告期末\s*本报告期初', context))
            durations = re.findall(r'(20\d{2})\s*年\s*1\s*[-至]\s*(\d{1,2})\s*月',context)
            current_duration = bool(durations and durations[0] == (year,str(int(month))))
            regulatory = any(token in context for token in ['监管标准','监管指标值','监管要求值','标准值'])
            regulatory_header = re.search(r'监管标准|监管指标值|监管要求值|标准值', context)
            current_header = re.search(r'本报告期(?:末)?\s*上年|本报告期末\s*本报告期初|' + date_pattern, context)
            trailing_threshold = bool(regulatory_header and current_header
                                      and current_header.start() < regulatory_header.start()
                                      and re.search(r'[<>≤≥]=?\s*\d+(?:\.\d+)?%\s*$', line))
            for label, field in FIELDS[model].items():
                if not (current_first or generic_first or (field == 'net_interest_margin' and current_duration)):
                    continue
                aliases = '|'.join(re.escape(x) for x in LABEL_ALIASES.get(label,(label,)))
                metric_line = line
                footnote = re.match(rf'^(\s*(?:{aliases})\s+)([1-9]\d?)\s+(?=\d+\.\d)', line)
                if footnote and re.search(
                        rf'(?:^|\n)\s*{footnote[2]}[.、]\s*(?:{aliases})\s*=', text):
                    metric_line = footnote[1] + line[footnote.end():]
                threshold = r'(?:[<>≤≥]=?\s*\d+(?:\.\d+)?(?:\s*\(注\s*\d+\))?|不适用)\s+' if regulatory and not trailing_threshold else ''
                match = re.match(rf'^\s*(?:{aliases})\s*(?:\((?:%|年化|年化,%|注\d*|\d+)\)\s*){{0,2}}\s*{threshold}(-?\d[\d,]*(?:\.\d+)?)\s*(%)?\s+(-?\d[\d,]*(?:\.\d+)?)', metric_line)
                header_unit = bool(re.search(r'(?:单位\s*:|(?:财务比率|资产质量指标|资本充足率指标|盈利能力指标|主要指标))\s*\(?\s*%',unit_context))
                if not match or not (match.group(2) or '%' in line or header_unit):
                    continue
                value = Decimal(match.group(1).replace(',',''))
                if value < 0 or value > 2000:
                    continue
                matches[field].append({'field_name':field,'value':str(value),'unit':'percent',
                    'page_number':page_index,'source_label':label,'excerpt':context[-2500:],
                    'statement_scope':'母公司（原文明确）' if scope_header else 'issuer regulatory disclosure; entity scope requires corroboration',
                    'scope_evidence':scope_header,
                    'capital_method':'高级法' if '高级法' in context else '权重法' if '权重法' in context else None,
                    'text_engine':engine, 'period_basis':'YTD' if field == 'net_interest_margin' and current_duration else 'period_end'})
    # Never choose one of several conflicting percentages silently.
    facts = []
    for items in matches.values():
        scoped = [item for item in items if item.get('scope_evidence')]
        if scoped and len({item['statement_scope'] for item in scoped}) == 1:
            scoped_pages = {item['page_number'] for item in scoped}
            if any(not item.get('scope_evidence') and item['page_number'] in scoped_pages for item in items):
                continue
            reference = min(scoped, key=lambda x: Decimal(x['value']).as_tuple().exponent)
            value = Decimal(reference['value'])
            if not all(value.quantize(Decimal(item['value']), rounding=ROUND_HALF_UP)
                       == Decimal(item['value']) for item in items):
                continue
            # An unlabeled duplicate is not a conflicting entity and cannot
            # supply scoped provenance or an additional corroborating source.
            items = scoped
        precise = min(items,key=lambda x:Decimal(x['value']).as_tuple().exponent)
        value = Decimal(precise['value'])
        # A rounded repeat inside the same PDF corroborates decoding, not source
        # independence. Different reported capital methods remain distinct.
        if len({x.get('capital_method') for x in items} - {None}) > 1:
            continue
        if len({x['statement_scope'] for x in items}) > 1:
            continue
        if all(value.quantize(Decimal(x['value']),rounding=ROUND_HALF_UP) == Decimal(x['value']) for x in items):
            facts.append({**precise,'supporting_pages':sorted({x['page_number'] for x in items}),
                          'supporting_text_engines':sorted({x['text_engine'] for x in items})})
    return facts


def _continued_bank_margin(previous, current, period, page_index, engine):
    year, month, _ = period.split('-')
    headers = list(re.finditer(r'项目\s+(20\d{2})\s*年\s*1\s*[-至]\s*(\d+)\s*月', previous))
    if not headers or page_index < 2:
        return None
    tail = previous[headers[-1].start():]
    durations = re.findall(r'(20\d{2})\s*年\s*1\s*[-至]\s*(\d+)\s*月', tail)
    if durations != [(year, str(int(month))), (str(int(year)-1), str(int(month))),
                     (str(int(year)-2), str(int(month)))]:
        return None
    parts = re.split(r'盈利能力指标\s*\(\s*%\s*\)', tail)
    if len(parts) != 2 or len(parts[1]) > 600:
        return None
    if re.search(r'20\d{2}|项目|母公司|子公司|非并表|监管|预计|目标', parts[1]):
        return None
    if not re.search(r'净利差[^\n]+\s*$', parts[1]):
        return None
    match = re.match(r'^\s*(?:\d+\s*\n)?\s*(净息差|净利息收益率)\s+'
                     r'(\d+\.\d+)\s+(\d+\.\d+)\s+[+-]?\d+\.\d+个百分点\s+'
                     r'(\d+\.\d+)(?:\s*\n|$)', current)
    if not match or any(Decimal(match[g]) > 100 for g in (2, 3, 4)):
        return None
    return {'field_name': 'net_interest_margin', 'value': match[2], 'unit': 'percent',
            'page_number': page_index, 'source_label': match[1],
            'excerpt': tail + '\n[following PDF page]\n' + match.group(),
            'statement_scope': 'issuer regulatory disclosure; entity scope requires corroboration',
            'scope_evidence': None, 'capital_method': None, 'text_engine': engine,
            'period_basis': 'YTD', 'period_header_page': page_index - 1}


def _regulatory_bank_rows(previous, current, period, page_index, engine):
    date = r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日'
    header = re.compile(r'监管指标\s*监管\s*标准\s*' + date + r'\s*' + date + r'\s*' + date)
    match = header.search(current)
    header_page = page_index
    body = current[match.end():] if match else ''
    if not match:
        match = header.search(previous)
        if (not match or not re.search(r'核心一级资本充足率[^\n]+\s*$', previous)
                or not re.match(r'^\s*[^\n]*半年度报告全文\s*\n\s*\d+\s*\n'
                                r'流动性\s+流动性比例', current)):
            return []
        header_page -= 1
        body = current
    values = match.groups()
    dates = ['%04d-%02d-%02d' % tuple(map(int, values[i:i+3])) for i in (0, 3, 6)]
    if dates != [period, f'{int(period[:4])-1}-12-31', f'{int(period[:4])-2}-12-31']:
        return []
    body = re.split(r'注\s*[:：]|\n\s*\d+[.、]\s*资本|\n\s*项目', body, maxsplit=1)[0]
    facts = []
    for label, field in FIELDS['bank'].items():
        if field == 'net_interest_margin':
            continue
        row = re.search(rf'^\s*{label}\s*\(%\)\s*([≥≤<>]=?)\s*(\d+(?:\.\d+)?)\s+'
                        r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$', body, re.M)
        if not row or Decimal(row[3]) > (2000 if field == 'provision_coverage' else 100):
            continue
        facts.append({'field_name': field, 'value': row[3], 'unit': 'percent',
                      'page_number': page_index, 'period_header_page': header_page,
                      'source_label': label, 'excerpt': match.group() + '\n' + row.group(),
                      'statement_scope': 'issuer regulatory disclosure; entity scope requires corroboration',
                      'scope_evidence': None, 'capital_method': None, 'text_engine': engine,
                      'period_basis': 'period_end', 'regulatory_threshold': row[1] + row[2]})
    return facts


def _continued_broker_risks(previous, current, page_index, engine):
    header = re.search(r'母公司净资本及有关风险控制指标\s*单位\s*:\s*元\s*'
                       r'项目\s*本报告期末\s*上年度末\s*本报告期末比上年度末增减\s*'
                       r'核心净资本[^\n]+\s*\n附属净资本[^\n]+\s*$', previous)
    if not header or page_index < 2:
        return []
    body = re.sub(r'^\s*[^\n]*半年度报告\s*\n\s*\d+\s*\n', '', current, count=1)
    if not re.match(r'^净资本\s+\d', body):
        return []
    body = re.split(r'\n\s*(?:项目|[一二三四五六七八九十]+、|注\s*:)', body, maxsplit=1)[0]
    facts = []
    for label, field in FIELDS['broker'].items():
        row = re.search(rf'^\s*{label}\s+(\d+(?:\.\d+)?)%\s+'
                        r'(\d+(?:\.\d+)?)%\s+[^\n]+$', body, re.M)
        if not row or Decimal(row[1]) > 2000:
            continue
        facts.append({'field_name': field, 'value': row[1], 'unit': 'percent',
                      'page_number': page_index, 'period_header_page': page_index - 1,
                      'source_label': label, 'excerpt': header.group() + '\n' + row.group(),
                      'statement_scope': '母公司（原文明确）',
                      'scope_evidence': header.group(), 'capital_method': None,
                      'text_engine': engine, 'period_basis': 'period_end'})
    return facts


def _continued_broker_label_units(previous, current, page_index, engine):
    header = re.search(r'母公司的净资本及风险控制指标\s*单位\s*:\s*元\s*币种\s*:\s*人民币\s*'
                       r'项目\s*本报告期末\s*上年度末\s*', previous)
    if not header or page_index < 2:
        return []
    numeric = r'\d[\d,]*(?:\.\d+)?'
    prior_body = previous[header.end():].strip()
    prior_rows = [r.strip() for r in prior_body.splitlines() if r.strip()]
    allowed = r'(?:净资本|净资产|净资本/各项风险准备之和\(%\)|净资本/净资产\(%\)|净资本/负债\(%\))'
    if (not prior_rows or not prior_rows[-1].startswith('净资本/负债(%)')
            or any(not re.fullmatch(rf'{allowed}\s+{numeric}\s+{numeric}', r) for r in prior_rows)):
        return []
    body = re.sub(r'^\s*[^\n]*半年度报告\s*\n\s*\d+\s*/\s*\d+\s*\n', '', current, count=1).lstrip()
    if not re.match(r'^净资产/负债\(%\)\s+\d', body):
        return []
    body = re.split(r'\n\s*(?:项目|[一二三四五六七八九十]+、|注\s*:)', body, maxsplit=1)[0]
    facts = []
    for label, field in FIELDS['broker'].items():
        # The legacy net-capital/risk-reserve ratio is not silently renamed.
        if field == 'risk_coverage':
            continue
        row = re.search(rf'^\s*{label}\(%\)\s+(\d+(?:\.\d+)?)\s+'
                        r'(\d+(?:\.\d+)?)\s*$', body, re.M)
        if not row or Decimal(row[1]) > 2000:
            continue
        facts.append({'field_name': field, 'value': row[1], 'unit': 'percent',
                      'page_number': page_index, 'period_header_page': page_index - 1,
                      'source_label': label, 'excerpt': header.group() + '\n' + row.group(),
                      'statement_scope': '母公司（原文明确）',
                      'scope_evidence': header.group(), 'capital_method': None,
                      'text_engine': engine, 'period_basis': 'period_end'})
    return facts


def collect_institution_metrics(limit: int = 80, *, symbols: list[str] | None = None) -> dict:
    from .pdf_text import extract_pages
    from .db import begin_run, connect, end_run, store_record
    from .financial_institutions import provisional_financial_type
    from .models import SourceRecord
    from .settings import get_settings

    logging.getLogger('pypdf').setLevel(logging.ERROR)
    settings = get_settings()
    stored = inspected = 0
    failures = []
    with connect(settings.database_url) as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('institution-metrics')) AS acquired").fetchone()['acquired']:
            return {'status':'already_running','stored':0}
        conn.execute("""CREATE TABLE IF NOT EXISTS institution_extractions (
            disclosure_id UUID NOT NULL REFERENCES official_disclosures(disclosure_id),
            parser_version TEXT NOT NULL, candidate_count INTEGER NOT NULL,
            processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY(disclosure_id,parser_version))""")
        # Keep the old evidence for audit, but never surface facts that the
        # replacement parser declined (for example conflicting table scopes).
        conn.execute("""UPDATE data_points p SET metadata = p.metadata ||
            jsonb_build_object('superseded_by_parser', %s::text)
            WHERE p.metadata ? 'institution_parser'
              AND p.metadata->>'institution_parser' <> %s
              AND EXISTS (SELECT 1 FROM institution_extractions e
                  WHERE e.disclosure_id::text=p.metadata->>'disclosure_id' AND e.parser_version=%s)""",
            (VERSION, VERSION, VERSION))
        run_id = begin_run(conn, 'collect-institution-metrics')
        conn.commit()
        reports = conn.execute("""SELECT DISTINCT ON(o.symbol) o.*, i.name, i.sector
            FROM official_disclosures o JOIN instruments i USING(symbol)
            WHERE o.archive_status = 'server_resident'
              AND o.review_status <> 'rejected'
              AND o.symbol IN (SELECT symbol FROM market_screen_results WHERE screen_date =
                (SELECT max(screen_date) FROM market_screen_results))
            ORDER BY o.symbol, o.report_period DESC, o.published_at DESC""").fetchall()
        for report in reports:
            if symbols is not None and report['symbol'] not in symbols:
                continue
            model = provisional_financial_type(report['name'], report['sector'])
            if model not in FIELDS or inspected >= limit:
                continue
            # Group solvency ratios belong to different regulated subsidiaries.
            # Do not attach one subsidiary's ratio to the listed holding company.
            if report['name'] in {'中国平安','中国太保','中国人保'}:
                continue
            checked = conn.execute('SELECT 1 FROM institution_extractions WHERE disclosure_id=%s AND parser_version=%s',
                (report['disclosure_id'], VERSION)).fetchone()
            if checked:
                continue
            already = conn.execute("""SELECT 1 FROM data_points p JOIN raw_documents d
                ON p.source_id=d.document_id WHERE p.symbol=%s AND d.sha256=%s
                AND p.metadata->>'institution_parser'=%s LIMIT 1""",
                (report['symbol'],report['sha256'],VERSION)).fetchone()
            if already:
                continue
            inspected += 1
            try:
                path = Path(report['local_path'])
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != report['sha256']:
                    raise ValueError('Archived PDF hash mismatch')
                pages = extract_pages(path)
                facts = parse_tables(pages, model, str(report['report_period']))
                if len(facts) < len(FIELDS[model]):
                    from pypdf import PdfReader
                    fallback_pages = [page.extract_text() or '' for page in PdfReader(path).pages]
                    facts = parse_tables(pages, model, str(report['report_period']),
                                         fallback_pages=fallback_pages)
                with conn.transaction():
                    for fact in facts:
                        store_record(conn, SourceRecord(
                            symbol=report['symbol'],field_name=fact['field_name'],period_label=str(report['report_period']),
                            value=Decimal(fact['value']),unit='percent',source_name='CNINFO official institution report',
                            source_url=report['source_url'],published_at=report['published_at'],
                            fetched_at=datetime.now(timezone.utc),parser_version=VERSION,raw_payload=raw,
                            local_path=str(path),point_metadata={**fact,'official_extraction':True,
                                'institution_parser':VERSION,'automatic_cross_source_verification':False,
                                'disclosure_id':str(report['disclosure_id'])}), 'pending')
                    conn.execute("""INSERT INTO institution_extractions(disclosure_id,parser_version,candidate_count)
                        VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""", (report['disclosure_id'],VERSION,len(facts)))
                conn.commit()
                stored += len(facts)
                print(json.dumps({'symbol':report['symbol'],'metrics':len(facts)},ensure_ascii=False),flush=True)
            except Exception as error:
                conn.rollback()
                failures.append({'symbol':report['symbol'],'error':str(error)[:250]})
        result = {'inspected':inspected,'stored':stored,'failures':failures,'parser':VERSION}
        end_run(conn,run_id,'succeeded' if not failures else 'failed',result)
    return result

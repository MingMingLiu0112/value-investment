"""Bounded local layout coverage audit; no data promotion or inferred zero debt."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.financing_table import TITLE, extract_financing_components, financing_applicability
from value_investment_agent.financing_transposed import extract_transposed_balances
from value_investment_agent.financing_cells import extract_financing_cells
from value_investment_agent.financing_year_layout import extract_year_financing

TITLE_VARIANTS = (TITLE, '筹资活动产生的各项负债的变动情况')


def ruled_financing_table(path, page_index):
    import pdfplumber
    with pdfplumber.open(path) as document:
        page = document.pages[page_index]
        results = []
        previous_bottom = 0
        for table in sorted(page.find_tables(), key=lambda t: t.bbox[1]):
            if table.bbox[1] <= previous_bottom:
                continue
            context = page.crop((0, previous_bottom, page.width, table.bbox[1])).extract_text() or ''
            previous_bottom = table.bbox[3]
            result = extract_financing_cells(table.extract(), context)
            if result:
                results.append({**result, 'table_bbox': table.bbox, 'context': context})
        return results[0] if len(results) == 1 else None


def continuation_evidence(layout, next_layout):
    """Capture a heading-only page followed immediately by a financing header."""
    lines = layout.splitlines()
    starts = [i for i, line in enumerate(lines)
              if any(''.join(line.split()).endswith(title) for title in TITLE_VARIANTS)]
    if len(starts) != 1:
        return None
    # Only a footer page number may follow the title. Never skip intervening text.
    if any(line.strip() and not re.fullmatch(r'\d+', line.strip())
           for line in lines[starts[0] + 1:]):
        return None
    section = []
    for line in next_layout.splitlines():
        if re.match(r'^\s*(?:\d+\s*[、．.]|[（(]\s*\d+\s*[）)])', line):
            break
        section.append(line)
    compact = ''.join(''.join(section).split())
    if not all(token in compact for token in
               ('项目', '期初余额', '期末余额', '本期增加', '本期减少', '现金变动', '非现金变动', '合计')):
        return None
    return {'layout': '\n'.join(section),
            'status': 'continuation_captured_not_financially_verified',
            'explicit_cny_unit': '单位：元' in [''.join(line.split()) for line in section]}


def continuation_cells(previous_layout, next_layout, prefix, cells):
    """Accept only the first ruled table immediately following a carried title."""
    evidence = continuation_evidence(previous_layout, next_layout)
    if not evidence or not evidence['explicit_cny_unit']:
        return None
    lines = [''.join(line.split()) for line in prefix.splitlines() if line.strip()]
    # A running annual-report header is optional; arbitrary prose is not.
    if lines and re.fullmatch(r'[^\d]+20\d{2}年年度报告(?:全文)?', lines[0]):
        lines = lines[1:]
    if len(lines) != 2 or lines[-1] != '单位：元':
        return None
    if financing_applicability(TITLE + '\n' + lines[0]) != 'declared_applicable':
        return None
    result = extract_financing_cells(cells, TITLE + '\n' + '\n'.join(lines))
    if result:
        return {**result, 'title_carried_from_previous_page': True,
                'previous_page_layout': previous_layout, 'next_page_prefix': prefix,
                'bounded_next_page_layout': evidence['layout']}
    return None


def ruled_continuation_table(path, page_index, previous_layout, next_layout):
    import pdfplumber
    with pdfplumber.open(path) as document:
        page = document.pages[page_index]
        tables = sorted(page.find_tables(), key=lambda table: table.bbox[1])
        if not tables:
            return None
        table = tables[0]
        prefix = page.crop((0, 0, page.width, table.bbox[1])).extract_text() or ''
        result = continuation_cells(previous_layout, next_layout, prefix, table.extract())
        if result:
            return {**result, 'table_bbox': table.bbox,
                    'physical_pages': [page_index, page_index + 1]}
    return None


def inspect(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(path)
    if len(reader.pages) > 600:
        raise ValueError('Report exceeds bounded page count')
    hits = []
    for index, text in enumerate(extract_pages(path), 1):
        matched_title = next((title for title in TITLE_VARIANTS if title in ''.join(text.split())), None)
        if matched_title is None:
            continue
        layout = reader.pages[index - 1].extract_text(extraction_mode='layout')
        result = (extract_financing_components(layout) or extract_transposed_balances(layout)
                  or extract_year_financing(layout))
        applicability = financing_applicability(layout)
        if result is None and applicability == 'declared_applicable':
            result = ruled_financing_table(path, index - 1)
        continuation = None
        if result is None and applicability != 'declared_not_applicable' and index < len(reader.pages):
            continuation = continuation_evidence(
                layout, reader.pages[index].extract_text(extraction_mode='layout'))
            if continuation:
                continuation['physical_page'] = index + 1
                result = ruled_continuation_table(
                    path, index, layout, reader.pages[index].extract_text(extraction_mode='layout'))
        status = ('parsed_scope_unverified' if result else
                  'declared_not_applicable_not_zero_debt' if applicability == 'declared_not_applicable' else
                  'cross_page_evidence_requires_parser_and_scope_review' if continuation else
                  'no_component_parse')
        hits.append({'physical_page': index, 'matched_title': matched_title,
                     'applicability': applicability, 'continuation': continuation,
                     'parsed': result, 'status': status})
    return {'path': str(path), 'sha256': digest, 'pages': len(reader.pages), 'hits': hits,
            'search_scope': 'Two known titles in PDFium text; image-only and other titles may be missed',
            'source_identity_verified': False, 'complete_debt_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdfs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(args.pdfs) > 10:
        parser.error('At most 10 explicitly selected local reports')
    rows = [inspect(path) for path in args.pdfs]
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(rows, stream, ensure_ascii=False, indent=2)
    print(json.dumps([{'path': r['path'], 'title_hits': len(r['hits']),
                       'parsed_tables': sum(h['parsed'] is not None for h in r['hits']),
                       'hit_pages': [h['physical_page'] for h in r['hits']]}
                      for r in rows], ensure_ascii=False))

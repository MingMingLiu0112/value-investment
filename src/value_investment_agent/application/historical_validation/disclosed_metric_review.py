"""Verify explicitly transcribed report rows without approving FinancialFacts."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import re

from ..product.common import require_inside, load_json_object, sha256_file
from ..product.workbench import load_existing_workbench_for_presentation
from ...infrastructure.filings.pdf_text import extract_pages


def review_disclosed_metrics(*, root: Path, path: Path, expected_sha256: str,
                            workbench_path: Path, workbench_sha256: str) -> dict:
    path = require_inside(root, path, 'metric transcription')
    if sha256_file(path) != expected_sha256:
        raise ValueError('metric transcription hash mismatch')
    request = load_json_object(path, 'metric transcription')
    workbench = load_existing_workbench_for_presentation(root=root, path=workbench_path,
                                                        expected_sha256=workbench_sha256)
    if (request.get('schema_version') != 'disclosed-metric-transcription-v1'
            or request.get('action') != 'no_order' or request.get('symbol') != workbench['symbol']):
        raise ValueError('metric transcription scope mismatch')
    binding = request['source_binding']
    matching = [source for source in workbench['research']['source_records']
                if source['path'] == binding['path'] and source['sha256'] == binding['sha256']
                and source.get('source_url') == binding['source_url']]
    if len(matching) != 1:
        raise ValueError('metric source not bound to verified workbench')
    source = require_inside(root, root / binding['path'], 'metric original')
    pages = extract_pages(source)
    if sha256_file(source) != binding['sha256']:
        raise ValueError('metric original changed during extraction')
    facts = []
    seen = set()
    for row in request['rows']:
        if (not row['required_context'] or row['unit'] not in {'CNY', 'percent'}
                or set(row['period_columns']) != set(row['values_by_period'])
                or len(set(row['period_columns'].values())) != len(row['period_columns'])):
            raise ValueError('metric periods, columns or unit context invalid')
        page_number = row['physical_page']
        if type(page_number) is not int or not 1 <= page_number <= len(pages):
            raise ValueError('metric physical page invalid')
        page = ' '.join(pages[page_number - 1].split())
        context_pages = row.get('context_physical_pages', [page_number])
        if (not context_pages or any(type(number) is not int or number not in {page_number - 1, page_number}
                or number < 1 for number in context_pages) or page_number not in context_pages):
            raise ValueError('metric context must be its page and optional preceding page')
        context_text = ' '.join(' '.join(pages[number - 1].split()) for number in context_pages)
        statement_scope = row.get('statement_scope', 'UNSPECIFIED')
        if statement_scope not in {'UNSPECIFIED', 'CONSOLIDATED', 'PARENT'}:
            raise ValueError('unknown metric statement scope')
        if statement_scope != 'UNSPECIFIED' and (
                '合并现金流量表' if statement_scope == 'CONSOLIDATED' else '母公司现金流量表') not in context_text:
            raise ValueError('cash statement scope missing from bound page context')
        excerpt = ' '.join(row['evidence_excerpt'].split())
        label = ' '.join(row['row_label'].split())
        if (not excerpt.startswith(label) or page.count(excerpt) != 1
                or not all(' '.join(context.split()) in context_text for context in row['required_context'])):
            raise ValueError('metric row or period/unit context not found uniquely in source')
        numbers = re.findall(r'[-+]?\d[\d,]*(?:\.\d+)?', excerpt[len(label):])
        for period, column in row['period_columns'].items():
            if type(column) is not int or not 0 <= column < len(numbers):
                raise ValueError('metric column invalid')
            value = Decimal(row['values_by_period'][period])
            if not value.is_finite() or value != Decimal(numbers[column].replace(',', '')):
                raise ValueError('metric value differs from transcribed source column')
            identity = (row['metric_name'], period)
            if identity in seen:
                raise ValueError('duplicate disclosed metric')
            seen.add(identity)
            facts.append(dict(symbol=request['symbol'], metric_name=row['metric_name'], period=period,
                value=str(value), unit=row['unit'], physical_page=page_number, source_binding=binding,
                context_physical_pages=context_pages, statement_scope=statement_scope,
                evidence_excerpt=excerpt, verification_status='TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY',
                availability_basis='CURRENT_REVIEW_OF_LATER_REPORT_NOT_ORIGINAL_PERIOD_AVAILABILITY'))
    if not facts:
        raise ValueError('metric review requires facts')
    if sha256_file(path) != expected_sha256:
        raise ValueError('metric transcription changed during review')
    return dict(schema_version='disclosed-metric-review-v1', symbol=request['symbol'],
        observed_at=datetime.now(timezone.utc).isoformat(), transcription_sha256=expected_sha256,
        workbench_sha256=workbench_sha256, facts=facts, action='no_order',
        financial_gate_admitted=False, forecast_assumptions_approved=False, strict_pit_admitted=False,
        limitation='Numeric row correspondence is not independent accounting review, complete FinancialFacts, a forecast or proof of historical availability.')

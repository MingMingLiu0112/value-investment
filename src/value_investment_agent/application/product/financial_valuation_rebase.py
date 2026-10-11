"""Bind retained statement inputs to a conditional shared-model proposal."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re

from .common import load_json_object, require_inside, sha256_file
from .financial_review_attachment import load_financial_review_attachment
from .statement_equity_bridge import reconcile_statement_equity
from ...infrastructure.filings.pdf_text import extract_pages
from ...valuation_models.residual_income import ResidualIncomeValuationTiming


def rebase_proposal_facts(*, root: Path, symbol: str, facts, policy: dict):
    """No package, research cutoff, approval or execution state is changed."""
    spec = policy['financial_rebase']
    review = load_financial_review_attachment(root=root, symbol=symbol,
        manifest_path=root / spec['manifest_path'], manifest_sha256=spec['manifest_sha256'])
    if (spec.get('schema_version') != 'financial-proposal-rebase-v1'
            or policy.get('profit_anchor_field') != 'ttm_ex_nonrecurring_parent_profit_cny'
            or spec.get('share_basis') != 'DISCLOSED_TOTAL_NOT_TREASURY_OR_DILUTION_ADJUSTED'
            or not spec.get('limitations')):
        raise ValueError('financial rebase requires an explicit unadmitted input basis')
    period = review['financial_period_end']
    if period > facts.as_of.isoformat():
        raise ValueError('financial rebase period is after retained research date')
    catalog = {row['id']: row for row in review['source_bindings']}
    pages = {}
    used = set()
    cutoff = datetime.fromisoformat(facts.as_of.isoformat() + 'T16:00:00+08:00')

    def excerpt(source_id, page, text):
        source = catalog[source_id]
        if datetime.fromisoformat(source['available_at_conservative']) > cutoff:
            raise ValueError('financial rebase source was unavailable at retained cutoff')
        path = require_inside(root, root / source['path'], 'financial rebase source')
        if source_id not in pages:
            pages[source_id] = extract_pages(path)
        if (type(page) is not int or not 1 <= page <= len(pages[source_id])
                or not isinstance(text, str) or not text.strip()
                or ''.join(text.split()) not in ''.join(pages[source_id][page - 1].split())):
            raise ValueError('financial rebase excerpt differs from original page')
        used.add(source_id)

    amounts = {}
    for field, unit, scope in (
        ('start_book_equity', 'CNY', 'consolidated_parent_attributable'),
        ('ordinary_shares', 'shares', 'disclosed_total_ordinary_shares'),
    ):
        row = spec[field]
        amount = Decimal(row['value'])
        if (row.get('period_end') != period or row.get('unit') != unit
                or row.get('scope') != scope or not amount.is_finite() or amount <= 0
                or (unit == 'shares' and amount != amount.to_integral_value())):
            raise ValueError('financial rebase capital unit/scope/period/value mismatch')
        excerpt(row['source_id'], row['physical_page'], row['evidence_excerpt'])
        numbers = [Decimal(value.replace(',', '')) for value in
                   re.findall(r'\d[\d,]*(?:\.\d+)?', row['evidence_excerpt'])]
        if amount not in numbers:
            raise ValueError('financial rebase capital amount absent from excerpt')
        compact = ''.join(row['evidence_excerpt'].split())
        if field == 'start_book_equity' and (
                not compact.startswith('归属于母公司所有者权益（或股东权益）合计')
                or numbers[0] != amount):
            raise ValueError('financial rebase requires current consolidated parent equity column')
        if field == 'ordinary_shares' and '总股本变为' + f'{int(amount):,}' + '股' not in ''.join(pages[row['source_id']][row['physical_page'] - 1].split()):
            raise ValueError('financial rebase requires an explicit share-count disclosure')
        amounts[field] = amount
    continuity = spec['share_continuity']
    if (continuity.get('period_end') != period
            or continuity['source_id'] != spec['ordinary_shares']['source_id']):
        raise ValueError('financial rebase share continuity period/source mismatch')
    excerpt(continuity['source_id'], continuity['physical_page'], continuity['evidence_excerpt'])
    if continuity['evidence_excerpt'] != '报告期内，公司股份总数及股本结构未发生变化。':
        raise ValueError('financial rebase requires explicit unchanged share continuity')
    year = int(period[:4])
    equity = spec['start_book_equity']
    header_page = equity['statement_header_page']
    if type(header_page) is not int or header_page < 1 or header_page not in {equity['physical_page'], equity['physical_page'] - 1}:
        raise ValueError('financial rebase statement header must be adjacent to equity row')
    header = pages[equity['source_id']][header_page - 1]
    compact_header = ''.join(header.split())
    column_header = f'项目附注{year}年6月30日{year-1}年12月31日'
    if '合并资产负债表' not in compact_header or column_header not in compact_header:
        raise ValueError('financial rebase equity statement column period mismatch')
    confirmation = spec['share_capital_confirmation']
    if confirmation['source_id'] != equity['source_id'] or confirmation['source_id'] != continuity['source_id']:
        raise ValueError('financial rebase capital confirmation requires the same current statement')
    excerpt(confirmation['source_id'], confirmation['physical_page'], confirmation['evidence_excerpt'])
    compact_capital = ''.join(pages[confirmation['source_id']][confirmation['physical_page'] - 1].split())
    current_report = f'{year}年半年度报告'
    if (current_report not in compact_capital or '期初余额' not in compact_capital or '期末余额' not in compact_capital
            or ''.join(confirmation['evidence_excerpt'].split()) !=
               '股份总数' + f'{amounts["ordinary_shares"]:,.2f}' * 2):
        raise ValueError('financial rebase historical shares do not reconcile to current capital table')

    calculation = review['calculations']['ttm_ex_nonrecurring_parent_profit']
    rows = {row['id']: row for row in review['facts']}
    expected = [f'FY{year-1}', f'H1{year}', f'H1{year-1}']
    if (period != f'{year}-06-30' or calculation['unit'] != 'CNY'
            or calculation['scope'] != 'consolidated_parent_attributable'
            or len(calculation['input_fact_ids']) != 3):
        raise ValueError('financial rebase requires declared parent-profit TTM components')
    terms = []
    for fact_id, index, period_label in zip(calculation['input_fact_ids'],
            calculation['input_column_indices'], expected):
        row = rows[fact_id]
        column = row['columns'][index]
        if (row.get('unit') != 'CNY' or row.get('currency') != 'CNY'
                or row.get('statement_scope') != 'consolidated_parent_attributable'
                or row.get('label') != '归属于上市公司股东的扣除非经常性损益的净利润'
                or column['period'] != period_label):
            raise ValueError('financial rebase TTM component unit/scope/period mismatch')
        excerpt(row['source_id'], row['physical_page'], row['evidence_excerpt'])
        amount = Decimal(column['value'])
        if not amount.is_finite():
            raise ValueError('financial rebase TTM amount is not finite')
        expected_excerpt = row['label'] + ''.join(f"{Decimal(item['value']):,.2f}" for item in row['columns'])
        if ''.join(row['evidence_excerpt'].split()) != expected_excerpt:
            raise ValueError('financial rebase TTM amounts differ from ordered original columns')
        terms.append(amount)
    anchor = terms[0] + terms[1] - terms[2]
    if not anchor.is_finite() or anchor <= 0 or anchor != Decimal(calculation['value']):
        raise ValueError('financial rebase TTM components do not reconcile')
    if spec.get('equity_bridge') is not None:
        bridge = reconcile_statement_equity(spec=spec['equity_bridge'], period_end=period,
            expected_equity=amounts['start_book_equity'], current_source_id=equity['source_id'],
            pages=pages, verify_excerpt=excerpt)
        spec = {**spec, 'equity_bridge_result': bridge}
    timing = ResidualIncomeValuationTiming(
        basis_at=datetime.fromisoformat(period + 'T23:59:59+08:00'),
        valuation_at=cutoff,
        evidence_refs=tuple(dict(id=source_id, sha256=catalog[source_id]['sha256']) for source_id in sorted(used)))
    manifest_path = root / spec['manifest_path']
    manifest = load_json_object(manifest_path, 'rebase manifest')
    bindings = [(manifest_path, spec['manifest_sha256'])]
    bindings.extend((manifest_path.parent / name, digest) for name, digest in manifest['outputs'].items())
    bindings.append((root / manifest['script']['path'], manifest['script']['sha256']))
    bindings.extend((root / catalog[key]['path'], catalog[key]['sha256']) for key in used)
    for path, digest in bindings:
        if sha256_file(path) != digest:
            raise ValueError('financial rebase source changed during extraction')
    rebased = replace(facts, operating_inputs={**facts.operating_inputs, **amounts},
        valuation_timing=timing, evidence_refs=[*facts.evidence_refs, *timing.evidence_refs])
    return rebased, anchor, bindings, spec

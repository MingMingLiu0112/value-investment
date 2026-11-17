"""Reviewed issuer-parent H1 case adapter, not a general debt maturity parser."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import re

from .parent_funding_facts_v1 import load_parent_facts, validate_supported_case
from .pdf_text import extract_pages


_PARENT_ROWS = {
    'short_term_borrowings': (39, '短期借款', '3001758333.34'),
    'trade_payables': (40, '应付账款', '44739969.13'),
    'advance_receipts': (40, '预收款项', '1004564.59'),
    'contract_liabilities': (40, '合同负债', '2631879.16'),
    'employee_payables': (40, '应付职工薪酬', '134193083.29'),
    'tax_payables': (40, '应交税费', '566687.43'),
    'other_payables_including_dividend': (40, '其他应付款', '12311533974.01'),
    'current_noncurrent_liabilities': (40, '一年内到期的非流动负债', '1510049088.62'),
    'other_current_liabilities': (40, '其他流动负债', '342144.29'),
    'current_liabilities_total': (40, '流动负债合计', '17006819723.86'),
    'dividend_payable': (40, '应付股利', '6501567650.57'),
    'noncurrent_borrowings': (40, '长期借款', '1220000000.00'),
    'retained_profit': (40, '未分配利润', '23214184665.64'),
    'cash_equivalents': (46, '六、期末现金及现金等价物余额', '23517778984.18'),
}
_FLOOR_SNAPSHOT_SHA = 'c1ef378b37b81809cc9fd3c3532c96aaa89be1be5f24e2bd526fe1295a1d932c'
_CONSTRAINT_MANIFEST_SHA = 'c47d077503c607c1b0dd2a7a6de6834ed3968f79b0cde600246b1213824c32ca'


def _inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Evidence outside root')
    return path


def load_parent_obligation_snapshot(*, root, native_path, cutoff):
    """Authenticate old originals without rewriting their accepted v1 bytes."""
    packet = load_parent_facts(root, native_path, cutoff=cutoff)
    validate_supported_case(packet, '2026-06-30')
    selected = [s for s in packet['sources'].values() if s['report_period'] == '2026-06-30']
    if len(selected) != 1:
        raise ValueError('One reviewed H1 original required')
    source = selected[0]
    path = _inside(root, source['path'])
    if sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Source hash mismatch')
    pages = extract_pages(path, limit=46)
    if sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Source changed during extraction')
    if '母公司资产负债表' not in pages[37] or '期末余额' not in pages[37]:
        raise ValueError('Parent current-column header missing')
    facts = {}
    for name, (page, label, value) in _PARENT_ROWS.items():
        compact = re.sub(r'[\s,]', '', pages[page - 1])
        if re.sub(r'\s', '', label) + value not in compact:
            raise ValueError('Reviewed parent row mismatch: ' + name)
        facts[name] = dict(id='parent-obligation-v2:' + name, value=value,
            label=label, physical_page=page, column_index=0,
            header_pages=[38, 40] if page < 41 else [45, 46],
            scope='issuer_parent_standalone', as_of='2026-06-30', unit='CNY',
            source_id=source['id'], source_sha256=source['sha256'])
    return dict(schema_version='parent-obligation-snapshot-v2', symbol=source['symbol'],
        scope='issuer_parent_standalone', as_of='2026-06-30', unit='CNY',
        balances={key: row['value'] for key, row in facts.items()}, facts=facts,
        source=source, native_sha256=packet['native_sha256'],
        evidence_available_at=max(s['identity_available_at'] for s in selected),
        parser_version='reviewed-parent-obligation-case-v2',
        exact_due_dates_proven=False, parent_debt_components_proven=False,
        subsequent_repayment_proven=False, action='no_order')


def load_frozen_cash_floor_assumption(*, root, relative_path, cutoff):
    """Read a frozen research assumption; do not certify it as operating need."""
    path = _inside(root, relative_path)
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != _FLOOR_SNAPSHOT_SHA:
        raise ValueError('Unreviewed floor assumption snapshot')
    packet = json.loads(raw)
    if cutoff.tzinfo is None or datetime.fromisoformat(packet['generated_at']) > cutoff:
        raise ValueError('Floor assumption not available at cutoff')
    for binding in packet['source_bindings']:
        if sha256(_inside(root, binding['path']).read_bytes()).hexdigest() != binding['sha256']:
            raise ValueError('Floor binding hash mismatch')
    row = packet['historical_bindings']['cash_floor']['assumption']
    return dict(value=row['value'], unit=row['unit'], rationale=row['rationale'],
        status='FROZEN_RESEARCH_ASSUMPTION_NOT_VERIFIED_OPERATING_REQUIREMENT',
        path=str(relative_path), sha256=_FLOOR_SNAPSHOT_SHA,
        available_at=packet['generated_at'], debt_overlap_proven=False,
        note='The rationale says maintain a cash floor but does not allocate debt, operations or commitments. Treating debt as included is a different combined-buffer assumption, not validation of the original minimum-cash floor.',
        action='no_order')


def load_official_parent_constraint_disclosures(*, bundle_root, cutoff):
    """Authenticate four reviewed supplementary originals and their limitations.

    Rule text, management statements and receivable-side schedules are not
    parent debt maturity schedules. No figure from these sources is added to
    the parent cash calculation. Local availability is actual acquisition,
    not the historical publication date. Manifest paths are archival metadata;
    originals are resolved by basename inside the supplied isolated bundle.
    """
    from html.parser import HTMLParser

    class TextOnly(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    if cutoff.tzinfo is None:
        raise ValueError('Aware cutoff required')
    manifest_path = _inside(bundle_root, 'minimal-new-sources-v1.json')
    raw = manifest_path.read_bytes()
    if sha256(raw).hexdigest() != _CONSTRAINT_MANIFEST_SHA:
        raise ValueError('Unreviewed constraint manifest')
    manifest = json.loads(raw)
    if datetime.fromisoformat(manifest['created_at']) > cutoff:
        raise ValueError('Constraint review not available at cutoff')
    verified = []
    for source in manifest['sources']:
        if datetime.fromisoformat(source['actual_acquired_at']) > cutoff:
            raise ValueError('Constraint source not available at cutoff')
        path = _inside(bundle_root, PureWindowsPath(source['path']).name)
        original = path.read_bytes()
        if sha256(original).hexdigest() != source['sha256']:
            raise ValueError('Constraint source hash mismatch')
        if path.suffix.lower() == '.pdf':
            pages = extract_pages(path)
        elif path.suffix.lower() == '.html':
            parser = TextOnly()
            parser.feed(original.decode('utf-8'))
            pages = [''.join(parser.parts)]
        else:
            raise ValueError('Unsupported constraint original')
        if sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Constraint source changed during extraction')
        locators = list(source['locators'])
        if source['source_id'] == 'H1-related-funds':
            # Frozen-manifest addendum: verify the direction on the actual row,
            # not merely the report title. Never consume OCR/derived JSON as fact.
            locators.append(dict(physical_page_1based=3, article_locator=None,
                needle='泸州老窖酿酒有限责任公司 子公司 其他应收款'))
        for locator in locators:
            page = locator['physical_page_1based']
            text = pages[page - 1] if page is not None else pages[0]
            compact = lambda value: re.sub(r'\s+', '', value)
            if compact(locator['needle']) not in compact(text):
                raise ValueError('Constraint locator missing: ' + source['source_id'])
        verified.append(dict(source_id=source['source_id'], path=path.name,
            official_url=source['official_url'], sha256=source['sha256'],
            actual_acquired_at=source['actual_acquired_at'],
            statement_scope=source['statement_scope'], locators=locators,
            supports_only=source['supports_only'], does_not_support=source['does_not_support']))
    return dict(status='SOURCE_BOUND_RULES_AND_QUALITATIVE_DISCLOSURES_NOT_CAPACITY',
        manifest_sha256=_CONSTRAINT_MANIFEST_SHA, symbol=manifest['symbol'],
        available_at=manifest['created_at'], sources=verified,
        parent_debt_decomposition_proven=False, subsequent_repayment_proven=False,
        legal_distribution_certified=False, operating_cash_floor_proven=False,
        receivables_offset_against_payables_allowed=False, action='no_order')

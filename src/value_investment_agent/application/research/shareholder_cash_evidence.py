"""Offline source-bound observations; never cash-path or research admission."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import json
import re

import pypdfium2 as pdfium

from . import parent_cash_research as parent
from ...infrastructure.filings.pdfium_runtime import serialized_pdfium
from ..product.common import require_inside, sha256_file


def _one(pattern, text, reason):
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError(reason)
    return matches[0]


def _page(pages, label):
    found = [(i + 1, text) for i, text in enumerate(pages) if label in parent._compact(text)]
    if len(found) != 1:
        raise ValueError('PAGE_MISSING_OR_AMBIGUOUS:' + label)
    return found[0]


def _fund(pages):
    number, text = _page(pages, '尚未履行的认缴出资余额均为人民币')
    compact = parent._compact(text)
    if '重要承诺事项' not in compact:
        raise ValueError('FUND_COMMITMENT_SCOPE_MISSING')
    match = _one(r'公司对([^。，]+?)和([^。，]+?)尚未履行的认缴出资余额均为人民币(\d+(?:\.\d+)?)亿元[。；]',
                 compact, 'FUND_TWO_OBLIGATIONS_REQUIRED')
    if match[1] == match[2]:
        raise ValueError('FUND_IDENTITIES_NOT_DISTINCT')
    amount = Decimal(match[3]) * Decimal(100000000)
    if amount <= 0:
        raise ValueError('FUND_AMOUNT_INVALID')
    return dict(physical_pages=[number], evidence_excerpt=match[0],
                scope='issuer_commitments', timing='reporting_period_end',
                obligations=[dict(entity=name, uncalled_cny=str(amount)) for name in match.groups()[:2]],
                total_uncalled_cny=str(amount * 2), payment_schedule=None)


def _digital(pages):
    number, text = _page(pages, '其他原因的合并范围变动')
    compact = parent._compact(text)
    match = _one(r'公司出资(\d+(?:\.\d+)?)亿元成立全资子公司([^，。]+数字科技有限公司)，[^。]*截至报告披露日已出资(\d+(?:\.\d+)?)亿元。',
                 compact, 'DIGITAL_PLANNED_PAID_SENTENCE_REQUIRED')
    planned, paid = (Decimal(match[i]) * Decimal(100000000) for i in (1, 3))
    # The registration table may continue onto the next physical page.
    table = parent._compact('\n'.join(pages[number-1:number+1]))
    start = table.find('企业集团的构成')
    end = table.find('重要的非全资子公司', start)
    if start < 0 or end < 0:
        raise ValueError('DIGITAL_REGISTRATION_TABLE_BOUNDARY_MISSING')
    table = table[start:end]
    if not all(label in table for label in ('注册资本', '单位：元', '币种：人民币')):
        raise ValueError('DIGITAL_REGISTRATION_UNIT_OR_LABEL_MISSING')
    row = _one(re.escape(match[2]) + r'((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})(?!\d)',
               table, 'DIGITAL_REGISTRATION_ROW_REQUIRED')
    registered = Decimal(row[1].replace(',', ''))
    if registered != planned or not 0 <= paid <= planned:
        raise ValueError('DIGITAL_REGISTERED_PLANNED_PAID_MISMATCH')
    return dict(physical_pages=[number, number+1], evidence_excerpt=match[0] + ' ' + row[0],
                scope='issuer_investment_in_wholly_owned_subsidiary',
                entity=match[2], timing='report_disclosure_date',
                registered_cny=str(registered), planned_cny=str(planned),
                paid_cny=str(paid), remaining_planned_cny=str(planned-paid),
                payment_schedule=None, legally_due_now=None)


@serialized_pdfium
def _verify_current_column(path, page_number, value, current_anchor, prior_anchor):
    """Check the sole printed amount against both CFO column right edges."""
    document = pdfium.PdfDocument(path)
    try:
        page = document[page_number-1]
        try:
            text = page.get_textpage()
            try:
                def right(token):
                    search = text.search(token)
                    try:
                        hit = search.get_next()
                        if hit is None or search.get_next() is not None:
                            raise ValueError('PDF_COLUMN_ANCHOR_AMBIGUOUS')
                        index, count = hit
                        return text.get_charbox(index+count-1)[2]
                    finally:
                        search.close()
                x, current, prior = map(right, (value, current_anchor, prior_anchor))
                if abs(x-current) > 3 or abs(current-prior) < 20:
                    raise ValueError('H1_SINGLE_AMOUNT_NOT_CURRENT_COLUMN')
            finally:
                text.close()
        finally:
            page.close()
    finally:
        document.close()


def _interim(pages, statement, path):
    number = statement['rows']['cfo_cny']['physical_page']
    text = pages[number-1].replace('\r', '')
    start = text.find('母公司现金流量表')
    if start < 0:
        raise ValueError('H1_PARENT_TABLE_PAGE_REQUIRED')
    text = text[start:]
    label = parent.LABELS['investment_income_cash_cny']
    match = _one(r'(?m)^' + re.escape(label) + r'[ \t]+(' + parent._MONEY + r')[ \t]*$',
                 text, 'H1_SINGLE_PRINTED_INVESTMENT_ROW_REQUIRED')
    following = text[match.end():].lstrip()
    if re.match(parent._MONEY, following):
        raise ValueError('H1_SINGLE_PRINTED_ROW_HAS_DETACHED_AMOUNT')
    cfo = statement['rows']['cfo_cny']['columns']
    anchors = [format(Decimal(col['value']), ',.2f') for col in cfo]
    _verify_current_column(path, number, match[1], *anchors)
    return dict(physical_pages=[number], evidence_excerpt=match[0],
                scope='listed_parent_only', timing='reporting_period',
                value_cny=str(Decimal(match[1].replace(',', ''))),
                comparison_period=statement['periods'][1], comparison_value_cny=None,
                comparison_status='BLANK_NOT_ZERO', subsidiary_dividends_identified=False)


def load_shareholder_cash_evidence(root, symbol, now):
    """Replay registered originals. Decimal amounts are strings; no files/network writes.

    Partial machine verification is separate from economic admission. Failures
    return no observations. Unknown companies return SOURCE_NOT_REGISTERED.
    """
    envelope = dict(schema_version='shareholder-cash-evidence-v1', symbol=symbol,
                    action='no_order', research_admitted=False, economic_approval=False,
                    source_bindings=[], observations={}, detailed_observations=[])
    stage = 'INPUT'
    try:
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError('AWARE_CLOCK_REQUIRED')
        root = Path(root).resolve()
        stage = 'SOURCE_REGISTRY'
        registry_path = require_inside(root, root/parent.SPEC, 'shareholder source registry')
        registry = json.loads(registry_path.read_bytes())
        if (registry['schema_version'] != 'two-company-earnings-source-spec-v1'
                or registry['scope'] != 'RETAINED_PUBLIC_ORIGINALS_NOT_RESEARCH_ADMISSION'
                or registry['action'] != 'no_order'):
            raise ValueError('SOURCE_REGISTRY_SCOPE_INVALID')
        if not isinstance(symbol, str) or re.fullmatch(r'[0-9]{6}', symbol) is None:
            raise ValueError('SECURITY_CODE_INVALID')
        for source in registry['companies'].get(symbol, []):
            stage = source['source_id'] + ':HASH_DATE_PREFLIGHT'
            relative = Path(source['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('ROOT_RELATIVE_SOURCE_REQUIRED')
            original = require_inside(root, root/relative, 'shareholder original')
            if sha256_file(original) != source['sha256']:
                raise ValueError('ORIGINAL_SHA256_MISMATCH')
            published = date.fromisoformat(source['published_date'])
            available = datetime.combine(published+timedelta(days=1), time(),
                                         timezone(timedelta(hours=8)))
            if available > now:
                raise ValueError('SOURCE_NOT_YET_AVAILABLE')
        stage = 'PARENT_SOURCE_HASH_DATE_SCOPE_REPLAY'
        base = parent.load_parent_cash_research(root=root, symbol=symbol, now=now, observations_only=True)
        if base is None:
            return dict(envelope, status='SOURCE_NOT_REGISTERED')
        if base['status'] != 'SOURCE_REPLAYED_PARTIAL_PARENT_CASH':
            raise ValueError('PARENT_SOURCE_VALIDATION_FAILED:' + base.get('reason', 'unknown'))
        refs = [dict(ref) for ref in base['source_bindings']]
        module = Path(__file__).resolve()
        module_hash = sha256_file(module)
        observations = []
        with localcontext() as context:
            context.prec = 48
            for statement in base['historical_statements']:
                binding = statement['source_binding']
                stage = binding['id'] + ':SECOND_READ'
                path = require_inside(root, root/binding['path'], 'shareholder cash original')
                if sha256_file(path) != binding['sha256']:
                    raise ValueError('ORIGINAL_CHANGED_BEFORE_READ')
                pages = parent.extract_pages(path)
                # Revalidate issuer, period, units and parent table on this read.
                spec = next(s for s in json.loads((root/parent.SPEC).read_bytes())['companies'][symbol]
                            if s['source_id'] == binding['id'])
                parent.extract_parent_cash_statement(pages=pages, spec=spec, observation_fields={'cfo_cny'})
                def add(kind, values, status='MACHINE_VERIFIED_OBSERVATION'):
                    observations.append(dict(id=binding['id'] + ':' + kind, kind=kind,
                        symbol=symbol, period=statement['periods'][0], currency='CNY',
                        verification_status=status, source_id=binding['id'],
                        source_binding=dict(binding), **values))
                stage = binding['id'] + ':FUND'
                add('fund_uncalled_commitments', _fund(pages))
                if statement['periods'][0].startswith('H1'):
                    stage = binding['id'] + ':DIGITAL'
                    add('digital_subsidiary_capital', _digital(pages))
                    stage = binding['id'] + ':H1_CURRENT_COLUMN'
                    add('investment_income_cash', _interim(pages, statement, path))
                # Review locators carry no extracted numeric assertion or admission.
                for kind, label, scope in (
                    ('statutory_reserve_non_cash_review', '按母公司净利润', 'listed_parent_only'),
                    ('cost_method_cash_equality_review', '成本法核算的长期股权投资收益', 'parent_note_review_required'),
                ):
                    located = [(i+1, p) for i, p in enumerate(pages) if label in parent._compact(p)]
                    if not located:
                        raise ValueError('REVIEW_SOURCE_LABEL_MISSING:' + label)
                    add(kind, dict(physical_pages=[i for i, _ in located], scope=scope,
                        evidence_excerpt='\n'.join(p for _, p in located),
                        value_cny=None, auto_admitted=False,
                        treatment='Review required; reserve transfer is not a cash payment.'
                        if kind.startswith('statutory') else 'Review cost-method income against annual cash; equality not machine verified.'),
                        'SOURCE_BOUND_REVIEW_NOT_AUTO_ADMITTED')
        latest = {row['kind']: row for row in observations if row['period'].startswith('H1')}
        named = {}
        for name, kind, field, classification in (
            ('fund_uncalled_total_cny', 'fund_uncalled_commitments', 'total_uncalled_cny', 'SOURCE_VERIFIED_DERIVED_SUM'),
            ('digital_registered_cny', 'digital_subsidiary_capital', 'registered_cny', 'SOURCE_VERIFIED_PRINTED'),
            ('digital_paid_cny', 'digital_subsidiary_capital', 'paid_cny', 'SOURCE_VERIFIED_PRINTED'),
            ('digital_remaining_cny', 'digital_subsidiary_capital', 'remaining_planned_cny', 'SOURCE_VERIFIED_DERIVED_DIFFERENCE'),
            ('interim_investment_cash_current_cny', 'investment_income_cash', 'value_cny', 'SOURCE_VERIFIED_PRINTED'),
            ('interim_investment_cash_comparative_cny', 'investment_income_cash', 'comparison_value_cny', 'SOURCE_VERIFIED_BLANK_NOT_ZERO'),
        ):
            row = latest[kind]
            named[name] = dict(value=row[field], classification=classification,
                symbol=symbol, period=row.get('comparison_period') if field == 'comparison_value_cny' else row['period'],
                scope=row['scope'], timing=row['timing'], currency='CNY',
                observation_id=row['id'],
                source_refs=[dict(row['source_binding'], physical_pages=row['physical_pages'])])
        named['fund_uncalled_total_cny']['formula'] = 'sum(obligations[].uncalled_cny); latest interim only'
        named['digital_remaining_cny']['formula'] = 'digital_registered_cny - digital_paid_cny'
        named['digital_remaining_cny']['legally_due_now'] = None
        stage = 'FINAL_BINDING_REVALIDATION'
        for ref in refs:
            if sha256_file(require_inside(root, root/ref['path'], 'final shareholder evidence check')) != ref['sha256']:
                raise ValueError('SOURCE_CHANGED_DURING_READ:' + ref['path'])
        if sha256_file(module) != module_hash:
            raise ValueError('IMPLEMENTATION_CHANGED_DURING_READ')
        refs.append(dict(path=module.relative_to(root).as_posix(), sha256=module_hash))
        return dict(envelope, status='SOURCE_REPLAYED_PARTIAL_ECONOMIC_OBSERVATIONS',
                    evaluated_at=now.isoformat(), source_bindings=refs, observations=named,
                    detailed_observations=observations,
                    availability_scope=base['availability_scope'],
                    limitations=['Not sustainable FCF, legal distribution capacity or payment dates.',
                                 'Annual cost-method equality and statutory reserve rate require review.',
                                 'Do not deduct commitments twice or treat reserve transfers as cash expenses.'])
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, IndexError) as error:
        return dict(envelope, status='SOURCE_REVALIDATION_FAILED',
                    reason=stage + ':' + str(error))

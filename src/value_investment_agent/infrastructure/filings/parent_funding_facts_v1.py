"""Read existing native facts and hash-bound official originals, without writes."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

REVIEWED_NATIVE_SHA256 = '223dc8bf4c8d0ad4d74f8ae10db3a8fecafab46189ef9301e4d1d0497b9882f9'


def load_parent_facts(root, relative_path, *, cutoff):
    root = Path(root).resolve()
    def contained(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('source outside root')
        return path
    raw = contained(relative_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REVIEWED_NATIVE_SHA256:
        raise ValueError('unreviewed native snapshot')
    packet = json.loads(raw)
    if cutoff.tzinfo is None:
        raise ValueError('aware cutoff required')
    if packet.get('generated_at') and datetime.fromisoformat(packet['generated_at']) > cutoff:
        raise ValueError('future packet')
    sources = {}
    for source in packet['sources']:
        for key in ('identity_available_at', 'published_at', 'published_date'):
            if source.get(key):
                stamp = datetime.fromisoformat(source[key])
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=cutoff.tzinfo)
                if stamp > cutoff:
                    raise ValueError('future ' + key)
        if source['id'] in sources:
            raise ValueError('duplicate source')
        if datetime.fromisoformat(source['available_at']) > cutoff:
            raise ValueError('future source')
        if hashlib.sha256(contained(source['path']).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('source hash mismatch')
        sources[source['id']] = source
        binding = source.get('identity_index_binding')
        if binding and hashlib.sha256(contained(binding['path']).read_bytes()).hexdigest() != binding['sha256']:
            raise ValueError('identity hash mismatch')
    facts = []
    for fact in packet['facts']:
        if fact.get('scope') != 'parent':
            continue
        if fact['source_id'] not in sources or not fact.get('physical_page'):
            raise ValueError('unbound fact')
        if fact.get('unit') != 'CNY':
            raise ValueError('CNY required')
        facts.append(fact)
    return dict(facts=facts, sources=sources,
                native_sha256=hashlib.sha256(raw).hexdigest(), action='no_order')


def bind_original_page(root, source, cutoff, page, amount):
    """Verify original bytes and a reviewed amount on an exact physical page."""
    from .pdf_text import extract_pages
    root = Path(root).resolve()
    path = (root / source['path']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('source outside root')
    if datetime.fromisoformat(source['available_at']) > cutoff:
        raise ValueError('future source')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source['sha256']:
        raise ValueError('source hash mismatch')
    text = extract_pages(path, limit=page)[page - 1]
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('source changed during extraction')
    if amount not in text:
        raise ValueError('reviewed amount missing from page')
    return dict(source=source, physical_page=page, amount=amount,
                excerpt=text, action='no_order')


def bind_payment_arrangement(root, receipt_path, cutoff):
    root = Path(root).resolve()
    path = (root / receipt_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('receipt outside root')
    raw = path.read_bytes()
    records = json.loads(raw)['records']
    matches = [r for r in records if r['source_id'] == 'cninfo:1225481717']
    if len(matches) != 1:
        raise ValueError('ambiguous payment source')
    source = matches[0]
    expected = 'bff4efd3a9aa3d486ffce8143117627aafa4d86dd5d0e1ecb74278ceb3b0980b'
    if source['sha256'] != expected:
        raise ValueError('unexpected payment original')
    amount = bind_original_page(root, source, cutoff, 1, '6,501,567,650.57')
    timing = bind_original_page(root, source, cutoff, 3, '28')
    if not re.search(r'2026年8月28日', re.sub(r'\s+', '', timing['excerpt'])):
        raise ValueError('full payment date missing')
    return dict(amount_evidence=amount, timing_evidence=timing,
                receipt_sha256=hashlib.sha256(raw).hexdigest(),
                status='IMPLEMENTATION_ARRANGEMENT',
                fiscal_attribution='FY2025', scheduled_date='2026-08-28',
                additional_cash_deduction='0', current_parent_cash=None,
                reason='Already reserved in H1 declared dividend; do not deduct twice.',
                action='no_order')

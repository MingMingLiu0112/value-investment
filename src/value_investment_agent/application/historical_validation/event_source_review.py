"""Prepare source-readable event review, never a human materiality decision."""
from datetime import datetime, timezone
from pathlib import Path

from ..product.common import load_json_object, require_inside, sha256_file
from .event_evidence_audit import audit_event_evidence
from ...infrastructure.filings.pdf_text import extract_pages


def prepare_event_source_review(*, root: Path, path: Path, expected_sha256: str,
                                symbol: str, recovered_originals: dict[str, Path] | None = None) -> dict:
    audit = audit_event_evidence(root=root, path=path, expected_sha256=expected_sha256,
                                symbol=symbol, recovered_originals=recovered_originals)
    if not audit['evidence_integrity_verified']:
        return dict(schema_version='event-source-review-packet-v1', symbol=symbol,
            status='NOT_READY', audit=audit, events=[], action='no_order',
            materiality_approved=False, model_basis_complete=False)
    payload = load_json_object(path, 'event scan')
    if payload.get('symbol') != symbol or sha256_file(path) != expected_sha256:
        raise ValueError('event scan identity or sealed bytes changed during read')
    audited = {ref['id']: ref for ref in audit['references']}
    events = []
    for announcement in payload['announcements']:
        sources = []
        for binding in announcement['evidence_refs']:
            ref = audited.get(binding['id'])
            if ref is None or binding.get('sha256') != ref['expected_sha256'] or binding.get('path') != ref['path']:
                raise ValueError('announcement source must match audited sealed reference')
            source = require_inside(root, root / ref.get('recovered_path', ref['path']), 'event PDF')
            if sha256_file(source) != ref['expected_sha256']:
                raise ValueError('event source changed before extraction')
            pages = extract_pages(source)
            if sha256_file(source) != ref['expected_sha256']:
                raise ValueError('event source changed during extraction')
            sources.append(dict(path=str(source.relative_to(root.resolve())).replace('\\', '/'),
                sha256=ref['expected_sha256'], source_url=announcement['source_url'],
                text_status='TEXT_EXTRACTED_NOT_SEMANTICALLY_VERIFIED' if any(text.strip() for text in pages)
                    else 'NO_READABLE_TEXT_REQUIRES_VISUAL_REVIEW',
                pages=[dict(physical_page=i + 1, text=text) for i, text in enumerate(pages)]))
        events.append(dict(announcement_id=announcement['announcement_id'], title=announcement['title'],
            published_at=announcement['published_at'], pre_model=announcement['pre_model'],
            machine_materiality_candidate=announcement['materiality_candidate'],
            materiality_review='PENDING_HUMAN_REVIEW', sources=sources,
            unresolved_questions=['Does the original change model inputs or assumptions?',
                'Was its impact already incorporated, and where is that evidence?',
                'Does it require recalculation, risk monitoring or thesis revalidation?']))
    if sha256_file(path) != expected_sha256:
        raise ValueError('event scan changed during source extraction')
    return dict(schema_version='event-source-review-packet-v1', symbol=symbol,
        observed_at=datetime.now(timezone.utc).isoformat(), status='SOURCE_PACKET_AVAILABLE_REVIEW_PENDING',
        audit=audit, events=events, parser_version='pdfium-page-text-v1', action='no_order',
        materiality_approved=False, model_basis_complete=False)

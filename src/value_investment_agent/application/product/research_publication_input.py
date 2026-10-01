"""Prepare a source-verified research handoff without touching any workbook."""
from pathlib import Path

from .common import require_inside, sha256_file, load_json_object, write_new_json
from ..historical_validation.event_evidence_audit import audit_event_evidence


def prepare_research_publication_input(*, root: Path, read_model_path: Path,
                                       expected_sha256: str, output_path: Path) -> dict:
    source = require_inside(root, read_model_path, 'research read model')
    output = require_inside(root / 'runtime', output_path, 'research publication input')
    if sha256_file(source) != expected_sha256:
        raise ValueError('research read model hash mismatch')
    envelope = load_json_object(source, 'research read model')
    if (envelope.get('schema_version') != 'historical-company-read-model-preview-v1'
            or envelope.get('action') != 'no_order'
            or envelope.get('canonical_written') is not False
            or envelope.get('historical_preview') is not True):
        raise ValueError('publication input requires a read-only research preview')
    snapshot = envelope.get('snapshot')
    if not isinstance(snapshot, dict) or snapshot.get('action') != 'no_order':
        raise ValueError('research snapshot must remain no_order')
    bindings = {}
    recoveries = {}
    event = envelope.get('event_source_binding')
    if event and event.get('recovered_originals'):
        audit = audit_event_evidence(root=root, path=root / event['path'], expected_sha256=event['sha256'],
            symbol=event['source_review']['symbol'],
            recovered_originals={identity: root / path for identity, path in event['recovered_originals']})
        if not audit['evidence_integrity_verified']:
            raise ValueError('event recovery is not verified')
        for reference in audit['references']:
            if reference.get('status') == 'PASS_RECOVERED_ORIGINAL':
                recoveries[(reference['path'].replace('\\', '/'), reference['expected_sha256'])] = reference['recovered_path']
    pending = [envelope]
    scanned = set()
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
            path = value.get('path', value.get('location'))
            digest = value.get('sha256')
            if not isinstance(path, str) or digest is None:
                continue
            if path.startswith(('https://', 'http://')):
                continue
            path = recoveries.get((path.replace('\\', '/'), digest), path)
            bound = require_inside(root, root / path.replace('\\', '/'), 'research original')
            relative = bound.relative_to(root.resolve()).as_posix()
            if relative in bindings and bindings[relative] != digest:
                raise ValueError('conflicting research source hashes')
            if sha256_file(bound) != digest:
                raise ValueError('research original hash mismatch: ' + relative)
            bindings[relative] = digest
            if bound.suffix.lower() == '.json' and relative not in scanned:
                scanned.add(relative)
                pending.append(load_json_object(bound, 'research bound document'))
    if not bindings:
        raise ValueError('publication input requires original source bindings')
    bindings[source.relative_to(root.resolve()).as_posix()] = expected_sha256
    for relative, digest in bindings.items():
        if sha256_file(require_inside(root, root / relative, 'research source')) != digest:
            raise ValueError('research source changed during preparation')
    result = dict(schema_version='research-publication-input-v1',
                  scope='SOURCE_VERIFIED_RESEARCH_HANDOFF_NOT_PUBLICATION_APPROVAL',
                  read_model_binding=dict(path=source.relative_to(root.resolve()).as_posix(), sha256=expected_sha256),
                  snapshot=snapshot, source_bindings=[dict(path=path, sha256=digest)
                      for path, digest in sorted(bindings.items())],
                  verified_source_recoveries=[dict(original_path=key[0], expected_sha256=key[1], recovered_path=path)
                      for key, path in sorted(recoveries.items())],
                  canonical_written=False, publication_approved=False,
                  strict_pit_admitted=False, current_price_admitted=False,
                  action='no_order')
    write_new_json(output, result)
    return result

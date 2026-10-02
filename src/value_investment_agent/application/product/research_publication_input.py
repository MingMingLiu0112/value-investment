"""Prepare a source-verified research handoff without touching any workbook."""
from pathlib import Path
import json

from .common import require_inside, sha256_file, load_json_object, write_new_json
from ..historical_validation.event_evidence_audit import audit_event_evidence


def _build_research_publication_input(*, root: Path, read_model_path: Path,
                                      expected_sha256: str) -> dict:
    source = require_inside(root, read_model_path, 'research read model')
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
    parent = envelope.get('publication_input_binding')
    if parent is not None:
        if not isinstance(parent, dict) or set(parent) != {'path', 'sha256'}:
            raise ValueError('invalid parent research publication binding')
        inherited = load_research_publication_input(root=root, path=root / parent['path'],
                                                   expected_sha256=parent['sha256'])
        # Recovery is inherited only from a freshly reverified parent, never
        # from unchecked paths in the newly composed presentation envelope.
        for recovery in inherited['verified_source_recoveries']:
            recoveries[(recovery['original_path'], recovery['expected_sha256'])] = recovery['recovered_path']
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
                document = json.loads(bound.read_text(encoding='utf-8-sig'))
                if not isinstance(document, (dict, list)):
                    raise ValueError('research bound document must be a JSON object or array')
                pending.append(document)
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
    return result


def prepare_research_publication_input(*, root: Path, read_model_path: Path,
                                       expected_sha256: str, output_path: Path) -> dict:
    output = require_inside(root / 'runtime', output_path, 'research publication input')
    result = _build_research_publication_input(root=root, read_model_path=read_model_path,
                                              expected_sha256=expected_sha256)
    write_new_json(output, result)
    return result


def load_research_publication_input(*, root: Path, path: Path, expected_sha256: str) -> dict:
    path = require_inside(root, path, 'research publication input')
    if sha256_file(path) != expected_sha256:
        raise ValueError('publication input hash mismatch')
    cached = load_json_object(path, 'research publication input')
    binding = cached.get('read_model_binding')
    if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
        raise ValueError('publication input requires pinned research result')
    fresh = _build_research_publication_input(root=root,
        read_model_path=root / binding['path'], expected_sha256=binding['sha256'])
    if fresh != cached:
        raise ValueError('publication input differs from reverified research result')
    if sha256_file(path) != expected_sha256:
        raise ValueError('publication input changed during verification')
    return fresh

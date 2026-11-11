"""Independent Web research-supplement publication, never Excel or admission."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .common import load_json_object, normalize_symbol, require_inside, write_new_json
from .pending_candidate_replay import (
    _available, _binding, _bound_path, verify_pending_candidate_replay,
)


POINTER_PATH = 'config/current-pending-candidate-replays-v1.json'
POINTER_SCHEMA = 'current-pending-candidate-replays-v1'
PUBLICATION_SCHEMA = 'pending-candidate-replay-publication-v1'


def _content(root: Path, candidate_binding: dict) -> dict:
    candidate = verify_pending_candidate_replay(root=root, binding=candidate_binding)
    directory = (root / candidate_binding['path']).parent
    return dict(schema_version=PUBLICATION_SCHEMA, action='no_order',
        symbol=candidate['symbol'], candidate_binding=candidate_binding,
        predecessor_binding=candidate['predecessor_binding'],
        package_binding=_binding(root, directory / 'package.json'),
        workbench_binding=_binding(root, directory / 'workbench.json'),
        review_packet_binding=_binding(root, directory / 'consumed-review.json'),
        model_context=candidate['model_context'],
        scope='UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY',
        approval_changed=False, research_admitted=False, price_admitted=False,
        canonical_written=False, position_guidance=None)


def prepare_pending_replay_publication(*, root: Path, candidate_binding: dict,
        output_path: Path) -> dict:
    root = root.resolve()
    target = require_inside(root / 'runtime', output_path, 'replay publication')
    payload = _content(root, candidate_binding)
    payload['generated_at'] = datetime.now(timezone.utc).isoformat()
    write_new_json(target, payload)
    binding = _binding(root, target)
    verify_pending_replay_publication(root=root, binding=binding)
    return dict(action='no_order', publication_binding=binding,
        candidate_binding=candidate_binding, current_registry_changed=False,
        canonical_written=False, approval_changed=False)


def verify_pending_replay_publication(*, root: Path, binding: dict) -> dict:
    root = root.resolve()
    path = _bound_path(root, binding)
    require_inside(root / 'runtime', path, 'replay publication')
    publication = load_json_object(path, 'replay publication')
    _available(publication['generated_at'])
    candidate = verify_pending_candidate_replay(root=root, binding=publication['candidate_binding'])
    if datetime.fromisoformat(publication['generated_at']) < datetime.fromisoformat(candidate['generated_at']):
        raise ValueError('Replay publication predates its candidate')
    expected = _content(root, publication['candidate_binding'])
    expected['generated_at'] = publication['generated_at']
    if publication != expected:
        raise ValueError('Replay publication differs from independently verified lineage')
    _bound_path(root, binding)
    return publication


def load_current_pending_replay(*, root: Path, symbol: str) -> dict | None:
    """Resolve the root-owned version registry; invalid entries raise, never fallback."""
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    path = root / POINTER_PATH
    if not path.exists():
        return None
    pointer_binding = _binding(root, path)
    pointer = load_json_object(path, 'pending replay version registry')
    if (set(pointer) != {'schema_version', 'action', 'publications'}
            or pointer['schema_version'] != POINTER_SCHEMA or pointer['action'] != 'no_order'
            or not isinstance(pointer['publications'], dict)):
        raise ValueError('Invalid pending replay version registry')
    binding = pointer['publications'].get(symbol)
    if binding is None:
        return None
    publication = verify_pending_replay_publication(root=root, binding=binding)
    if publication['symbol'] != symbol:
        raise ValueError('Replay publication issuer differs from registry')
    candidate = verify_pending_candidate_replay(root=root, binding=publication['candidate_binding'])
    _bound_path(root, pointer_binding)
    return dict(action='no_order', symbol=symbol, publication_binding=binding,
        registry_binding=pointer_binding, publication=publication, candidate=candidate,
        scope='UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY', approval_changed=False,
        research_admitted=False, price_admitted=False, canonical_written=False,
        position_guidance=None)

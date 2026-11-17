"""Read the published research version without regeneration or approval."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import load_json_object, require_inside, sha256_file
from .pending_research_candidate import verify_pending_research_candidate
from ...infrastructure.evidence.workbook_publication import verify_workbook_publication


def _pinned(root: Path, binding: dict[str, Any]) -> dict[str, Any]:
    path = require_inside(root / 'runtime', root / binding['path'], 'published research')
    if sha256_file(path) != binding['sha256']:
        raise ValueError('published research hash mismatch')
    return load_json_object(path, 'published research')


def read_published_research(*, root: Path, workbook: Path) -> dict[str, Any]:
    root = root.resolve()
    pointer_path = root/'config/current-trial-workbook.json'
    pointer_sha = sha256_file(pointer_path)
    pointer = load_json_object(pointer_path, 'current workbook')
    floor = verify_workbook_publication(root, pointer)
    if pointer.get('workbook_source') != 'WORKBOOK_PATH' or floor is None:
        raise ValueError('published workflow requires the canonical v5 publication')
    if sha256_file(workbook) != pointer['canonical_workbook_sha256']:
        raise ValueError('canonical workbook hash mismatch')
    pub = pointer['current_publication']
    receipt = _pinned(root, {'path': pub['receipt'], 'sha256': pub['receipt_sha256']})
    sources = _pinned(root, {'path': receipt['source_bindings_path'],
                             'sha256': receipt['source_bindings_sha256']})
    for binding in sources['source_bindings']:
        path = require_inside(root, root/binding['path'], 'published source')
        if sha256_file(path) != binding['sha256']:
            raise ValueError('published source hash mismatch: ' + binding['path'])
    handoff = _pinned(root, sources['publication_input_binding'])
    if handoff.get('schema_version') != 'research-publication-input-v1' or handoff.get('action') != 'no_order':
        raise ValueError('published workflow scope mismatch')
    snapshot = handoff['snapshot']
    if snapshot.get('action') != 'no_order' or snapshot.get('schema_version') != 'm7-product-workbench-v1':
        raise ValueError('published snapshot scope mismatch')
    result = dict(pointer=pointer, snapshot=snapshot, source_bindings=sources['source_bindings'],
                  quote_observation_as_of=floor.isoformat(), canonical_written=False,
                  position_guidance=None, action='no_order', pending_candidates={})
    workflow = root/'config/user-research-workflow-v1.json'
    if workflow.exists():
        config = load_json_object(workflow, 'user workflow')
        if config.get('schema_version') != 'user-research-workflow-v1' or config.get('action') != 'no_order':
            raise ValueError('user workflow configuration scope mismatch')
        for symbol in config.get('review_candidates', {}):
            binding = selected_review_candidate(root=root, published=result, symbol=symbol)
            result['pending_candidates'][symbol] = _pinned(root, binding)
    if sha256_file(pointer_path) != pointer_sha or sha256_file(workbook) != pointer['canonical_workbook_sha256']:
        raise ValueError('publication changed during daily view')
    return result


def selected_review_candidate(*, root: Path, published: dict[str, Any], symbol: str,
                              bound_draft: bool = False, now=None) -> dict[str, str]:
    config = load_json_object(root/'config/user-research-workflow-v1.json', 'user workflow')
    if config.get('schema_version') != 'user-research-workflow-v1' or config.get('action') != 'no_order':
        raise ValueError('user workflow configuration scope mismatch')
    if bound_draft:
        from .bound_draft_review import verify_bound_draft_review_candidate
        binding = config.get('bound_draft_review_candidates', {}).get(symbol)
        if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
            raise ValueError('EXACT_VERSION_REVIEW_CANDIDATE_MISSING')
        verify_bound_draft_review_candidate(root=root, symbol=symbol, binding=binding, now=now)
        return dict(binding)
    binding = config['review_candidates'].get(symbol)
    if not isinstance(binding, dict) or binding not in published['source_bindings']:
        raise ValueError('review candidate is not bound to current publication')
    candidate = verify_pending_research_candidate(root=root, path=root/binding['path'],
                                                 expected_sha256=binding['sha256'])
    if candidate['symbol'] != symbol:
        raise ValueError('review candidate issuer mismatch')
    return dict(binding)


def verify_user_update_registry(*, root: Path, published: dict[str, Any], symbols: list[str]) -> Path:
    path = root/'config/user-daily-trade-assistant-v1.json'
    registry = load_json_object(path, 'user daily cases')
    if registry.get('schema_version') != 'daily-trade-assistant-cases-v1' or registry.get('action') != 'no_order':
        raise ValueError('user update registry scope mismatch')
    for symbol in symbols:
        binding = selected_review_candidate(root=root, published=published, symbol=symbol)
        candidate = _pinned(root, binding)
        case = registry['cases'].get(symbol)
        package = (root/binding['path']).parent/'package.json'
        expected = {'path': package.relative_to(root).as_posix(), 'sha256':sha256_file(package)}
        if not isinstance(case, dict) or expected not in candidate['source_bindings']:
            raise ValueError('update package is not bound to the selected candidate')
        if case.get('package') != expected['path'] or case.get('package_sha256') != expected['sha256']:
            raise ValueError('update registry differs from selected candidate package')
    return path

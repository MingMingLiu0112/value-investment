"""Read a registered new-input candidate as unapproved review material only."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .common import load_json_object, normalize_symbol, require_inside, sha256_file
from .pending_research_candidate import JOINT_IMPLEMENTATIONS
from .neutral_valuation_proposal import JOINT_SCHEMA
from .research_review_packet import project_research_review_packet


WORKFLOW_PATH = 'config/user-research-workflow-v1.json'
MODE = 'REGISTERED_NEW_INPUT_CANDIDATE'
SCOPE = 'UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY'
GENERATOR = 'src/value_investment_agent/application/product/pending_research_candidate.py'


def _path(root, binding):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str) or not isinstance(binding['sha256'], str)
            or re.fullmatch(r'[0-9a-f]{64}', binding['sha256']) is None):
        raise ValueError('Candidate supplement requires an exact path/hash binding')
    relative = Path(binding['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Candidate supplement binding must be project relative')
    path = require_inside(root, root / relative, 'candidate supplement source')
    if sha256_file(path) != binding['sha256']:
        raise ValueError('Candidate supplement source binding drift')
    return path


def _available(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > datetime.now(timezone.utc):
        raise ValueError('Candidate supplement input is not yet available')


def load_current_pending_candidate_supplement(*, root: Path, symbol: str) -> dict | None:
    """Absent returns None; invalid registration raises, with no other lookup."""
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    registry_path = root / WORKFLOW_PATH
    if not registry_path.exists():
        return None
    registry_binding = dict(path=WORKFLOW_PATH, sha256=sha256_file(registry_path))
    workflow = load_json_object(_path(root, registry_binding), 'user research workflow')
    if workflow.get('schema_version') != 'user-research-workflow-v1' or workflow.get('action') != 'no_order':
        raise ValueError('Invalid candidate supplement workflow registry')
    entries = workflow.get('supplemental_review_candidates', {})
    if not isinstance(entries, dict):
        raise ValueError('Invalid supplemental review candidates')
    if symbol not in entries:
        return None
    binding = entries[symbol]
    candidate_path = require_inside(root / 'runtime', _path(root, binding), 'supplement candidate')
    from .source_native_candidate_v2 import (
        verify_review_candidate, SCHEMA as NATIVE_SCHEMA, IMPLEMENTATIONS as NATIVE_IMPLEMENTATIONS,
    )
    candidate = verify_review_candidate(root=root, path=candidate_path,
        expected_sha256=binding['sha256'])
    if (candidate['symbol'] != symbol or candidate.get('model_context_scope') != 'ACTUALLY_CONSUMED'
            or any(key in candidate for key in ('preparation_mode', 'predecessor_binding', 'bound_draft_inputs'))):
        raise ValueError('Supplement requires a consumed standard new-input candidate for this issuer')
    implementations = candidate.get('implementation_bindings')
    if candidate['schema_version'] == NATIVE_SCHEMA:
        if candidate.get('input_mode') != 'SOURCE_NATIVE_EXACT_INPUT_V1':
            raise ValueError('Unsupported source-native supplement input mode')
        expected_implementations = set(NATIVE_IMPLEMENTATIONS)
    else:
        if candidate.get('input_mode') not in (None, JOINT_SCHEMA):
            raise ValueError('Unsupported candidate supplement input mode')
        expected_implementations = JOINT_IMPLEMENTATIONS if candidate.get('input_mode') == JOINT_SCHEMA else {GENERATOR}
    if (not isinstance(implementations, list) or len(implementations) != len(expected_implementations)
            or any(not isinstance(item, dict) or set(item) != {'path', 'sha256'} for item in implementations)
            or {item['path'] for item in implementations} != expected_implementations):
        raise ValueError('Supplement requires the standard pending candidate producer')
    for implementation in implementations:
        _path(root, implementation)
    _available(candidate['generated_at'])
    sources = candidate['source_bindings']
    source_paths = [_path(root, item) for item in sources]
    if len(set(source_paths)) != len(source_paths):
        raise ValueError('Candidate supplement source bindings must be unique')
    bindings = {}
    for role, name in (('package', 'package.json'), ('workbench', 'workbench.json'),
                       ('review_packet', 'consumed-review.json')):
        path = candidate_path.parent / name
        item = dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
        if role != 'review_packet' and item not in sources:
            raise ValueError('Candidate supplement requires bound ' + role)
        bindings[role + '_binding'] = item
    package = load_json_object(root / bindings['package_binding']['path'], 'supplement package')
    workbench = load_json_object(root / bindings['workbench_binding']['path'], 'consumed workbench')
    for stamp in (package['point_in_time']['computed_at'], package['point_in_time']['available_at'],
                  workbench['generated_at']):
        _available(stamp)
    packet = project_research_review_packet(root=root,
        package_path=root / bindings['package_binding']['path'],
        package_sha256=bindings['package_binding']['sha256'],
        workbench_path=root / bindings['workbench_binding']['path'],
        workbench_sha256=bindings['workbench_binding']['sha256'])
    if (load_json_object(root / bindings['review_packet_binding']['path'], 'consumed review packet') != packet
            or packet['symbol'] != symbol
            or packet['input_descriptor_sha256'] != candidate['model_context']['input_descriptor_sha256']
            or packet['gate']['results'].get('G3_估值门') is not False
            or any(item not in sources for item in packet['source_bindings'])):
        raise ValueError('Candidate supplement packet differs from unapproved consumed inputs')
    for item in [binding, registry_binding, *bindings.values(), *sources, *implementations]:
        _path(root, item)
    return dict(action='no_order', symbol=symbol, mode=MODE, scope=SCOPE,
        candidate_binding=dict(binding), **bindings, candidate=candidate,
        model_context=candidate['model_context'], registry_binding=registry_binding,
        approval_changed=False, research_admitted=False, price_admitted=False,
        canonical_written=False, registered_current_case_changed=False, position_guidance=None)

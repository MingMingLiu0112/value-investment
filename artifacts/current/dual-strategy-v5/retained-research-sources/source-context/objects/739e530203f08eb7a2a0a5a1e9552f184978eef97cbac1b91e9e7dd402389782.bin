"""Replay stale pending receipts with unchanged input bytes, never admission."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re

from .common import (
    load_json_object, require_inside, sha256_file, write_new_bytes, write_new_json,
)
from .pending_research_candidate import verify_pending_research_candidate
from .research_review_packet import build_research_review_packet, project_research_review_packet
from .research_reviews import build_research_review_model_context
from .source_bound_inputs import verify_package_local_sources
from .workbench import build_current_workbench_for_symbol
from ...m1_valuation_package_builder import build_descriptor
from ...research_input import build_research_run_spec


MODE = 'IMMUTABLE_CURRENT_IMPLEMENTATION_EXACT_INPUT_REPLAY_V1'
GENERATOR = 'src/value_investment_agent/application/product/pending_research_candidate.py'
IMPLEMENTATIONS = (
    GENERATOR,
    'src/value_investment_agent/application/product/pending_candidate_replay.py',
    'src/value_investment_agent/application/product/pending_replay_publication.py',
    'src/value_investment_agent/application/product/workbench.py',
    'src/value_investment_agent/application/product/company_research.py',
    'src/value_investment_agent/application/product/source_bound_inputs.py',
    'src/value_investment_agent/application/product/research_review_packet.py',
    'src/value_investment_agent/application/product/research_reviews.py',
    'src/value_investment_agent/m1_valuation_package_builder.py',
    'src/value_investment_agent/research_input.py',
    'src/value_investment_agent/research_application.py',
    'src/value_investment_agent/valuation_router.py',
    'src/value_investment_agent/valuation_models/residual_income.py',
)
BOUNDARY_FLAGS = (
    'approval_changed', 'research_admitted', 'price_admitted',
    'canonical_written', 'registered_current_case_changed',
)


def _binding(root: Path, path: Path) -> dict:
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def _bound_path(root: Path, binding: dict) -> Path:
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str)
            or not isinstance(binding['sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('Replay requires an exact path/hash binding')
    relative = Path(binding['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Replay binding must be project relative')
    path = require_inside(root, root / relative, 'replay input')
    if sha256_file(path) != binding['sha256']:
        raise ValueError('Replay source binding drift: ' + binding['path'])
    return path


def _available(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > datetime.now(timezone.utc):
        raise ValueError('Replay generation time must be aware and available')
    return stamp


def _pending(data: dict) -> None:
    if (data.get('schema_version') != 'pending-research-candidate-v1'
            or data.get('status') != 'PENDING_REVIEW' or data.get('action') != 'no_order'
            or any(data.get(key) is not False for key in BOUNDARY_FLAGS)
            or data.get('position_guidance') is not None
            or data.get('strict_contemporaneous_pit') != 'NOT_PROVEN'):
        raise ValueError('Replay requires an unapproved no-order pending receipt')
    _available(data['generated_at'])


def _sources(root: Path, bindings: list[dict]) -> None:
    if not isinstance(bindings, list) or not bindings:
        raise ValueError('Replay source bindings missing')
    seen = set()
    for binding in bindings:
        path = _bound_path(root, binding)
        if path in seen:
            raise ValueError('Replay source bindings must be unique')
        seen.add(path)


def _predecessor(root: Path, binding: dict) -> tuple[dict, dict, Path]:
    path = _bound_path(root, binding)
    require_inside(root / 'runtime', path, 'predecessor receipt')
    data = load_json_object(path, 'predecessor receipt')
    _pending(data)
    if data.get('preparation_mode') == MODE:
        raise ValueError('Replay requires the original stale producer receipt')
    _sources(root, data.get('source_bindings'))
    implementations = data.get('implementation_bindings')
    if (not isinstance(implementations, list) or len(implementations) != 1
            or implementations[0].get('path') != GENERATOR
            or not re.fullmatch(r'[0-9a-f]{64}', implementations[0].get('sha256', ''))):
        raise ValueError('Replay requires the retained pending producer binding')
    if sha256_file(root / GENERATOR) == implementations[0]['sha256']:
        raise ValueError('Pending producer is not stale; no repair replay needed')
    package_path, workbench_path = path.parent / 'package.json', path.parent / 'workbench.json'
    for source in (package_path, workbench_path):
        if _binding(root, source) not in data['source_bindings']:
            raise ValueError('Predecessor inputs and outputs must be source bound')
    package = load_json_object(package_path, 'retained candidate package')
    if (package.get('quote') is not None or package.get('research_reviews')
            or package['research_case']['valuation_status'] in ('approved', 'approved_low_confidence')):
        raise ValueError('Replay cannot carry market or economic admission')
    verify_package_local_sources(root, package)
    policy = load_json_object(_bound_path(root, data['economic_policy_binding']), 'retained policy')
    if (data['economic_policy_binding'] not in data['source_bindings']
            or data.get('review_groups') != policy.get('human_review_groups', [])):
        raise ValueError('Replay policy/review scope differs from retained policy')
    descriptor = build_descriptor(package, root=root)
    context = build_research_review_model_context(descriptor=descriptor,
        spec=build_research_run_spec(descriptor))
    old_workbench = load_json_object(workbench_path, 'retained workbench')
    if (data['symbol'] != package['symbol'] or old_workbench['symbol'] != package['symbol']
            or data['candidate_research_as_of'] != package['point_in_time']['research_as_of']
            or data['model_context'] != context
            or data.get('model_context_scope') != 'ACTUALLY_CONSUMED'
            or not old_workbench.get('decision_recommendation')
            or data['candidate_valuation'] != old_workbench.get('valuation')
            or data['execution_status'] != old_workbench.get('suggested_state')
            or data['research_blockers'] != old_workbench.get('research_blockers', [])
            or data['schedule_gate'] != old_workbench.get('schedule_gate')):
        raise ValueError('Predecessor differs from retained inputs or outputs')
    # This projects the actual artifact bundle, not the stale candidate envelope.
    packet = project_research_review_packet(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), workbench_path=workbench_path,
        workbench_sha256=sha256_file(workbench_path))
    if packet['gate']['results'].get('G3_估值门') is not False:
        raise ValueError('Replay must retain an unapproved G3 gate')
    return data, package, package_path


def _request(package: dict) -> dict:
    return dict(schema_version='research-schedule-request-v1', symbol=package['symbol'],
        source_id='LOCAL_VERIFIED_RESEARCH', period=package['point_in_time']['report_period'],
        research_question_id='consumed_input_review_handoff',
        blocker_id='exact_version_review_candidate_missing',
        reopen_condition_met=False, new_evidence_ids=[])


def _successor(root: Path, target: Path, predecessor: dict, binding: dict,
               workbench: dict, generated_at: str) -> dict:
    result = deepcopy(predecessor)
    result.update(generated_at=generated_at, predecessor_binding=binding,
        preparation_mode=MODE, research_date_advanced=False, valuation_date_advanced=False,
        date_semantics='Actual replay time is envelope-only; all package dates and economic inputs are unchanged.',
        candidate_valuation=workbench.get('valuation'), execution_status=workbench.get('suggested_state'),
        schedule_gate=workbench.get('schedule_gate'),
        research_blockers=workbench.get('research_blockers', []),
        recommendation_type=workbench.get('suggested_state'),
        decision_blockers=list(dict.fromkeys([
            *(workbench.get('decision_recommendation') or {}).get('blockers', []),
            *workbench.get('research_blockers', [])])))
    sources = {item['path']: item for item in predecessor['source_bindings']}
    for path in (root / binding['path'], target / 'package.json', target / 'workbench.json',
                 target / 'consumed-review.json', target / 'schedule-request.json',
                 root / 'config/research-evidence-stop-ledger-v1.json'):
        sources[path.relative_to(root).as_posix()] = _binding(root, path)
    result['source_bindings'] = list(sources.values())
    result['implementation_bindings'] = [_binding(root, root / name) for name in IMPLEMENTATIONS]
    return result


def verify_pending_candidate_replay(*, root: Path, binding: dict) -> dict:
    """Independently recheck lineage, frozen bytes and consumed outputs."""
    root = root.resolve()
    path = _bound_path(root, binding)
    candidate = verify_pending_research_candidate(root=root, path=path,
        expected_sha256=binding['sha256'])
    _pending(candidate)
    if candidate.get('preparation_mode') != MODE:
        raise ValueError('Not an immutable pending replay')
    predecessor_binding = candidate['predecessor_binding']
    predecessor, package, original_package = _predecessor(root, predecessor_binding)
    if (path.parent / 'package.json').read_bytes() != original_package.read_bytes():
        raise ValueError('Replay changed the retained package bytes')
    if load_json_object(path.parent / 'schedule-request.json', 'replay scope') != _request(package):
        raise ValueError('Replay must not reopen evidence or change review scope')
    workbench = load_json_object(path.parent / 'workbench.json', 'replayed workbench')
    if _available(candidate['generated_at']) < max(
            _available(predecessor['generated_at']), _available(workbench['generated_at'])):
        raise ValueError('Replay receipt predates its predecessor or actual workbench')
    expected = _successor(root, path.parent, predecessor, predecessor_binding,
        workbench, candidate['generated_at'])
    if candidate != expected:
        raise ValueError('Replay differs from its exact predecessor/successor contract')
    if workbench.get('valuation') != predecessor['candidate_valuation']:
        raise ValueError('Current implementation changed retained valuation; review separately')
    packet = project_research_review_packet(root=root, package_path=path.parent / 'package.json',
        package_sha256=sha256_file(original_package), workbench_path=path.parent / 'workbench.json',
        workbench_sha256=sha256_file(path.parent / 'workbench.json'))
    if (load_json_object(path.parent / 'consumed-review.json', 'replayed review packet') != packet
            or packet['gate']['results'].get('G3_估值门') is not False):
        raise ValueError('Replay review packet or unapproved G3 differs')
    _sources(root, candidate['source_bindings'])
    _bound_path(root, binding)
    return candidate


def prepare_pending_candidate_replay(*, root: Path, predecessor_path: Path,
        predecessor_sha256: str, output_dir: Path) -> dict:
    """Create a successor only after real shared application consumption."""
    root = root.resolve()
    source = require_inside(root / 'runtime', predecessor_path, 'predecessor')
    binding = dict(path=source.relative_to(root).as_posix(), sha256=predecessor_sha256)
    predecessor, package, package_source = _predecessor(root, binding)
    implementations = [_binding(root, root / name) for name in IMPLEMENTATIONS]
    target = require_inside(root / 'runtime', output_dir, 'replay output')
    target.mkdir(parents=True, exist_ok=False)
    package_path = target / 'package.json'
    write_new_bytes(package_path, package_source.read_bytes())
    request = _request(package)
    request_path = target / 'schedule-request.json'
    write_new_json(request_path, request)
    workbench_path = target / 'workbench.json'
    workbench = build_current_workbench_for_symbol(root=root, symbol=package['symbol'],
        package_path=package_path, output_path=workbench_path, schedule_request=request,
        schedule_request_sha256=sha256_file(request_path))['result']
    if not workbench.get('decision_recommendation'):
        raise ValueError('Replay blocked by current scheduler; no successor candidate created')
    if (workbench.get('input_descriptor_sha256') != predecessor['model_context']['input_descriptor_sha256']
            or workbench.get('valuation') != predecessor['candidate_valuation']):
        raise ValueError('Current implementation changed retained inputs/valuation; no successor created')
    build_research_review_packet(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), workbench_path=workbench_path,
        workbench_sha256=sha256_file(workbench_path), output_path=target / 'consumed-review.json')
    packet = load_json_object(target / 'consumed-review.json', 'replayed review packet')
    if packet['gate']['results'].get('G3_估值门') is not False:
        raise ValueError('Replay cannot promote G3; no successor created')
    # Fail closed on changes during calculation, including the implementation itself.
    _predecessor(root, binding)
    _sources(root, implementations)
    candidate = _successor(root, target, predecessor, binding, workbench,
        datetime.now(timezone.utc).isoformat())
    candidate['implementation_bindings'] = implementations
    candidate_path = target / 'candidate.json'
    write_new_json(candidate_path, candidate)
    candidate_binding = _binding(root, candidate_path)
    verify_pending_candidate_replay(root=root, binding=candidate_binding)
    return dict(action='no_order', candidate_binding=candidate_binding,
        predecessor_binding=binding, approval_changed=False, research_admitted=False,
        price_admitted=False, current_registry_changed=False, canonical_written=False,
        research_date_advanced=False, valuation_date_advanced=False, position_guidance=None)

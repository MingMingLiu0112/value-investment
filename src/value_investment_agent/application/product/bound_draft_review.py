"""Adapt an unchanged verified draft into existing pending-review contracts."""
from datetime import datetime, timezone
from pathlib import Path

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .research_draft import BOUND_DRAFT_SCHEMA, POINTER_PATH, load_current_research_draft
from .pending_research_candidate import verify_pending_research_candidate
from .research_review_packet import build_research_review_packet, project_research_review_packet
from .research_reviews import build_research_review_model_context
from .workbench import build_current_workbench_for_symbol
from ...m1_valuation_package_builder import build_descriptor
from ...research_input import build_research_run_spec


def current_bound_draft_inputs(*, root: Path, symbol: str, now=None) -> dict:
    draft = load_current_research_draft(root, symbol, now=now)
    if draft is None or draft['schema_version'] != BOUND_DRAFT_SCHEMA:
        raise ValueError('CURRENT_SOURCE_BOUND_DRAFT_UNAVAILABLE')
    pointer = load_json_object(root / POINTER_PATH, 'research draft pointer')
    draft_binding = pointer['drafts'][draft['symbol']]
    path = require_inside(root / 'artifacts/current', root / draft_binding['path'], 'bound draft')
    declared = load_json_object(path, 'bound draft')
    declared.pop('input_verification', None)
    verified = {key: value for key, value in draft.items() if key != 'input_verification'}
    if sha256_file(path) != draft_binding['sha256'] or declared != verified:
        raise ValueError('Current draft changed during review preparation')
    package_binding = draft['model_input_binding']['package']
    return dict(draft=draft_binding, package=package_binding,
                input_sha256=draft['input_verification']['input_sha256'])


def verify_bound_draft_review_candidate(*, root: Path, symbol: str,
        binding: dict, now=None) -> dict:
    """Reject predecessor or foreign candidates, not merely missing signatures."""
    current = current_bound_draft_inputs(root=root, symbol=symbol, now=now)
    candidate = verify_pending_research_candidate(root=root,
        path=root / binding['path'], expected_sha256=binding['sha256'])
    clock = now or datetime.now(timezone.utc)
    generated = datetime.fromisoformat(candidate['generated_at'])
    if (clock.utcoffset() is None or generated.utcoffset() is None or generated > clock):
        raise ValueError('Review candidate is not yet available')
    package = root / binding['path']
    package = package.parent / 'package.json'
    if (candidate['symbol'] != symbol
            or candidate.get('bound_draft_inputs') != current
            or sha256_file(package) != current['package']['sha256']
            or candidate['model_context']['input_descriptor_sha256'] != current['input_sha256']):
        raise ValueError('Review candidate does not bind the current source-bound draft')
    packet = package.parent / 'consumed-review.json'
    packet_binding = dict(path=packet.relative_to(root).as_posix(), sha256=sha256_file(packet))
    if packet_binding not in candidate['source_bindings']:
        raise ValueError('Consumed review packet is not bound to the candidate')
    expected = project_research_review_packet(root=root, package_path=package,
        package_sha256=current['package']['sha256'], workbench_path=package.parent / 'workbench.json',
        workbench_sha256=sha256_file(package.parent / 'workbench.json'))
    if load_json_object(packet, 'consumed review packet') != expected:
        raise ValueError('Consumed review packet differs from verified research')
    return candidate


def prepare_bound_draft_review_candidate(*, root: Path, symbol: str,
        output_dir: Path) -> dict:
    """Run the ordinary scoped scheduler; retain facts, assumptions and old stops.

    This is exact-input engineering replay for review preparation, not reopened
    economic research. It neither invents new official evidence nor approves it.
    """
    root = root.resolve()
    bindings = current_bound_draft_inputs(root=root, symbol=symbol)
    source = require_inside(root, root / bindings['package']['path'], 'bound draft package')
    package = load_json_object(source, 'bound draft package')
    descriptor = build_descriptor(package, root=root)
    if descriptor.input_sha256 != bindings['input_sha256']:
        raise ValueError('Review descriptor differs from verified draft')
    target = require_inside(root / 'runtime', output_dir, 'bound draft review output')
    if target.exists():
        raise FileExistsError('Bound draft review output must be new')
    target.mkdir(parents=True)
    package_path = target / 'package.json'
    with package_path.open('xb') as stream:
        stream.write(source.read_bytes())
    request = dict(schema_version='research-schedule-request-v1', symbol=symbol,
        source_id='LOCAL_VERIFIED_RESEARCH', period=package['point_in_time']['report_period'],
        research_question_id='consumed_input_review_handoff',
        blocker_id='exact_version_review_candidate_missing',
        reopen_condition_met=False, new_evidence_ids=[])
    request_path = target / 'schedule-request.json'
    write_new_json(request_path, request)
    workbench_path = target / 'workbench.json'
    workbench = build_current_workbench_for_symbol(root=root, symbol=symbol,
        package_path=package_path, output_path=workbench_path,
        schedule_request=request, schedule_request_sha256=sha256_file(request_path))['result']
    if not workbench.get('decision_recommendation'):
        raise ValueError('Bound review replay did not produce a consumed workbench')
    if workbench.get('input_descriptor_sha256') != descriptor.input_sha256:
        raise ValueError('Review replay changed the source-bound descriptor')
    context = build_research_review_model_context(descriptor=descriptor,
        spec=build_research_run_spec(descriptor))
    groups = [
        dict(id='CAPITAL_BASIS', question='归母权益、股份口径和资本基准日是否一致？',
            support='查阅消耗输入审核包的官方事实锚点、原件页码及归一化组件。',
            countercase='合并权益、库存股或日期错配会改变每股估值；文件哈希不证明经济解释。',
            impact='影响每股净资产及剩余收益估值基数。',
            field_paths=['facts.operating_inputs', 'source_contract']),
        dict(id='ECONOMIC_ASSUMPTIONS', question='权益成本、ROE路径、留存率和终端条件是否有充分依据？',
            support='查阅消耗输入审核包逐项假设、来源、敏感性及反证。',
            countercase='预测不是官方财务事实；条件情景和代数交叉检查不证明可分配现金或盈利优势。',
            impact='影响Bear/Base/Bull及估值可靠性；逐组回应不能替代整模型批准。',
            field_paths=['facts.scenario_inputs', 'assumptions']),
        dict(id='FINANCIAL_AND_EVENTS', question='财务口径、未决公告及模型有效性限制是否已处理？',
            support='查阅完整财务摘要、原件、公告扫描和模型有效性输出。',
            countercase='不完整公告覆盖、未决材料性、严格PIT及财务研究缺口不能由本次重放消除。',
            impact='财务、材料性、模型批准与价格准入分别核验。',
            field_paths=['research_case.financial_summary', 'model_validity_input']),
    ]
    policy_path = target / 'review-scope.json'
    write_new_json(policy_path, dict(action='no_order', human_review_groups=groups,
        scope='EXACT_BOUND_INPUT_REVIEW_NOT_NEW_ECONOMIC_POLICY'))
    packet_path = target / 'consumed-review.json'
    build_research_review_packet(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), workbench_path=workbench_path,
        workbench_sha256=sha256_file(workbench_path), output_path=packet_path)
    now = datetime.now(timezone.utc)
    candidate = dict(schema_version='pending-research-candidate-v1', symbol=symbol,
        status='PENDING_REVIEW', action='no_order', generated_at=now.isoformat(),
        candidate_research_as_of=package['point_in_time']['research_as_of'],
        financial_period=package['point_in_time']['report_period'],
        model_context=context, model_context_scope='ACTUALLY_CONSUMED',
        candidate_valuation=workbench.get('valuation'),
        execution_status=workbench.get('suggested_state'),
        research_blockers=workbench.get('research_blockers', []),
        schedule_gate=workbench.get('schedule_gate'),
        economic_policy_binding=dict(path=policy_path.relative_to(root).as_posix(), sha256=sha256_file(policy_path)),
        review_groups=groups, bound_draft_inputs=bindings,
        preparation_mode='EXACT_INPUT_ENGINEERING_REPLAY_NOT_NEW_ECONOMIC_RESEARCH',
        approval_changed=False, research_admitted=False, price_admitted=False,
        canonical_written=False, registered_current_case_changed=False,
        position_guidance=None, strict_contemporaneous_pit='NOT_PROVEN',
        source_bindings=[dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
            for path in (source, root / bindings['draft']['path'], package_path,
                         workbench_path, policy_path, packet_path, request_path)])
    candidate_path = target / 'candidate.json'
    write_new_json(candidate_path, candidate)
    binding = dict(path=candidate_path.relative_to(root).as_posix(), sha256=sha256_file(candidate_path))
    verify_bound_draft_review_candidate(root=root, symbol=symbol, binding=binding)
    return dict(action='no_order', candidate_binding=binding,
                approval_changed=False, current_registry_changed=False)

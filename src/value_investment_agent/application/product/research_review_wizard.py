"""Local unsigned drafting over the existing pending-review response contract."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from .common import require_inside, sha256_file, write_new_json
from .research_reviews import prepare_pending_review_intake, prepare_pending_review_response


def _materiality_schedule_binding(*, root, candidate_binding, candidate):
    """Recover only the exact request consumed by a bound research execution."""
    from .company_research import load_schedule_request
    from .event_scan_supplement import _read
    from ...domain.research.evidence_stop import schedule_request_from_payload

    directory = require_inside(root / 'runtime', root / candidate_binding['path'],
        'materiality candidate').parent
    request_path = require_inside(root / 'runtime', directory / 'schedule-request.json',
        'materiality schedule request')
    relative = request_path.relative_to(root).as_posix()
    refs = [ref for ref in candidate['source_bindings'] if ref['path'] == relative]
    workbench_ref = None
    if len(refs) > 1:
        raise ValueError('Schedule request has conflicting candidate bindings')
    if refs:
        binding = refs[0]
    else:
        workbench_path = require_inside(root / 'runtime', directory / 'workbench.json',
            'materiality schedule workbench')
        refs = [ref for ref in candidate['source_bindings']
            if ref['path'] == workbench_path.relative_to(root).as_posix()]
        if len(refs) != 1:
            raise ValueError('Original schedule requires one candidate-bound sibling workbench')
        workbench_ref = refs[0]
        workbench = _read(root, workbench_ref)
        if (workbench['symbol'] != candidate['symbol']
                or workbench['schedule_gate'] != candidate['schedule_gate']):
            raise ValueError('Original schedule workbench issuer/scope mismatch')
        expected = workbench['research_receipt']['input_sha256']['schedule_request']
        binding = dict(path=relative, sha256=expected)
    original = _read(root, binding)
    request, actual = load_schedule_request(root, request_path)
    if request != original or actual != binding['sha256']:
        raise ValueError('Schedule request differs from its consumed byte hash')
    parsed = schedule_request_from_payload(request)
    if parsed.symbol != candidate['symbol']:
        raise ValueError('Schedule request issuer mismatch')
    scope = candidate['schedule_gate'].get('scope_key')
    if scope is not None and parsed.key != tuple(scope[key].casefold() for key in
            ('source_id', 'period', 'research_question_id', 'blocker_id')):
        raise ValueError('Schedule request differs from the consumed research scope')
    if (_read(root, binding) != original
            or (workbench_ref is not None and _read(root, workbench_ref) != workbench)):
        raise ValueError('Original schedule inputs changed during read')
    return dict(binding)


def _materiality_handoff_view(*, root, candidate_binding, candidate, package_binding, now):
    """Project a retained signing packet without adding fields to its bytes."""
    from .event_scan_supplement import _read
    from .event_supplement_handoff import _authenticated_import, _available, _quote
    from .research_materiality_reviews import prepare_materiality_review_handoff

    package = _read(root, package_binding)
    scan = package.get('model_validity_input', {}).get('event_scan_ref')
    if not isinstance(scan, dict):
        raise ValueError('原研究包尚未绑定完整公告扫描；须先按对应模型版本补齐并核验后，再办理事件审核。')
    scan_binding = {key: scan[key] for key in ('path', 'sha256')}
    expected = prepare_materiality_review_handoff(root=root,
        package_path=root / package_binding['path'], package_sha256=package_binding['sha256'],
        scan_path=root / scan_binding['path'], scan_sha256=scan_binding['sha256'])
    if expected['model_context'] != candidate['model_context']:
        raise ValueError('Materiality handoff requires the exact consumed model context')
    for stamp in (expected['scan_window']['retrieved_at'], package['point_in_time']['available_at'],
                  package['point_in_time']['computed_at']):
        _available(stamp, now)
    for item in expected['announcements']:
        _available(item['published_at'], now)

    coverage = candidate.get('coverage_binding', {})
    if not isinstance(coverage, dict):
        raise ValueError('Materiality coverage binding must be an object')
    raw_binding = coverage.get('handoff_binding')
    if 'handoff_binding' in coverage and raw_binding is None:
        raise ValueError('Declared materiality signing packet binding is missing')
    if raw_binding is None:
        raw_path = require_inside(root / 'runtime',
            (root / candidate_binding['path']).parent / 'materiality-handoff.json', 'materiality handoff')
        if not raw_path.exists():
            prepare = ('python scripts/current/review_materiality.py prepare '
                f"--package {_quote(package_binding['path'])} --package-sha256 {package_binding['sha256']} "
                f"--scan {_quote(scan_binding['path'])} --scan-sha256 {scan_binding['sha256']} "
                f"--output {_quote(raw_path.relative_to(root).as_posix())}")
            return dict(status='MATERIALITY_HANDOFF_BLOCKED', action='no_order',
                approval_granted=False, g3_approval_granted=False,
                reason='完整扫描已核验；须先用 prepare 命令保存原始签署合同，再重新读取交接材料。',
                commands=dict(prepare_handoff=prepare))
        raw_binding = dict(path=raw_path.relative_to(root).as_posix(), sha256=sha256_file(raw_path))
    require_inside(root / 'runtime', root / raw_binding['path'], 'materiality handoff')
    raw = _read(root, raw_binding)
    # A replay may retain the original packet's package path for identical bytes.
    # Its signature contract must be rebuilt using that exact retained locator.
    if (raw['package_binding']['sha256'] != package_binding['sha256']
            or raw['scan_binding'] != scan_binding or raw['model_context'] != candidate['model_context']):
        raise ValueError('Materiality signing packet differs from consumed inputs')
    rebuilt = prepare_materiality_review_handoff(root=root,
        package_path=root / raw['package_binding']['path'], package_sha256=raw['package_binding']['sha256'],
        scan_path=root / scan_binding['path'], scan_sha256=scan_binding['sha256'])
    if raw != rebuilt:
        raise ValueError('Materiality signing packet differs from its verified raw contract')
    imported = _authenticated_import(root, dict(model_context=candidate['model_context']),
        dict(package_binding=package_binding, scan_binding=scan_binding), now)
    consume = ('python scripts/current/review_materiality.py consume '
        f"--handoff {_quote(raw_binding['path'])} --handoff-sha256 {raw_binding['sha256']} "
        '--response <SIGNED_RESPONSE_PATH> --response-sha256 <SIGNED_RESPONSE_SHA256> '
        '--trust-root <PINNED_TRUST_ROOT_PATH> --trust-root-sha256 <PINNED_TRUST_ROOT_SHA256> '
        '--output <NEW_RUNTIME_DIRECTORY>')
    recompute = ('python scripts/current/run_company_research.py '
        f"--symbol {candidate['symbol']} --package {_quote(package_binding['path'])} ")
    schedule_binding = None
    schedule_error = None
    try:
        schedule_binding = _materiality_schedule_binding(root=root,
            candidate_binding=candidate_binding, candidate=candidate)
        recompute += f"--schedule-request {_quote(schedule_binding['path'])} "
    except (ValueError, OSError, KeyError, TypeError) as error:
        schedule_error = '原始研究范围请求尚未通过核验，重算不可交接：' + str(error)
    packet_ref = imported['review_packet_binding'] if imported else None
    recompute += ('--research-reviews ' + (_quote(packet_ref['path']) if packet_ref else '<IMPORTED_RESEARCH_REVIEWS_PATH>')
        + ' --research-reviews-sha256 ' + (packet_ref['sha256'] if packet_ref else '<IMPORTED_RESEARCH_REVIEWS_SHA256>')
        + ' --output <NEW_RUNTIME_RESEARCH_JSON>')
    result = dict(raw, status='EXTERNAL_SIGNATURE_REQUIRED', handoff_binding=dict(raw_binding),
        commands=dict(consume_signed_response=consume),
        approval_granted=False, g3_approval_granted=False, research_admitted=False,
        price_admitted=False, position_guidance=None, recompute_required=True, publication_required=True)
    if schedule_binding is not None:
        result.update(schedule_binding=schedule_binding, recompute_status='SCHEDULE_VERIFIED')
        result['commands']['recompute'] = recompute
    else:
        result.update(recompute_status='BLOCKED', recompute_reason=schedule_error)
    if imported:
        result.update(imported, status='AUTHENTICATED_RESPONSE_IMPORTED',
            consumption_binding=imported['materiality_consumption_binding'])
    if _read(root, raw_binding) != raw:
        raise ValueError('Materiality signing packet changed during read')
    return result


def build_external_review_handoff(*, root: Path, symbol: str, now, bound_draft=False) -> dict:
    """Keep an independent event-only version separate from current G3 materials."""
    from .event_supplement_handoff import load_current_event_supplement_handoff
    try:
        event = load_current_event_supplement_handoff(root=root, symbol=symbol, now=now)
    except (ValueError, OSError, KeyError, TypeError):
        event = dict(status='MATERIALITY_HANDOFF_BLOCKED', action='no_order',
            approval_granted=False, g3_approval_granted=False,
            reason='独立公告研究版本当前核验未通过，不能交付签署回应。')
    try:
        result = _build_external_review_handoff(root=root, symbol=symbol, now=now, bound_draft=bound_draft)
    except (ValueError, OSError, KeyError, TypeError):
        if event is None:
            raise
        result = dict(action='no_order', status='NOT_READY', symbol=symbol,
            blockers=['CURRENT_G3_HANDOFF_MISSING_OR_INVALID'],
            verification=dict(approval_changed=False, research_admitted=False))
    if event is not None:
        try:
            if load_current_event_supplement_handoff(root=root, symbol=symbol, now=now) != event:
                raise ValueError('Independent event handoff changed during G3 projection')
        except (ValueError, OSError, KeyError, TypeError):
            event = dict(status='MATERIALITY_HANDOFF_BLOCKED', action='no_order',
                approval_granted=False, g3_approval_granted=False,
                reason='独立公告研究版本或授权在读取期间发生变化，请重新核验。')
        result['supplemental_materiality_handoff'] = event
    return result


def _build_external_review_handoff(*, root: Path, symbol: str, now, bound_draft=False) -> dict:
    """Deliver the existing exact-version signing contract, never a local G3 button."""
    from .publication_chain import load_current_chain
    from .user_research_workflow import selected_review_candidate
    from ..decision.value_price_policy import load_value_policy_review, review_manifest_binding
    from ...infrastructure.evidence.trust_root_registry import pinned_trust_root_fingerprints
    from .pending_replay_publication import POINTER_PATH as REPLAY_POINTER_PATH, load_current_pending_replay
    from .pending_candidate_supplement import load_current_pending_candidate_supplement

    root = root.resolve()
    draft_inputs = None
    replay = None
    supplement = None
    replay_unavailable = dict(action='no_order', status='NOT_READY', symbol=symbol,
        blockers=['CURRENT_PENDING_REPLAY_MISSING_OR_INVALID'],
        verification=dict(approval_changed=False, research_admitted=False))
    if bound_draft:
        from .bound_draft_review import current_bound_draft_inputs
        try:
            draft_inputs = current_bound_draft_inputs(root=root, symbol=symbol, now=now)
            binding = selected_review_candidate(root=root, symbol=symbol,
                published={}, bound_draft=True, now=now)
        except (ValueError, OSError, KeyError, TypeError):
            result = dict(action='no_order', status='NOT_READY', symbol=symbol,
                blockers=['EXACT_VERSION_REVIEW_CANDIDATE_MISSING_OR_INVALID'
                    if draft_inputs else 'CURRENT_SOURCE_BOUND_DRAFT_UNAVAILABLE'],
                verification=dict(approval_changed=False, research_admitted=False))
            if draft_inputs:
                result['bindings'] = draft_inputs
            return result
    else:
        try:
            supplement = load_current_pending_candidate_supplement(root=root, symbol=symbol)
            if supplement is not None:
                if (now.utcoffset() is None or
                        datetime.fromisoformat(supplement['candidate']['generated_at']) > now):
                    raise ValueError('Supplemental candidate is not yet available')
                binding = supplement['candidate_binding']
        except (ValueError, OSError, KeyError, TypeError):
            return dict(action='no_order', status='NOT_READY', symbol=symbol,
                blockers=['CURRENT_PENDING_CANDIDATE_SUPPLEMENT_MISSING_OR_INVALID'],
                verification=dict(approval_changed=False, research_admitted=False))
    if not bound_draft and supplement is None:
        try:
            replay = load_current_pending_replay(root=root, symbol=symbol)
            if replay is None and (root / REPLAY_POINTER_PATH).exists():
                registry = json.loads((root / REPLAY_POINTER_PATH).read_bytes())
                if symbol in registry['publications']:
                    raise ValueError('Registered replay has no valid publication binding')
            if replay is not None:
                if (now.utcoffset() is None or any(datetime.fromisoformat(stamp) > now
                        for stamp in (replay['publication']['generated_at'], replay['candidate']['generated_at']))):
                    raise ValueError('Replay review inputs are not yet available')
                binding = replay['publication']['candidate_binding']
        except (ValueError, OSError, KeyError, TypeError):
            return replay_unavailable
        if replay is None:
            chain = load_current_chain(root)
            binding = selected_review_candidate(root=root, symbol=symbol,
                published={'source_bindings': chain['sources']['source_bindings']})
    preview = preview_pending_review_response(root=root,
        candidate_path=root / binding['path'], candidate_sha256=binding['sha256'])
    consumed_materials = None
    if bound_draft:
        from .bound_draft_review import verify_bound_draft_review_candidate
        candidate = verify_bound_draft_review_candidate(root=root, symbol=symbol,
            binding=binding, now=now)
        packet_path = require_inside(root / 'runtime',
            (root / binding['path']).parent / 'consumed-review.json', 'consumed review packet')
        packet_binding = dict(path=packet_path.relative_to(root).as_posix(), sha256=sha256_file(packet_path))
        if packet_binding not in candidate['source_bindings']:
            raise ValueError('Consumed review packet is not bound to the candidate')
        consumed_materials = json.loads(packet_path.read_bytes())
        current_draft = json.loads((root / draft_inputs['draft']['path']).read_bytes())
        consumed_materials['current_draft_interpretation'] = dict(
            scope='DISPLAY_INTERPRETATION_NOT_A_CHANGE_TO_CONSUMED_RESEARCH',
            research_version=current_draft.get('research_version'),
            summary=current_draft.get('summary'),
            counter_evidence=current_draft.get('counter_evidence', []),
            limitations=current_draft.get('limitations', []))
        if (sha256_file(packet_path) != packet_binding['sha256']
                or sha256_file(root / draft_inputs['draft']['path']) != draft_inputs['draft']['sha256']):
            raise ValueError('Bound review materials changed during read')
    elif supplement is not None:
        packet_binding = supplement['review_packet_binding']
        packet_path = require_inside(root / 'runtime', root / packet_binding['path'], 'supplement review packet')
        # The standard producer binds the consumed package/workbench. The
        # adapter recomputes their packet and verifies its exact saved bytes.
        consumed_materials = json.loads(packet_path.read_bytes())
        if sha256_file(packet_path) != packet_binding['sha256']:
            raise ValueError('Supplement review materials changed during read')
    elif replay is not None:
        packet_binding = replay['publication']['review_packet_binding']
        packet_path = require_inside(root / 'runtime', root / packet_binding['path'], 'replay review packet')
        if packet_binding not in replay['candidate']['source_bindings']:
            raise ValueError('Replay review packet is not bound to the candidate')
        consumed_materials = json.loads(packet_path.read_bytes())
        if sha256_file(packet_path) != packet_binding['sha256']:
            raise ValueError('Replay review materials changed during read')
    valuation_hash = preview['draft']['valuation_artifact_sha256']
    review = None
    if not bound_draft and supplement is None:
        manifest = json.loads((root / review_manifest_binding(root)['path']).read_bytes())
        if symbol in manifest['items']:
            review = load_value_policy_review(root, symbol, now)
    if (not valuation_hash or (review is not None
            and review['draft']['basis']['valuation_input_version'] != valuation_hash)):
        raise ValueError('Review handoff does not bind the current valuation')
    count = len(pinned_trust_root_fingerprints())
    candidate_args = (f'--symbol {symbol} --candidate "{binding["path"]}" '
                      f'--candidate-sha256 {binding["sha256"]}')
    from .research_materiality_reviews import registered_materiality_handoff
    try:
        if bound_draft or replay is not None or supplement is not None:
            package_binding = (draft_inputs['package'] if bound_draft else
                supplement['package_binding'] if supplement is not None else replay['publication']['package_binding'])
            materiality_candidate = candidate if bound_draft else (supplement if supplement is not None else replay)['candidate']
            materiality_handoff = _materiality_handoff_view(root=root, candidate_binding=binding,
                candidate=materiality_candidate, package_binding=package_binding, now=now)
        else:
            materiality_handoff = registered_materiality_handoff(root=root, symbol=symbol, today=now)
    except (ValueError, OSError, KeyError, TypeError) as error:
        materiality_handoff = dict(status='MATERIALITY_HANDOFF_BLOCKED', action='no_order',
            approval_granted=False, g3_approval_granted=False, reason=str(error), steps=[])
    if replay is not None:
        try:
            if load_current_pending_replay(root=root, symbol=symbol) != replay:
                raise ValueError('Registered replay changed during handoff')
        except (ValueError, OSError, KeyError, TypeError):
            return replay_unavailable
    if supplement is not None:
        if load_current_pending_candidate_supplement(root=root, symbol=symbol) != supplement:
            raise ValueError('Registered supplemental candidate changed during handoff')
    if ((bound_draft or replay is not None or supplement is not None)
            and materiality_handoff['status'] in ('EXTERNAL_SIGNATURE_REQUIRED', 'AUTHENTICATED_RESPONSE_IMPORTED')):
        try:
            if _materiality_handoff_view(root=root, candidate_binding=binding,
                    candidate=materiality_candidate, package_binding=package_binding, now=now) != materiality_handoff:
                raise ValueError('Materiality handoff changed during projection')
        except (ValueError, OSError, KeyError, TypeError):
            materiality_handoff = dict(status='MATERIALITY_HANDOFF_BLOCKED', action='no_order',
                approval_granted=False, g3_approval_granted=False,
                reason='公告签署合同或授权在读取期间发生变化，请重新核验。')
    result = dict(action='no_order', status='EXTERNAL_SIGNATURE_REQUIRED',
        materiality_handoff=materiality_handoff,
        symbol=symbol, candidate_binding=binding,
        model_context=preview['draft']['model_context'],
        valuation_artifact_sha256=valuation_hash,
        review_questions=preview['review_questions'], unsigned_response=preview['draft'],
        public_research_materials=(consumed_materials if bound_draft or replay is not None or supplement is not None else
            review['model_review'] if review else preview['draft']['model_context']),
        source_bindings=review['source_bindings'] if review else ([binding, draft_inputs['draft'], draft_inputs['package']]
            if draft_inputs else [binding]),
        authorization=dict(pinned_root_count=count,
            status='AUTHORIZED_IDENTITY_REQUIRED' if count == 0 else 'EXACT_REVIEWER_SCOPE_MUST_BE_VERIFIED'),
        steps=[
            dict(id='MATERIALS', action='核对候选、模型版本、支持、反证和字段范围；下载材料不构成批准。'),
            dict(id='IDENTITY', action='真实审核人使用本人控制的密钥；公钥信任根须经独立审核登记并限定证券、profile、有效期及权限。本机登录不授予G3身份。'),
            dict(id='RESPONSE', action='本人逐组填写VERIFIED / REJECTED / INSUFFICIENT、理由及范围；整模型G3为独立对象，重大事件另按模型绑定的完整扫描逐项审查。'),
            dict(id='SIGN', action='由有权本人按既有pending-research-response签名合同签署；不向Web上传私钥，不由系统代签。'),
            dict(id='CONSUME', action='通过现有签名消费命令核验身份、精确候选和回应链；保留不可变回执，再按当前发布流程重新验证资格和刷新页面。未发布的回执不会自动升级公共研究。')],
        commands=dict(draft_preview=f'python scripts/current/review_research.py {candidate_args} --preview',
            consume_signed_response=f'python scripts/current/review_research.py {candidate_args} '
                '--signed-review-response <本人签名回应文件> --review-trust-root <已登记信任根文件> '
                '--output <runtime下新的消费目录>'),
        event_review_entry='scripts/current/review_event.py',
        instructions='docs/current/d2-human-review-usage-20261011.md',
        verification=dict(approval_changed=False, research_admitted=False,
            policy_confirmation_is_not_g3=True,
            required_results=['authenticated-review-response.json', '共享研究重新核验结果', '当前发布版本及页面资格']),
        position_guidance=None)
    if replay is not None:
        publication = replay['publication']
        result['replay_publication_binding'] = replay['publication_binding']
        result['source_bindings'] = list({item['path']: item for item in [
            *result['source_bindings'], replay['registry_binding'], replay['publication_binding'],
            binding, publication['predecessor_binding'], publication['package_binding'],
            publication['workbench_binding'], publication['review_packet_binding']]}.values())
    if supplement is not None:
        result['candidate_preparation_mode'] = supplement['mode']
        result['current_public_price_policy_changed'] = False
        result['source_bindings'] = list({item['path']: item for item in [
            *result['source_bindings'], supplement['registry_binding'],
            supplement['candidate_binding'], supplement['package_binding'],
            supplement['workbench_binding'], supplement['review_packet_binding']]}.values())
    if replay is not None or supplement is not None:
        from ..research.value_research_analysis import project_value_research_analysis
        inputs = supplement if supplement is not None else replay['publication']
        analysis = project_value_research_analysis(root=root, now=now,
            package_binding=inputs['package_binding'], workbench_binding=inputs['workbench_binding'])
        analysis['review_binding'] = dict(candidate_binding=binding,
            model_context=result['model_context'], valuation_artifact_sha256=valuation_hash,
            review_packet_binding=inputs['review_packet_binding'])
        result['value_research_analysis'] = analysis
    if ((bound_draft or replay is not None or supplement is not None)
            and materiality_handoff.get('handoff_binding')):
        result['source_bindings'] = list({item['path']: item for item in [
            *result['source_bindings'], materiality_handoff['handoff_binding'],
            materiality_handoff['package_binding'], materiality_handoff['scan_binding']]}.values())
        if materiality_handoff.get('schedule_binding'):
            result['source_bindings'].append(materiality_handoff['schedule_binding'])
    return result


def preview_pending_review_response(*, root: Path, candidate_path: Path,
        candidate_sha256: str) -> dict:
    """Read exact questions and response slots without saving or approving anything."""
    draft = prepare_pending_review_response(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    intake = prepare_pending_review_intake(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    return dict(status='READ_ONLY_PREVIEW_NOT_APPROVED', action='no_order',
        approval_changed=False, draft=draft, review_questions=intake['groups'])


def render_review_preview(preview: dict, *, advanced: bool = False) -> str:
    draft = preview['draft']
    context = draft['model_context']
    lines = [f"公司：{draft['symbol']}；状态：待本人审核，未批准。",
        f"模型：{context['model_id']} / {context['model_version']}；研究日：{context['research_as_of']}",
        '每组意见草稿不替代整模型 G3、公告材料性或价格准入。']
    for group in preview['review_questions']:
        lines.extend([f"\n{group['id']}：{group.get('question', '')}",
            f"支持：{group.get('support', '')}", f"反证：{group.get('countercase', '')}",
            f"影响：{group.get('impact', '')}",
            '范围：' + ', '.join(group['field_paths'])])
    if advanced:
        lines.append(json.dumps(draft, ensure_ascii=False, indent=2))
    return '\n'.join(lines)


def draft_pending_review_response(*, root: Path, candidate_path: Path,
        candidate_sha256: str, output_path: Path,
        read: Callable[[str], str] = input, show: Callable[[str], None] = print) -> dict:
    """Save only an explicitly confirmed unsigned draft; cancellation writes nothing."""
    root = root.resolve()
    candidate_path = require_inside(root, candidate_path, 'review candidate')
    output_path = require_inside(root / 'runtime', output_path, 'review draft')
    if output_path.exists():
        raise FileExistsError('review draft must be new')
    original = prepare_pending_review_response(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    draft = json.loads(json.dumps(original))
    intake = prepare_pending_review_intake(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    cancelled = dict(status='CANCELLED', action='no_order', approval_changed=False)

    def ask(prompt):
        try:
            value = read(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None
        return None if value.lower() == 'cancel' else value

    show('当前仅填写未签名草稿，不提供审核身份、签名或整模型批准。')
    show(render_review_preview(dict(draft=original, review_questions=[])))
    for group, evidence in zip(draft['groups'], intake['groups']):
        show(render_review_preview(dict(draft=original, review_questions=[evidence])))
        while True:
            state = ask(f"{group['id']}：VERIFIED 已核实 / REJECTED 拒绝 / INSUFFICIENT 证据不足 / skip 暂不回答 / cancel 取消：")
            if state is None:
                return cancelled
            if state.lower() == 'skip':
                break
            if state.upper() not in {'VERIFIED', 'REJECTED', 'INSUFFICIENT'}:
                show('请选择上述状态。')
                continue
            values = {}
            for field in ('response_reason', 'confirmed_scope'):
                while True:
                    label = '判断理由' if field == 'response_reason' else '确认范围'
                    value = ask(label + '（输入 cancel 取消）：')
                    if value is None:
                        return cancelled
                    if value:
                        values[field] = value
                        break
                    show('此项不能为空。')
            group.update(response=state.upper(), **values)
            break
    show('全部回答预览（whole_model_approval 保持为空，未签名）：')
    for group in draft['groups']:
        show(f"{group['id']}：{group['response'] or 'PENDING'}\n理由：{group['response_reason'] or '未填写'}\n范围：{group['confirmed_scope'] or '未填写'}")
    if ask('预览完成。输入 save 保存未签名草稿，或 cancel 取消：') != 'save':
        return cancelled
    current = prepare_pending_review_response(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    if current != original:
        raise ValueError('review candidate context changed while drafting')
    write_new_json(output_path, draft)
    return dict(status='UNSIGNED_DRAFT_SAVED_NOT_APPROVED', action='no_order',
        approval_changed=False, path=output_path.relative_to(root).as_posix(),
        sha256=sha256_file(output_path),
        pending_groups=[g['id'] for g in draft['groups'] if g['response'] is None])

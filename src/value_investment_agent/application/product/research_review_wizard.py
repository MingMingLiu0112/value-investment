"""Local unsigned drafting over the existing pending-review response contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .common import require_inside, sha256_file, write_new_json
from .research_reviews import prepare_pending_review_intake, prepare_pending_review_response


def build_external_review_handoff(*, root: Path, symbol: str, now) -> dict:
    """Deliver the existing exact-version signing contract, never a local G3 button."""
    from .publication_chain import load_current_chain
    from .user_research_workflow import selected_review_candidate
    from ..decision.value_price_policy import load_value_policy_review, review_manifest_binding
    from ...infrastructure.evidence.trust_root_registry import pinned_trust_root_fingerprints

    root = root.resolve()
    chain = load_current_chain(root)
    binding = selected_review_candidate(root=root, symbol=symbol,
        published={'source_bindings': chain['sources']['source_bindings']})
    preview = preview_pending_review_response(root=root,
        candidate_path=root / binding['path'], candidate_sha256=binding['sha256'])
    valuation_hash = preview['draft']['valuation_artifact_sha256']
    review = None
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
        materiality_handoff = registered_materiality_handoff(root=root, symbol=symbol, today=now)
    except (ValueError, OSError, KeyError, TypeError) as error:
        materiality_handoff = dict(status='MATERIALITY_HANDOFF_BLOCKED', action='no_order',
            approval_granted=False, g3_approval_granted=False, reason=str(error), steps=[])
    return dict(action='no_order', status='EXTERNAL_SIGNATURE_REQUIRED',
        materiality_handoff=materiality_handoff,
        symbol=symbol, candidate_binding=binding,
        model_context=preview['draft']['model_context'],
        valuation_artifact_sha256=valuation_hash,
        review_questions=preview['review_questions'], unsigned_response=preview['draft'],
        public_research_materials=review['model_review'] if review else preview['draft']['model_context'],
        source_bindings=review['source_bindings'] if review else [binding],
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

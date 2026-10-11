"""Local unsigned drafting over the existing pending-review response contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .common import require_inside, sha256_file, write_new_json
from .research_reviews import prepare_pending_review_intake, prepare_pending_review_response


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

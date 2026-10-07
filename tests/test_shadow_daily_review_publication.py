"""A readable card must stay bound to the same daily inputs and refusal state."""
import json
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.operations import shadow_daily_review_publication as publication


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return {'path': path.name, 'sha256': sha256_file(path)}


def _daily(tmp_path, *, decision_state='NOT_READY'):
    common = dict(action='no_order', run_id='synthetic-review', session_date='2026-10-02',
                  orders=[], broker_called=False)
    explanation = _write(tmp_path / 'explanation.json', {'synthetic': True})
    bindings = {
        'research': _write(tmp_path / 'research.json', common | {'result': {
            'symbol': '600887', 'status': 'BLOCKED_BY_RESEARCH_SCHEDULER',
            'blockers': ['BLOCKED_SCOPE_REQUIRED']}}),
        'model': _write(tmp_path / 'model.json', common | {
            'model_validity': 'NOT_ESTABLISHED', 'price_bridge': 'NOT_ADMITTED'}),
        'decision': _write(tmp_path / 'decision.json', common | {
            'suggested_state': decision_state, 'blockers': ['BLOCKED_SCOPE_REQUIRED']}),
        'product': _write(tmp_path / 'product.json', common | {
            'source_anchored_explanation': dict(symbol='600887', action='no_order',
                rows={'公告事实': '合成测试文本'}, unresolved_questions=['现金流待核实'],
                **explanation)}),
    }
    manifest = tmp_path / 'input.json'
    manifest.write_text(json.dumps({'symbols': ['600887'], 'bindings': bindings}), encoding='utf-8')
    return manifest


def test_card_explains_blockers_and_preserves_audit_codes(monkeypatch, tmp_path):
    manifest = _daily(tmp_path)
    explanation = json.loads((tmp_path / 'product.json').read_text(encoding='utf-8'))['source_anchored_explanation']
    monkeypatch.setattr(publication, 'read_event_followup', lambda **kwargs: explanation)
    monkeypatch.setattr(publication, 'audit_shadow_daily_input', lambda **kwargs: {
        'session_date': '2026-10-02', 'input_consistency_status': 'SHADOW_INPUT_INCOMPLETE',
        'blockers': ['MISSING_DAG_ARTIFACT:quote', 'EVENT_COVERAGE_INCOMPLETE',
                     'DAG_EXECUTION_INCOMPLETE']})
    card = publication.render_bound_daily_review(root=tmp_path, manifest_path=manifest,
        manifest_sha256=sha256_file(manifest), now=datetime.now(timezone.utc))
    assert '研究：本次未获准重新计算' in card
    assert '行情：缺少同日有效收盘价' in card
    assert '事件：公告扫描' in card
    assert '计算链：研究、模型' in card
    assert card.index('## 为什么现在不能行动') < card.index('## 已披露事实')
    assert card.index('## 审计细项') > card.index('## 证据与执行边界')
    assert 'MISSING_DAG_ARTIFACT:quote' in card
    assert '合成测试文本' in card and 'action=no_order' in card
    assert sha256_file(manifest) in card


def test_card_rejects_tampered_explanation_and_positive_state(monkeypatch, tmp_path):
    manifest = _daily(tmp_path)
    monkeypatch.setattr(publication, 'audit_shadow_daily_input', lambda **kwargs: {
        'session_date': '2026-10-02', 'input_consistency_status': 'SHADOW_INPUT_INCOMPLETE',
        'blockers': ['MISSING_DAG_ARTIFACT:quote']})
    (tmp_path / 'explanation.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='explanation hash mismatch'):
        publication.render_bound_daily_review(root=tmp_path, manifest_path=manifest,
            manifest_sha256=sha256_file(manifest), now=datetime.now(timezone.utc))
    positive = _daily(tmp_path, decision_state='MANUAL_BUY_REVIEW')
    with pytest.raises(ValueError, match='incomplete daily input'):
        publication.render_bound_daily_review(root=tmp_path, manifest_path=positive,
            manifest_sha256=sha256_file(positive), now=datetime.now(timezone.utc))


def test_card_rejects_rehashed_display_drift(monkeypatch, tmp_path):
    manifest = _daily(tmp_path)
    expected = json.loads((tmp_path / 'product.json').read_text(encoding='utf-8'))['source_anchored_explanation']
    monkeypatch.setattr(publication, 'audit_shadow_daily_input', lambda **kwargs: {
        'session_date': '2026-10-02', 'input_consistency_status': 'SHADOW_INPUT_INCOMPLETE',
        'blockers': ['MISSING_DAG_ARTIFACT:quote']})
    monkeypatch.setattr(publication, 'read_event_followup', lambda **kwargs: expected)
    product = json.loads((tmp_path / 'product.json').read_text(encoding='utf-8'))
    product['source_anchored_explanation']['rows']['公告事实'] = '已满足买入条件'
    binding = _write(tmp_path / 'product.json', product)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    payload['bindings']['product'] = binding
    _write(manifest, payload)
    with pytest.raises(ValueError, match='differs from verified originals'):
        publication.render_bound_daily_review(root=tmp_path, manifest_path=manifest,
            manifest_sha256=sha256_file(manifest), now=datetime.now(timezone.utc))


def test_card_revalidates_originals_with_session_cutoff(monkeypatch, tmp_path):
    manifest = _daily(tmp_path)
    monkeypatch.setattr(publication, 'audit_shadow_daily_input', lambda **kwargs: {
        'session_date': '2026-10-02', 'input_consistency_status': 'SHADOW_INPUT_INCOMPLETE',
        'blockers': []})
    def reject_original(**kwargs):
        assert kwargs['cutoff'].isoformat() == '2026-10-02'
        raise ValueError('event followup requires unchanged originals')
    monkeypatch.setattr(publication, 'read_event_followup', reject_original)
    with pytest.raises(ValueError, match='unchanged originals'):
        publication.render_bound_daily_review(root=tmp_path, manifest_path=manifest,
            manifest_sha256=sha256_file(manifest), now=datetime.now(timezone.utc))

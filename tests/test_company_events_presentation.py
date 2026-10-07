from dataclasses import replace
import pytest
from test_product_workbench_read_model import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload, EvidenceRecord
from value_investment_agent.presentation.read_models.company_events import project_company_event_questions


def test_company_events_keep_gates_and_show_scope_and_originals():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    evidence = EvidenceRecord('event-fixture', 'Events', 'research', 'runtime/scan.json', 'a'*64, model.as_of)
    packet = dict(schema_version='event-source-review-packet-v1', action='no_order', symbol=card.symbol,
                  materiality_approved=False, model_basis_complete=False,
                  audit={'evidence_integrity_verified': True}, events=[dict(announcement_id='123',
                      title='回购报告', published_at='2026-09-17', materiality_review='PENDING_HUMAN_REVIEW',
                      sources=[dict(source_url='https://example.test/report.pdf', sha256='b'*64,
                                    pages=[{}], text_status='TEXT_EXTRACTED_NOT_SEMANTICALLY_VERIFIED')])])
    output = project_company_event_questions(model, packet, evidence)
    updated = output.companies[0]
    assert replace(updated, decision_review=card.decision_review, evidence_refs=card.evidence_refs) == card
    assert output.portfolio == model.portfolio
    assert 'https://example.test/report.pdf' in dict(updated.decision_review)['待复核公告 123 回购报告']
    assert '不代表今日' in dict(updated.decision_review)['公告覆盖边界']
    packet['materiality_approved'] = True
    with pytest.raises(ValueError): project_company_event_questions(model, packet, evidence)


def test_failed_originals_do_not_surface_unverified_event_text():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    evidence = EvidenceRecord('failed-event', 'Events', 'research', 'runtime/scan.json', 'a'*64, model.as_of)
    packet = dict(schema_version='event-source-review-packet-v1', action='no_order', symbol=card.symbol,
                  materiality_approved=False, model_basis_complete=False,
                  audit={'evidence_integrity_verified': False}, events=[{'title': 'untrusted'}])
    output = project_company_event_questions(model, packet, evidence)
    assert 'untrusted' not in str(output.companies[0].decision_review)
    assert output.companies[0].decision_process == card.decision_process


def _followup(tmp_path, monkeypatch):
    import json
    from value_investment_agent.application.product import event_followup
    from value_investment_agent.application.product.common import sha256_file
    model = product_workbench_from_payload(_payload())
    card = replace(model.companies[0], decision_review=(("Old gap", "No reviewed outcome"),))
    model = replace(model, companies=(card, *model.companies[1:]))
    packet = dict(audit=dict(evidence_integrity_verified=True), events=[dict(
        announcement_id="new-event", sources=[dict(source_url="https://example.test/official.pdf",
            pages=[dict(physical_page=1, text="Company reported payment of 100 on September 29")])])])
    monkeypatch.setattr(event_followup, "prepare_event_source_review", lambda **kwargs: packet)
    value = dict(schema_version="research-event-followup-v1", scope="SOURCE_ANCHORED_EXPLANATION_ONLY",
        symbol=card.symbol, action="no_order", observed_at=model.as_of.isoformat()+"T10:00:00+08:00",
        event_scan=dict(path="scan.json", sha256="a"*64),
        claims=[dict(announcement_id="new-event", label="New outcome", summary="Payment disclosed, liquidity still unknown",
                     anchors=[dict(physical_page=1, excerpt="payment of 100")])],
        historical_labels=["Old gap"], unresolved_questions=["Post-payment cash/debt missing"])
    path = tmp_path / "followup.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return model, packet, value, path, sha256_file(path)


def _apply_followup(*, root, model, path, expected_sha256):
    from value_investment_agent.application.product.event_followup import read_event_followup
    from value_investment_agent.presentation.read_models.event_followup import project_event_followup
    return project_event_followup(model, read_event_followup(root=root, cutoff=model.as_of,
        path=path, expected_sha256=expected_sha256))


def test_followup_preserves_investment_gates_and_keeps_history(tmp_path, monkeypatch):
    model, _, _, path, digest = _followup(tmp_path, monkeypatch)
    result = _apply_followup(root=tmp_path, model=model, path=path, expected_sha256=digest)
    old, new = model.companies[0], result.companies[0]
    assert tuple(step.status for step in new.decision_process) == tuple(step.status for step in old.decision_process)
    for before, after in zip(old.decision_process, new.decision_process):
        if before.key == 'research_gate':
            assert before.reason in after.reason
            assert '披露前阻断记录' in after.reason
            assert 'Post-payment cash/debt missing' in after.next_action
            assert result.audit_evidence[-1].evidence_id in after.evidence_refs
        else:
            assert after == before
    assert new.price == old.price and new.valuation == old.valuation
    assert new.margin_of_safety == old.margin_of_safety
    assert result.portfolio == model.portfolio and result.events == model.events
    assert result.opportunities == model.opportunities
    assert len(result.today_items) == len(model.today_items) + 1
    assert result.today_items[-1].symbol == old.symbol
    assert "不构成买卖建议" in result.today_items[-1].current_status
    assert "No reviewed outcome" in dict(new.decision_review).values()
    assert any(label.startswith("历史缺项记录") for label, _ in new.decision_review)
    assert "Post-payment cash/debt missing" in dict(new.decision_review)["新披露后的待复核事项"]
    assert '新增正式披露已核对原件' in new.latest_change
    assert 'Post-payment cash/debt missing' in new.next_trigger
    assert new.research_status == old.research_status
    assert result.action == "no_order"


def test_followup_company_card_surfaces_new_evidence_before_old_research(tmp_path, monkeypatch):
    from value_investment_agent.presentation.read_models.conditional_expectations import render_company_review_cards
    model, _, _, path, digest = _followup(tmp_path, monkeypatch)
    current = _apply_followup(root=tmp_path, model=model, path=path, expected_sha256=digest)
    report = render_company_review_cards(current)
    assert report.index('### 本次新证据（影响未批准）') < report.index('### 先看研究结论与反证')
    assert report.count('New outcome：Payment disclosed') == 1
    assert '不等于模型、重大性、价格或买卖准入' in report


@pytest.mark.parametrize("problem", ["anchor", "page", "issuer", "future", "scope", "missing_gap", "integrity", "unresolved"])
def test_followup_fails_closed_on_unverified_explanations(tmp_path, monkeypatch, problem):
    import json
    from value_investment_agent.application.product.common import sha256_file
    model, packet, value, path, _ = _followup(tmp_path, monkeypatch)
    if problem == "anchor": value["claims"][0]["anchors"][0]["excerpt"] = "payment of 999"
    elif problem == "page": value["claims"][0]["anchors"][0]["physical_page"] = 2
    elif problem == "issuer": value["symbol"] = "999999"
    elif problem == "future": value["observed_at"] = "2099-01-01T00:00:00+08:00"
    elif problem == "scope": value["scope"] = "APPROVE_BUY"
    elif problem == "missing_gap": value["historical_labels"] = ["Nonexistent"]
    elif problem == "integrity": packet["audit"]["evidence_integrity_verified"] = False
    else: value["unresolved_questions"] = []
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        _apply_followup(root=tmp_path, model=model, path=path, expected_sha256=sha256_file(path))

"""Seven M5 product dispositions reach the bounded read model and workbook."""
from dataclasses import replace
from datetime import date, datetime
import hashlib

import pytest

from product_workbench_candidate_fixture import (
    materialize_synthetic_legacy_packet, synthetic_legacy_packet,
)
from value_investment_agent.application.product.product_workbench_candidate import (
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_EVENTS, SHEET_SYSTEM_AUDIT, build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.m5_event_state_projection import (
    EventStateInput, project_m5_event_states,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    EvidenceRecord, product_workbench_from_payload,
)


def _evidence(root):
    path = root / "evidence" / "m5-synthetic-source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'{"synthetic":true}')
    return EvidenceRecord(
        evidence_id="m5-source", title="Synthetic M5 source",
        artifact_type="synthetic", path="evidence/m5-synthetic-source.json",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        available_at=date(2026, 9, 24),
    )


def _input(root, state):
    return EventStateInput(
        state=state, event_id=f"m5-{state}", company_name="Synthetic Company",
        what_happened="Synthetic disclosure", impact_area="Research",
        evidence=(_evidence(root),),
        published_at=datetime.fromisoformat("2026-09-24T09:00:00+08:00"),
        observed_at=datetime.fromisoformat("2026-09-24T10:00:00+08:00"),
        canonical_event_id="m5-original" if state == "duplicate" else None,
        duplicate_event_id=f"m5-{state}" if state == "duplicate" else None,
        correction_of_event_id="m5-original" if state == "correction" else None,
        previous_conclusion="原结论待证据" if state == "correction" else None,
        corrected_conclusion="更正后仍待证据" if state == "correction" else None,
        missing_evidence="原件" if state == "insufficient_evidence" else None,
        reopen_condition="原件可核验" if state == "insufficient_evidence" else None,
        unavailable_reason="输入缺失" if state == "model_unavailable" else None,
        model_requirements="已核现金流" if state == "model_unavailable" else None,
    )


def _workbook(root, projection):
    packet = synthetic_legacy_packet("2026-09-26T03:00:00+00:00")
    materialize_synthetic_legacy_packet(root, packet)
    payload = build_product_workbench_candidate_payload(
        packet, root=root, m5_event_projection=projection.as_payload(),
    )
    model = product_workbench_from_payload(payload)
    return model, build_product_workbench_workbook(model)


@pytest.mark.parametrize("state,visible,disposition", [
    ("material", True, "USER_VISIBLE_EVENT"),
    ("duplicate", False, "SUPPRESSED_DUPLICATE"),
    ("late", False, "AUDIT_ONLY"),
    ("correction", False, "AUDIT_ONLY"),
    ("nonmaterial", False, "AUDIT_ONLY"),
    ("insufficient_evidence", True, "EVIDENCE_GAP"),
    ("model_unavailable", True, "MODEL_NOT_AVAILABLE"),
])
def test_seven_states_have_distinct_excel_and_audit_dispositions(
    tmp_path, state, visible, disposition,
):
    projection = project_m5_event_states((_input(tmp_path, state),))
    model, book = _workbook(tmp_path, projection)
    assert model.action == "no_order"
    assert len(model.events) == 1 + int(visible)
    decision = model.event_audit_decisions[0]
    assert decision.disposition == disposition
    assert decision.visible is visible
    event_text = " ".join(str(cell.value) for row in book[SHEET_EVENTS] for cell in row)
    audit_text = " ".join(str(cell.value) for row in book[SHEET_SYSTEM_AUDIT] for cell in row)
    assert ("Synthetic disclosure" in event_text) is visible
    assert disposition in audit_text
    assert f"m5-{state}" in audit_text
    if state == "duplicate":
        assert decision.canonical_event_id == "m5-original"
        assert decision.duplicate_event_id == "m5-duplicate"
    if state == "insufficient_evidence":
        assert "原研究结论不变" in event_text
        assert "原件可核验" in event_text
    if state == "model_unavailable":
        assert "暂不可评估" in event_text
        assert "已核现金流" in event_text


@pytest.mark.parametrize("state,changes", [
    ("late", {"affects_research": True}),
    ("correction", {"impact": True}),
])
def test_impactful_late_or_correction_is_visible_without_erasing_history(
    tmp_path, state, changes,
):
    projection = project_m5_event_states((replace(_input(tmp_path, state), **changes),))
    model, book = _workbook(tmp_path, projection)
    assert len(model.events) == 2
    text = " ".join(str(cell.value) for row in book[SHEET_EVENTS] for cell in row)
    assert "Synthetic disclosure" in text
    assert model.event_audit_decisions[0].disposition == "USER_VISIBLE_EVENT"
    if state == "late":
        assert "发布 2026-09-24T09:00:00+08:00" in text
        assert "发现 2026-09-24T10:00:00+08:00" in text
    else:
        assert "原结论待证据" in text
        assert "更正后仍待证据" in text
        assert model.event_audit_decisions[0].correction_of_event_id == "m5-original"


def test_tampered_m5_source_fails_before_product_render(tmp_path):
    projection = project_m5_event_states((_input(tmp_path, "material"),))
    (tmp_path / "evidence" / "m5-synthetic-source.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Evidence hash mismatch"):
        _workbook(tmp_path, projection)


def test_audit_suppression_cannot_be_bypassed_with_a_user_card(tmp_path):
    projection = project_m5_event_states((_input(tmp_path, "duplicate"),)).as_payload()
    projection["events"] = [project_m5_event_states((_input(tmp_path, "material"),)).as_payload()["events"][0]]
    packet = synthetic_legacy_packet("2026-09-26T03:00:00+00:00")
    materialize_synthetic_legacy_packet(tmp_path, packet)
    with pytest.raises(ValueError, match="visible events differ"):
        build_product_workbench_candidate_payload(
            packet, root=tmp_path, m5_event_projection=projection,
        )

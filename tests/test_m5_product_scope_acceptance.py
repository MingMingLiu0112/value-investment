"""Bounded product presentation checks for synthetic M5 event states.

The current product adapter does not consume M5 actual run receipts. These
tests cover only the read-model and Excel contracts reachable today.
"""

from __future__ import annotations

import pytest

from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_EVENTS,
    build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    ACTION_NO_ORDER,
    PRODUCT_WORKBENCH_SCHEMA_VERSION,
    product_workbench_from_payload,
)


def _payload(events: list[dict] | None = None) -> dict:
    return {
        "schema_version": PRODUCT_WORKBENCH_SCHEMA_VERSION,
        "generated_at": "2026-09-26T03:00:00+00:00",
        "as_of": "2026-09-24",
        "action": ACTION_NO_ORDER,
        "overview": {"pending_count": 0},
        "system_health": {
            "status": "EVIDENCE_INSUFFICIENT",
            "message": "Synthetic evidence awaits review.",
        },
        "stages": {
            key: {"status": "WAIT", "detail": "Synthetic pending state."}
            for key in ("m2", "m3", "m4", "m5", "m6")
        },
        "today_items": [],
        "opportunities": [],
        "companies": [],
        "portfolio": {
            "real_data_available": False,
            "status": "NOT_STARTED",
            "connection_hint": "No private portfolio input.",
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": events or [],
        "audit": {
            "evidence": [{
                "evidence_id": "synthetic-evidence",
                "title": "Synthetic event evidence",
                "artifact_type": "synthetic",
                "path": "synthetic/event.json",
                "sha256": "a" * 64,
                "available_at": "2026-09-25",
                "action": ACTION_NO_ORDER,
            }],
        },
    }


def _event(event_type: str) -> dict:
    return {
        "event_id": "synthetic-event-1",
        "event_type": event_type,
        "company_name": "Synthetic Company",
        "what_happened": "Synthetic disclosure was reviewed.",
        "impact_area": "Research thesis",
        "current_conclusion": "Requires human reassessment.",
        "research_action": "REOPEN_RESEARCH",
        "next_step": "Review the synthetic evidence.",
        "evidence_refs": ["synthetic-evidence"],
        "action": ACTION_NO_ORDER,
    }


def test_material_event_reaches_read_model_and_excel_with_evidence() -> None:
    model = product_workbench_from_payload(
        _payload([_event("MATERIAL_REQUIRES_RECALCULATION")])
    )
    assert model.action == ACTION_NO_ORDER
    assert len(model.events) == 1
    event = model.events[0]
    assert event.category.code == "MATERIAL_REQUIRES_RECALCULATION"
    assert event.research_action.code == "REOPEN_RESEARCH"
    assert event.evidence_refs == ("synthetic-evidence",)
    assert event.action == ACTION_NO_ORDER

    sheet = build_product_workbench_workbook(model)[SHEET_EVENTS]
    assert sheet["A4"].value == (
        "需要重新评估的重大事件 | Synthetic Company"
    )
    assert [sheet.cell(6, column).value for column in range(1, 6)] == [
        "Synthetic disclosure was reviewed.",
        "Research thesis",
        "Requires human reassessment.",
        "需要重新研究",
        "Review the synthetic evidence.",
    ]
    assert sheet["F6"].value == "查看证据 (1)"


@pytest.mark.parametrize(
    "state",
    (
        "DUPLICATE",
        "LATE",
        "CORRECTION",
        "NONMATERIAL",
        "INSUFFICIENT_EVIDENCE",
    ),
)
def test_unmapped_m5_states_cannot_be_presented_as_event_categories(
    state: str,
) -> None:
    with pytest.raises(ValueError, match=rf"Unknown event.event_type: {state}"):
        product_workbench_from_payload(_payload([_event(state)]))


def test_no_classified_event_has_explicit_empty_excel_state() -> None:
    model = product_workbench_from_payload(_payload())
    assert model.events == ()
    assert model.action == ACTION_NO_ORDER
    sheet = build_product_workbench_workbook(model)[SHEET_EVENTS]
    assert sheet["A4"].value == "当前没有已分类的用户事件。"

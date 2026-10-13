"""Compose one company's already-published research into the workbench contract.

The projection rearranges hash-bound publication artifacts that the API has
already verified: the published company card inside the product read model and,
when the symbol has one, its bound value-decision explanation. It never prices a
security, recomputes a valuation, promotes research state or emits an order, and
it reports missing evidence as null or an explicit status instead of a guess.
"""
from __future__ import annotations

from typing import Any


# The published decision process, in reading order. Kept verbatim so the page can
# show exactly the gates the publication recorded.
GATE_KEYS = ("financial_facts", "business_quality", "model_applicability", "valuation",
             "price_bridge", "research_gate", "portfolio_gate", "decision_gate")


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _object(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list:
    return list(value) if isinstance(value, list) else []


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _strings(value: Any) -> list[str]:
    return [row for row in _items(value) if isinstance(row, str)]


def _gate(company: dict, key: str) -> dict | None:
    for row in _items(company.get("decision_process")):
        if isinstance(row, dict) and row.get("key") == key:
            return {"key": key, "status": _text(row.get("status")), "reason": _text(row.get("reason")),
                    "next_action": _text(row.get("next_action")),
                    "evidence_refs": [ref for ref in _items(row.get("evidence_refs"))
                                      if isinstance(ref, str)]}
    return None


def _assessment(value: Any) -> dict | None:
    """Copy a published company-card assessment without loosening its status."""
    card = _object(value)
    if not card:
        return None
    return {"status": _object(card.get("status")).get("code"),
            "label": _text(_object(card.get("status")).get("user_label")),
            "available": card.get("available") if isinstance(card.get("available"), bool) else None,
            "value_text": _text(card.get("value_text")),
            "unavailable_reason": _text(card.get("unavailable_reason")),
            "needed_evidence": _text(card.get("needed_evidence")),
            "evidence_refs": [ref for ref in _items(card.get("evidence_refs"))
                              if isinstance(ref, str)]}


def _reading_order(company: dict) -> list[dict]:
    rows = []
    for row in _items(company.get("decision_review")):
        if (isinstance(row, (list, tuple)) and len(row) == 2
                and isinstance(row[0], str) and isinstance(row[1], str)):
            rows.append({"label": row[0], "value": row[1]})
    return rows


def _evidence(value: Any) -> list[dict]:
    rows = []
    for ref in _items(value):
        row = _object(ref)
        if isinstance(row.get("id"), str) and isinstance(row.get("path"), str):
            rows.append({"id": row["id"], "path": row["path"],
                         "sha256": row.get("sha256") if isinstance(row.get("sha256"), str) else None})
    return rows


def _quote_sources(value: Any) -> list[dict]:
    """Keep only the two provider documents behind the verified close."""
    rows = []
    for ref in _items(value):
        row = _object(ref)
        if row.get("kind") != "quote_provider_document":
            continue
        rows.append({"provider": _text(row.get("provider")), "source_url": _text(row.get("source_url")),
                     "fetched_at": _text(row.get("fetched_at")),
                     "sha256": row.get("sha256") if isinstance(row.get("sha256"), str) else None})
    return rows


def _price_bridge_execution(value: Any, published_bridge_status: Any) -> dict | None:
    """Copy the executed admission verdict; never recompute a price or a margin.

    The publication owns the research-bound bridge. This block only reports what
    the shared admission said about the registered close, and the two must agree
    (``READY``) before any price comparison can be called eligible.
    """
    row = _object(value)
    if not _text(row.get("schema_version")):
        return None
    quote = _object(row.get("quote"))
    case = _object(row.get("research_case"))
    pointer = _object(row.get("pointer"))
    admitted = row.get("price_admitted") if isinstance(row.get("price_admitted"), bool) else None
    return {
        "schema_version": _text(row.get("schema_version")),
        "status": _text(row.get("status")),
        "reason": _text(row.get("reason")),
        "next_step": _text(row.get("next_step")),
        "price_admitted": admitted,
        "comparison_eligible": bool(admitted and _text(published_bridge_status) == "READY"),
        "quote_date": _text(quote.get("quote_date")),
        "display_price": _text(quote.get("display_price")),
        "collected_at": _text(quote.get("collected_at")),
        "display_scope": _text(quote.get("display_scope")),
        "is_historical_close": (quote.get("is_historical_close")
                                if isinstance(quote.get("is_historical_close"), bool) else None),
        "latest_completed_session": _text(quote.get("latest_completed_session")),
        "bundle_path": _text(quote.get("bundle_path")),
        "bundle_sha256": _text(quote.get("bundle_sha256")),
        "research_day": _text(row.get("research_day")),
        "research_version": _text(case.get("package_version")),
        "pointer_path": _text(pointer.get("path")),
        "pointer_sha256": _text(pointer.get("sha256")),
        "sources": _quote_sources(row.get("sources")),
    }


def project_value_decision_detail(*, symbol: str, company: dict | None,
                                  explanation: dict | None, binding_status: str = "NOT_BOUND",
                                  binding: dict | None = None,
                                  binding_blockers: list[str] | None = None,
                                  price_bridge_execution: dict | None = None) -> dict:
    """Return the spec fields for one company, all of them traceable to an artifact."""
    company = _object(company)
    explanation = _object(explanation)
    valuation = _object(explanation.get("valuation"))
    price_context = _object(explanation.get("price_context"))
    bridge = _object(price_context.get("price_bridge"))
    zone = _object(price_context.get("price_attractiveness"))
    validity = _object(explanation.get("model_validity"))
    rule = _object(explanation.get("rule_evidence"))
    valuation_range = _object(explanation.get("valuation_range"))
    research_status = _object(company.get("research_status"))
    price_card = _assessment(company.get("price"))
    price_reason = (price_card or {}).get("unavailable_reason")
    return {
        "symbol": symbol,
        "company_name": (_text(explanation.get("company_name"))
                         or _text(company.get("company_name"))),
        "action": "no_order",
        "research_binding": {
            "status": binding_status,
            "path": _text(_object(binding).get("path")),
            "sha256": _text(_object(binding).get("sha256")),
        },
        "research_status": {
            "code": _text(research_status.get("code")),
            "label": _text(research_status.get("user_label")),
            "case_status": _text(explanation.get("research_status")),
            "financial_period": _text(explanation.get("financial_period")),
            "evidence_scope": _text(explanation.get("evidence_scope")),
        },
        "decision_cutoff": _text(explanation.get("decision_as_of")),
        "research_version": _text(explanation.get("research_version")),
        "source_version": (_text(bridge.get("model_version")) or _text(valuation.get("model_version"))
                           or _text(valuation.get("model_type"))),
        "financial_facts_status": _gate(company, "financial_facts"),
        "business_quality_status": _gate(company, "business_quality"),
        "valuation_model": _text(valuation.get("model_type")),
        "valuation": {
            "model_type": _text(valuation.get("model_type")),
            "model_version": _text(valuation.get("model_version")),
            "valuation_date": _text(valuation.get("valuation_date")),
            "status": _text(valuation.get("status")) or _text(_object(valuation.get("assumptions")).get("status")),
            "confidence": _text(valuation.get("confidence")),
            "bear": _first(valuation_range.get("bear"), valuation.get("bear_value")),
            "base": _first(valuation_range.get("base"), valuation.get("base_value")),
            "bull": _first(valuation_range.get("bull"), valuation.get("bull_value")),
            "currency": _text(valuation_range.get("currency")),
            "basis": _text(valuation_range.get("basis")),
            "disclaimer": _text(_object(valuation.get("assumptions")).get("disclaimer")),
            "scope": _text(_object(valuation.get("assumptions")).get("scope")),
        },
        "valuation_confidence": _text(valuation.get("confidence")),
        "model_validity": {
            "status": _text(validity.get("status")),
            "model_id": _text(validity.get("model_id")),
            "model_as_of": _text(validity.get("model_as_of")),
            "valid_from": _text(validity.get("valid_from")),
            "last_material_event_check": _text(validity.get("last_material_event_check")),
            "blockers": _strings(validity.get("blockers")),
        },
        "price": {
            "current_price": bridge.get("current_price"),
            "price_as_of": _text(bridge.get("quote_date")),
            "quote_admission_status": _text(bridge.get("quote_status")),
            "bridge_status": _text(bridge.get("bridge_status")),
            "model_validity_status": _text(bridge.get("model_validity_status")),
            "margin_to_base": bridge.get("margin_to_base"),
            "margin_to_bear": bridge.get("margin_to_bear"),
            "attractiveness_status": _text(zone.get("status")),
            "attractiveness_label": _text(zone.get("display_status")),
            "unavailable_reason": price_reason,
            "needed_evidence": (price_card or {}).get("needed_evidence"),
            "blockers": _strings(bridge.get("blockers")),
        },
        "price_as_of": _text(bridge.get("quote_date")),
        "quote_admission_status": _text(bridge.get("quote_status")),
        "price_bridge_execution": _price_bridge_execution(price_bridge_execution,
                                                          bridge.get("bridge_status")),
        "margin_to_base": bridge.get("margin_to_base"),
        "margin_to_bear": bridge.get("margin_to_bear"),
        "gates": [_gate(company, key) for key in GATE_KEYS],
        "research_gate": _gate(company, "research_gate"),
        "decision_gate": _gate(company, "decision_gate"),
        "portfolio_gate": _gate(company, "portfolio_gate"),
        "suggested_state": {
            "value": _text(explanation.get("candidate_action")),
            "human_review_required": (explanation.get("requires_human_review")
                                      if isinstance(explanation.get("requires_human_review"), bool) else None),
            "boundary": "研究状态不等于买卖信号；系统只输出待人工复核的候选，不下单。",
        },
        "candidate_explanation": _text(explanation.get("candidate_explanation")),
        "position_guidance": explanation.get("position_guidance"),
        "portfolio_input_status": _text(explanation.get("portfolio_input_status")),
        "thesis": _text(explanation.get("thesis")),
        "return_driver": _text(explanation.get("return_driver")),
        "mispricing_hypothesis": _text(explanation.get("mispricing_hypothesis")),
        "blockers": [*_first_present(_strings(explanation.get("blockers")),
                                     _strings(rule.get("blockers"))),
                     *(binding_blockers or [])],
        "next_events": _items(explanation.get("next_events")),
        "reopen_triggers": [text for text in (_text(_object(row).get("text"))
                                              for row in _items(explanation.get("next_events"))) if text],
        "exit_conditions": _strings(explanation.get("exit_conditions")),
        "evidence_refs": _evidence(explanation.get("evidence_refs")),
        "reading_order": _reading_order(company),
        "valuation_provenance": {
            "bound_decision": _text(explanation.get("decision_as_of")),
            "bound_research_version": _text(explanation.get("research_version")),
            "registered_research_note": ("研究底稿按登记版本登记；上方情景来自当前绑定的决策解释。"),
        },
    }


def _first_present(*lists: list[str]) -> list[str]:
    """Prefer the decision payload blockers; fall back to the rule evidence list."""
    for rows in lists:
        if rows:
            return rows
    return []

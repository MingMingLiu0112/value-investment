from dataclasses import replace
from datetime import date
from decimal import Decimal
import json

import pytest

from value_investment_agent.model_validity import (
    MaterialEvent,
    ModelValidity,
    evaluate_model_validity,
)
from value_investment_agent.price_bridge import (
    bridge,
    bridge_with_quote,
    pending_price_bridge_for_incomplete_valuation,
    price_bridge_from_payload,
)
from value_investment_agent.quote_snapshot import QuoteSnapshot
from value_investment_agent.valuation_models.base import ValuationResult


MODEL_REF = {
    "id": "model-a",
    "path": "fixtures/model-a.json",
    "sha256": "fixture-v1",
}
QUOTE_REF = {
    "id": "quote",
    "path": "fixtures/quote.json",
    "sha256": "quote-hash",
}


def valuation():
    return ValuationResult(
        "600519",
        "fixture",
        date(2026, 9, 16),
        Decimal("400"),
        Decimal("500"),
        Decimal("600"),
        "中",
        {},
        [],
        [MODEL_REF],
        [],
        "ready",
        "fixture-v1",
    )


def validity(status="VALID"):
    if status == "VALID":
        return ModelValidity(
            "fixture-v1",
            "600519",
            date(2026, 9, 16),
            date(2026, 9, 16),
            date(2026, 9, 18),
            False,
            False,
            False,
            "VALID",
            [],
            [{"id": "events", "sha256": "event-scan-hash"}],
        )
    return ModelValidity(
        "fixture-v1",
        "600519",
        date(2026, 9, 16),
        date(2026, 9, 16),
        date(2026, 9, 18) if status == "STALE" else None,
        status == "STALE",
        False,
        status == "STALE",
        status,
        [] if status == "STALE" else ["event check missing"],
        [{"id": "event"}],
    )


def test_missing_quote_keeps_valuation_and_returns_pending_bridge():
    outcome = bridge(
        valuation(),
        validity(),
        quote_date=None,
        current_price=None,
        quote_status="PENDING_EXTERNAL_DATA",
        evidence_refs=[],
    )
    assert outcome.bridge_status == "PENDING_EXTERNAL_DATA"
    assert outcome.current_price is None
    assert valuation().base_value == Decimal("500")


def test_valid_later_quote_can_bridge_without_same_date_model():
    outcome = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert outcome.bridge_status == "READY"
    assert outcome.margin_to_base == Decimal("0.1")


def test_evaluator_allows_later_quote_after_no_material_event():
    checked = evaluate_model_validity(
        model_id="fixture-v1",
        symbol="600519",
        model_as_of=date(2026, 9, 16),
        valid_from=date(2026, 9, 16),
        quote_date=date(2026, 9, 18),
        events=[],
        event_scan_evidence_refs=[{"id": "event-scan"}],
    )
    outcome = bridge(
        valuation(),
        checked,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert checked.status == "VALID"
    assert outcome.bridge_status == "READY"


def test_evaluator_stales_model_when_new_filing_precedes_quote():
    event = MaterialEvent(
        date(2026, 9, 17),
        "financial_statement",
        "interim filing",
        [{"id": "filing"}],
    )
    checked = evaluate_model_validity(
        model_id="fixture-v1",
        symbol="600519",
        model_as_of=date(2026, 9, 16),
        valid_from=date(2026, 9, 16),
        quote_date=date(2026, 9, 18),
        events=[event],
        event_scan_evidence_refs=[{"id": "event-scan"}],
    )
    outcome = bridge(
        valuation(),
        checked,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert checked.status == "STALE"
    assert outcome.bridge_status == "STALE_MODEL"


def test_evaluator_requires_event_scan_evidence():
    checked = evaluate_model_validity(
        model_id="fixture-v1",
        symbol="600519",
        model_as_of=date(2026, 9, 16),
        valid_from=date(2026, 9, 16),
        quote_date=date(2026, 9, 18),
        events=[],
        event_scan_evidence_refs=[],
    )
    assert checked.status == "UNKNOWN"
    assert bridge(
        valuation(),
        checked,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    ).bridge_status == "INVALID"


def test_bridge_refuses_unchecked_validity_after_quote_date():
    unchecked = ModelValidity(
        "fixture-v1",
        "600519",
        date(2026, 9, 16),
        date(2026, 9, 16),
        date(2026, 9, 17),
        False,
        False,
        False,
        "VALID",
        [],
        [{"id": "event-scan"}],
    )
    outcome = bridge(
        valuation(),
        unchecked,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert outcome.bridge_status == "INVALID"


def test_stale_model_refuses_price_comparison():
    stale = ModelValidity(
        "fixture-v1",
        "600519",
        date(2026, 9, 16),
        date(2026, 9, 16),
        date(2026, 9, 18),
        True,
        False,
        True,
        "STALE",
        ["new report"],
        [{"id": "event"}],
    )
    outcome = bridge(
        valuation(),
        stale,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert outcome.bridge_status == "STALE_MODEL"


def test_incomplete_valuation_keeps_a_pending_bridge_without_inventing_validity():
    incomplete = ValuationResult(
        "000333",
        "FCFF",
        date(2025, 12, 31),
        None,
        None,
        None,
        "低",
        {"scope": "input gate"},
        [],
        [{"id": "facts"}],
        ["missing_input"],
        "not_ready",
        "fcff-input-gate-v1",
    )
    outcome = pending_price_bridge_for_incomplete_valuation(
        incomplete,
        evidence_refs=incomplete.evidence_refs,
    )

    assert outcome.bridge_status == "PENDING_EXTERNAL_DATA"
    assert outcome.model_validity_status == "UNKNOWN"
    assert outcome.quote_status == "PENDING_EXTERNAL_DATA"
    assert (outcome.current_price, outcome.margin_to_bear, outcome.margin_to_base) == (
        None,
        None,
        None,
    )
    assert "正式估值未形成，价格桥接不启用" in outcome.blockers
    assert outcome.evidence_refs == [{"id": "facts"}]


def test_incomplete_bridge_adapter_rejects_an_existing_scenario_value():
    with pytest.raises(ValueError, match="only valid when no scenario value exists"):
        pending_price_bridge_for_incomplete_valuation(
            valuation(),
            evidence_refs=valuation().evidence_refs,
        )


def test_cross_company_model_validity_cannot_become_ready():
    other = ModelValidity(
        "fixture-v1",
        "000333",
        date(2026, 9, 16),
        date(2026, 9, 16),
        date(2026, 9, 18),
        False,
        False,
        False,
        "VALID",
        [],
        [{"id": "other-scan"}],
    )
    outcome = bridge(
        valuation(),
        other,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert outcome.bridge_status == "INVALID"
    assert "valuation and model validity symbols differ" in outcome.blockers


def test_wrong_model_snapshot_cannot_become_ready():
    other = replace(validity(), model_id="other-snapshot")
    outcome = bridge(
        valuation(),
        other,
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    assert outcome.bridge_status == "INVALID"
    assert "valuation model snapshot" in outcome.blockers[-1]


def test_verified_quote_without_hash_addressed_evidence_is_invalid():
    outcome = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[{"id": "quote"}],
    )
    assert outcome.bridge_status == "INVALID"
    assert any("hash-addressed evidence" in blocker for blocker in outcome.blockers)


def test_unverified_quote_and_wrong_quote_identity_are_invalid():
    unverified = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="unverified",
        evidence_refs=[QUOTE_REF],
    )
    assert unverified.bridge_status == "INVALID"
    assert "报价未通过核验" in unverified.blockers

    wrong_quote = bridge_with_quote(
        valuation(),
        validity(),
        QuoteSnapshot(
            symbol="000333",
            quote_date=date(2026, 9, 18),
            current_price=Decimal("450"),
            status="verified_close",
            evidence_refs=[QUOTE_REF],
        ),
    )
    assert wrong_quote.bridge_status == "INVALID"
    assert "valuation and quote symbols differ" in wrong_quote.blockers


def test_tampered_direct_bridge_margins_are_rejected():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    with pytest.raises(ValueError, match="margins must be recomputed"):
        replace(ready, margin_to_base=Decimal("0.99"))


def test_json_restore_rejects_conflicting_security_identity():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    tampered = json.loads(ready.to_json())
    tampered["symbol"] = "000333"
    tampered["quote_symbol"] = "000333"
    with pytest.raises(ValueError, match="symbols differ"):
        price_bridge_from_payload(valuation(), tampered)


def test_legacy_ready_payload_is_revalidated_with_its_model_validity():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    legacy = {
        key: value
        for key, value in json.loads(ready.to_json()).items()
        if key
        not in {
            "schema_version",
            "model_id",
            "model_version",
            "model_as_of",
            "quote_symbol",
            "valuation_bear_value",
            "valuation_base_value",
            "quote_evidence_refs",
        }
    }
    legacy["evidence_refs"] = [QUOTE_REF]

    restored = price_bridge_from_payload(
        valuation(),
        legacy,
        model_validity_payload=json.loads(validity().to_json()),
    )
    assert restored.bridge_status == "READY"
    assert "legacy_price_bridge_contract_revalidated" in restored.blockers

    with pytest.raises(ValueError, match="Legacy READY bridge requires"):
        price_bridge_from_payload(valuation(), legacy)


def test_legacy_ready_payload_rejects_wrong_validity_symbol():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    legacy = {
        key: value
        for key, value in json.loads(ready.to_json()).items()
        if key not in {
            "schema_version", "model_id", "model_version", "model_as_of",
            "quote_symbol", "valuation_bear_value", "valuation_base_value",
            "quote_evidence_refs",
        }
    }
    legacy["evidence_refs"] = [QUOTE_REF]
    wrong_validity = json.loads(validity().to_json())
    wrong_validity["symbol"] = "000333"

    with pytest.raises(ValueError, match="symbols differ"):
        price_bridge_from_payload(
            valuation(),
            legacy,
            model_validity_payload=wrong_validity,
        )


def test_json_restore_rejects_model_version_conflict():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    tampered = json.loads(ready.to_json())
    tampered["model_version"] = "other-v1"

    with pytest.raises(ValueError, match="model version"):
        price_bridge_from_payload(valuation(), tampered)


def test_json_restore_rejects_quote_without_hash_evidence():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    tampered = json.loads(ready.to_json())
    tampered["quote_evidence_refs"] = [{"id": "quote"}]

    with pytest.raises(ValueError, match="verified quote evidence"):
        price_bridge_from_payload(valuation(), tampered)


def test_json_restore_rejects_tampered_margin():
    ready = bridge(
        valuation(),
        validity(),
        quote_date=date(2026, 9, 18),
        current_price=Decimal("450"),
        quote_status="verified_close",
        evidence_refs=[QUOTE_REF],
    )
    tampered = json.loads(ready.to_json())
    tampered["margin_to_base"] = "0.99"

    with pytest.raises(ValueError, match="margins must be recomputed"):
        price_bridge_from_payload(valuation(), tampered)

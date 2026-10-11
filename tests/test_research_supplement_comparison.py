"""Pinned supplement comparisons never advance research or admission."""
from copy import deepcopy
import hashlib
import json

import pytest

from value_investment_agent.application.product.research_supplement_comparison import (
    compare_research_supplements,
)


def _write(root, name, payload):
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _payload(root, role):
    source = _write(root, "source.json", {"original": "retained"})
    common = dict(symbol="600887", action="no_order", generated_at="2026-10-11T01:00:00Z",
                  source_bindings=[source], price_admitted=False)
    if role == "financial_review":
        return dict(**common, status="SOURCE_VERIFIED_RESEARCH_SUPPLEMENT_NOT_ADMITTED",
                    financial_period_end="2026-06-30", facts=[{"value": "10", "source_binding": source}],
                    calculations={"profit": "10"}, limitations=["Not normalized"])
    return dict(**common, schema_version="finite-neutral-valuation-proposal-v1",
                original_research_as_of="2026-09-22", original_valuation_date="2026-09-22",
                choices=[{"valuation": {"base_value": "10", "generated_at": "old"}}],
                normalized_profit=None, assumptions_approved=False)


def _compare(root, role, before, after):
    old = _write(root, "old.json", before)
    new = _write(root, "new.json", after)
    receipt = _write(root, "receipt.json", dict(schema_version="daily-trade-assistant-receipt-v1",
        symbol="600887", action="no_order", outputs={role: old, "report": {"path": "ignored"}}))
    return compare_research_supplements(root=root, symbol="600887",
        current_bindings=[dict(role=role, **new), {"role": "ignored", "path": "../ignored"}],
        previous_receipt_path=receipt["path"], previous_receipt_sha256=receipt["sha256"])


@pytest.mark.parametrize("role", ["financial_review", "valuation_proposal"])
def test_generation_only_is_unchanged_and_dates_retained(tmp_path, role):
    before = _payload(tmp_path, role)
    after = deepcopy(before)
    after["generated_at"] = "later"
    if role == "valuation_proposal":
        after["choices"][0]["valuation"]["generated_at"] = "later"
    result = _compare(tmp_path, role, before, after)
    assert result["roles"][role]["status"] == "UNCHANGED"
    assert "generated_at" not in result["roles"][role]["fields"]
    date_field = "financial_period_end" if role == "financial_review" else "original_research_as_of"
    assert result["roles"][role]["fields"][date_field]["current"] == before[date_field]
    assert result["action"] == "no_order"
    for flag in ("approval_changed", "decision_changed", "research_date_advanced", "current_admission"):
        assert result[flag] is False
    assert result["official_facts_status"] == "NO_NEW_DISCLOSED_FACTS_ESTABLISHED"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("role,field", [("financial_review", "calculations"), ("valuation_proposal", "choices")])
def test_semantic_changes_and_missing_fields(tmp_path, role, field):
    before = _payload(tmp_path, role)
    after = deepcopy(before)
    after[field] = {"revised": "11"}
    after["new_research_note"] = "needs review"
    result = _compare(tmp_path, role, before, after)["roles"][role]
    assert result["status"] == "CHANGED_RESEARCH_ARTIFACT"
    assert result["fields"][field]["status"] == "CHANGED_RESEARCH_ARTIFACT"
    assert result["fields"]["new_research_note"]["status"] == "UNAVAILABLE"


def test_missing_previous_and_unavailable_supplement(tmp_path):
    binding = _write(tmp_path, "failed.json", dict(action="no_order",
        status="RESEARCH_SUPPLEMENT_UNAVAILABLE", error="missing original", decision_changed=False))
    result = compare_research_supplements(root=tmp_path, symbol="600887",
        current_bindings=[dict(role="financial_review", **binding)])
    assert all(row["status"] == "UNAVAILABLE" for row in result["roles"].values())
    assert result["roles"]["financial_review"]["current_reason"] == "missing original"


@pytest.mark.parametrize("mutation", ["action", "symbol", "price_admitted", "source", "nested_action", "nested_source"])
def test_rejects_tampering(tmp_path, mutation):
    payload = _payload(tmp_path, "valuation_proposal")
    if mutation == "source":
        (tmp_path / "source.json").write_text("drift", encoding="utf-8")
    elif mutation == "nested_source":
        payload["choices"][0]["source_binding"] = {"path": "../outside", "sha256": "0" * 64}
    elif mutation == "nested_action":
        payload["choices"][0]["action"] = "order"
    else:
        payload[mutation] = {"action": "order", "symbol": "600519", "price_admitted": True}[mutation]
    binding = _write(tmp_path, "input.json", payload)
    with pytest.raises(ValueError):
        compare_research_supplements(root=tmp_path, symbol="600887",
            current_bindings=[dict(role="valuation_proposal", **binding)])


def test_pins_containment_duplicates_and_receipt_identity(tmp_path):
    payload = _payload(tmp_path, "valuation_proposal")
    binding = dict(role="valuation_proposal", **_write(tmp_path, "input.json", payload))
    for bad in ({**binding, "sha256": "0" * 64}, {**binding, "path": "../outside"},
                {**binding, "sha256": "invalid"}):
        with pytest.raises(ValueError):
            compare_research_supplements(root=tmp_path, symbol="600887", current_bindings=[bad])
    with pytest.raises(ValueError, match="duplicate"):
        compare_research_supplements(root=tmp_path, symbol="600887", current_bindings=[binding, binding])
    for kwargs in ({"previous_receipt_path": "missing"}, {"previous_receipt_sha256": "0" * 64}):
        with pytest.raises(ValueError, match="both"):
            compare_research_supplements(root=tmp_path, symbol="600887", current_bindings=[], **kwargs)
    for key, value in (("symbol", "600519"), ("action", "order"), ("schema_version", "other")):
        receipt = dict(schema_version="daily-trade-assistant-receipt-v1", symbol="600887",
                       action="no_order", outputs={})
        receipt[key] = value
        pin = _write(tmp_path, "receipt.json", receipt)
        with pytest.raises(ValueError):
            compare_research_supplements(root=tmp_path, symbol="600887", current_bindings=[],
                previous_receipt_path=pin["path"], previous_receipt_sha256=pin["sha256"])


def test_previous_output_is_verified_and_missing_roles_stay_unavailable(tmp_path):
    payload = _payload(tmp_path, "financial_review")
    old = _write(tmp_path, "old.json", payload)
    receipt = _write(tmp_path, "receipt.json", dict(schema_version="daily-trade-assistant-receipt-v1",
        symbol="600887", action="no_order", outputs={"financial_review": old}))
    args = dict(root=tmp_path, symbol="600887", current_bindings=[],
                previous_receipt_path=receipt["path"], previous_receipt_sha256=receipt["sha256"])
    result = compare_research_supplements(**args)
    assert result["roles"]["financial_review"]["previous_available"]
    assert result["roles"]["financial_review"]["status"] == "UNAVAILABLE"
    (tmp_path / "old.json").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        compare_research_supplements(**args)


@pytest.mark.parametrize("raw", ['{"action":"no_order","action":"order"}',
                               '{"action":"no_order","value":NaN}',
                               '{"action":"no_order","value":1e999}'])
def test_rejects_ambiguous_or_nonfinite_json(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="finite UTF-8 JSON"):
        compare_research_supplements(root=tmp_path, symbol="600887", current_bindings=[{
            "role": "valuation_proposal", "path": path,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}])


def test_json_types_are_semantic_and_input_files_remain_unchanged(tmp_path):
    before = _payload(tmp_path, "financial_review")
    after = deepcopy(before)
    before["calculations"] = {"value": 1}
    after["calculations"] = {"value": True}
    result = _compare(tmp_path, "financial_review", before, after)
    assert result["roles"]["financial_review"]["fields"]["calculations"]["status"] == "CHANGED_RESEARCH_ARTIFACT"
    assert json.loads((tmp_path / "old.json").read_text(encoding="utf-8")) == before
    assert json.loads((tmp_path / "new.json").read_text(encoding="utf-8")) == after


def test_detects_source_drift_during_comparison(tmp_path, monkeypatch):
    from value_investment_agent.application.product import research_supplement_comparison as module

    payload = _payload(tmp_path, "financial_review")
    binding = _write(tmp_path, "input.json", payload)
    original_hash = module.sha256_file
    calls = 0

    def changing_hash(path):
        nonlocal calls
        if path.name == "source.json":
            calls += 1
            if calls == 2:
                path.write_text("drift", encoding="utf-8")
        return original_hash(path)

    monkeypatch.setattr(module, "sha256_file", changing_hash)
    with pytest.raises(ValueError, match="hash mismatch|changed during comparison"):
        compare_research_supplements(root=tmp_path, symbol="600887",
            current_bindings=[dict(role="financial_review", **binding)])


@pytest.mark.parametrize("drift", [None, "output", "evidence", "receipt"])
def test_historical_implementation_provenance_is_separate_from_evidence(tmp_path, drift):
    payload = _payload(tmp_path, "financial_review")
    old = _write(tmp_path, "old.json", payload)
    current = _write(tmp_path, "current.json", payload)
    implementation = _write(tmp_path, "renderer.json", {"implementation": "historical"})
    receipt = _write(tmp_path, "receipt.json", dict(schema_version="daily-trade-assistant-receipt-v1",
        symbol="600887", action="no_order", outputs={"financial_review": old},
        implementation_bindings=[implementation]))
    (tmp_path / "renderer.json").write_text("current implementation differs", encoding="utf-8")
    args = dict(root=tmp_path, symbol="600887",
        current_bindings=[dict(role="financial_review", **current)],
        previous_receipt_path=receipt["path"], previous_receipt_sha256=receipt["sha256"])
    if drift:
        target = {"output": "old.json", "evidence": "source.json", "receipt": "receipt.json"}[drift]
        (tmp_path / target).write_text("drift", encoding="utf-8")
        with pytest.raises(ValueError, match="hash mismatch"):
            compare_research_supplements(**args)
        return
    result = compare_research_supplements(**args)
    assert result["roles"]["financial_review"]["status"] == "UNCHANGED"
    assert result["previous_receipt_provenance"] == {
        "receipt_path": receipt["path"], "receipt_sha256": receipt["sha256"],
        "scope": "HISTORICAL_RUN_PROVENANCE_NOT_CURRENT_IMPLEMENTATION"}
    assert {item["path"] for item in result["source_bindings"]} == {
        "old.json", "current.json", "source.json"}
    from value_investment_agent.application.product.research_publication_input import (
        _build_research_publication_input,
    )

    comparison = _write(tmp_path, "comparison.json", result)
    envelope = _write(tmp_path, "read-model.json", dict(
        schema_version="historical-company-read-model-preview-v1", action="no_order",
        canonical_written=False, historical_preview=True, snapshot={"action": "no_order"},
        research_supplement_bindings=[dict(role="research_supplement_comparison", **comparison)]))
    publication = _build_research_publication_input(root=tmp_path,
        read_model_path=tmp_path / envelope["path"], expected_sha256=envelope["sha256"])
    assert {item["path"] for item in publication["source_bindings"]} == {
        "read-model.json", "comparison.json", "old.json", "current.json", "source.json"}


def test_previous_receipt_is_rehashed_at_final_check(tmp_path, monkeypatch):
    from value_investment_agent.application.product import research_supplement_comparison as module

    receipt = _write(tmp_path, "receipt.json", dict(schema_version="daily-trade-assistant-receipt-v1",
        symbol="600887", action="no_order", outputs={}))
    original_hash = module.sha256_file
    calls = 0

    def changing_hash(path):
        nonlocal calls
        if path.name == "receipt.json":
            calls += 1
            if calls == 2:
                path.write_text("drift", encoding="utf-8")
        return original_hash(path)

    monkeypatch.setattr(module, "sha256_file", changing_hash)
    with pytest.raises(ValueError, match="changed during comparison"):
        compare_research_supplements(root=tmp_path, symbol="600887", current_bindings=[],
            previous_receipt_path=receipt["path"], previous_receipt_sha256=receipt["sha256"])

"""Synthetic bound public drafts exercise real source and model verification."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json

import pytest

from test_d2_source_bound_package_contract import market_package, source_package
from value_investment_agent.application.product.research_draft import (
    BOUND_DRAFT_SCHEMA, DRAFT_STATUS, POINTER_PATH, POINTER_SCHEMA,
    _verify_bound_draft, load_current_research_draft,
)
from value_investment_agent.application.product.source_bound_inputs import source_catalog_sha256
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.model_validity import evaluate_model_validity
from value_investment_agent.valuation_models.residual_income import ResidualIncomeEquityValuationModel


def write_binding(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    path.write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


def publish(root, payload):
    binding = write_binding(root, "artifacts/current/synthetic-bound/draft.json", payload)
    write_binding(root, POINTER_PATH.as_posix(), {
        "schema_version": POINTER_SCHEMA, "action": "no_order",
        "drafts": {payload["symbol"]: binding},
    })


@pytest.fixture
def bound_draft(market_package):
    root, original, _ = market_package
    package = deepcopy(original)
    package["requested_model"] = "residual_income_or_equity_value"
    source = package["sources"][0]
    source["kind"] = "official_issuer_filing"
    contract = package["source_contract"]
    contract.update(schema_version="source-bound-research-inputs-v3",
        share_basis="issued_ordinary_shares",
        source_catalog_sha256=source_catalog_sha256(package["sources"]))
    summary = package["research_case"]["financial_summary"]
    summary.update(parent_equity_cny="1000", issued_ordinary_shares="100")
    contract["fact_anchors"] = [dict(field=field, source_id=source["id"],
        physical_page=7, source_value=summary[field], unit=unit, scope=scope,
        period_end=package["facts"]["as_of"], sha256=source["sha256"])
        for field, unit, scope in (
            ("parent_equity_cny", "CNY", "consolidated_parent_equity"),
            ("issued_ordinary_shares", "shares", "issued_ordinary_shares"))]
    contract["consumed_fact_bindings"] = [
        dict(field_path="operating_inputs.start_book_equity", anchor_field="parent_equity_cny"),
        dict(field_path="operating_inputs.ordinary_shares", anchor_field="issued_ordinary_shares"),
    ]
    descriptor = build_descriptor(package, root=root)
    result = ResidualIncomeEquityValuationModel().value(descriptor.facts, descriptor.research_case)
    validity_input = descriptor.model_validity_input
    validity = evaluate_model_validity(
        model_id=validity_input.model_id, symbol=descriptor.symbol,
        model_as_of=result.valuation_date, valid_from=validity_input.valid_from,
        quote_date=descriptor.quote.quote_date, events=list(validity_input.events),
        event_scan_evidence_refs=list(validity_input.event_scan_evidence_refs),
        blockers=list(validity_input.blockers), event_scan=validity_input.event_scan,
    )
    validity_policy = json.loads(validity.to_json())
    now = descriptor.point_in_time.computed_at + timedelta(hours=1)
    payload = {
        "schema_version": BOUND_DRAFT_SCHEMA, "action": "no_order",
        "symbol": package["symbol"], "status": DRAFT_STATUS,
        "available_at": descriptor.point_in_time.computed_at.isoformat(),
        "research_as_of": descriptor.point_in_time.research_as_of.isoformat(),
        "financial_facts": deepcopy(summary),
        "model_validity": {key: validity_policy[key] for key in
            ("model_id", "model_as_of", "last_material_event_check", "status", "blockers")},
        "model_input_binding": {
            "package": write_binding(root, "artifacts/current/synthetic-bound/package.json", package),
            "input_sha256": descriptor.input_sha256,
        },
        "valuation": {
            "status": "conditional_research_only", "model_type": result.model_type,
            "model_version": result.model_version, "confidence": result.confidence,
            "valuation_date": result.valuation_date.isoformat(),
            "assumptions": [{key: row.as_policy()[key] for key in
                ("name", "unit", "bear", "base", "bull", "basis", "rationale", "confidence")}
                for row in descriptor.assumptions.assumptions],
            "scenarios": [{"scenario": name, "per_share_value": str(getattr(result, name + "_value"))}
                for name in ("bear", "base", "bull")],
        },
        "quote_fact": {"status": "VERIFIED_CLOSE_NOT_ADMITTED",
            "quote_date": descriptor.quote.quote_date.isoformat(),
            "current_price": str(descriptor.quote.current_price)},
        "price_bridge": {"status": "INVALID", "price_admitted": False,
            "margin_to_bear": None, "margin_to_base": None},
        "gates": {"results": {"G3_估值门": False}},
    }
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is not None
    return root, package, payload, now


def test_bound_draft_rebuilds_real_descriptor_and_shared_model(bound_draft):
    root, package, payload, now = bound_draft
    before = deepcopy(payload)
    descriptor = build_descriptor(package, root=root)
    result = ResidualIncomeEquityValuationModel().value(descriptor.facts, descriptor.research_case)
    verification = _verify_bound_draft(root, payload, now)
    loaded = load_current_research_draft(root, package["symbol"], now=now)
    assert loaded is not None
    assert loaded == {**payload, "input_verification": verification}
    assert payload == before
    assert verification["status"] == "SOURCE_AND_MODEL_INPUTS_MATCH"
    assert verification["input_sha256"] == descriptor.input_sha256
    assert verification["economic_approval"] is False
    assert {row["field"]: row["value"] for row in verification["capital_inputs"]} == {
        "start_book_equity": "1000", "ordinary_shares": "100"}
    assert [Decimal(row["per_share_value"]) for row in loaded["valuation"]["scenarios"]] == [
        result.bear_value, result.base_value, result.bull_value]
    assert loaded["price_bridge"]["price_admitted"] is False
    assert loaded["gates"]["results"]["G3_估值门"] is False
    assert loaded["action"] == "no_order"


@pytest.mark.parametrize("field", ["terminal_residual_contribution_ratio",
    "basis_to_valuation_factor", "dividend_crosscheck_difference"])
@pytest.mark.parametrize("value", ["999", "NaN"])
def test_displayed_derivations_cannot_drift_from_shared_model(bound_draft, field, value):
    root, package, payload, now = bound_draft
    descriptor = build_descriptor(package, root=root)
    result = ResidualIncomeEquityValuationModel().value(descriptor.facts, descriptor.research_case)
    for row, computed in zip(payload["valuation"]["scenarios"], result.sensitivities):
        if field in computed:
            row[field] = computed[field]
    assert _verify_bound_draft(root, payload, now)["economic_approval"] is False
    payload["valuation"]["scenarios"][0][field] = value
    with pytest.raises(ValueError, match="derivation differs"):
        _verify_bound_draft(root, payload, now)
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("field", [
    "model_id", "model_as_of", "last_material_event_check", "status", "blockers",
])
def test_model_validity_display_must_match_evaluated_evidence(bound_draft, field):
    root, _, payload, now = bound_draft
    original_values = deepcopy(payload["valuation"])
    validity = payload["model_validity"]
    if field == "status":
        validity[field] = "UNKNOWN" if validity[field] == "VALID" else "VALID"
    elif field == "blockers":
        validity[field] = [*validity[field], "SYNTHETIC_UNBOUND_VALIDITY_CLAIM"]
    elif field in {"model_as_of", "last_material_event_check"}:
        validity[field] = "2026-09-21"
    else:
        validity[field] = "SYNTHETIC_UNBOUND_MODEL"
    assert payload["valuation"] == original_values
    with pytest.raises(ValueError, match="model validity differs"):
        _verify_bound_draft(root, payload, now)
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("field", [
    "name", "unit", "bear", "base", "bull", "basis", "rationale", "confidence",
])
def test_display_assumption_drift_rejected_with_unchanged_model_values(bound_draft, field):
    root, _, payload, now = bound_draft
    original_values = deepcopy(payload["valuation"]["scenarios"])
    payload["valuation"]["assumptions"][0][field] = (
        "0.99" if field in {"bear", "base", "bull"} else "SYNTHETIC_DISPLAY_DRIFT")
    assert payload["valuation"]["scenarios"] == original_values
    with pytest.raises(ValueError, match="assumptions differ"):
        _verify_bound_draft(root, payload, now)
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("mutation", [
    "model-output", "model-version", "equity-display", "quote-price", "quote-date",
    "input-hash", "package-hash", "future-output", "earlier-output", "research-date",
    "admitted-bridge", "margin", "duplicate-scenario",
])
def test_bound_verifier_and_loader_reject_display_or_binding_drift(bound_draft, mutation):
    root, _, payload, now = bound_draft
    if mutation == "model-output":
        payload["valuation"]["scenarios"][0]["per_share_value"] = "999"
    elif mutation == "model-version":
        payload["valuation"]["model_version"] = "SYNTHETIC_WRONG_MODEL"
    elif mutation == "equity-display":
        payload["financial_facts"]["parent_equity_cny"] = "2000"
    elif mutation == "quote-price":
        payload["quote_fact"]["current_price"] = "999"
    elif mutation == "quote-date":
        payload["quote_fact"]["quote_date"] = "2026-09-21"
    elif mutation == "input-hash":
        payload["model_input_binding"]["input_sha256"] = "0" * 64
    elif mutation == "package-hash":
        payload["model_input_binding"]["package"]["sha256"] = "0" * 64
    elif mutation == "future-output":
        now = datetime.fromisoformat(payload["available_at"]) - timedelta(seconds=1)
    elif mutation == "earlier-output":
        payload["available_at"] = "2026-09-22T16:59:59+08:00"
    elif mutation == "research-date":
        payload["research_as_of"] = "2026-09-21"
    elif mutation == "admitted-bridge":
        payload["price_bridge"]["status"] = "VALID"
    elif mutation == "margin":
        payload["price_bridge"]["margin_to_base"] = "0.5"
    else:
        payload["valuation"]["scenarios"].append(deepcopy(payload["valuation"]["scenarios"][0]))
    with pytest.raises(ValueError):
        _verify_bound_draft(root, payload, now)
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("mutation", ["equity", "shares", "future-computed", "future-available"])
def test_rehashed_package_still_requires_valid_capital_and_current_timing(bound_draft, mutation):
    root, package, payload, now = bound_draft
    if mutation in {"equity", "shares"}:
        field = "start_book_equity" if mutation == "equity" else "ordinary_shares"
        package["facts"]["operating_inputs"][field] = "2000"
    else:
        future = (now + timedelta(hours=1)).isoformat()
        package["point_in_time"]["computed_at"] = future
        if mutation == "future-available":
            package["point_in_time"]["available_at"] = future
        descriptor = build_descriptor(package, root=root)
        payload["model_input_binding"]["input_sha256"] = descriptor.input_sha256
        payload["available_at"] = future
    payload["model_input_binding"]["package"] = write_binding(
        root, "artifacts/current/synthetic-bound/package.json", package)
    with pytest.raises(ValueError):
        _verify_bound_draft(root, payload, now)
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("permission", ["formal_eligibility", "trade_eligible", "position_guidance"])
def test_loader_rejects_nested_permission_even_with_valid_model_binding(bound_draft, permission):
    root, _, payload, now = bound_draft
    payload["valuation"]["extension"] = [{permission: True}]
    publish(root, payload)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("source_state", ["changed", "missing"])
def test_loader_rechecks_draft_hash_and_retained_source_bytes(bound_draft, source_state):
    root, package, payload, now = bound_draft
    path = root / "artifacts/current/synthetic-bound/draft.json"
    path.write_bytes(path.read_bytes() + b"\n")
    assert load_current_research_draft(root, payload["symbol"], now=now) is None
    publish(root, payload)
    source = root / package["sources"][0]["local_path"]
    if source_state == "changed":
        source.write_bytes(b"SYNTHETIC_CHANGED_SOURCE_ONLY")
    else:
        source.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        _verify_bound_draft(root, payload, now)
    assert load_current_research_draft(root, payload["symbol"], now=now) is None


@pytest.mark.parametrize("schema", ["public-research-draft-v1", BOUND_DRAFT_SCHEMA])
def test_authored_verification_cannot_impersonate_loader_result(bound_draft, schema):
    root, _, payload, now = bound_draft
    payload["schema_version"] = schema
    payload["input_verification"] = {"status": "SYNTHETIC_FORGED_VERIFICATION"}
    publish(root, payload)
    loaded = load_current_research_draft(root, payload["symbol"], now=now)
    assert loaded is not None
    if schema == "public-research-draft-v1":
        assert "input_verification" not in loaded
    else:
        assert loaded["input_verification"] == _verify_bound_draft(root, payload, now)
        assert loaded["input_verification"]["status"] == "SOURCE_AND_MODEL_INPUTS_MATCH"

"""Accounting replay does not grant valuation or reviewer authority."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import economic_review_bundle as bundle


NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@pytest.fixture
def retained(tmp_path, monkeypatch):
    original = tmp_path / "original.pdf"
    original.write_bytes(b"test retained original; not semantic PDF certification")
    digest = sha256(original.read_bytes()).hexdigest()
    sources = [dict(id=name, path="original.pdf", sha256=digest,
        source_url="https://example.org/filing", report_period=period,
        published_date="2026-08-15") for name, period in (
        ("annual", "2025-01-01/2025-12-31"), ("interim", "2026-01-01/2026-06-30"))]
    cash, equity = [], []
    for period, source, opening in (("FY2025", "annual", "100"), ("H1_2026", "interim", "110")):
        cash.append(dict(period=period, source_id=source, entity_scope="issuer_parent_standalone",
            physical_pages=[2, 3], opening_cash_and_equivalents_cny=opening, cfo_cny="20",
            cfi_cny="-5", cff_cny="-5", fx_effect_reported_cny=None,
            fx_effect_reconciliation_residual_cny="0", reported_net_change_cny="10",
            closing_cash_and_equivalents_cny=str(int(opening)+10),
            closing_reconciliation_difference_cny="0"))
        for scope in ("issuer_parent_standalone", "consolidated_attributable_to_parent"):
            row = dict(period=period, source_id=source, entity_scope=scope, physical_page=4,
                opening_equity_cny=opening, net_profit_cny="20", distribution_signed_cny="-8",
                net_owner_capital_change_signed_cny="-2", closing_equity_cny=str(int(opening)+10),
                reconciliation_difference_cny="0")
            if scope == "issuer_parent_standalone":
                row.update(oci_reported_cny=None, oci_and_other_reconciliation_residual_cny="0")
            else:
                row["oci_cny"] = "0"
            equity.append(row)
    research = dict(research_version=bundle.BRIDGE_VERSION, symbol="600519", unit="CNY",
        artifact_kind="independent_parent_distribution_capital_research", action="no_order",
        research_date="2026-10-08", sources=sources, parent_cash_bridges=cash,
        equity_bridges=equity, model_binding=dict(reviewed_package_path="old/package.json",
            forward_distribution_capacity_cny=None, future_retained_capital_return=None))
    path = tmp_path / "research" / "parent-distribution-capital-bridge-v1.json"
    path.parent.mkdir()
    original_binding = dict(path="original.pdf", sha256=digest)
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(dict(symbol="600519", generated_at="2026-10-08T12:00:00+00:00",
        model_context=dict(input_descriptor_sha256="a"*64))), encoding="utf-8")
    analysis = dict(symbol="600519", action="no_order", input_descriptor_sha256="a"*64,
        review_binding=dict(candidate_binding=dict(path="candidate.json", sha256="b"*64)),
        source_catalog=[], source_bindings=[original_binding],
        consumed_operating_inputs=dict(start_book_equity="120"))
    def persist():
        analysis["review_binding"]["candidate_binding"]["sha256"] = sha256(candidate.read_bytes()).hexdigest()
        path.write_text(json.dumps(research), encoding="utf-8")
        binding = dict(path="research/"+path.name, sha256=sha256(path.read_bytes()).hexdigest())
        analysis["source_catalog"] = [dict(id="original", local_path="original.pdf", sha256=digest),
            dict(id="bridge", local_path=binding["path"], sha256=binding["sha256"],
                source_available_at="2026-10-08T12:00:00+00:00")]
        analysis["source_bindings"] = [original_binding, binding, analysis["review_binding"]["candidate_binding"]]
    persist()
    monkeypatch.setattr(bundle, "load_current_value_research_analysis", lambda **kw: deepcopy(analysis))
    return tmp_path, research, analysis, persist


def test_exact_candidate_bridge_replay_and_unknowns(retained):
    root, _, _, _ = retained
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)
    assert len(result["bridge_results"]) == 6
    assert all(row["difference_cny"] == "0" for row in result["bridge_results"])
    assert result["bridge_results"][0]["reported_adjustment"] is None
    assert result["primary_valuation_usable"] is result["approval_changed"] is False
    assert result["future_distribution_capacity_cny"] is None
    assert "/model_binding/forward_distribution_capacity_cny" in result["unknown_fields"]
    assert result["input_descriptor_sha256"] == "a"*64
    later = bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW+timedelta(hours=1))
    assert later["bundle_sha256"] == result["bundle_sha256"]
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("fault", ["amount", "scope", "period", "page", "duplicate", "symbol", "unit", "future", "source", "consumed"])
def test_invalid_bound_research_rejected(retained, fault):
    root, research, analysis, persist = retained
    if fault == "amount": research["parent_cash_bridges"][0]["cfo_cny"] = "21"
    if fault == "scope": research["parent_cash_bridges"][0]["entity_scope"] = "consolidated_attributable_to_parent"
    if fault == "period": research["parent_cash_bridges"][0]["period"] = "FY2024"
    if fault == "page": research["equity_bridges"][0]["physical_page"] = True
    if fault == "duplicate": research["equity_bridges"].append(research["equity_bridges"][0])
    if fault == "symbol": research["symbol"] = "600887"
    if fault == "unit": research["unit"] = "CNY_thousand"
    if fault == "future": research["research_date"] = "2027-01-01"
    if fault == "source": research["sources"][0]["sha256"] = "c"*64
    if fault == "consumed": analysis["consumed_operating_inputs"]["start_book_equity"] = "121"
    persist()
    with pytest.raises(ValueError):
        bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)


def test_tampered_original_rejected(retained):
    root, _, _, _ = retained
    (root/"original.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)


def test_old_forward_values_remain_historical_only(retained):
    root, research, _, persist = retained
    research['model_binding']['forward_distribution_capacity_cny'] = '123456'
    research['model_binding']['future_retained_capital_return'] = '0.25'
    persist()
    result = bundle.build_current_economic_review_bundle(root=root, symbol='600519', now=NOW)
    assert result['historical_model_binding']['forward_distribution_capacity_cny'] == '123456'
    assert result['historical_model_binding']['future_retained_capital_return'] == '0.25'
    assert result['future_distribution_capacity_cny'] is None
    assert result['future_retained_capital_return'] is None
    assert result['forward_economic_status'] == 'NOT_ESTABLISHED'
    assert result['economic_approval_granted'] is False


def test_uncovered_company_never_borrows_moutai_bridge(retained):
    root, _, analysis, _ = retained
    analysis["symbol"] = "600887"
    candidate = root / "candidate.json"
    payload = json.loads(candidate.read_bytes())
    payload["symbol"] = "600887"
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    analysis["review_binding"]["candidate_binding"]["sha256"] = sha256(candidate.read_bytes()).hexdigest()
    analysis["source_catalog"] = analysis["source_catalog"][:1]
    result = bundle.build_current_economic_review_bundle(root=root, symbol="600887", now=NOW)
    assert result["status"] == "NO_SUPPORTED_BOUND_BRIDGE"
    assert result["bridge_results"] == []
    assert result["primary_valuation_usable"] is False


def test_different_descriptor_is_rejected(retained):
    root, _, analysis, _ = retained
    first = bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)
    analysis["input_descriptor_sha256"] = "e"*64
    with pytest.raises(ValueError, match="descriptor"):
        bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)


def test_catalog_alias_allowed_only_same_binding_and_no_future(retained):
    root, _, analysis, _ = retained
    alias = deepcopy(analysis["source_catalog"][-1])
    alias["id"] = "bridge-lineage-alias"
    analysis["source_catalog"].append(alias)
    assert len(bundle.build_current_economic_review_bundle(
        root=root, symbol="600519", now=NOW)["bridge_results"]) == 6
    alias["retrieved_at"] = "2027-01-01T12:00:00+00:00"
    with pytest.raises(ValueError, match="not available"):
        bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)


def test_source_drift_during_replay_rejected(retained, monkeypatch):
    root, _, _, _ = retained
    replay = bundle._replay
    def drift(*args):
        result = replay(*args)
        (root / "original.pdf").write_bytes(b"concurrent replacement")
        return result
    monkeypatch.setattr(bundle, "_replay", drift)
    with pytest.raises(ValueError, match="hash mismatch"):
        bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)


@pytest.mark.parametrize("value", [True, None, "NaN", "Infinity"])
def test_nonfinite_or_missing_amount_rejected(retained, value):
    root, research, _, persist = retained
    research["parent_cash_bridges"][0]["cfo_cny"] = value
    persist()
    with pytest.raises(ValueError):
        bundle.build_current_economic_review_bundle(root=root, symbol="600519", now=NOW)


@pytest.mark.parametrize("symbol", ["600519", "600887"])
def test_real_readonly_source_replay(symbol):
    location = os.environ.get("VALUE_ECONOMIC_REPLAY_ROOT")
    if not location:
        pytest.skip("Explicit retained source tree required")
    result = bundle.build_current_economic_review_bundle(root=Path(location), symbol=symbol, now=NOW)
    assert result["action"] == "no_order"
    assert result["primary_valuation_usable"] is False
    if symbol == "600519":
        assert len(result["bridge_results"]) == 6
        assert result["bridge_results"][-1]["computed_closing_cny"] == "251253594419.50"
    else:
        assert result["status"] == "NO_SUPPORTED_BOUND_BRIDGE"

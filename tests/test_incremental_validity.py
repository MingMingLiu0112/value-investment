"""Synthetic explicit supplemental bindings; no real approval or research edits."""
from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
import runpy
import sys
from pathlib import Path

import pytest

from test_research_validity_review import _registered_fixture, _write, CUTOFF, TODAY
from value_investment_agent.application.product.incremental_validity import (
    BINDING_SCHEMA, collect_registered_validity_scan, resolve_incremental_model_validity,
)
from value_investment_agent.application.product.research_validity_review import review_registered_research_validity
from value_investment_agent.price_bridge import bridge_with_quote
from value_investment_agent.quote_snapshot import QuoteSnapshot, QUOTE_STATUS_VERIFIED_CLOSE
from value_investment_agent.valuation_models.base import ValuationResult


def _supplement(root):
    fixture = _registered_fixture(root)
    scan = json.loads(fixture["scan"].read_text(encoding="utf-8"))
    scan_ref = {"path": fixture["scan"].relative_to(root).as_posix(), "sha256": fixture["scan_sha256"]}
    observation_path = root / "runtime/events/observation.json"
    observation = {"schema_version": "daily-event-observation-v1", "symbol": "600887",
        "scan_binding": scan_ref, "scan_from": "2026-10-11", "scan_to": CUTOFF.isoformat(),
        "pagination_complete": True, "collection_status": "OFFICIAL_QUERY_ARCHIVED",
        "announcement_count": 0, "source_bindings": scan["evidence_refs"],
        "full_calendar_window_elapsed": True, "acquired_at": scan["retrieved_at"]}
    observation_sha = _write(observation_path, observation)
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    binding = {"schema_version": BINDING_SCHEMA, "symbol": "600887", "action": "no_order",
        "package_ref": {"path": fixture["package"].relative_to(root).as_posix(),
                        "sha256": fixture["package_sha256"]},
        "research_as_of": "2026-10-11", "review_cutoff": CUTOFF.isoformat(),
        "model_id": package["model_validity_input"]["model_id"],
        "observation_ref": {"path": observation_path.relative_to(root).as_posix(), "sha256": observation_sha},
        "scan_ref": scan_ref}
    path = root / "runtime/events/incremental-binding.json"
    digest = _write(path, binding)
    return fixture, {"path": path.relative_to(root).as_posix(), "sha256": digest}, binding


def _resolve(root, ref):
    return resolve_incremental_model_validity(root=root, symbol="600887", binding_ref=ref,
        review_cutoff=CUTOFF, today=TODAY)


def test_explicit_supplement_reaches_shared_model_validity_and_real_price_bridge(tmp_path):
    fixture, ref, _ = _supplement(tmp_path)
    before = fixture["package"].read_bytes()
    validity = _resolve(tmp_path, ref)
    assert validity.status == "VALID"  # Synthetic pre-reviewed input only.
    valuation = ValuationResult(symbol="600887", model_type="TEST_ONLY", valuation_date=date(2026, 10, 11),
        bear_value=Decimal("20"), base_value=Decimal("30"), bull_value=Decimal("40"),
        confidence="低", assumptions={}, sensitivities=[], evidence_refs=[{"id": "TEST_ONLY-value"}],
        blockers=[], status="conditional_research_only", model_version=validity.model_id)
    quote = QuoteSnapshot(symbol="600887", quote_date=CUTOFF, current_price=Decimal("18"),
        status=QUOTE_STATUS_VERIFIED_CLOSE, evidence_refs=[{"id": "TEST_ONLY-quote", "sha256": "a" * 64}])
    bridge = bridge_with_quote(valuation, validity, quote)
    assert bridge.bridge_status == "READY"
    assert bridge.margin_to_base == Decimal("0.4")
    assert any(row["path"] == ref["path"] for row in bridge.evidence_refs if "path" in row)
    assert valuation.status == "conditional_research_only"
    assert fixture["package"].read_bytes() == before
    assert bridge_with_quote(valuation, validity, replace(quote, quote_date=date(2026, 10, 13))).bridge_status == "INVALID"
    assert bridge_with_quote(replace(valuation, model_version="wrong-model"), validity, quote).bridge_status == "INVALID"
    # Replaying evidence, not trusting a previously produced VALID label.
    (tmp_path / "runtime/events/index.json").write_text("tampered", encoding="utf-8")
    changed = _resolve(tmp_path, ref)
    assert changed.status == "UNKNOWN"
    assert bridge_with_quote(valuation, changed, quote).bridge_status != "READY"


def test_batch_uses_only_explicit_supplement_and_preserves_prior_blockers(tmp_path):
    fixture, ref, binding = _supplement(tmp_path)
    # A sidecar may supplement a package with no embedded scan reference.
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    package["model_validity_input"].pop("event_scan_ref")
    package["model_validity_input"]["blockers"] = ["TEST_ONLY_prior_review_missing"]
    sha = _write(fixture["package"], package)
    pointer = tmp_path / "config/current-quote-bridge.json"
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["quotes"]["600887"]["research_package_sha256"] = sha
    _write(pointer, payload)
    binding["package_ref"]["sha256"] = sha
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    args = dict(root=tmp_path, review_cutoff=CUTOFF, today=TODAY, symbols=["600887"])
    without = review_registered_research_validity(**args, output_path=tmp_path / "runtime/without.json")
    assert without["reviews"][0]["status"] == "PENDING"
    result = review_registered_research_validity(**args, output_path=tmp_path / "runtime/with.json",
        incremental_bindings=[ref])
    row = result["reviews"][0]
    assert row["status"] == "BLOCKED_ON_MODEL_VALIDITY"
    assert "TEST_ONLY_prior_review_missing" in row["review"]["model_validity_review"]["current"]["blockers"]
    assert row["incremental_binding_ref"] == ref
    assert row["formal_eligibility"] is False
    assert _resolve(tmp_path, ref).status == "UNKNOWN"


@pytest.mark.parametrize("failure", ["package", "model", "observation", "future", "window", "snapshot"])
def test_supplement_mismatch_cannot_be_consumed(tmp_path, failure):
    _, ref, binding = _supplement(tmp_path)
    if failure == "package":
        binding["package_ref"]["sha256"] = "0" * 64
    elif failure == "model":
        binding["model_id"] = "wrong-model"
    elif failure == "window":
        binding["review_cutoff"] = "2026-10-14"
    else:
        obs_ref = binding["observation_ref"]
        path = tmp_path / obs_ref["path"]
        observation = json.loads(path.read_text(encoding="utf-8"))
        if failure == "observation":
            observation["announcement_count"] = 99
        elif failure == "future":
            observation["acquired_at"] = "2099-01-01T00:00:00+00:00"
        else:
            observation["full_calendar_window_elapsed"] = False
        obs_ref["sha256"] = _write(path, observation)
    ref["sha256"] = _write(tmp_path / ref["path"], binding)
    with pytest.raises(ValueError):
        _resolve(tmp_path, ref)


def test_collector_reuses_existing_service_and_binds_immutable_package(tmp_path, monkeypatch):
    fixture, _, binding = _supplement(tmp_path)
    from value_investment_agent.application.product import daily_event_observation
    output = tmp_path / "runtime/new-acquisition"
    seen = {}

    def acquire(**kwargs):
        seen.update(kwargs)
        output.mkdir()
        observation = json.loads((tmp_path / binding["observation_ref"]["path"]).read_text(encoding="utf-8"))
        _write(output / "observation.json", observation)
        return observation

    monkeypatch.setattr(daily_event_observation, "collect_daily_event_observation", acquire)
    result = collect_registered_validity_scan(root=tmp_path, symbol="600887", review_cutoff=CUTOFF,
                                             output_dir=output)
    assert seen["retain_raw_index"] is True
    assert seen["start"] == date(2026, 10, 11)
    assert seen["end"] == CUTOFF
    bound = json.loads((tmp_path / result["binding_ref"]["path"]).read_text(encoding="utf-8"))
    assert bound["package_ref"]["sha256"] == fixture["package_sha256"]
    assert bound["g3_approval_granted"] is bound["materiality_approved"] is False
    repeated = collect_registered_validity_scan(root=tmp_path, symbol="600887", review_cutoff=CUTOFF,
                                                output_dir=output)
    assert repeated == result
    with pytest.raises(ValueError, match="31 days"):
        collect_registered_validity_scan(root=tmp_path, symbol="600887", review_cutoff=date(2026, 12, 1),
            output_dir=tmp_path / "runtime/not-created")


def test_collection_cli_registers_through_service(tmp_path, monkeypatch, capsys):
    _, ref, _ = _supplement(tmp_path)
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/current/collect_registered_validity_scan.py"))
    main = namespace["main"]
    main.__globals__["ROOT"] = tmp_path
    main.__globals__["collect_registered_validity_scan"] = lambda **kwargs: {"binding_ref": ref, "action": "no_order"}
    monkeypatch.setattr(sys, "argv", ["collect", "--symbol", "600887", "--review-cutoff", CUTOFF.isoformat(),
        "--output-dir", "runtime/TEST_ONLY", "--register"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["registration"]["binding_ref"] == ref
    pointer = json.loads((tmp_path / "config/current-quote-bridge.json").read_text(encoding="utf-8"))
    assert pointer["quotes"]["600887"]["incremental_validity_binding"] == ref

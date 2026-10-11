"""Monthly recap boundaries; synthetic public research only."""
from copy import deepcopy
import json

import pytest

from test_current_decision_surface import decision_workbench
from value_investment_agent.application.product import monthly_research_review as monthly
from value_investment_agent.application.product.common import sha256_file


def _write(root, name, payload):
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path, sha256_file(path)


def _run(root, current, previous=None, **kwargs):
    path, digest = _write(root, "current.json", current)
    args = dict(root=root, symbol=current["symbol"], current_workbench_path=path,
                current_workbench_sha256=digest)
    if previous is not None:
        old, pin = _write(root, "previous.json", previous)
        args.update(previous_workbench_path=old, previous_workbench_sha256=pin)
    return monthly.build_monthly_research_review(**args, **kwargs)


def test_unchanged_replays_real_contract_and_no_new_facts(tmp_path):
    workbench = decision_workbench()
    previous = deepcopy(workbench)
    current = deepcopy(workbench)
    current["generated_at"] = "2026-10-01T12:00:00+00:00"
    result = _run(tmp_path, current, previous)["result"]
    assert result["comparison_status"] == "SAME_RESEARCH_DATE"
    assert result["official_facts_status"] == "NO_NEW_DISCLOSED_FACTS_ESTABLISHED"
    assert result["fields"]["price_attractiveness"]["status"] == "UNCHANGED"
    assert result["fields"]["dividend_policy"]["status"] == "UNAVAILABLE"
    assert result["fields"]["thesis_consistency"]["status"] == "UNAVAILABLE"
    assert result["fields"]["main_valuation_assumptions"]["status"] == "UNAVAILABLE"
    assert any("consistency unavailable" in note for note in result["uncertainty"])
    assert result["position_guidance"] is None
    assert result["action"] == "no_order"
    assert "orders" not in result and "positions" not in result
    assert current == workbench | {"generated_at": current["generated_at"]}


def test_changed_explicit_fields_are_research_not_official(tmp_path, monkeypatch):
    # Exercise extraction with controlled already-verified dependency shapes;
    # the unchanged test above independently exercises actual replay.
    from types import SimpleNamespace
    def verify(payload):
        return SimpleNamespace(dependency_objects=payload["test_objects"])
    monkeypatch.setattr(monthly, "verify_current_decision_workbench", verify)
    monkeypatch.setattr(monthly, "artifact_payload", lambda obj: ("fixture", obj))
    def snapshot(as_of, n):
        return dict(symbol="600519", generated_at=as_of + "T12:00:00+00:00", test_objects={
            "research_case": {"as_of": as_of, "financial_summary": {"dividend_policy": str(n)},
                              "next_events": [{"kind": "hypothesis", "text": str(n)}]},
            "financial_facts": {"verified": True, "evidence_refs": [{"id": "public"}],
                                "operating_inputs": {"revenue": str(n)}, "scenario_inputs": {"future": "excluded"}},
            "valuation_assumptions": {"model_type": "residual", "assumptions": [{"base": str(n), "confidence": "low"}]},
            "price_attractiveness": {"status": str(n)},
            "investment_consistency_review": {"status": str(n)},
        })
    result = _run(tmp_path, snapshot("2026-10-01", 2), snapshot("2026-09-01", 1))["result"]
    assert all(row["status"] == "CHANGED_RESEARCH_ARTIFACT" for row in result["fields"].values())
    assert "scenario_inputs" not in result["fields"]["financial_operating_facts"]["current"]
    assert result["official_facts_status"] == "NO_NEW_DISCLOSED_FACTS_ESTABLISHED"
    assert result["approval_changed"] is False


def test_historical_scope_never_upgrades_admission(tmp_path):
    original, digest = _write(tmp_path, "original.json", {"public": "historical"})
    historical = dict(schema_version="product-existing-research-workbench-v1", symbol="600519",
                      generated_at="2026-10-01T12:00:00+00:00", action="no_order",
                      scope="EXISTING_RESEARCH_ONLY_NOT_CURRENT_ADVICE", suggested_state="NOT_READY",
                      position_guidance=None, research={"source_records": [{"path": original.name, "sha256": digest}],
                                                       "dependency_view": {"valuation_date": "2025-12-31"}})
    result = _run(tmp_path, historical, historical)["result"]
    assert result["scope"] == "HISTORICAL_RESEARCH_ONLY_NOT_CURRENT_ADVICE"
    assert not result["current_admission"]
    assert all(row["status"] == "UNAVAILABLE" for row in result["fields"].values())
    assert any("strict PIT" in note for note in result["uncertainty"])
    original.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="original hash"):
        _run(tmp_path, historical)


def test_missing_previous_is_explicit(tmp_path):
    result = _run(tmp_path, decision_workbench())["result"]
    assert result["comparison_status"] == "PREVIOUS_UNAVAILABLE"
    assert all(row["status"] == "UNAVAILABLE" for row in result["fields"].values())


@pytest.mark.parametrize("legacy_side", ["current", "previous", "both"])
def test_legacy_source_contract_retains_non_admitted_scope(tmp_path, legacy_side):
    previous = decision_workbench()
    current = deepcopy(previous)
    current["generated_at"] = "2026-10-01T12:00:00+00:00"
    legacy = "LEGACY_CONTRACT_NOT_REAL_INPUT_ADMISSION"
    for side, workbench in (("current", current), ("previous", previous)):
        workbench["source_verification"] = {
            "status": "LOCAL_BYTES_VERIFIED",
            "scope": "byte_integrity_not_fact_semantics_or_investment_approval",
            "source_contract_status": legacy if legacy_side in (side, "both") else
                "SOURCE_CUTOFF_AND_SCENARIO_BINDINGS_VALIDATED",
        }
    outcome = _run(tmp_path, current, previous, output_path=tmp_path / "legacy-review.json")
    result = outcome["result"]
    assert result["scope"] == (legacy if legacy_side in ("current", "both") else
                               "VERIFIED_SECURITY_RESEARCH_ONLY")
    assert result["previous_scope"] == (legacy if legacy_side in ("previous", "both") else
                                        "VERIFIED_SECURITY_RESEARCH_ONLY")
    assert result["comparison_status"] == "SAME_RESEARCH_DATE"
    assert result["official_facts_status"] == "NO_NEW_DISCLOSED_FACTS_ESTABLISHED"
    assert result["fields"]["price_attractiveness"]["status"] == "UNCHANGED"
    assert any("does not establish real-input admission" in note for note in result["uncertainty"])
    assert result["current_admission"] is False
    assert result["approval_changed"] is False
    assert result["action"] == outcome["receipt"]["action"] == "no_order"
    assert result["position_guidance"] is None
    assert "positions" not in result and "orders" not in result
    assert json.loads((tmp_path / "legacy-review.json").read_text(encoding="utf-8")) == result


def test_immutable_output_and_containment(tmp_path):
    output = tmp_path / "review.json"
    outcome = _run(tmp_path, decision_workbench(), output_path=output)
    assert outcome["receipt"]["output_sha256"] == sha256_file(output)
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        _run(tmp_path, decision_workbench(), output_path=output)
    assert output.read_bytes() == original
    with pytest.raises(ValueError, match="project root"):
        _run(tmp_path, decision_workbench(), output_path=tmp_path / ".." / "outside.json")


@pytest.mark.parametrize("key,value", [("action", "order"), ("position_guidance", {"weight": 1}),
                                       ("symbol", "600519")])
def test_rejects_scope_tampering(tmp_path, key, value):
    workbench = decision_workbench()
    workbench[key] = value
    with pytest.raises(ValueError):
        _run(tmp_path, workbench)


def test_hash_and_input_containment(tmp_path):
    source, digest = _write(tmp_path, "source.json", decision_workbench())
    with pytest.raises(ValueError, match="hash mismatch"):
        monthly.build_monthly_research_review(root=tmp_path, symbol="600519",
            current_workbench_path=source, current_workbench_sha256="0" * 64)
    with pytest.raises(ValueError, match="project root"):
        monthly.build_monthly_research_review(root=tmp_path, symbol="600519",
            current_workbench_path=tmp_path / ".." / "other.json", current_workbench_sha256=digest)


def test_rejects_reversed_chronology(tmp_path):
    current = decision_workbench()
    previous = deepcopy(current)
    previous["generated_at"] = "2026-10-01T12:00:00+00:00"
    with pytest.raises(ValueError, match="later than current"):
        _run(tmp_path, current, previous)

"""New shared research may join existing product cards without inventing holdings."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_current_decision_surface import decision_workbench, forged_candidate
from test_product_workbench_excel import _payload
from test_decision_recommendation import AS_OF, SYMBOL, _case
from value_investment_agent.application.product.decision_surface import project_verified_decision_workbench
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


def _inputs(tmp_path, workbench):
    source = tmp_path / "runtime" / "decision.json"
    source.parent.mkdir()
    source.write_text(json.dumps(workbench, ensure_ascii=False), encoding="utf-8")
    payload = _payload()
    payload["as_of"] = AS_OF.isoformat()
    payload["generated_at"] = "2026-09-22T13:00:00+00:00"
    return payload, dict(root=tmp_path, path=source,
                         expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest())


@pytest.mark.parametrize("missing_approval", [False, True])
def test_registration_appends_verified_company_and_preserves_personal_records(tmp_path, missing_approval):
    payload, inputs = _inputs(tmp_path, decision_workbench(missing_approval=missing_approval))
    before = deepcopy(payload)
    project_verified_decision_workbench(payload, register_company=True, **inputs)
    model = product_workbench_from_payload(payload)
    assert payload["companies"][:-1] == before["companies"]
    assert payload["opportunities"][:-1] == before["opportunities"]
    assert payload["portfolio"] == before["portfolio"]
    assert payload["events"] == before["events"]
    assert len(model.companies) == 2
    card = payload["companies"][-1]
    assert card["symbol"] == SYMBOL
    assert card["company_name"] == _case().name
    assert card["original_thesis"] != _case().thesis
    assert "尚未建立" in card["original_thesis"]
    assert card["action"] == "no_order"
    assert card["decision_process"][6]["status"] == "BLOCKED"
    assert card["dividend"]["available"] is False
    assert card["valuation"]["value_text"].count(" 元") == 1
    assert card["decision_process"][-1]["status"] == ("BLOCKED" if missing_approval else "CONDITIONAL")
    assert payload["today_items"][-1]["symbol"] == SYMBOL
    assert payload["today_items"][:-1] == before["today_items"]
    assert payload["overview"]["pending_count"] == len(payload["today_items"])


@pytest.mark.parametrize("partial", [None, "companies", "opportunities", "duplicate"])
def test_registration_is_opt_in_and_rejects_partial_or_duplicate_existing_views(tmp_path, partial):
    payload, inputs = _inputs(tmp_path, decision_workbench())
    if partial in {"companies", "opportunities"}:
        payload[partial][0]["symbol"] = SYMBOL
    elif partial == "duplicate":
        payload["companies"][0]["symbol"] = SYMBOL
        payload["opportunities"][0]["symbol"] = SYMBOL
        payload["companies"].append(deepcopy(payload["companies"][0]))
    before = deepcopy(payload)
    with pytest.raises(ValueError, match="already exist"):
        project_verified_decision_workbench(payload, register_company=partial is not None, **inputs)
    assert payload == before


def test_forged_positive_cannot_create_company(tmp_path):
    payload, inputs = _inputs(tmp_path, forged_candidate())
    before = deepcopy(payload)
    with pytest.raises(ValueError, match="full repository replay"):
        project_verified_decision_workbench(payload, register_company=True, **inputs)
    assert payload == before


def test_existing_company_keeps_user_entry_thesis_when_registration_is_enabled(tmp_path):
    payload, inputs = _inputs(tmp_path, decision_workbench())
    payload["companies"][0]["symbol"] = SYMBOL
    payload["opportunities"][0]["symbol"] = SYMBOL
    original = payload["companies"][0]["original_thesis"]
    prior_item = deepcopy(payload["today_items"][0])
    prior_item.update(symbol=SYMBOL, category="RESEARCH_CHANGE")
    payload["today_items"].append(prior_item)
    project_verified_decision_workbench(payload, register_company=True, **inputs)
    assert len(payload["companies"]) == 1
    assert payload["companies"][0]["original_thesis"] == original
    assert prior_item in payload["today_items"]


def test_original_drift_blocks_registration_even_when_artifact_bundle_is_unchanged(tmp_path):
    workbench = decision_workbench()
    original = tmp_path / "original.pdf"
    original.write_bytes(b"bound-original")
    workbench["source_verification"] = {
        "status": "LOCAL_BYTES_VERIFIED",
        "sources": [{"path": "original.pdf", "sha256": hashlib.sha256(original.read_bytes()).hexdigest()}],
    }
    payload, inputs = _inputs(tmp_path, workbench)
    before = deepcopy(payload)
    original.write_bytes(b"changed-original")
    with pytest.raises(ValueError, match="source hash mismatch"):
        project_verified_decision_workbench(payload, register_company=True, **inputs)
    assert payload == before

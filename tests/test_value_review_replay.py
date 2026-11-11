import hashlib
import json
from decimal import Decimal

import pytest

from test_value_decision_explanation import synthetic_restored
from value_investment_agent.application.decision.value_review_replay import replay_value_review_inputs
from value_investment_agent.human_research_approval import artifact_fingerprint
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_input import facts_to_payload
from value_investment_agent.valuation_router import VALUATION_MODEL_REGISTRY
from value_investment_agent.valuation_models.residual_income import QualityCompounderFacts, ResidualIncomeScenarioInputs


def replay_fixture(tmp_path):
    restored = synthetic_restored("BUY_CANDIDATE")
    case = restored.dependency_objects["research_case"]
    facts = QualityCompounderFacts(symbol=case.symbol, as_of=case.as_of, verified=True, confidence="低",
        evidence_refs=[dict(id="isolated-facts")], blockers=[],
        operating_inputs=dict(start_book_equity=Decimal("1000"), ordinary_shares=Decimal("100")),
        scenario_inputs={key: ResidualIncomeScenarioInputs(cost_of_equity=Decimal("0.09"),
            forecast_roes=(Decimal("0.15"), Decimal("0.12")), terminal_roe=Decimal("0.09"),
            terminal_growth=Decimal("0"), retention=Decimal("0.15")) for key in ("bear", "base", "bull")})
    model = VALUATION_MODEL_REGISTRY.build("residual_income_or_equity_value")
    valuation = artifact_payload(model.value(facts, case))[1]
    package = dict(symbol=case.symbol, profile_id="quality_compounder", requested_model=None,
        research_case=artifact_payload(case)[1], facts=facts_to_payload(facts))
    explanation = dict(symbol=case.symbol, action="no_order", valuation=valuation,
        decision_dependency_refs=[dict(role=role, payload_sha256=artifact_fingerprint(payload))
            for role, payload in (("research_case", artifact_payload(case)[1]),
                ("financial_facts", artifact_payload(facts)[1]), ("valuation", valuation))])
    bindings = []
    for name, payload in (("runtime/package.json", package), ("runtime/explanation.json", explanation)):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        raw = json.dumps(payload).encode()
        path.write_bytes(raw)
        bindings.append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest()))
    return bindings, explanation


def test_isolated_shared_replay_matches_full_payload_without_approval(tmp_path):
    bindings, _ = replay_fixture(tmp_path)
    isolated = tmp_path / ".tmp/isolated"
    receipt = replay_value_review_inputs(tmp_path, package_binding=bindings[0],
        explanation_binding=bindings[1], isolated_root=isolated)
    assert receipt["status"] == "EXACT_VALUATION_REPLAY"
    assert receipt["full_payload_match"] is True and all(receipt["output_checks"].values())
    assert receipt["copied_file_count"] == 2
    assert receipt["formal_eligibility"] is False and receipt["g3_approved"] is False
    with pytest.raises(ValueError, match="new isolated"):
        replay_value_review_inputs(tmp_path, package_binding=bindings[0],
            explanation_binding=bindings[1], isolated_root=isolated)


def test_replay_rejects_changed_consumed_fingerprint_even_with_new_file_hash(tmp_path):
    bindings, _ = replay_fixture(tmp_path)
    path = tmp_path / bindings[0]["path"]
    package = json.loads(path.read_bytes())
    package["facts"]["operating_inputs"]["ordinary_shares"] = "999999"
    raw = json.dumps(package).encode()
    path.write_bytes(raw)
    bindings[0]["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="consumed fingerprints"):
        replay_value_review_inputs(tmp_path, package_binding=bindings[0],
            explanation_binding=bindings[1], isolated_root=tmp_path / ".tmp/isolated")


def test_replay_reports_output_mismatch_without_promoting_admission(tmp_path):
    bindings, explanation = replay_fixture(tmp_path)
    explanation["valuation"]["base_value"] = "999"
    explanation["decision_dependency_refs"][-1]["payload_sha256"] = artifact_fingerprint(explanation["valuation"])
    raw = json.dumps(explanation).encode()
    (tmp_path / bindings[1]["path"]).write_bytes(raw)
    bindings[1]["sha256"] = hashlib.sha256(raw).hexdigest()
    receipt = replay_value_review_inputs(tmp_path, package_binding=bindings[0],
        explanation_binding=bindings[1], isolated_root=tmp_path / ".tmp/isolated")
    assert receipt["status"] == "VALUATION_REPLAY_MISMATCH"
    assert receipt["formal_eligibility"] is False

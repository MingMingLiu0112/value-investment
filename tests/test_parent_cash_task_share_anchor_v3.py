from datetime import datetime

import pytest

from value_investment_agent.application.research import parent_cash_task_share_anchor_v3 as anchors


@pytest.fixture
def replay_and_facts(monkeypatch):
    symbol = "000568"
    period = "2024-12-31"
    url = "https://static.cninfo.com.cn/finalpage/2025-04-29/1225240660.PDF"
    binding = dict(path="runtime/sample.pdf", sha256="a" * 64)
    spec = dict(path="runtime/spec.json", sha256="b" * 64)
    completed = "2025-11-21T00:00:00+00:00"
    provenance = dict(spec_binding=spec, task_id="task", completed_at=completed)
    ref = dict(binding, source_id="cninfo:1225240660", source_url=url,
               available_at="2025-11-01T00:00:00+00:00", physical_page=17,
               excerpt="截至 2024 年 12 月 31 日，公司股份总数为 1,234 股。")
    proof = dict(count="1234", period_end=period, unit="shares",
                 scope="TOTAL_ISSUED_ORDINARY_SHARES", source_refs=[ref],
                 classification="DERIVED_FACT",
                 derivation="ANNUAL_SHARE_TABLE_AND_DATED_TOTAL_NO_PREFERRED")
    facts = dict(symbol=symbol, valuation_date=period, ordinary_shares=proof)

    def read_facts(*, root, spec_binding, now):
        assert spec_binding == spec
        assert now == datetime.fromisoformat(completed)
        return facts

    monkeypatch.setattr(anchors, "read_parent_cash_agent_facts_v2", read_facts)
    descriptor = dict(symbol=symbol, point_in_time=dict(valuation_date=period),
        source_contract=dict(provenance, schema_version=anchors.RECEIPT_SCHEMA,
                             completed_at="2025-11-21T08:00:00+08:00"),
        sources=[dict(id=ref["source_id"], location=url, sha256=binding["sha256"],
                      kind="official_issuer_filing", issuer_identity=dict(
                          issuer_name="泸州老窖股份有限公司", organization_id="gssz0000568",
                          security_code=symbol, venue="CNINFO"))],
        facts=dict(operating_inputs=dict(ordinary_shares="1234"),
                   scenario_inputs={key: dict(ordinary_shares="1234")
                                    for key in ("bear", "base", "bull")}))
    result = dict(symbol=symbol, provenance=provenance, descriptor=descriptor,
                  source_bindings=[binding], action="no_order", formal_eligibility=False,
                  main_range_adopted=False, valuation=dict(symbol=symbol, valuation_date=period,
                                                          status="conditional_research_only"))
    return result, proof, ref


@pytest.mark.parametrize("classification", ["FACT", "DERIVED_FACT"])
def test_projects_bound_opening_anchor(tmp_path, replay_and_facts, classification):
    result, proof, ref = replay_and_facts
    proof["classification"] = classification
    if classification == "FACT":
        proof.pop("derivation")
        ref["excerpt"] = "三、股份总数 1,234"
    [anchor] = anchors.read_task_share_anchors(root=tmp_path, result=result)
    assert anchor["field"] == "ordinary_shares"
    assert anchor["classification"] == classification
    assert anchor["scope"] == proof["scope"]
    assert anchor["source_value"] == "1234"
    assert anchor["period_end"] == "2024-12-31"
    assert anchor["physical_page"] == 17
    assert anchor["excerpt"] == ref["excerpt"]
    assert anchor["binding"] == result["source_bindings"][0]


@pytest.mark.parametrize("change", ["wrong_date", "undated", "unknown_derivation", "unbound"])
def test_returns_no_anchor_for_unsupported_evidence(tmp_path, replay_and_facts, change):
    result, proof, ref = replay_and_facts
    if change == "wrong_date":
        ref["excerpt"] = ref["excerpt"].replace("2024", "2025")
    elif change == "undated":
        ref["excerpt"] = "三、股份总数 1,234"
    elif change == "unknown_derivation":
        proof["derivation"] = "BALANCE_SHEET_ONLY"
    else:
        ref["sha256"] = "c" * 64
    assert anchors.read_task_share_anchors(root=tmp_path, result=result) == []


@pytest.mark.parametrize("change", ["scenario", "dated_count", "duplicate", "formal"])
def test_rejects_inconsistent_replay_or_proof(tmp_path, replay_and_facts, change):
    result, proof, ref = replay_and_facts
    if change == "scenario":
        result["descriptor"]["facts"]["scenario_inputs"]["bear"]["ordinary_shares"] = "999"
    elif change == "dated_count":
        ref["excerpt"] = ref["excerpt"].replace("1,234", "1,235")
    elif change == "duplicate":
        proof["source_refs"].append(dict(ref, physical_page=18))
    else:
        result["formal_eligibility"] = True
    with pytest.raises(ValueError, match="TASK_SHARE_"):
        anchors.read_task_share_anchors(root=tmp_path, result=result)

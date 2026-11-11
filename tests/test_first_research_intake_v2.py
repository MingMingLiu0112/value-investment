from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from test_first_research_input_v1 import first  # noqa: F401 - shared E2 integration fixture
from value_investment_agent.application.research import first_research_input_v1 as v1
from value_investment_agent.application.research.first_research_intake_v2 import (
    SCHEMA,
    compile_first_research_from_intake,
    prepare_first_research_intake,
)
from value_investment_agent.application.product.common import encode_json_bytes


NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
STAMP = NOW.isoformat()


def _put(root, relative, payload):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = encode_json_bytes(payload)
    path.write_bytes(raw)
    return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}


def _snapshot(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


def _intake(root, symbol="600323"):
    basis = "2026-06-30"
    raw = _put(root, "runtime/native/original.json", {"revenue": "100"})
    source = _put(root, "runtime/native/facts.json", {
        "schema_version": "native-facts-v1", "symbol": symbol, "generated_at": STAMP,
        "financial_basis": basis,
        "sources": [{"id": "official", "source_available_at": STAMP, "local_path": raw["path"],
                     "sha256": raw["sha256"]}],
        "facts": [{"id": "revenue", "source_id": "official", "value": "100"}],
    })
    rationale = _put(root, "runtime/d2/rationale.json", {"generated_at": STAMP, "statement": "bounded"})
    assumptions = _put(root, "runtime/d2/assumptions.json", {
        "schema_version": v1.ASSUMPTIONS_SCHEMA, "action": "no_order", "symbol": symbol,
        "financial_basis": basis, "generated_at": STAMP,
        "assumption_scope": "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST",
        "source_bindings": [rationale], "choice": {"id": "d2"},
        "historical_bindings": {"revenue": {"fact_id": "revenue"}},
        "scenarios": {name: {"drivers": {}, "terminal_policy": {}, "cost_of_equity": "0.09"}
                      for name in ("bear", "base", "bull")},
    })
    profile = _put(root, "runtime/c/profile.json", {
        "schema_version": "company-research-profile-v1", "action": "no_order", "symbol": symbol,
        "status": "SOURCE_BOUND_PROFILE", "as_of": basis, "report_period": basis,
        "available_at": STAMP, "profile": {"profile_id": "quality_compounder"},
        "route": {"status": "SUPPORTED", "profile_id": "quality_compounder",
                  "requested_model": v1.MODEL},
    })
    return {
        "schema_version": SCHEMA, "action": "no_order", "symbol": symbol, "name": "测试公司",
        "run_id": "first-intake-v2", "point_in_time": {
            "report_period": basis, "research_as_of": "2026-11-09", "valuation_date": basis,
            "available_at": STAMP, "computed_at": STAMP,
        },
        "source_binding": source, "assumption_binding": assumptions, "profile_binding": profile,
        "capital_bindings": {"start_book_equity": "equity", "ordinary_shares": "shares"},
        "share_basis": "issued_ordinary_shares",
        "research_case": {
            "industry": "测试", "investment_path": "研究", "thesis": "测试假设",
            "return_driver": "经营", "mispricing_hypothesis": "未评估", "positives": [],
            "counter_evidence": [], "thesis_breakers": [], "next_events": [],
        },
    }


def test_prepares_exact_v1_spec_from_bound_inputs_without_writing(tmp_path):
    intake = _intake(tmp_path)
    before = _snapshot(tmp_path)
    result = prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)
    assert _snapshot(tmp_path) == before
    assert result["status"] == "FIRST_INPUT_SPEC_PREPARED"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["approvals_created"] == 0 and result["writes_formal_candidate"] is False
    assert set(result["spec"]) == {
        "schema_version", "action", "symbol", "name", "profile_id", "run_id", "point_in_time",
        "native_facts_binding", "capital_bindings", "share_basis", "assumption_binding", "research_case",
    }
    assert result["spec"]["schema_version"] == v1.SCHEMA
    assert result["spec"]["symbol"] == "600323"
    assert result["spec"]["profile_id"] == "quality_compounder"
    assert json.loads(result["spec_bytes"]) == result["spec"]
    assert result["input_manifest"]["profile_binding"] == intake["profile_binding"]
    assert result["input_manifest"]["spec_sha256"] == hashlib.sha256(result["spec_bytes"]).hexdigest()


@pytest.mark.parametrize("symbol", ["600323", "000568"])
def test_symbol_is_carried_by_bound_artifacts_not_symbol_specific_code(tmp_path, symbol):
    intake = _intake(tmp_path, symbol=symbol)
    result = prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)
    assert result["spec"]["symbol"] == symbol
    assert result["input_manifest"]["symbol"] == symbol


def test_profile_research_date_may_follow_matching_financial_period(tmp_path):
    intake = _intake(tmp_path)
    path = tmp_path / intake["profile_binding"]["path"]
    profile = json.loads(path.read_bytes())
    profile["as_of"] = "2026-10-31"
    intake["profile_binding"] = _put(tmp_path, "runtime/c/profile-later.json", profile)
    result = prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)
    assert result["input_manifest"]["profile_binding"] == intake["profile_binding"]


@pytest.mark.parametrize("profile_as_of,report_period", [
    ("2026-06-29", "2026-06-30"),
    ("2026-11-10", "2026-06-30"),
    ("2026-10-31", "2025-12-31"),
])
def test_profile_date_or_financial_basis_mismatch_is_rejected(
        tmp_path, profile_as_of, report_period):
    intake = _intake(tmp_path)
    path = tmp_path / intake["profile_binding"]["path"]
    profile = json.loads(path.read_bytes())
    profile["as_of"] = profile_as_of
    profile["report_period"] = report_period
    intake["profile_binding"] = _put(tmp_path, "runtime/c/profile-invalid.json", profile)
    with pytest.raises(ValueError, match="Company profile"):
        prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)


def test_changed_source_hash_fails_closed(tmp_path):
    intake = _intake(tmp_path)
    (tmp_path / intake["source_binding"]["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="native facts hash mismatch"):
        prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)


@pytest.mark.parametrize("mutation", ["wrong_symbol", "unsupported_profile", "unsupported_route", "future", "missing_rationale"])
def test_identity_profile_time_and_assumption_gaps_fail_closed(tmp_path, mutation):
    intake = _intake(tmp_path)
    if mutation == "wrong_symbol":
        intake["symbol"] = "000568"
    elif mutation == "unsupported_profile":
        path = tmp_path / intake["profile_binding"]["path"]
        data = json.loads(path.read_bytes())
        data["profile"]["profile_id"] = "mature_manufacturing"
        intake["profile_binding"] = _put(tmp_path, "runtime/c/profile-v2.json", data)
    elif mutation == "unsupported_route":
        path = tmp_path / intake["profile_binding"]["path"]
        data = json.loads(path.read_bytes())
        data["route"]["status"] = "UNSUPPORTED"
        intake["profile_binding"] = _put(tmp_path, "runtime/c/profile-v2.json", data)
    elif mutation == "future":
        intake["point_in_time"]["available_at"] = "2099-01-01T00:00:00+00:00"
    else:
        path = tmp_path / intake["assumption_binding"]["path"]
        data = json.loads(path.read_bytes())
        data["source_bindings"] = []
        intake["assumption_binding"] = _put(tmp_path, "runtime/d2/assumptions-v2.json", data)
    with pytest.raises(ValueError):
        prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)


def test_intake_never_supplies_missing_economic_defaults(tmp_path):
    intake = _intake(tmp_path)
    del intake["research_case"]["thesis"]
    with pytest.raises(ValueError, match="research-case"):
        prepare_first_research_intake(root=tmp_path, intake=intake, now=NOW)


def test_intake_compiles_through_existing_e2_core_without_second_engine(first):
    """The generic intake writes a new spec then consumes the established core."""
    root, spec, _, _, cold, _, _ = first
    profile = _put(root, "runtime/c/profile.json", {
        "schema_version": "company-research-profile-v1", "action": "no_order",
        "symbol": spec["symbol"], "status": "SOURCE_BOUND_PROFILE",
        "as_of": spec["point_in_time"]["valuation_date"],
        "report_period": spec["point_in_time"]["report_period"],
        "available_at": spec["point_in_time"]["available_at"],
        "profile": {"profile_id": "quality_compounder"},
        "route": {"status": "SUPPORTED", "profile_id": "quality_compounder",
                  "requested_model": v1.MODEL},
    })
    intake = {
        "schema_version": SCHEMA, "action": "no_order", "symbol": spec["symbol"],
        "name": spec["name"], "run_id": "generic-e2-first-intake",
        "point_in_time": deepcopy(spec["point_in_time"]),
        "source_binding": deepcopy(spec["native_facts_binding"]),
        "assumption_binding": deepcopy(spec["assumption_binding"]),
        "profile_binding": profile, "capital_bindings": deepcopy(spec["capital_bindings"]),
        "share_basis": spec["share_basis"], "research_case": deepcopy(spec["research_case"]),
    }
    result = compile_first_research_from_intake(
        root=root, intake=intake, intake_output_dir=root / "runtime/intake",
        output_dir=root / "runtime/compiled-from-intake", now=NOW, fact_replay=cold,
    )
    assert result["status"] == "FIRST_INPUT_COMPILED_FROM_INTAKE"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["compilation"]["status"] == "FIRST_INPUT_COMPILED"
    assert (root / result["spec_binding"]["path"]).is_file()
    assert (root / result["input_manifest_binding"]["path"]).is_file()
    with pytest.raises(FileExistsError, match="already exists"):
        compile_first_research_from_intake(
            root=root, intake=intake, intake_output_dir=root / "runtime/intake",
            output_dir=root / "runtime/compiled-again", now=NOW, fact_replay=cold,
        )

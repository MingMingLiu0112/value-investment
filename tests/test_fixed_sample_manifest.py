from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile

import pytest

from value_investment_agent.fixed_sample_manifest import (
    DEFAULT_MANIFEST_PATH,
    load_fixed_sample_manifest,
)
from value_investment_agent.research_profile import PROFILES


ROOT = Path(__file__).resolve().parents[1]


def test_default_manifest_contains_the_three_frozen_companies():
    manifest = load_fixed_sample_manifest()

    assert manifest.schema_version == "fixed-sample-manifest-v1"
    assert manifest.manifest_version == "20260922.1"
    assert manifest.protocol_version == "fixed-sample-admission-v1"
    assert {entry.symbol for entry in manifest.companies} == {
        "600519",
        "000333",
        "601088",
    }
    assert {entry.name for entry in manifest.companies} == {
        "贵州茅台",
        "美的集团",
        "中国神华",
    }


def test_manifest_policies_match_profiles_models_and_decisions():
    manifest = load_fixed_sample_manifest()
    expected = {
        "600519": ("quality_compounder", "CONTINUE_CONDITIONAL_MODEL"),
        "000333": ("mature_manufacturing", "RESOLVE_MODEL_INPUTS"),
        "601088": ("cyclical_cash_return", "PAUSE_PRODUCTION_VALUATION"),
    }

    for symbol, (profile_id, decision) in expected.items():
        entry = manifest.entry(symbol)
        profile = PROFILES[profile_id]

        assert entry.profile_id == profile_id
        assert entry.primary_model == profile.primary_valuation_model
        assert entry.admission_state == "ADMITTED_FOR_RESEARCH"
        assert entry.distribution_status == "PARTIAL"
        assert entry.decision == decision
        assert entry.as_policy().profile_id == profile_id
        assert entry.as_policy().decision == decision


def test_manifest_contains_no_execution_or_position_fields():
    raw = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "action",
        "trade_approved",
        "target_weight",
        "position_size",
        "order_quantity",
        "proposed_entry",
        "buy",
        "sell",
        "live_eligible",
    }

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(raw)


def test_script_uses_the_versioned_manifest_instead_of_hardcoded_policies():
    spec = importlib.util.spec_from_file_location(
        "fixed_sample_review_script",
        ROOT / "scripts/review_fixed_sample_admission.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    loaded = load_fixed_sample_manifest()
    assert module.policies() == loaded.policies
    assert module.MANIFEST_PATH == DEFAULT_MANIFEST_PATH


def test_manifest_rejects_execution_keys():
    raw = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["companies"][0]["target_weight"] = "0.10"
    with tempfile.TemporaryDirectory(prefix="manifest-") as directory:
        path = Path(directory) / "manifest.json"
        path.write_text(
            json.dumps(raw, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="execution keys"):
            load_fixed_sample_manifest(path)


def test_manifest_rejects_duplicate_symbols():
    raw = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["companies"].append(dict(raw["companies"][0]))
    with tempfile.TemporaryDirectory(prefix="manifest-") as directory:
        path = Path(directory) / "manifest.json"
        path.write_text(
            json.dumps(raw, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unique"):
            load_fixed_sample_manifest(path)


def test_manifest_rejects_profile_model_mismatch():
    raw = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["companies"][0]["primary_model"] = "fcff"
    with tempfile.TemporaryDirectory(prefix="manifest-") as directory:
        path = Path(directory) / "manifest.json"
        path.write_text(
            json.dumps(raw, ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="primary model"):
            load_fixed_sample_manifest(path)


@pytest.mark.skipif(
    not (ROOT / "runtime/fixed-sample-admission-review-latest.json").is_file(),
    reason="frozen admission review pointer is not available in a clean checkout",
)
def test_manifest_based_review_preserves_frozen_company_decisions():
    spec = importlib.util.spec_from_file_location(
        "fixed_sample_review_script",
        ROOT / "scripts/review_fixed_sample_admission.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    current = module.build_review()
    pointer = json.loads(
        (ROOT / "runtime/fixed-sample-admission-review-latest.json").read_text(
            encoding="utf-8"
        )
    )
    frozen_path = ROOT / pointer["path"] / "evidence.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))

    assert current["engineering_orchestration_status"] == frozen[
        "engineering_orchestration_status"
    ]
    assert current["production_valuation_available"] == frozen[
        "production_valuation_available"
    ]
    assert current["action"] == frozen["action"] == "no_order"
    assert set(current["research_sample_members"]) == set(
        frozen["research_sample_members"]
    )

    current_companies = {
        item["symbol"]: item for item in current["companies"]
    }
    frozen_companies = {
        item["symbol"]: item for item in frozen["companies"]
    }
    for symbol in {"600519", "000333", "601088"}:
        for field in (
            "profile_id",
            "decision",
            "decision_reason",
            "cash_return_status",
            "bounded_value_judgment",
            "production_valuation_status",
            "required_evidence",
            "action",
        ):
            assert current_companies[symbol][field] == frozen_companies[symbol][field]


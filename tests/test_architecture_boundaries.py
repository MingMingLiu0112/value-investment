from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _load_growth_baseline() -> dict[str, object]:
    return json.loads(
        (ROOT / "config" / "architecture-growth-baseline-v1.json").read_text(
            encoding="utf-8"
        )
    )


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_hash_bound_historical_validation_contract_is_byte_for_byte_frozen():
    path = ROOT / "src" / "value_investment_agent" / "historical_validation.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    assert digest == "806d890817611000a588c9ee76ee00cc18a2529d5e1ee9769c092cc00452c5ba"


def test_historical_validation_domain_has_no_infrastructure_or_presentation_imports():
    path = (
        ROOT
        / "src"
        / "value_investment_agent"
        / "historical_validation.py"
    )
    forbidden_prefixes = (
        "openpyxl",
        "psycopg",
        "requests",
        "httpx",
        "scripts",
        "tests",
        "value_investment_agent.presentation",
        "value_investment_agent.operations",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in _imported_modules(path)
        for prefix in forbidden_prefixes
    )


def test_gap_classification_domain_and_legacy_shim_export_same_contracts():
    legacy = importlib.import_module("value_investment_agent.gap_classification")
    domain = importlib.import_module(
        "value_investment_agent.domain.research.gap_classification"
    )

    assert domain.__all__
    for name in domain.__all__:
        assert getattr(legacy, name) is getattr(domain, name)


def test_research_profile_domain_and_legacy_shim_export_same_contracts():
    legacy = importlib.import_module("value_investment_agent.research_profile")
    domain = importlib.import_module(
        "value_investment_agent.domain.research.research_profile"
    )

    assert domain.__all__
    for name in domain.__all__:
        assert getattr(legacy, name) is getattr(domain, name)


def test_research_case_domain_and_legacy_shim_export_same_contracts():
    legacy = importlib.import_module("value_investment_agent.research_case")
    domain = importlib.import_module(
        "value_investment_agent.domain.research.research_case"
    )

    assert domain.__all__ == ["ResearchCase"]
    for name in domain.__all__:
        assert getattr(legacy, name) is getattr(domain, name)


def test_research_gate_contracts_domain_and_legacy_shims_export_same_objects():
    cases = (
        (
            "value_investment_agent.human_research_approval",
            "value_investment_agent.domain.research.human_research_approval",
            (
                "artifact_fingerprint",
                "HumanResearchApprovalReceipt",
                "resolve_human_research_approval",
            ),
        ),
        (
            "value_investment_agent.research_gate",
            "value_investment_agent.domain.research.research_gate",
            (
                "ResearchGate",
                "evaluate",
                "evaluate_with_human_approval",
                "evaluate_with_valuation",
            ),
        ),
        (
            "value_investment_agent.research_run_contract",
            "value_investment_agent.domain.research.research_run_contract",
            (
                "ResearchValuationApproval",
                "AssumptionScenarioBinding",
                "canonical_contract_payload",
                "valuation_result_sha256",
            ),
        ),
    )

    for legacy_name, domain_name, contracts in cases:
        legacy = importlib.import_module(legacy_name)
        domain = importlib.import_module(domain_name)
        for contract in contracts:
            assert getattr(legacy, contract) is getattr(domain, contract)


def test_new_layers_do_not_import_presentation_operations_or_scripts():
    forbidden_prefixes = (
        "openpyxl",
        "psycopg",
        "requests",
        "httpx",
        "scripts",
        "tests",
        "value_investment_agent.presentation",
        "value_investment_agent.operations",
    )
    for layer in ("domain", "application"):
        for path in (ROOT / "src" / "value_investment_agent" / layer).rglob("*.py"):
            imported = _imported_modules(path)
            assert not any(
                name == prefix or name.startswith(prefix + ".")
                for name in imported
                for prefix in forbidden_prefixes
            ), path


def test_root_artifact_clutter_does_not_grow():
    root_xlsx = list(ROOT.glob("*.xlsx"))
    root_manifests = [
        path
        for path in ROOT.glob("*.json")
        if path.name.endswith(".manifest.json") or path.name.endswith(".receipt.json")
    ]

    assert len(root_xlsx) <= 29
    assert len(root_manifests) <= 29


def test_current_artifact_entry_is_documented():
    current_index = (ROOT / "artifacts" / "current" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "config/current-trial-workbook.json" in current_index
    assert "WORKBOOK_PATH" in current_index


def test_new_code_placement_rules_are_recorded():
    rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    inventory = (
        ROOT / "docs" / "architecture" / "repository-architecture.md"
    ).read_text(encoding="utf-8")

    assert "## New Code Placement Rules" in rules
    assert "DEPRECATED_COMPATIBILITY_SHIM" in rules
    assert "NEW_CODE_PLACEMENT_RULES = ACTIVE" in inventory
    assert "HISTORICAL_VALIDATION_DOMAIN_MIGRATION" in inventory


def test_new_root_python_module_growth_is_blocked():
    baseline = _load_growth_baseline()
    allowed = set(baseline["allowed_root_modules"])
    current = {
        path.name
        for path in (ROOT / "src" / "value_investment_agent").glob("*.py")
    }

    assert current <= allowed


def test_script_business_logic_growth_is_blocked():
    baseline = _load_growth_baseline()
    threshold = int(baseline["script_business_logic_threshold_lines"])
    oversized = dict(baseline["oversized_scripts"])
    current = {
        path.name: _line_count(path)
        for path in (ROOT / "scripts").glob("*.py")
    }

    assert not {
        name
        for name, lines in current.items()
        if lines > threshold and name not in oversized
    }
    assert not {
        name
        for name, limit in oversized.items()
        if current.get(name, 0) > int(limit)
    }


def test_new_domain_and_application_code_has_no_symbol_literals():
    symbol = re.compile(r"[0-9]{6}")
    for layer in ("domain", "application"):
        for path in (ROOT / "src" / "value_investment_agent" / layer).rglob(
            "*.py"
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            literals = {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and symbol.fullmatch(node.value)
            }
            assert not literals, (path, literals)

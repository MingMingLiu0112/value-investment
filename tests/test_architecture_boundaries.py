from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

    assert len(root_xlsx) <= 35
    assert len(root_manifests) <= 40


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

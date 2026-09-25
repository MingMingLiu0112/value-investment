from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_validation_domain_and_legacy_shim_export_same_contracts():
    legacy = importlib.import_module("value_investment_agent.historical_validation")
    domain = importlib.import_module(
        "value_investment_agent.domain.historical_validation"
    )

    assert domain.__all__
    for name in domain.__all__:
        assert getattr(legacy, name) is getattr(domain, name)


def test_historical_validation_domain_has_no_infrastructure_or_presentation_imports():
    path = (
        ROOT
        / "src"
        / "value_investment_agent"
        / "domain"
        / "historical_validation"
        / "admission.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

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
        for name in imported
        for prefix in forbidden_prefixes
    )


def test_new_code_placement_rules_are_recorded():
    rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    inventory = (
        ROOT / "docs" / "architecture" / "repository-architecture.md"
    ).read_text(encoding="utf-8")

    assert "## New Code Placement Rules" in rules
    assert "DEPRECATED_COMPATIBILITY_SHIM" in rules
    assert "NEW_CODE_PLACEMENT_RULES = ACTIVE" in inventory

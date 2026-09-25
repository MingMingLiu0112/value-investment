from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    assert "HISTORICAL_VALIDATION_DOMAIN_MIGRATION" in inventory

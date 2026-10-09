from __future__ import annotations

import ast
from pathlib import Path

from value_investment_agent import evidence_dependencies, provider_scope, roe_scope
from value_investment_agent.domain.research import evidence_dependencies as evidence_domain
from value_investment_agent.infrastructure.market_data import provider_scope as provider_adapter
from value_investment_agent.infrastructure.market_data import roe_scope as roe_adapter


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "value_investment_agent"


def test_migrated_root_modules_are_compatibility_only():
    paths = {
        "evidence_dependencies.py": (evidence_dependencies.affected_point_ids,
                                     evidence_domain.affected_point_ids),
        "provider_scope.py": (provider_scope.snapshot_proves_provider_field,
                              provider_adapter.snapshot_proves_provider_field),
        "roe_scope.py": (roe_scope.snapshot_proves_simple_roe,
                         roe_adapter.snapshot_proves_simple_roe),
    }
    for filename, (legacy, canonical) in paths.items():
        assert legacy is canonical
        path = PACKAGE / filename
        source = path.read_text(encoding="utf-8")
        assert "DEPRECATED_COMPATIBILITY_SHIM" in source
        tree = ast.parse(source)
        assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in tree.body)


def test_migrated_domain_has_no_external_runtime_imports():
    path = PACKAGE / "domain" / "research" / "evidence_dependencies.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body)


def test_agent_application_has_no_excel_database_or_shell_imports():
    application = PACKAGE / "application" / "research" / "agent_review"
    forbidden = ("openpyxl", "psycopg", "subprocess", "presentation.excel", "operations")
    for path in application.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                name = node.module or ""
            elif isinstance(node, ast.Import):
                name = " ".join(alias.name for alias in node.names)
            else:
                continue
            assert not any(item in name for item in forbidden), path

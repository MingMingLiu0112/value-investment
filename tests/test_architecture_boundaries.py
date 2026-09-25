from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess

import pytest


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
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            if node.level:
                imported.update(
                    alias.name for alias in node.names if alias.name
                )
    return imported


def _tracked_root_names() -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return {
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item and b"/" not in item
    }


def test_all_receipt_bound_paths_are_byte_for_byte_frozen():
    manifest = json.loads(
        (ROOT / "config" / "architecture-frozen-paths-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["action"] == "no_order"
    for relative, expected in manifest["paths"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


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


def test_valuation_confidence_domain_and_legacy_shim_export_same_contracts():
    legacy = importlib.import_module("value_investment_agent.valuation_confidence")
    domain = importlib.import_module(
        "value_investment_agent.domain.valuation.confidence"
    )

    assert domain.__all__
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
        "presentation",
        "operations",
        "scripts",
        "tests",
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
    allowlist = json.loads(
        (ROOT / "config" / "architecture-root-artifact-allowlist-v1.json").read_text(
            encoding="utf-8"
        )
    )
    try:
        tracked_root = _tracked_root_names()
    except (OSError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"Git index unavailable: {exc}")

    root_xlsx = {name for name in tracked_root if name.endswith(".xlsx")}
    root_manifests = {
        name
        for name in tracked_root
        if name.endswith("manifest.json") or name.endswith("receipt.json")
    }

    assert allowlist["action"] == "no_order"
    assert root_xlsx == set(allowlist["workbooks"])
    assert root_manifests == set(allowlist["manifests_and_receipts"])


def test_relative_import_resolution_flags_layer_escapes(tmp_path: Path):
    module = tmp_path / "module.py"
    module.write_text(
        "from ...presentation.excel import Workbook\nfrom . import operations\n",
        encoding="utf-8",
    )

    imported = _imported_modules(module)
    assert "presentation.excel" in imported
    assert "operations" in imported


def test_current_artifact_entry_is_documented():
    current_index = (ROOT / "artifacts" / "current" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "config/current-trial-workbook.json" in current_index
    assert "WORKBOOK_PATH" in current_index


def test_current_cli_registry_is_explicit_and_bounded():
    registry = json.loads(
        (ROOT / "config" / "current-cli-entrypoints-v1.json").read_text(
            encoding="utf-8"
        )
    )
    entries = registry["entrypoints"]

    assert registry["action"] == "no_order"
    assert 20 <= len(entries) <= 50
    assert len({entry["path"] for entry in entries}) == len(entries)
    assert {
        entry["category"] for entry in entries
    } == {
        "CURRENT_OPERATIONAL_CLI",
        "CURRENT_PRODUCT_CLI",
        "CURRENT_RESEARCH_CLI",
    }
    for entry in entries:
        path = ROOT / entry["path"]
        assert path.is_file(), path
        if entry.get("status") == "FROZEN_INPUT":
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_script_inventory_covers_all_tooling_files():
    inventory = json.loads(
        (ROOT / "docs" / "architecture" / "script-inventory-v1.json").read_text(
            encoding="utf-8"
        )
    )
    entries = inventory["entries"]
    paths = {entry["path"] for entry in entries}

    assert inventory["action"] == "no_order"
    assert inventory["current_entrypoint_count"] == 43
    assert len(paths) == len(entries)
    assert sum(inventory["counts"].values()) == len(entries)
    assert "scripts/diagnostics/audit_script_inventory.py" in paths
    assert "scripts/research_cases/moutai/build_moutai_product_ttm.py" in paths
    assert "scripts/research_cases/shenhua/build_shenhua_2025_business_evidence.py" in paths
    assert not (ROOT / "scripts" / "build_moutai_product_ttm.py").exists()


def test_compatibility_shims_are_registered_and_forwarding():
    registry = json.loads(
        (ROOT / "docs" / "architecture" / "compatibility-shims-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert registry["action"] == "no_order"
    for item in registry["shims"]:
        old_path = ROOT / item["old_path"]
        new_path = ROOT / item["new_path"]
        assert old_path.is_file(), old_path
        assert new_path.is_file(), new_path
        assert "DEPRECATED_COMPATIBILITY_SHIM" in old_path.read_text(encoding="utf-8")


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


def test_company_valuation_builder_delegates_to_application_service():
    path = ROOT / "scripts" / "build_company_valuation_result.py"
    text = path.read_text(encoding="utf-8")

    assert "FCFFValuationModel" not in text
    assert "FinancialFacts" not in text
    assert "build_company_valuation_result" in text
    assert _line_count(path) <= 90


def test_legacy_research_archive_preserves_relocation_hashes():
    archive = ROOT / "docs" / "archive" / "legacy-research-20260925"
    record = json.loads(
        (archive / "relocation-record.json").read_text(encoding="utf-8")
    )

    assert record["action"] == "no_order"
    for item in record["records"]:
        path = ROOT / item["new_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_artifact_archive_preserves_relocation_hashes():
    archive = ROOT / "artifacts" / "archive" / "legacy-root-20260925"
    record = json.loads(
        (archive / "relocation-record.json").read_text(encoding="utf-8")
    )

    assert record["action"] == "no_order"
    for item in record["records"]:
        path = ROOT / item["new_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_current_artifact_registry_matches_relocation_inventory():
    inventory = json.loads(
        (
            ROOT
            / "docs"
            / "architecture"
            / "artifact-relocation-inventory-20260925.json"
        ).read_text(encoding="utf-8")
    )
    registry = json.loads(
        (
            ROOT / "artifacts" / "current" / "artifact-registry-v1.json"
        ).read_text(encoding="utf-8")
    )

    assert registry["action"] == "no_order"
    assert registry["artifact_count"] == inventory["artifact_count"]
    assert {
        (item["path"], item["sha256"]) for item in registry["records"]
    } == {
        (item["path"], item["sha256"]) for item in inventory["artifacts"]
    }


def test_phase2_document_archive_preserves_relocation_hashes():
    archive = ROOT / "docs" / "archive" / "legacy-financing-debt-20260926"
    record = json.loads(
        (archive / "relocation-record.json").read_text(encoding="utf-8")
    )

    assert record["action"] == "no_order"
    assert len(record["records"]) == 12
    for item in record["records"]:
        path = ROOT / item["new_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_current_docs_index_points_to_required_phase2_entries():
    index = (ROOT / "docs" / "current" / "README.md").read_text(encoding="utf-8")

    for expected in (
        "docs/current-stage-goal.md",
        "docs/execution-status.md",
        "docs/m4-private-input-package.md",
        "docs/m6-production-authorization-package-20260924.md",
        "config/current-trial-workbook.json",
        "docs/historical-validation-current-status.md",
        "docs/architecture/repository-architecture.md",
    ):
        assert expected in index


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

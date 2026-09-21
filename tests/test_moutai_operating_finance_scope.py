import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_operating_finance_scope", ROOT / "scripts" / "audit_moutai_operating_finance_scope.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_scope_audit_keeps_material_shared_cost_boundary_blocked():
    result = MODULE.audit()
    gates = {gate["id"]: gate for gate in result["gates"]}
    assert result["approved"] is False
    assert gates["explicit_finance_profit_rows_excluded"]["passed"] is True
    assert gates["financial_company_equity_scope"]["passed"] is False
    assert gates["shared_cost_and_asset_boundary"]["passed"] is False
    assert gates["materiality_test"]["passed"] is False
    assert result["shared_cost_sensitivity"]["total_cases"] == 648
    assert result["shared_cost_sensitivity"]["crossing_30pct_entry_cases"] == 72

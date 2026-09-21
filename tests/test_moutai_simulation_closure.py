import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_closure", ROOT / "scripts" / "run_moutai_simulation_closure.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_closure_runner_uses_the_project_virtual_environment():
    assert MODULE.PYTHON == ROOT / "runtime" / "venv" / "Scripts" / "python.exe"


def test_closure_output_remains_under_the_project_root():
    assert MODULE.ROOT / "runtime" / "strategy-validation" == ROOT / "runtime" / "strategy-validation"


def test_relative_cli_path_is_normalized_under_project_root(monkeypatch):
    monkeypatch.chdir(ROOT)
    output = MODULE.resolve_project_path(Path("runtime/strategy-validation/closure-relative-output-test"))
    assert output.is_absolute()
    assert output.is_relative_to(ROOT.resolve())


def test_closure_does_not_call_execution_mechanics_simulation_admission():
    source = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"execution_mechanics_verified": execution_mechanics_verified' in source
    assert '"simulation_eligible": False' in source


def test_closure_selects_dated_fees_for_real_history_only():
    source = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"--fee-model", "historical_sse"' in source


def test_closure_runs_the_frozen_cash_anchor_contract_separately():
    source = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"scripts/build_moutai_cash_anchor_paper_contract.py"' in source
    assert '"cash_anchor_research_history"' in source


def test_closure_retains_generated_synthetic_decision_and_sizing_evidence():
    source = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"generated_decision_states": generated_states' in source
    assert '"generated_quantities": generated_quantities' in source
    assert 'if synthetic_was_initialized and not generated_decisions:' in source

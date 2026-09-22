from pathlib import Path
import importlib.util
import json
from copy import deepcopy


ROOT = Path(__file__).resolve().parents[1]


def test_current_observation_closure_refuses_to_invent_open_or_fill():
    script = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert "--current-quote-report" in script
    assert "No proposed order exists" in script
    assert '"journal_rows": 0' in script
    assert '"new_fills": 0' in script


def test_current_only_mode_preserves_the_full_closure_pointer():
    script = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"--current-only"' in script
    assert "moutai-current-observation-latest.json" in script
    assert "It does not replay historical accounts" in script


def test_current_only_mode_can_skip_an_unchanged_archived_report():
    script = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"--skip-unchanged-current"' in script
    assert '"status": "unchanged"' in script
    assert "def current_quote_identity" in script
    assert "decision-relevant quote facts match" in script


def test_daily_paper_mode_uses_the_existing_closure_entry_and_persistent_account():
    script = (ROOT / "scripts" / "run_moutai_simulation_closure.py").read_text(encoding="utf-8")
    assert '"--daily-paper"' in script
    assert "build_moutai_current_daily_simulation.py" in script
    assert "daily-paper-state.json" in script
    assert "moutai-daily-paper-latest.json" in script
    assert '"--bounded-orders"' in script
    assert '"--simulation-policy"' in script


def test_current_cache_reuses_identical_dependencies_but_recomputes_changed_model(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("current_cache", ROOT / "scripts/run_moutai_simulation_closure.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from build_moutai_current_conditional_observation import build

    quote = ROOT / "runtime/quote-sessions/20260911T094557691211Z/report.json"
    evidence = tmp_path / "evidence.json"
    observation = build(quote)
    assert observation["scenarios"] == []
    assert "current_model_not_same_date_as_quote_session" in observation["reason_codes"]
    evidence.write_text(json.dumps(observation), encoding="utf-8")
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps({"path": str(tmp_path.relative_to(ROOT)), "sha256": module.digest(evidence)}), encoding="utf-8")
    monkeypatch.setattr(module, "CURRENT_OBSERVATION_POINTER", pointer)
    assert module.unchanged_current_observation(quote)["sha256"] == module.digest(evidence)
    model, dependencies = module.load_primary_model()
    changed = deepcopy(dependencies)
    changed["model"]["sha256"] = "0" * 64
    monkeypatch.setattr(module, "load_primary_model", lambda: (model, changed))
    assert module.unchanged_current_observation(quote) is None

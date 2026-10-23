"""The read-only audit command must not create strategy admission."""
import importlib.util
import json
from pathlib import Path

import pytest


def test_audit_uses_registered_sources_and_rejects_injection(tmp_path, monkeypatch):
    from value_investment_agent.application.hotspot import independent_validation
    monkeypatch.setattr(independent_validation, "validate_current_hotspot_strategy",
        lambda **kwargs: dict(action="no_order", strategy_validation="NOT_PROVEN"))
    path = Path(__file__).resolve().parents[1] / "scripts/current/build_hotspot_structure_validation.py"
    spec = importlib.util.spec_from_file_location("hotspot_audit_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.main(["--independent-audit", "--output-dir", "runtime/audit"]) == 2
    report = json.loads((tmp_path / "runtime/audit/independent-validation.json").read_bytes())
    assert report == dict(action="no_order", strategy_validation="NOT_PROVEN")
    with pytest.raises(FileExistsError):
        module.main(["--independent-audit", "--output-dir", "runtime/audit"])
    with pytest.raises(SystemExit):
        module.main(["--independent-audit", "--output-dir", "runtime/other",
                     "--selection-report", "injected.json"])
    with pytest.raises(ValueError, match="project root"):
        module.main(["--independent-audit", "--output-dir", "../outside"])

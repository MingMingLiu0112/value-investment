"""TL9 MVP-2: the one daily entry stays thin, registered and fail-closed."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/current/run_daily_workbench.ps1"


def _pwsh() -> str | None:
    for name in ("pwsh", "pwsh.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def test_daily_entry_is_registered_in_both_registries():
    v2 = json.loads(
        (ROOT / "config/current-cli-entrypoints-v2.json").read_text(encoding="utf-8")
    )
    assert "scripts/current/run_daily_workbench.ps1" in v2["SUPPORTED_PRODUCT_CLI"]
    inventory = json.loads(
        (ROOT / "docs/architecture/script-inventory-v1.json").read_text(encoding="utf-8")
    )
    entry = next(
        item for item in inventory["entries"]
        if item["path"] == "scripts/current/run_daily_workbench.ps1"
    )
    assert entry["category"] == "CURRENT_PRODUCT_CLI"
    assert "config/current-cli-entrypoints-v2.json" in entry["current_consumers"]


def test_daily_entry_orchestrates_existing_clis_without_new_side_doors():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ValidateSet('READ_ONLY', 'SAFE_REFRESH')" in text
    # The entry orchestrates the existing packet builder, collector and Web
    # starter instead of re-implementing any business calculation.
    assert "scripts/current/build_daily_public_packet.py" in text
    assert "scripts/collect_quote_sessions.py" in text
    assert "scripts/current/pin_current_quote_bridge.py" in text
    assert "start_web_workbench.ps1" in text
    assert "-AutoDiscoverResearchContexts" in text
    assert "--discover-contexts" in text
    assert "--test-only-retrospective" in text
    assert "--authorize-paid-api" not in text
    # It never orders, never publishes the canonical workbook and never signs
    # a human approval.
    assert "action=no_order" in text
    assert "publish_product_workbench_to_canonical" not in text
    assert "git " not in text
    assert '--no-publish' in text
    assert 'open_current_trial_workbook.py' not in text


def test_daily_entry_runs_read_only_and_reports_plain_language(tmp_path):
    pwsh = _pwsh()
    if pwsh is None:
        pytest.skip("PowerShell 7 is unavailable")
    project = tmp_path / "isolated-entry"
    current = project / "scripts/current"
    current.mkdir(parents=True)
    shutil.copy2(SCRIPT, current / SCRIPT.name)
    shutil.copy2(ROOT / "scripts/current/build_daily_public_packet.py", current)
    shutil.copytree(ROOT / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    protected = [ROOT / "config/current-daily-public-snapshot.json",
                 ROOT / ".tmp/daily-workbench-latest-run.json"]
    before = {path: path.read_bytes() if path.exists() else None for path in protected}
    completed = subprocess.run(
        [pwsh, "-NoProfile", "-File", str(current / SCRIPT.name), "-Mode", "READ_ONLY", "-NoServer", "-Symbols", "600519"],
        cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    output = completed.stdout or ""
    assert completed.returncode == 2, (completed.returncode, output, completed.stderr)
    assert "运行结果" in output
    assert "action=no_order" in output
    assert {path: path.read_bytes() if path.exists() else None for path in protected} == before
    receipt = json.loads((project / ".tmp/daily-workbench-latest-run.json").read_text(encoding="utf-8-sig"))
    assert receipt["status"] == "BLOCKED"
    assert receipt["action"] == "no_order"


def test_daily_entry_keeps_update_and_web_results_separate():
    """TL10-RC: a Web failure must never mask a failed update."""
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in ("运行结果", "公开快照", "Web 服务", "整体结果"):
        assert marker in text
    # The header documents the four update-first outcomes, including exit 4.
    assert "4  Web failed to start while the update itself succeeded" in text
    # Both Web-failure paths fall back to 4 only when the update reported 0.
    assert "} else { 4 }" in text
    assert "} elseif ($webExit -ne 0) { 4 } else { 0 }" in text
    assert "数据更新优先" in text
    # Still no shell-based repo mutation and no canonical workbook publish.
    assert "git " not in text
    assert "publish_product_workbench_to_canonical" not in text
    assert 'if (-not $coreBlocked)' in text

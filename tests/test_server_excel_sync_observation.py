from pathlib import Path


def test_server_sync_runs_local_current_observation_before_remote_payload_sync() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "run_server_excel_sync.ps1").read_text(encoding="utf-8")

    assert "function Update-MoutaiCurrentObservation" in script
    assert "function Assert-MoutaiCurrentP1Ready" in script
    assert "function ConvertFrom-AgentJsonLine" in script
    assert "scripts\\collect_quote_sessions.py --symbols 600519" in script
    assert "scripts\\prepare_moutai_current_execution_contract.py --quote-report $report" in script
    assert "Current execution-contract preparation failed" in script
    assert "ConvertFrom-AgentJsonLine -Output $collectionText -Context 'Quote collection'" in script
    assert "ConvertFrom-AgentJsonLine -Output $observationText -Context 'Daily paper-account cycle'" in script
    assert "[IO.Path]::GetFullPath([string]$collection.path)" in script
    assert "--daily-paper --current-quote-report $report --execution-contract $contract" in script
    assert "Daily paper-account cycle failed" in script
    assert "$p1 = Assert-MoutaiCurrentP1Ready -ProjectRoot $ProjectRoot" in script
    assert script.index("Assert-MoutaiCurrentP1Ready -ProjectRoot $ProjectRoot") < script.index("scripts\\collect_quote_sessions.py --symbols 600519")
    assert "Current P1 model is stale for this quote session" in script
    assert "Current P1 admission is not restricted to the permitted paper-research scope" in script
    assert "Pinned P1 contract evidence hash changed" in script
    assert "Pinned P1 current model hash changed" in script
    assert "Pinned current P1 admission evidence hash changed" in script
    assert "$observationStatus = Update-MoutaiCurrentObservation" in script
    assert "currentObservation = $observationStatus" in script
    assert "remote payload synchronization does not count as a successful daily paper cycle" in script
    assert "if ($observationStatus.status -ne 'succeeded')" in script
    assert script.index("$observationStatus = Update-MoutaiCurrentObservation") < script.index("Sync SSH key was not found")
    assert "scripts\\publish_moutai_case_workbook.py" in script
    assert "decision_relevant_observation_unchanged" in script
    assert script.index("scripts\\publish_moutai_case_workbook.py") < script.index("Sync SSH key was not found")
    assert script.count("ConvertTo-Json -Depth 8 | Set-Content") == 3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_postclose_model_refresh_has_an_internal_close_buffer_guard():
    script = (ROOT / "scripts/run_moutai_postclose_p1_refresh.ps1").read_text(encoding="utf-8")
    assert "[TimeSpan]::Parse('15:05:00')" in script
    assert "Post-close P1 refresh must not run before" in script


def test_postclose_refresh_stages_b1_research_without_bypassing_p1_gate():
    script = (ROOT / "scripts/run_moutai_postclose_p1_refresh.ps1").read_text(encoding="utf-8")
    assert "model_staged_simulation_blocked" in script
    assert "p1_simulation_admitted" in script
    assert "blocking_gate_ids = $admission.blocking_gate_ids" in script
    assert "P1 admission remains blocked; the 16:50 paper cycle must fail closed" not in script
    assert "trade_approved = $false" in script


def test_daily_b1_refresh_only_accepts_declared_postclose_states():
    script = (ROOT / "scripts/run_moutai_b1_after_close.ps1").read_text(encoding="utf-8")
    assert "ConvertFrom-Json -ErrorAction Stop" in script
    assert "'p1_simulation_admitted', 'model_staged_simulation_blocked'" in script
    assert "Unexpected post-close P1 refresh status" in script


def test_mvp_publication_is_candidate_first_and_explicitly_opt_in():
    script = (ROOT / "scripts/run_excel_mvp_publication.ps1").read_text(encoding="utf-8")
    assert "[switch]$Publish" in script
    assert "preview_workbook_frontdoor.py" in script
    assert "'--skip-render'" in script
    assert "verify_wps_navigation.ps1" in script
    assert "publish_workbook_candidate.py" in script
    assert "verified_not_published" in script
    assert "expected-destination-sha256" in script


def test_scheduled_b1_publication_requires_a_same_date_research_result():
    script = (ROOT / "scripts/run_moutai_b1_excel_publish.ps1").read_text(encoding="utf-8")
    assert "$value.valuation_date -ne $ExpectedDate" in script
    assert "$reverse.quote_date -ne $ExpectedDate" in script
    assert "$null -eq $value.current_price" in script
    assert "$null -eq $value.margin_to_bear" in script
    assert "Join-Path $evidencePath 'evidence.json'" in script
    assert "run_excel_mvp_publication.ps1') -Publish" in script
    assert "trade_approved = $false" in script

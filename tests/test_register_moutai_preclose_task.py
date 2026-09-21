from pathlib import Path


def test_preclose_task_is_weekday_before_close_and_bounded():
    script = (Path(__file__).parents[1] / "scripts" / "register_moutai_preclose_task.ps1").read_text(encoding="utf-8")
    assert "ValueInvestmentAgent-MoutaiPrecloseCapitalRefresh" in script
    assert "14:45" in script
    assert "Monday, Tuesday, Wednesday, Thursday, Friday" in script
    assert "ExecutionTimeLimit (New-TimeSpan -Minutes 12)" in script
    assert "MultipleInstances IgnoreNew" in script

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workbook_validator_checks_current_guide_structure_not_a_retired_literal():
    script = (ROOT / "scripts" / "validate_workbook_output.py").read_text(encoding="utf-8")
    assert "guide_text =" in script
    assert "投资路径 | 可以重叠；行业口径另行匹配" in script
    assert "财务五问 | 所有适用公司必答，不用单一总分替代" in script
    assert "日常模拟、R1、R2分开验收" in script
    assert "完整策略细则 | 实验参数仍需按目标MD验收" not in script

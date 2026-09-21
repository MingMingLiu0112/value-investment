from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_execution_contract_patch_is_limited_to_existing_moutai_status_cells():
    script = (ROOT / "scripts" / "patch_moutai_execution_contract_workbook.py").read_text(encoding="utf-8")
    assert 'workbook["09_公司研究"]' in script
    assert 'workbook["21_决策验证"]' in script
    assert 'research.cell(research_row, 16)' in script
    assert 'headers.index("策略验证状态") + 1' in script
    assert "Execution status would exceed Excel cell text limit" in script

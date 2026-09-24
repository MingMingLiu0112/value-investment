from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

VERIFIERS = (
    "scripts/verify_m3_history_original_workbook_wps.ps1",
    "scripts/verify_m7_daily_workbench_wps.ps1",
    "scripts/verify_m7_workbench_wps.ps1",
    "scripts/verify_m7_workbench_v2_wps.ps1",
)


def test_wps_verifiers_materialize_values_instead_of_using_usedrange_text():
    for relative in VERIFIERS:
        path = ROOT / relative
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ".UsedRange.Text" not in line:
                continue
            assert line.lstrip().startswith("#"), (
                f"{relative}:{line_number} uses WPS COM UsedRange.Text, "
                "which is empty on this host"
            )

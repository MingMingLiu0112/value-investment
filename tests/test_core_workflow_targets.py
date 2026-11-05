"""Keep the explicit offline CI test list free of duplicate collections."""
from collections import Counter
from pathlib import Path
import re


def test_core_offline_pytest_targets_are_unique():
    workflow = (Path(__file__).resolve().parents[1]
                / ".github/workflows/core-research-gates.yml").read_text(encoding="utf-8")
    targets = re.findall(r"^\s+(tests/\S+\.py)\s*$", workflow, flags=re.MULTILINE)
    assert targets
    assert {target: count for target, count in Counter(targets).items() if count > 1} == {}

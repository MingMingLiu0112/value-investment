from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "m7_workbench_v2_candidate_builder",
    ROOT / "scripts" / "build_m7_workbench_v2_candidate.py",
)
BUILDER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BUILDER)


def test_v2_adds_pinned_joint_checkpoint_as_seventh_layer():
    assert BUILDER.V2_MANIFEST_SCHEMA == "m7-workbench-candidate-v2"
    assert len(BUILDER.V2_ADDON_SPECS) == 7
    assert BUILDER.V2_ADDON_SPECS[-1] == BUILDER.JOINT_CHECKPOINT_SPEC
    assert BUILDER.V2_ADDON_SPECS[-1]["id"] == "m4_m5_joint_checkpoint"
    assert BUILDER.V2_ADDON_SPECS[-1]["prefix"] == "M4M5联合_"
    assert BUILDER.V2_ADDON_SPECS[-1]["overview_sheet"] == "M4M5联合_00_总览"
    assert BUILDER.V2_ADDON_SPECS[-1]["sha256"] == (
        "353f6b4572cc6ee1be3d1f44011a984a1e475bf9a33a938975e0d3f593d92612"
    )

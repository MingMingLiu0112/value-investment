import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_paper", ROOT / "scripts" / "run_moutai_paper_decisions.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_legacy_reference_is_visible_but_cannot_unblock_historical_orders():
    rows = MODULE.json.loads(MODULE.INPUT.read_text(encoding="utf-8"))
    decisions = MODULE.build_decisions(rows, MODULE.load_legacy_references())
    assert len(decisions) == 2674
    assert all(row["state"] == "blocked" and row["action"] == "no_order" for row in decisions)
    assert all(row["legacy_reference_status"].startswith("unapproved_") for row in decisions)
    assert all("unapproved_legacy_pe_pb_reference" in row["reasons"] for row in decisions)

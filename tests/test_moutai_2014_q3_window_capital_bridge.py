import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "moutai_2014_q3_window_capital_bridge",
    ROOT / "scripts" / "audit_moutai_2014_q3_window_capital_bridge.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_bridge_covers_announcements_without_claiming_clean_surplus():
    result = module.build()
    assert result["index_coverage"]["announcement_count"] == 12
    assert len(result["reviewed_documents"]) == 4
    assert all(not item["capital_term_hits"]["pypdf"] for item in result["reviewed_documents"])
    assert all(not item["capital_term_hits"]["pdfium"] for item in result["reviewed_documents"])
    assert "clean_surplus_unresolved" in result["status"]
    assert result["formal_fair_value"] is None
    assert result["trade_approved"] is False

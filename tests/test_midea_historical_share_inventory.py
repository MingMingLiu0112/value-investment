import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("midea_share_inventory", ROOT / "scripts" / "inventory_midea_historical_share_disclosures.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_candidate_inventory_is_page_bound_and_does_not_extract_share_values():
    records = MODULE.candidates(["\u7b2c\u4e00\u9875", "\u516c\u53f8\u80a1\u672c 100 \u5143\uff1b\u5e93\u5b58\u80a1 3 \u80a1\u3002"])
    assert {(row["page"], row["term"]) for row in records} == {(2, "\u80a1\u672c"), (2, "\u5e93\u5b58\u80a1")}
    assert all("value" not in row for row in records)


def test_archived_annual_inventory_stays_unapproved():
    inventory = MODULE.build_inventory()
    assert [row["report_year"] for row in inventory["reports"]] == list(range(2014, 2025))
    assert all(len(row["sha256"]) == 64 for row in inventory["reports"])
    assert inventory["share_timeline_approved"] is False
    assert inventory["trade_approved"] is False

"""Direct Q3/H1 historical bridge tests; real public PDFs are opt-in."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

import pytest

from value_investment_agent.application.research.current_capital_q3_h1_bridge_v1 import (
    REGISTRY, read_q3_h1_capital_bridge,
)

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
FORK = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_root(tmp_path):
    for relative in (REGISTRY, "config/current-capital-h1-ocr-v2.json"):
        dest = tmp_path / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FORK / relative, dest)
    return tmp_path


def test_clean_missing_q3_original_fails_closed(clean_root):
    result = read_q3_h1_capital_bridge(clean_root, NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["error_code"] == "Q3_REGISTERED_SOURCE_MISSING"
    assert result["q3_ordinary_shares"] == "UNKNOWN"
    assert result["h1_ordinary_shares"] == "UNKNOWN"
    assert result["current_continuity"] == "UNPROVEN"
    assert result["formal_eligibility"] is False


@pytest.mark.parametrize("damage,code", [
    ("hash", "Q3_REGISTERED_SOURCE_HASH_MISMATCH"),
    ("traversal", "Q3_REGISTRATION_INVALID"),
    ("date", "H1_SOURCE_AVAILABILITY_INVALID"),
    ("future", "H1_SOURCE_NOT_AVAILABLE_AS_OF"),
])
def test_registered_q3_rejects_bad_source_or_time(clean_root, damage, code):
    path = clean_root / REGISTRY
    data = json.loads(path.read_text(encoding="utf-8"))
    q3 = data["q3"]
    if damage == "hash":
        file = clean_root / q3["original"]["path"]
        file.parent.mkdir(parents=True)
        file.write_bytes(b"wrong")
    elif damage == "traversal":
        q3["original"]["path"] = "runtime/../outside/original.pdf"
    elif damage == "date":
        q3["available_at"] = "2026-10-31T23:59:59+08:00"
    else:
        q3["available_at"] = "2026-11-01T00:00:00+08:00"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = read_q3_h1_capital_bridge(clean_root, NOW if damage != "future" else
        datetime.fromisoformat("2026-10-31T23:59:59+08:00"))
    assert result["status"] == "UNASSESSABLE"
    assert result["error_code"] == code
    assert result["q3_ordinary_shares"] == "UNKNOWN"


def test_real_q3_h1_cold_replay():
    root = os.environ.get("TEST_Q3_H1_BRIDGE_ROOT")
    if not root:
        pytest.skip("Set TEST_Q3_H1_BRIDGE_ROOT for public-original cold replay")
    root = Path(root)
    original = root / "runtime/q3-2026-600519/original.pdf"
    before = original.read_bytes()
    result = read_q3_h1_capital_bridge(root, NOW)
    assert original.read_bytes() == before
    assert result["status"] == "MONETARY_CAPITAL_VERIFIED_SHARES_UNKNOWN", result
    assert result["q3_monetary_capital_cny"] == "1250081601.00"
    assert result["q3_comparison_capital_cny"] == "1252270215.00"
    assert result["monetary_capital_unit"] == "CNY"
    assert result["statement_header_page"] == 5 and result["monetary_capital_page"] == 7
    assert result["q3_ordinary_shares"] == "UNKNOWN"
    assert result["h1_ordinary_shares"] == 1250081601
    assert result["h1_to_q3_continuity"] == "UNKNOWN"
    assert result["current_continuity"] == "UNPROVEN"
    assert result["formal_eligibility"] is False


def test_real_q3_without_registered_h1_fails_closed(clean_root):
    root = os.environ.get("TEST_Q3_H1_BRIDGE_ROOT")
    if not root:
        pytest.skip("Set TEST_Q3_H1_BRIDGE_ROOT for source-bound missing-H1 check")
    source = Path(root) / "runtime/q3-2026-600519"
    target = clean_root / "runtime/q3-2026-600519"
    shutil.copytree(source, target)
    result = read_q3_h1_capital_bridge(clean_root, NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["error_code"].startswith("Q3_H1_NOT_VERIFIED:")
    assert result["q3_ordinary_shares"] == "UNKNOWN"
    assert result["h1_ordinary_shares"] == "UNKNOWN"

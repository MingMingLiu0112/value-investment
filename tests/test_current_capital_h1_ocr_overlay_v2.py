"""Direct tests for explicit H1 registration; real evidence is opt-in."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

from value_investment_agent.application.research.current_capital_h1_ocr_overlay_v2 import (
    REGISTRY, read_capital_with_h1_shares,
)

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
CONFIG = Path(__file__).resolve().parents[1] / REGISTRY


def read(root, as_of=NOW):
    return read_capital_with_h1_shares(root, "600519", as_of)


@pytest.fixture
def clean_root(tmp_path):
    target = tmp_path / REGISTRY
    target.parent.mkdir(parents=True)
    shutil.copyfile(CONFIG, target)
    return tmp_path


def test_clean_checkout_missing_original_fails_closed(clean_root):
    result = read(clean_root)
    h1 = result["h1_share_observation"]
    assert h1["status"] == "UNASSESSABLE"
    assert h1["ordinary_shares"] is None
    assert h1["error_code"] == "H1_REGISTERED_SOURCE_MISSING"
    assert h1["current_continuity"] == "UNPROVEN"
    assert result["formal_eligibility"] is False
    assert result["current_capital_continuity"] == "NOT_PROVEN"


@pytest.mark.parametrize("damage,code", [
    ("hash", "H1_REGISTERED_SOURCE_HASH_MISMATCH"),
    ("traversal", "H1_REGISTRATION_INVALID"),
    ("absolute", "H1_REGISTRATION_INVALID"),
    ("missing_field", "H1_REGISTRY_CASE_INVALID"),
])
def test_registration_rejects_bad_binding(clean_root, damage, code):
    path = clean_root / REGISTRY
    data = json.loads(path.read_text(encoding="utf-8"))
    case = data["cases"]["600519"]
    if damage == "missing_field":
        del case["cross_notice_available_at"]
    else:
        item = case["files"]["source-manifest.json"]
        if damage == "hash":
            target = clean_root / item["path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(b"wrong")
        elif damage == "traversal":
            item["path"] = "runtime/../outside/source-manifest.json"
        else:
            item["path"] = str((clean_root / item["path"]).resolve())
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert read(clean_root)["h1_share_observation"]["error_code"] == code


def test_unregistered_symbol_has_no_h1_observation(clean_root):
    result = read_capital_with_h1_shares(clean_root, "000568", NOW)
    assert result["h1_share_observation"]["status"] == "NOT_REGISTERED"


def test_real_registered_h1_cold_replay(monkeypatch):
    root = os.environ.get("TEST_H1_OVERLAY_ROOT")
    if not root:
        pytest.skip("Set TEST_H1_OVERLAY_ROOT for real cold replay")
    monkeypatch.setitem(sys.modules, "rapidocr", None)
    result = read(Path(root))
    h1 = result["h1_share_observation"]
    assert h1["status"] == "VERIFIED", h1
    assert (h1["shares_before"], h1["cancelled_shares"], h1["ordinary_shares"]) == (
        1252270215, 2188614, 1250081601)
    assert h1["report_period_end"] == "2026-06-30"
    assert h1["current_continuity"] == "UNPROVEN"
    assert h1["formal_eligibility"] is False
    assert result["formal_eligibility"] is False
    early = read(Path(root), datetime.fromisoformat("2026-08-15T23:59:59+08:00"))
    assert early["h1_share_observation"]["status"] == "UNASSESSABLE"
    assert early["h1_share_observation"]["ordinary_shares"] is None
    assert early["h1_share_observation"]["error_code"] == "H1_SOURCE_NOT_AVAILABLE_AS_OF"

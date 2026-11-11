"""Direct source/PIT/scope tests; sealed public originals are explicit opt-in."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

import pytest

from value_investment_agent.infrastructure.filings import parent_wc_history_600519_v1 as mod

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)
FORK = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_root(tmp_path):
    target = tmp_path / mod.REGISTRY
    target.parent.mkdir(parents=True)
    shutil.copyfile(FORK / mod.REGISTRY, target)
    return tmp_path


def test_missing_original_is_unassessable(clean_root):
    result = mod.read_parent_wc_history(clean_root, NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["error_code"] == "PARENT_WC_ORIGINAL_MISSING"
    assert result["operating_wc_cash_cny"] == "UNKNOWN"


@pytest.mark.parametrize("damage,code", [
    ("hash", "PARENT_WC_ORIGINAL_HASH_MISMATCH"),
    ("path", "PARENT_WC_SOURCE_BINDING_INVALID"),
    ("future", "PARENT_WC_SOURCE_NOT_AVAILABLE_AS_OF"),
    ("naive", "PARENT_WC_SOURCE_NOT_AVAILABLE_AS_OF"),
    ("url_date", "PARENT_WC_SOURCE_NOT_AVAILABLE_AS_OF"),
])
def test_source_fail_closed(clean_root, damage, code):
    registry = clean_root / mod.REGISTRY
    data = json.loads(registry.read_text(encoding="utf-8"))
    source = data["sources"][0]
    if damage == "hash":
        path = clean_root / source["path"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"wrong")
    elif damage == "path":
        source["path"] = "runtime/../outside/original.pdf"
    elif damage == "future":
        source["available_at"] = "2027-01-01T00:00:00+08:00"
    elif damage == "naive":
        source["available_at"] = "2026-10-30T10:40:54"
    else:
        source["published_date"] = "2026-04-18"
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = mod.read_parent_wc_history(clean_root, NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["error_code"] == code
    assert result["operating_wc_cash_cny"] == "UNKNOWN"


def test_real_parent_balance_not_wc_cash():
    root = os.environ.get("TEST_PARENT_WC_ROOT")
    if not root:
        pytest.skip("Set TEST_PARENT_WC_ROOT for public FY/H1 cold replay")
    result = mod.read_parent_wc_history(Path(root), NOW)
    assert result["status"] == "PARENT_BALANCE_MOVEMENTS_ONLY", result
    assert result["operating_wc_cash_cny"] == "UNKNOWN"
    assert result["formal_eligibility"] is False
    fy, h1 = result["observations"]
    assert fy["parent_cfo_cny"] == "32618216666.91"
    assert fy["excluded_group_note_cfo_cny"] == "61522204989.35"
    assert h1["parent_cfo_cny"] == "15224606455.02"
    assert h1["excluded_group_note_cfo_cny"] == "70690750119.06"
    assert h1["balance_rows"]["inventory"]["balance_change_cny"] == "-166098556.24"
    assert h1["balance_rows"]["accounts_receivable"]["balance_change_cny"] == "-2049025456.39"
    assert h1["balance_rows"]["accounts_payable"]["balance_change_cny"] == "-632741986.99"
    early = mod.read_parent_wc_history(Path(root), datetime.fromisoformat("2026-11-10T13:11:09+00:00"))
    assert early["status"] == "UNASSESSABLE"
    assert early["operating_wc_cash_cny"] == "UNKNOWN"


def test_group_note_cannot_be_attributed_to_parent(monkeypatch):
    root = os.environ.get("TEST_PARENT_WC_ROOT")
    if not root:
        pytest.skip("Set TEST_PARENT_WC_ROOT for real scope rejection")
    original = mod._pages
    def changed(path, numbers):
        pages = original(path, numbers)
        if 115 in pages:
            pages[115] = pages[115].replace("61,522,204,989.35", "32,618,216,666.91")
        return pages
    monkeypatch.setattr(mod, "_pages", changed)
    result = mod.read_parent_wc_history(Path(root), NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["error_code"] == "PARENT_WC_NOTE_SCOPE_NOT_GROUP"
    assert result["operating_wc_cash_cny"] == "UNKNOWN"

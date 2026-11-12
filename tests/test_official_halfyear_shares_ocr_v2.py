import json
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

import pytest

from value_investment_agent.infrastructure.filings.official_halfyear_shares_ocr_v2 import (
    _availability, replay_halfyear_shares,
)

SHA = "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6"


def test_portable_availability_next_day_boundary():
    manifest = {"source_url": "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF",
                "original_available_at": "2026-08-16T00:00:00+08:00"}
    available = datetime.fromisoformat(manifest["original_available_at"])
    assert _availability(manifest, "original", available) == available
    with pytest.raises(ValueError, match="H1_SOURCE_NOT_AVAILABLE_AS_OF"):
        _availability(manifest, "original", datetime.fromisoformat("2026-08-15T23:59:59+08:00"))


@pytest.mark.parametrize("url_date,available", [
    ("2026-05-28", "2026-05-28T23:59:59+08:00"),
    ("2026-05-28", "2026-05-30T00:00:00+08:00"),
    ("2026-05-28", "2026-05-29T00:00:00"),
    ("2026-02-30", "2026-03-01T00:00:00+08:00"),
    ("2026-05-28", "2026-05-29T01:00:00+08:00"),
])
def test_portable_availability_rejects_bad_date_or_timezone(url_date, available):
    manifest = {"cross_notice_url": f"https://static.cninfo.com.cn/finalpage/{url_date}/1225333825.PDF",
                "cross_notice_available_at": available}
    with pytest.raises(ValueError, match="H1_SOURCE_AVAILABILITY_INVALID"):
        _availability(manifest, "cross_notice", datetime(2026, 11, 11, tzinfo=timezone.utc))


@pytest.fixture
def evidence():
    root = os.environ.get("TEST_H1_OCR_ROOT")
    if not root or not Path(root).is_dir():
        pytest.skip("Set TEST_H1_OCR_ROOT for sealed cold replay")
    return Path(root)


def replay(root, **changes):
    args = dict(root=root, symbol="600519", issuer_name="贵州茅台酒股份有限公司",
                report_year=2026, expected_original_sha256=SHA,
                as_of=datetime(2026, 11, 11, tzinfo=timezone.utc))
    args.update(changes)
    return replay_halfyear_shares(**args)


def test_real_cold_replay(evidence):
    result = replay(evidence)
    assert (result["shares_before"], result["cancelled_shares"], result["ordinary_shares"]) == (
        1252270215, 2188614, 1250081601)
    assert result["report_period_end"] == "2026-06-30"
    assert result["current_continuity"] == "UNPROVEN"
    assert result["formal_eligibility"] is False
    assert replay(evidence, as_of=datetime.fromisoformat("2026-08-16T00:00:00+08:00"))["ordinary_shares"] == 1250081601


def test_real_replay_without_rapidocr_install(evidence, monkeypatch):
    monkeypatch.setitem(sys.modules, "rapidocr", None)
    assert replay(evidence)["ordinary_shares"] == 1250081601


@pytest.mark.parametrize("change,code", [
    ("issuer", "H1_ISSUER_OR_PERIOD_INVALID"),
    ("source_hash", "H1_SOURCE_BINDING_INVALID"),
    ("ocr_number", "H1_OCR_RECONCILIATION_FAILED"),
    ("image_hash", "H1_OCR_BINDING_INVALID"),
    ("cross_hash", "H1_SOURCE_BINDING_INVALID"),
    ("package_hash", "H1_OCR_BINDING_INVALID"),
    ("model_hash", "H1_OCR_BINDING_INVALID"),
    ("render_hash", "H1_OCR_BINDING_INVALID"),
])
def test_fail_closed(tmp_path, evidence, change, code):
    source = evidence
    if change == "issuer":
        with pytest.raises(ValueError, match=code):
            replay(source, issuer_name="错误发行人")
        return
    if change == "source_hash":
        with pytest.raises(ValueError, match=code):
            replay(source, expected_original_sha256="0" * 64)
        return
    shutil.copytree(source, tmp_path / "evidence")
    root = tmp_path / "evidence"
    if change == "ocr_number":
        path = root / "page-23.ocr.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data["rows"]:
            row["text"] = row["text"].replace("1,250,081,601", "1,250,081,602")
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif change == "image_hash":
        with (root / "page-22.png").open("ab") as f:
            f.write(b"changed")
    elif change == "cross_hash":
        with (root / "cross-notice.pdf").open("ab") as f:
            f.write(b"changed")
    elif change == "package_hash":
        path = root / "page-22.ocr.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        name = next(iter(data["package_sha256"]))
        data["package_sha256"][name] = "0" * 64
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif change == "render_hash":
        path = root / "page-22.ocr.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["render_raw_sha256"] = "0" * 64
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif change == "model_hash":
        path = root / "page-23.ocr.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        name = next(k for k in data["package_sha256"] if k.endswith(".onnx"))
        data["package_sha256"][name] = "0" * 64
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=code):
        replay(root)


@pytest.mark.parametrize("change,code", [
    ("before_original", "H1_SOURCE_NOT_AVAILABLE_AS_OF"),
    ("before_cross", "H1_SOURCE_NOT_AVAILABLE_AS_OF"),
    ("naive_as_of", "H1_AS_OF_INVALID"),
    ("future_original", "H1_SOURCE_AVAILABILITY_INVALID"),
    ("same_day_cross", "H1_SOURCE_AVAILABILITY_INVALID"),
    ("naive_available", "H1_SOURCE_AVAILABILITY_INVALID"),
    ("url_date_mismatch", "H1_SOURCE_AVAILABILITY_INVALID"),
])
def test_availability_gate(tmp_path, evidence, change, code):
    source = evidence
    if change == "before_original":
        with pytest.raises(ValueError, match=code):
            replay(source, as_of=datetime.fromisoformat("2026-08-15T23:59:59+08:00"))
        return
    if change == "naive_as_of":
        with pytest.raises(ValueError, match=code):
            replay(source, as_of=datetime(2026, 11, 11))
        return
    shutil.copytree(source, tmp_path / "evidence")
    root = tmp_path / "evidence"
    path = root / "source-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if change == "before_cross":
        manifest["cross_notice_url"] = manifest["cross_notice_url"].replace("2026-05-28", "2026-12-01")
        manifest["cross_notice_available_at"] = "2026-12-02T00:00:00+08:00"
    elif change == "future_original":
        manifest["original_available_at"] = "2027-08-16T00:00:00+08:00"
    elif change == "same_day_cross":
        manifest["cross_notice_available_at"] = "2026-05-28T23:59:59+08:00"
    elif change == "naive_available":
        manifest["original_available_at"] = "2026-08-16T00:00:00"
    elif change == "url_date_mismatch":
        manifest["cross_notice_url"] = manifest["cross_notice_url"].replace("2026-05-28", "2026-05-29")
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=code):
        replay(root)

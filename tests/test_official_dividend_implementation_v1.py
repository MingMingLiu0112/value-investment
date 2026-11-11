"""TEST_ONLY fixture for strict official dividend implementation replay."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.infrastructure.filings import official_dividend_implementation_v1 as mod

FIRST = ("证券代码：600519 贵州茅台酒股份有限公司\n"
         "2025年年度权益分派实施公告\nA 股每股现金红利28.02423元\n"
         "2026 年 6 月 11 日的2025年度股东会审议通过。")
SECOND = ("（二）分派对象：全体股东\n"
          "扣除回购专用账户内的股份1,250,081,601股为基数，"
          "每股派发现金红利28.02423元（含税），"
          "共计派发现金红利35,032,574,305.19元。\n"
          "Ａ股 2026/6/25 － 2026/6/26 2026/6/26\n分配实施办法")


def _fixture(tmp_path, monkeypatch, *, second=SECOND):
    source = tmp_path / "original.pdf"
    source.write_bytes(b"TEST_ONLY_PDF")
    index = tmp_path / "index.json"
    stamp = int(datetime(2026, 6, 22, tzinfo=timezone.utc).timestamp() * 1000)
    row = dict(secCode="600519", announcementId="1225379934",
               adjunctUrl="finalpage/2026-06-22/1225379934.PDF", announcementTime=stamp)
    index.write_text(json.dumps({"announcements": [row]}), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    packet = dict(schema_version="research-source-receipt-v1", action="no_order",
        symbol="600519", source_host="static.cninfo.com.cn",
        published_date="2026-06-22", index_announcement_id="1225379934",
        index_announcement_time_ms=stamp,
        source_url="https://static.cninfo.com.cn/finalpage/2026-06-22/1225379934.PDF",
        fetched_at="2026-11-10T00:00:00+00:00", source_path="original.pdf",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_bytes=source.stat().st_size,
        index_captures=[dict(path="index.json", sha256=hashlib.sha256(index.read_bytes()).hexdigest())])
    receipt.write_text(json.dumps(packet), encoding="utf-8")
    monkeypatch.setattr(mod, "validate_pdf_original", lambda path: None)
    monkeypatch.setattr(mod, "extract_pages", lambda path, limit=None: [FIRST, second])
    return source, index, receipt


def _replay(root, receipt, *, at="2026-11-11T00:00:00+00:00"):
    return mod.replay_implemented_distribution(root=root, receipt_path=receipt,
        symbol="600519", issuer_name="贵州茅台酒股份有限公司",
        as_of=datetime.fromisoformat(at))


def test_approved_distribution_is_historical_schedule_not_future_policy(tmp_path, monkeypatch):
    _, _, receipt = _fixture(tmp_path, monkeypatch)
    result = _replay(tmp_path, receipt)
    assert result["scheduled_total_cny"] == "35032574305.19"
    assert result["entitled_shares"] == 1250081601
    assert result["scheduled_payment_date"] == "2026-06-26"
    assert result["formal_eligibility"] is False and result["action"] == "no_order"
    assert "NOT_PERSONAL_RECEIPT" in result["status"]


def test_original_index_and_pit_cannot_be_replaced(tmp_path, monkeypatch):
    source, index, receipt = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="NOT_AVAILABLE_AS_OF"):
        _replay(tmp_path, receipt, at="2026-11-09T00:00:00+00:00")
    index.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="INDEX_CHANGED"):
        _replay(tmp_path, receipt)
    index.write_text(json.dumps({"announcements": []}), encoding="utf-8")
    source.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="ORIGINAL_CHANGED"):
        _replay(tmp_path, receipt)


def test_headline_arithmetic_and_issuer_required(tmp_path, monkeypatch):
    _, _, receipt = _fixture(tmp_path, monkeypatch, second=SECOND.replace("35,032,574,305.19", "35,032,574,305.18"))
    with pytest.raises(ValueError, match="ARITHMETIC_OR_HEADLINE_CONFLICT"):
        _replay(tmp_path, receipt)
    monkeypatch.setattr(mod, "extract_pages", lambda path, limit=None: [FIRST.replace("600519", "600520"), SECOND])
    with pytest.raises(ValueError, match="ISSUER_OR_APPROVAL_CONTEXT_INVALID"):
        _replay(tmp_path, receipt)

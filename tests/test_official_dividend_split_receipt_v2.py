"""Direct replay of three retained official originals and four split captures."""
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil

import pytest

from value_investment_agent.infrastructure.filings import official_dividend_split_receipt_v2 as mod

EVIDENCE = None
REAL_ROOT = os.environ.get("DIVIDEND_SPLIT_EVIDENCE_ROOT")
NOW = datetime.fromisoformat("2026-11-12T12:00:00+08:00")
EXPECTED = {
    "1222015210": ("FY2024_interim", 1256197800, "23.882", "30000515859.60", "2024-12-20",
                   "c2ae81be30b3feaa191bf8897e94da37ef7392be57c60181bd49f49318ee3a6e"),
    "1223934491": ("FY2024_final", 1252887715, "27.673", "34671161737.20", "2025-06-26",
                   "8ff3e6e370c75cece700e5474337c8ecf1adb87b01a1a696bae02fd25982af3b"),
    "1224867074": ("FY2025_interim", 1252270215, "23.957", "30000637540.76", "2025-12-19",
                   "ad2f4548490a203bbcada1181341d9dc90b19a64a0ecf14ff1c8e6b9d4b71673"),
}


@pytest.fixture(scope="module", autouse=True)
def _source_mode(tmp_path_factory):
    """CI uses synthetic bytes; explicit opt-in reads the separate real corpus."""
    global EVIDENCE
    if REAL_ROOT:
        EVIDENCE = Path(REAL_ROOT).resolve()
        if not EVIDENCE.is_dir():
            raise ValueError("DIVIDEND_SPLIT_EVIDENCE_ROOT is missing")
        yield
        return
    EVIDENCE = tmp_path_factory.mktemp("synthetic-split-dividend")
    mp = pytest.MonkeyPatch()
    texts = {}
    for aid, (period, shares, per_share, total, payment, _) in EXPECTED.items():
        year, kind = period[2:6], ("中期" if period.endswith("interim") else "年度")
        published = {"1222015210": "2024-12-14", "1223934491": "2025-06-20",
                     "1224867074": "2025-12-11"}[aid]
        record = {"1222015210": "2024/12/19", "1223934491": "2025/6/25",
                  "1224867074": "2025/12/18"}[aid]
        paid = payment.replace("-", "/").replace("/06/", "/6/")
        first = (f"证券代码：600519 贵州茅台酒股份有限公司{year}年{kind}权益分派实施公告 "
                 f"A股每股现金红利{per_share}元 Ａ股{record}－{paid}{paid} "
                 f"本次方案经股东大会审议通过。（二）分派对象：全体股东。发放年度：{year}年{kind}")
        if kind == "中期":
            second = (f"登记在册。本次利润分配以方案实施前的公司总股本{shares:,}股为基数，"
                      f"每股派发现金红利{per_share}元（含税），共计派发现金红利{Decimal(total):,.2f}元")
        else:
            second = (f"登记在册。截至本公告日回购专用证券账户内股份数3,310,085股，"
                      f"总股本扣除回购专用证券账户内的股份数为{shares:,}股，"
                      f"每股派发现金红利{per_share}元（含税），共计派发现金红利{Decimal(total):,.2f}元")
        texts[aid] = [first, second]
        pdf = EVIDENCE / f"{aid}.pdf"
        pdf.write_bytes(f"TEST_ONLY_SYNTHETIC_PDF_{aid}".encode("ascii"))
        EXPECTED[aid] = (*EXPECTED[aid][:-1], sha256(pdf.read_bytes()).hexdigest())
        url = f"https://static.cninfo.com.cn/finalpage/{published}/{aid}.PDF"
        stamp = int(datetime.fromisoformat(published + "T00:00:00+08:00").timestamp() * 1000)
        row = {"announcementId": aid, "secCode": "600519", "orgId": "gssh0600519",
               "adjunctUrl": f"finalpage/{published}/{aid}.PDF", "announcementTime": stamp}
        index = json.dumps({"announcements": [row]}, ensure_ascii=False).encode("utf-8")
        (EVIDENCE / f"{aid}-cninfo-response.json").write_bytes(index)
        availability = mod.indexed_disclosure_availability(
            {"url": mod.SEARCH_URL, "announcements": [row]}, symbol="600519",
            source_id=f"cninfo:{aid}", source_url=url)
        request = {"pageNum": "1", "column": "sse", "stock": "600519,gssh0600519",
                   "searchkey": "", "category": "", "seDate": f"{published}~{published}"}
        ir = {"metadata": {"url": mod.SEARCH_URL, "method": "POST", "request": request,
              "body_representation": "RECEIVED_RESPONSE_CONTENT_NOT_RESERIALIZED_JSON",
              "sha256": sha256(index).hexdigest(), "size_bytes": len(index),
              "acquired_at": "2026-11-11T21:00:00+00:00"}, "announcement": row,
              "availability": availability}
        (EVIDENCE / f"{aid}-index-receipt.json").write_text(json.dumps(ir), encoding="utf-8")
        pr = {"method": "GET", "url": url, "collector": mod.COLLECTOR,
              "sha256": sha256(pdf.read_bytes()).hexdigest(), "size_bytes": pdf.stat().st_size,
              "acquired_at": "2026-11-11T21:01:00+00:00"}
        (EVIDENCE / f"{aid}-pdf-receipt.json").write_text(json.dumps(pr), encoding="utf-8")
    mp.setattr(mod, "validate_pdf_original", lambda path: None)
    mp.setattr(mod, "extract_pages", lambda path, limit=None: list(texts[path.stem]))
    yield
    mp.undo()


def _paths(root, aid):
    return dict(root=root, index_response_path=root / f"{aid}-cninfo-response.json",
        index_receipt_path=root / f"{aid}-index-receipt.json", pdf_path=root / f"{aid}.pdf",
        pdf_receipt_path=root / f"{aid}-pdf-receipt.json", symbol="600519",
        issuer_name="贵州茅台酒股份有限公司", as_of=NOW)


def _copy_captures(tmp_path, aid):
    for suffix in ("-cninfo-response.json", "-index-receipt.json", ".pdf", "-pdf-receipt.json"):
        shutil.copyfile(EVIDENCE / f"{aid}{suffix}", tmp_path / f"{aid}{suffix}")
    return _paths(tmp_path, aid)


@pytest.mark.parametrize("aid", EXPECTED)
def test_three_source_replay(aid):
    result = mod.replay_split_dividend_implementation(**_paths(EVIDENCE, aid))
    period, shares, per_share, total, payment, digest = EXPECTED[aid]
    assert (result["report_period"], result["implemented_shares"], result["per_share_cny"],
            result["implemented_total_cny"], result["scheduled_payment_date"],
            result["pdf_sha256"]) == (period, shares, per_share, total, payment, digest)
    assert result["announcement_id"] == aid
    assert result["status"] == "HISTORICAL_IMPLEMENTATION_SCHEDULE_NOT_PERSONAL_RECEIPT"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["historical_capture_proven"] is False
    assert datetime.fromisoformat(result["available_at"]) >= datetime.fromisoformat(
        result["conservative_public_available_at"])


@pytest.mark.parametrize("aid", EXPECTED)
@pytest.mark.parametrize("part", ("index_response_path", "index_receipt_path", "pdf_path", "pdf_receipt_path"))
def test_changed_capture_hash_fails(tmp_path, aid, part):
    args = _copy_captures(tmp_path, aid)
    if part in {"index_receipt_path", "pdf_receipt_path"}:
        receipt = json.loads(args[part].read_text(encoding="utf-8"))
        binding = receipt["metadata"] if part == "index_receipt_path" else receipt
        binding["sha256"] = "0" * 64
        args[part].write_text(json.dumps(receipt), encoding="utf-8")
    else:
        args[part].write_bytes(args[part].read_bytes() +
            (b" " if part == "index_response_path" else b"changed"))
    expected = "INDEX_HASH_OR_REQUEST" if part.startswith("index") else "PDF_HASH_OR_RECEIPT"
    with pytest.raises(ValueError, match=expected):
        mod.replay_split_dividend_implementation(**args)


@pytest.mark.parametrize("aid", EXPECTED)
def test_wrong_issuer_in_verified_pdf_text_fails(monkeypatch, aid):
    original = mod.extract_pages
    def changed(path, limit=None):
        pages = original(path, limit)
        pages[0] = pages[0].replace("贵州茅台酒股份有限公司", "其他股份有限公司")
        return pages
    monkeypatch.setattr(mod, "extract_pages", changed)
    with pytest.raises(ValueError, match="ISSUER_OR_APPROVAL"):
        mod.replay_split_dividend_implementation(**_paths(EVIDENCE, aid))


@pytest.mark.parametrize("aid", EXPECTED)
def test_wrong_issuer_in_index_receipt_fails(tmp_path, aid):
    args = _copy_captures(tmp_path, aid)
    receipt = json.loads(args["index_receipt_path"].read_text(encoding="utf-8"))
    receipt["announcement"]["secCode"] = "600520"
    args["index_receipt_path"].write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="INDEX_IDENTITY"):
        mod.replay_split_dividend_implementation(**args)


@pytest.mark.parametrize("aid", EXPECTED)
def test_wrong_report_period_in_verified_pdf_text_fails(monkeypatch, aid):
    original = mod.extract_pages
    def changed(path, limit=None):
        pages = original(path, limit)
        pages[0] = re.sub(r"(发放年度：\s*)20\d{2}", r"\g<1>2030", pages[0], count=1)
        return pages
    monkeypatch.setattr(mod, "extract_pages", changed)
    with pytest.raises(ValueError, match="REPORT_PERIOD"):
        mod.replay_split_dividend_implementation(**_paths(EVIDENCE, aid))


@pytest.mark.parametrize("aid", EXPECTED)
def test_wrong_implemented_total_in_verified_pdf_text_fails(monkeypatch, aid):
    original = mod.extract_pages
    total = f"{Decimal(EXPECTED[aid][3]):,.2f}"
    def changed(path, limit=None):
        pages = original(path, limit)
        pages[1] = pages[1].replace(total, "1.00")
        return pages
    monkeypatch.setattr(mod, "extract_pages", changed)
    with pytest.raises(ValueError, match="IMPLEMENTED_AMOUNT"):
        mod.replay_split_dividend_implementation(**_paths(EVIDENCE, aid))


@pytest.mark.parametrize("aid", EXPECTED)
def test_before_capture_time_fails(aid):
    receipt = json.loads((EVIDENCE / f"{aid}-pdf-receipt.json").read_text(encoding="utf-8"))
    args = _paths(EVIDENCE, aid)
    args["as_of"] = datetime.fromisoformat(receipt["acquired_at"]) - timedelta(microseconds=1)
    with pytest.raises(ValueError, match="NOT_AVAILABLE_AS_OF"):
        mod.replay_split_dividend_implementation(**args)

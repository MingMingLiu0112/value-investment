"""TEST_ONLY layout negatives plus opt-in immutable real original replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.pending_candidate_alignment import _cash_terms, _operating_events
from value_investment_agent.application.research.value_research_analysis import _bound


def pages():
    return [
        "1\n证券代码：600887 公告编号：临2026-039\n2025年年度权益分派实施公告\n"
        "A股每股现金红利0.90元\n差异化分红送转：否\n"
        "股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n"
        "Ａ股 2026/6/4 － 2026/6/5 2026/6/5\n"
        "(三)分配方案：本次利润分配以方案实施前的公司总股本100股为基数，"
        "向全体股东每股派发现金红利0.90元（含税），共计派发现金红利90.00元。",
        "2\n三、相关日期\n"
        "股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n"
        "Ａ股 2026/6/4 － 2026/6/5 2026/6/5\n"
        "本次权益分派不涉及派送红股或转增股本。\n董事会2026年5月29日",
    ]


def test_complete_cross_page_cash_scheme_reconciles_without_payment_claim():
    result = _cash_terms(pages(), "600887")
    assert result["cash_per_share"] == "0.90"
    assert result["total_gross_cash"] == "90.00"
    assert result["term_pages"]["chronology"] == [1, 2]
    assert result["amendment_chain_verified"] is False
    assert result["cash_payment_status"] == "DECLARED_SCHEDULE_NOT_PROOF_OF_RECEIPT"


@pytest.mark.parametrize("old,new", [
    ("90.00元", "91.00元"),
    ("A股每股现金红利0.90元", "A股每股现金红利0.91元"),
    ("三、相关日期", "相关日期不明"),
    ("不涉及派送红股或转增股本", "涉及派送红股或转增股本"),
    ("差异化分红送转：否", "差异化分红送转：是"),
    ("证券代码：600887", "证券代码：600519"),
    ("董事会2026年5月29日", "董事会2026年6月6日"),
])
def test_unknown_or_conflicting_terms_rejected(old, new):
    with pytest.raises(ValueError):
        _cash_terms([page.replace(old, new) for page in pages()], "600887")


def test_conflicting_duplicate_date_table_rejected():
    changed = deepcopy(pages())
    changed[1] = changed[1].replace("2026/6/5", "2026/6/6")
    with pytest.raises(ValueError):
        _cash_terms(changed, "600887")


def test_additional_non_cash_terms_not_hidden_by_exact_negative_sentence():
    changed = pages()
    changed[1] = changed[1].replace("董事会", "另每10股转增股本2股。董事会")
    with pytest.raises(ValueError):
        _cash_terms(changed, "600887")


def test_real_original_cross_page_replay():
    root = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not root:
        pytest.skip("real original root explicitly required; not a real-data pass")
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    path = Path(root) / "runtime/value-f2-replays/600887-annual-dividend-20261115T1741423113652Z/original.pdf"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "c8cd69e0a195ec9daa702306a2ba1ebf7cb8b53b1f5cae5d872cd590b0ba3c70"
    result = _cash_terms(extract_pages(path), "600887")
    assert result["eligible_distribution_shares"] == "6325360667"
    assert result["cash_per_share"] == "0.90"
    assert result["total_gross_cash"] == "5692824600.30"
    assert result["ex_date"] == result["cash_payment_date"] == "2026-06-05"
    assert path.read_bytes() == raw

def test_numbered_interim_scheme_uses_the_same_reconciliation():
    changed = [page.replace("(三)分配方案", "3.分配方案").replace(
        "2025年年度权益分派实施公告", "2026年半年度权益分派实施公告") for page in pages()]
    result = _cash_terms(changed, "600887")
    assert result["eligible_distribution_shares"] == "100"
    assert result["term_pages"]["scheme"] == [1]
    assert result["cash_payment_status"] == "DECLARED_SCHEDULE_NOT_PROOF_OF_RECEIPT"
    with pytest.raises(ValueError):
        _cash_terms([changed[0].replace("90.00元", "91.00元"), changed[1]], "600887")


def test_real_numbered_interim_distribution_original():
    root = os.environ.get("VALUE_REAL_SOURCE_ROOT")
    if not root:
        pytest.skip("real original root explicitly required; not a real-data pass")
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    path = Path(root) / "runtime/value-f2-replays/parent-q3-scope-20261120/600398-h1-distribution.pdf"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "4d1439d79185c5d7e4daa0eca57b35d3bc4c856f6762da15750cc53f75aa08b8"
    result = _cash_terms(extract_pages(path), "600398")
    assert result["eligible_distribution_shares"] == "4802770296"
    assert result["cash_per_share"] == "0.27"
    assert result["total_gross_cash"] == "1296747979.92"
    assert result["record_date"] == "2026-10-13"
    assert result["ex_date"] == result["cash_payment_date"] == "2026-10-14"
    assert result["term_pages"] == {"scheme": [1], "chronology": [1, 2]}
    assert path.read_bytes() == raw
    index_bytes = path.with_name("600398-distribution-index.json").read_bytes()
    assert hashlib.sha256(index_bytes).hexdigest() == "41bdfd6bbbe524ef927fdb2a4a4ac687bf0ddddf783924cdc98429b40f6e8fa5"
    notice, = [row for row in json.loads(index_bytes)["announcements"]
               if row["announcementId"] == "1225595367" and row["secCode"] == "600398"]
    source_url = "https://static.cninfo.com.cn/" + notice["adjunctUrl"]
    published = datetime.fromtimestamp(notice["announcementTime"] / 1000, timezone(timedelta(hours=8)))
    replay_bytes = path.with_name("600398-distribution-replay.json").read_bytes()
    assert hashlib.sha256(replay_bytes).hexdigest() == "829aa70e298aad2c0c30d75d1abd71de2939e5a5cd0d2480559b40c9dd6a9435"
    acquired = datetime.fromisoformat(json.loads(replay_bytes)["captured_at"])
    ref = dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(raw).hexdigest(),
               source_url=source_url)
    window = dict(acquired_at=acquired.isoformat(), announcements=[dict(
        announcement_id=notice["announcementId"], title=notice["announcementTitle"],
        published_at=published.isoformat(), source_url=source_url, evidence_refs=[ref])])
    analysis = dict(symbol="600398", input_descriptor_sha256="a" * 64,
                    review_binding=dict(candidate_binding={"path": "TEST_ONLY", "sha256": "b" * 64}))
    event, = _operating_events(analysis, [window], acquired,
                               lambda binding: _bound(Path(root), binding))
    assert event["status"] == "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
    assert not event["materiality_approved"] and not event["model_inputs_changed"]
    fact, = event["facts"]
    assert fact["terms"]["effective_date"] is None
    assert fact["terms"]["terms"] == result
    assert event["action"] == "no_order"

    window["announcements"][0]["title"] = notice["announcementTitle"].replace("半年度", "中期")
    mismatch, = _operating_events(analysis, [window], acquired,
                                  lambda binding: _bound(Path(root), binding))
    assert not mismatch["facts"]
    assert mismatch["unresolved"][0]["reason"] == "INTERIM_IMPLEMENTATION_ORIGINAL_TITLE_MISMATCH"

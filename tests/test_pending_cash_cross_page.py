"""TEST_ONLY layout negatives plus opt-in immutable real original replay."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research.pending_candidate_alignment import _cash_terms


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

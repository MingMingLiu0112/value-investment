"""Explicit real-source opt-in; mutations are TEST_ONLY in-memory originals."""
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.opening_action_terms import (
    parse_opening_action_terms, ADJUSTMENT, AUTHORIZATION,
)
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.application.product.daily_event_observation import verify_retained_event_coverage

OBSERVATION = "runtime/value-opening-action-observation/20261030T055129707003Z/observation.json"
HASHES = {
    "1225347653": "f51131858f82005c9ed36dcb78ecca961f3f10cff71dc54039c4a37804ed5412",
    "1225366264": "6868e886abe37f8c844a9df980775cb667d7caf2935f5ca01ea08bb68e4312c9",
}


@pytest.fixture(scope="module")
def originals():
    configured = os.environ.get("VALUE_OPENING_ACTION_REAL_ROOT")
    if configured is None:
        pytest.skip("VALUE_OPENING_ACTION_REAL_ROOT unset; skip is not real-source acceptance")
    assert configured.strip()
    root = Path(configured).resolve(strict=True)
    observation = json.loads((root / OBSERVATION).read_bytes())
    proof = verify_retained_event_coverage(root, observation, symbol="600519",
        required_from=date(2026,5,27), required_to=date(2026,6,12), now=datetime.now(timezone.utc))
    assert proof["coverage_status"] == "COMPLETE"
    scan = json.loads((root / observation["scan_binding"]["path"]).read_bytes())
    result = {}
    for row in scan["announcements"]:
        identity = row["announcement_id"]
        if identity not in HASHES:
            continue
        ref = row["evidence_refs"][0]
        path = (root / ref["path"]).resolve(strict=True)
        assert path.is_relative_to(root)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == ref["sha256"] == HASHES[identity]
        result[identity] = dict(pages=extract_pages(path), source_url=row["source_url"])
    assert set(result) == set(HASHES)
    return root, observation, result


@pytest.mark.parametrize("identity,event_type,published,effective", [
    ("1225347653", ADJUSTMENT, "2026-06-03", "2026-05-28"),
    ("1225366264", AUTHORIZATION, "2026-06-12", "2026-06-11"),
])
def test_real_original_uniform_contract_and_publication_binding(originals, identity, event_type, published, effective):
    _, _, docs = originals
    result = parse_opening_action_terms(docs[identity]["pages"], symbol="600519")
    assert result["parser_version"] == "opening-action-terms-v2"
    assert result["event_type"] == event_type
    assert result["published_date"] == published
    assert '/finalpage/' + result["published_date"] + '/' in docs[identity]["source_url"]
    assert result["effective_date"] == effective
    for field in ("summary", "implication", "terms", "affected_model_fields", "term_pages", "limitations"):
        assert result[field]
    assert result["action"] == "no_order"


def test_real_confirmed_cancellation_and_rounding(originals):
    result = parse_opening_action_terms(originals[2]["1225347653"]["pages"], symbol="600519")
    terms = result["terms"]
    assert terms["confirmed_cancellation_date"] == "2026-05-28"
    assert terms["cancelled_shares"] == "2188614"
    assert terms["issued_shares"] == "1250081601"
    assert terms["treasury_shares"] == "0" and terms["treasury_zero"]
    assert terms["capital_as_of"] == "2026-06-03"
    assert terms["previous_cash_per_share"] == "27.993"
    assert terms["annual_cash_per_share"] == "28.02423"
    assert terms["original_annual_total_cash_cny"] == "35032568759.73"
    assert terms["annual_total_cash_cny"] == "35032574305.19"
    assert terms["per_share_decimal_places"] == 5 and terms["total_decimal_places"] == 2
    assert "四舍五入保留小数点后五位" in terms["precision_text"]
    assert not terms["accounting_one_cent_difference_resolved"]
    assert result["term_pages"]["confirmed_cancellation"] == [2]


def test_real_authorization_is_neither_scheme_nor_cash_obligation(originals):
    result = parse_opening_action_terms(originals[2]["1225366264"]["pages"], symbol="600519")
    terms = result["terms"]
    assert terms["authorization_period_text"] == "2026年中期"
    assert terms["amount_cap_text"] == "分红金额上限不超过公司2026年上半年实现归属于上市公司股东的净利润。"
    assert "在符合《公司章程》利润分配的条件下" in terms["authorization_text"]
    assert terms["authorization_expiry_date"] is None
    assert terms["authorization_expiry_status"] == "NOT_DISCLOSED_IN_CLAUSE"
    assert terms["follow_up_required"]
    assert not any(terms[k] for k in ("scheme_determined", "implementation_verified", "cash_obligation_established"))
    assert terms["interim_cash_per_share"] is None and terms["interim_total_cash_cny"] is None
    assert terms["capital_as_of"] == "2026-05-31"
    assert result["term_pages"]["interim_authorization"] == [3,4]


@pytest.mark.parametrize("identity,old,new", [
    ("1225347653", "证券代码：600519", "证券代码：600518"),
    ("1225366264", "证券代码：600519", "证券代码：600518"),
    ("1225347653", "将全部回购股份", "拟将全部回购股份"),
    ("1225347653", "2,188,614", "2,188,615"),
    ("1225347653", "1,250,081,601", "1,250,081,602"),
    ("1225347653", "内股份数为 0 股", "内股份数为 1 股"),
    ("1225347653", "保留小数点后五位", "保留小数点后四位"),
    ("1225347653", "35,032,574,305.19", "35,032,574,305.20"),
    ("1225347653", "28.02423", "28.02424"),
    ("1225347653", "（含税）", "（税后）"),
    ("1225347653", "2026 年 6 月 3 日", "2026 年 5 月 1 日"),
    ("1225366264", "2026 年 6 月 11 日", "2026 年 6 月 13 日"),
    ("1225366264", "同意 反对 弃权", "反对 同意 弃权"),
    ("1225366264", "审议结果：通过", "审议结果：未通过"),
    ("1225366264", "股东会授权董事会", "股东会未授权董事会"),
    ("1225366264", "上半年实现归", "下半年实现归"),
    ("1225366264", "2026 年中期", "2027 年中期"),
    ("1225366264", "1,250,081,601", "1,250,081,602"),
])
def test_real_body_mutations_rejected(originals, identity, old, new):
    pages = originals[2][identity]["pages"]
    assert any(old in page for page in pages), old
    with pytest.raises(ValueError):
        parse_opening_action_terms([p.replace(old,new) for p in pages], symbol="600519")


@pytest.mark.parametrize("identity", list(HASHES))
@pytest.mark.parametrize("change", ["correction", "missing_page", "duplicate_page", "only_title_amounts", "wrong_symbol"])
def test_no_title_amount_or_changed_original_fallback(originals, identity, change):
    pages = list(originals[2][identity]["pages"])
    symbol = "600519"
    if change == "correction":
        pages[0] += "更正公告"
    elif change == "missing_page":
        pages.pop()
    elif change == "duplicate_page":
        pages[1] = pages[0]
    elif change == "only_title_amounts":
        pages = [p.splitlines()[0] + "\\n证券代码：600519 股本1250081601 分红28.02423" for p in pages]
    else:
        symbol = "000333"
    with pytest.raises(ValueError):
        parse_opening_action_terms(pages, symbol=symbol)


def test_real_complete_source_observation_not_historical_approval(originals):
    root, observation, _ = originals
    assert observation["announcement_count"] == 9
    assert observation["reused_original_count"] == 3
    assert observation["full_calendar_window_elapsed"] and observation["pagination_complete"]
    assert observation["acquired_at"].startswith("2026-10-30T")
    assert not observation["materiality_approved"] and not observation["model_revalidated"]
    with pytest.raises(ValueError):
        verify_retained_event_coverage(root, observation, symbol="600519",
            required_from=date(2026,5,27), required_to=date(2026,6,12),
            now=datetime(2026,10,29,15,tzinfo=timezone.utc))


@pytest.mark.parametrize("page,old,new", [
    (0, "35,032,574,305.19", "35,032,574,305.20"),
    (0, "2026 年 4 月 15 日", "2026 年 7 月 15 日"),
    (1, "35,032,568,759.73", "35,032,568,759.74"),
    (0, "每股派发现金红", "每十股派发现金红"),
])
def test_adjustment_single_location_conflict_rejected(originals, page, old, new):
    pages = list(originals[2]["1225347653"]["pages"])
    assert old in pages[page]
    pages[page] = pages[page].replace(old, new, 1)
    with pytest.raises(ValueError):
        parse_opening_action_terms(pages, symbol="600519")


@pytest.mark.parametrize("row,eligible,error", [
    ("0 0.0000 874,013,979 100.0000 0 0.0000", None, "PASSED_LABEL_NOT_SUPPORTED"),
    ("873,780,224 99.9733 120,655 0.0138 113,101 0.0129", None, "COUNTS_OR_PERCENTAGES"),
    ("873,780,224 99.9732 120,655 0.0138 113,100 0.0129", None, "COUNTS_OR_PERCENTAGES"),
    ("873,780,224 99.9733 113,100 0.0138 120,655 0.0129", None, "COUNTS_OR_PERCENTAGES"),
    ("0 99.9733 874,013,979 0.0138 0 0.0129", None, "COUNTS_OR_PERCENTAGES"),
    ("437,006,990 50.0000 437,006,990 50.0000 0 0.0000", "874,013,980", "PASSED_LABEL_NOT_SUPPORTED"),
    ("437,000,000 50.0000 437,000,000 50.0000 0 0.0000", None, "COUNTS_OR_PERCENTAGES"),
])
def test_passed_label_cannot_override_vote_arithmetic(originals, row, eligible, error):
    import re
    pages = list(originals[2]["1225366264"]["pages"])
    pattern = r"A\s*股\s+873,780,224\s+99\.9733\s+120,655\s+0\.0138\s+113,100\s+0\.0129"
    pages[2], count = re.subn(pattern, "A 股 " + row, pages[2])
    assert count == 1 and "审议结果：通过" in pages[2]
    if eligible:
        assert pages[0].count("874,013,979") == 1
        pages[0] = pages[0].replace("874,013,979", eligible)
    with pytest.raises(ValueError, match=error):
        parse_opening_action_terms(pages, symbol="600519")


def test_real_vote_counts_percentages_and_majority_reconciled(originals):
    result = parse_opening_action_terms(originals[2]["1225366264"]["pages"], symbol="600519")
    assert result["terms"]["annual_vote"] == dict(eligible_votes="874013979",
        agree_votes="873780224", against_votes="120655", abstain_votes="113100",
        percentages=["99.9733", "0.0138", "0.0129"], percentage_decimal_places=4,
        simple_majority_verified=True)
    assert result["term_pages"]["eligible_votes"] == [1]
    assert not result["terms"]["scheme_determined"]
    assert not result["terms"]["cash_obligation_established"]

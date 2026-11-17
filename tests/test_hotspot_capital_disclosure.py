"""TEST_ONLY synthetic HK forms; optional local official originals are explicit."""
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot.corporate_action_coverage import inspect_official_action_coverage
from value_investment_agent.infrastructure.hotspot.capital_disclosure import parse_hk_form_a_share_buyback


def _pages():
    return ["""FF305 第1頁 共2頁 v1.3.0 翌日披露報表 狀態：新提交
呈交日期：2026年10月22日 第一章節
股份類別 A 於香港聯交所上市 否
證券代號 (如上市) 300750 說明 A股股票於深圳證券交易所上市
贖回/購回股份 (擬註銷但截至期終結存日期尚未註銷)""",
        """FF305 第2頁 共2頁 v1.3.0 購回報告 第二章節
股份類別 A 於香港聯交所上市 否
證券代號 (如上市) 300750 說明 A股股票於深圳證券交易所上市
交易日 購回股份數目 購回方式 (註1) 每股購回價或每股最高購回價 (元) 每股最低購回價 (元) 付出的價格總額 (元)
1). 2026年10月22日 100 於其他證券交易所進行 深圳證券交易所 RMB 11 RMB 9 RMB 1,000
合共購回股份總數 100 合共付出的價格總額 (元) RMB 1,000
購回股份（擬註銷）數目 100 購回股份（擬持作庫存股份）數目 0
第二章節註釋 此處為TEST_ONLY非真實交易"""]


def test_a_share_buyback_not_h_share_only_and_not_completed_cancellation():
    terms = parse_hk_form_a_share_buyback(_pages(), symbol="300750")
    assert terms["share_class"] == "A" and terms["execution_venue"] == "SZSE"
    assert terms["bought_shares"] == terms["intended_for_cancellation_shares"] == "100"
    assert terms["effective_cancellation_proven"] is False
    assert terms["completed_cancelled_shares"] is None
    assert terms["price_adjustment_allowed"] is False and terms["action"] == "no_order"


@pytest.mark.parametrize("old,new", [
    ("股份類別 A", "股份類別 H"), ("300750", "300751"), ("狀態：新提交", "狀態：修訂"),
    ("尚未註銷", "已經註銷"), ("RMB", "HKD"), ("共2頁", "共3頁"),
    ("合共購回股份總數 100", "合共購回股份總數 101"),
    ("數目 0", "數目 1"), ("RMB 1,000", "RMB 9,999"),
])
def test_unsupported_or_conflicting_form_is_not_guessed(old, new):
    pages = [page.replace(old, new) for page in _pages()]
    with pytest.raises(ValueError):
        parse_hk_form_a_share_buyback(pages, symbol="300750")


def test_trade_date_must_match_submission_and_whole_form_required():
    pages = _pages()
    pages[1] = pages[1].replace("2026年10月22日", "2026年10月23日")
    with pytest.raises(ValueError):
        parse_hk_form_a_share_buyback(pages, symbol="300750")
    with pytest.raises(ValueError):
        parse_hk_form_a_share_buyback(_pages()[:1], symbol="300750")


def test_template_note_is_not_an_operative_revision():
    pages = _pages()
    pages[1] += "\n確認内容建議格式可予以修訂"
    assert parse_hk_form_a_share_buyback(pages, symbol="300750")["price_adjustment_allowed"] is False
    pages[1] = pages[1].replace("第二章節註釋", "本次更正第二章節註釋")
    with pytest.raises(ValueError):
        parse_hk_form_a_share_buyback(pages, symbol="300750")


@pytest.mark.parametrize("extra", [
    "股份類別 H 於香港聯交所上市 是 證券代號 (如上市) 03750",
    "2). 2026年10月22日 100 於其他證券交易所進行 深圳證券交易所 HKD 11 HKD 9 HKD 1,000",
    "呈交日期：2026年10月23日", "呈交日期：2026年10月22日",
])
def test_extra_identity_trade_or_submission_date_cannot_be_ignored(extra):
    pages = _pages()
    pages[1] = pages[1].replace("合共購回股份總數", extra + " 合共購回股份總數")
    with pytest.raises(ValueError):
        parse_hk_form_a_share_buyback(pages, symbol="300750")


@pytest.mark.skipif(not os.environ.get("HOTSPOT_CAPITAL_ROOT"), reason="Optional actual official acquisition")
def test_bound_real_capital_form_and_native_official_coverage_are_not_complete():
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    root = Path(os.environ["HOTSPOT_CAPITAL_ROOT"])
    base = root / "runtime/swing-300750-actions-20261024/46d01e8a6ada4f0992e61dfe000e4af8/entry-window"
    pdf = base / "300750-1225616988.pdf"
    assert sha256(pdf.read_bytes()).hexdigest() == "ea52aa426d8a9eec7efa063e5aa232e50d0ce710dd1b8b599b423986ed749212"
    parsed = parse_hk_form_a_share_buyback(extract_pages(pdf, limit=16), symbol="300750")
    assert parsed["bought_shares"] == "2271000" and parsed["total_paid_cny"] == "499946748.7"
    observation = base / "observation.json"
    binding = dict(path=observation.relative_to(root).as_posix(), sha256=sha256(observation.read_bytes()).hexdigest())
    data = json.loads(observation.read_bytes())
    cutoff = datetime.fromisoformat(data["acquired_at"])
    coverage = inspect_official_action_coverage(root=root, symbol="300750", start=date(2024, 10, 14),
        end=date(2026, 10, 23), now=cutoff, observation_binding=binding)
    assert coverage["official_publication_coverage"] == "PARTIAL"
    assert coverage["corporate_action_coverage"] == coverage["price_comparability"] == "UNKNOWN"
    review = coverage["capital_disclosure_review"]
    assert len(review["observations"]) == 1
    assert review["comparison_allowed"] is review["complete_coverage_proven"] is False
    earlier = inspect_official_action_coverage(root=root, symbol="300750", start=date(2026, 10, 22),
        end=date(2026, 10, 23), now=datetime.fromisoformat("2026-10-23T21:00:00+08:00"), observation_binding=binding)
    assert earlier["official_publication_coverage"] == "INVALID_OR_UNAVAILABLE"
    corrupted = dict(binding, sha256="a" * 64)
    rejected = inspect_official_action_coverage(root=root, symbol="300750", start=date(2026, 10, 22),
        end=date(2026, 10, 23), now=cutoff, observation_binding=corrupted)
    assert rejected["official_publication_coverage"] == "INVALID_OR_UNAVAILABLE"

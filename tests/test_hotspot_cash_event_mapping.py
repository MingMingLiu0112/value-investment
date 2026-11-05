"""TEST_ONLY source-body fixtures plus optional retained real original replay."""
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot.cash_event_mapping import build_cash_event_mapping
from value_investment_agent.application.hotspot.report_text import render_cash_event_mapping_markdown
from value_investment_agent.domain.hotspot.cash_price_mapping import map_cash_price_coordinates
from value_investment_agent.infrastructure.hotspot import cash_implementation as adapter
from value_investment_agent.quote_sessions import CHINA


NOW = datetime(2026, 10, 23, 20, tzinfo=CHINA)
PAGES = [
    "证券代码：600519 证券简称：TEST_ONLY 公告编号：临2025-001\n权益分派实施公告\n"
    "A股每股现金红利2元（含税）\n差异化分红送转：否\n"
    "股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n"
    "Ａ股 2025/12/18 － 2025/12/19 2025/12/19",
    "（三）分配方案：本次利润分配以方案实施前的公司总股本100股为基数，"
    "每股派发现金红利2元（含税），共计派发现金红利200元（含税）。三、相关日期\n"
    "TEST_ONLY公司董事会2025年12月11日",
]


def _fixture(root, monkeypatch):
    from pypdf import PdfWriter
    original = root / "implementation.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with original.open("wb") as stream:
        writer.write(stream)
    evidence = dict(path=original.name, sha256=sha256(original.read_bytes()).hexdigest(),
        url="https://static.cninfo.com.cn/finalpage/2025-12-11/999999.PDF", pages=[1, 2])
    event = dict(symbol="600519", record_date="2025-12-18", ex_date="2025-12-19",
        cash_payment_date="2025-12-19", cash_amount="2", per_shares="1", cash_per_share="2",
        amount_basis="implemented_gross_entitlement", evidence=[evidence])
    registry = root / "registry.json"
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
    # Only PDF text transport is synthetic. PDF container, native registry,
    # hash/date/amount/body checks and mapping are not bypassed.
    monkeypatch.setattr(adapter, "extract_pages", lambda path, limit: PAGES)
    return registry, event


def _binding(path, root, *, available_at=NOW):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest(),
                available_at=available_at.isoformat())


def _build(root, ref, **overrides):
    args = dict(root=root, symbol="600519", record_date=date(2025, 12, 18),
        registry_binding=ref, now=NOW, original_protection="100", current_price="99",
        original_basis_date=date(2025, 12, 18), current_basis_date=date(2025, 12, 19))
    args.update(overrides)
    return build_cash_event_mapping(**args)


def _safe(result):
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["window_comparability"] == "UNKNOWN"
    assert result["position_guidance"] is None and result["strategy_validation"] == "NOT_PROVEN"
    assert "REFERENCE_ONLY" in result["price_input_scope"]


def test_exact_cash_body_and_price_coordinate_arithmetic(tmp_path, monkeypatch):
    registry, _ = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    result = _build(tmp_path, _binding(registry, tmp_path))
    assert result["status"] == "CONDITIONAL_SINGLE_EVENT_MAPPING", result
    assert result["event_proof"]["terms"]["body_terms_reconciled"] is True
    assert result["event_proof"]["revision_status"] == "ABSENCE_NOT_PROVEN"
    assert result["event_proof"]["terms"]["term_pages"]["scheme"] == [2]
    mapping = result["mapping"]
    assert mapping["original_protection_price"] == "100"
    assert mapping["original_current_price"] == "99"
    assert mapping["event_only_protection_on_current_basis"] == "98"
    assert mapping["event_only_current_on_original_basis"] == "101"
    assert mapping["raw_distance_to_original_protection"] == "-1"
    assert mapping["event_only_distance_to_protection"] == "1"
    assert mapping["same_basis_confirmed"] is False
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir()}
    _safe(result)


def test_ex_basis_effect_does_not_claim_cash_received_on_later_payment_date(tmp_path, monkeypatch):
    registry, event = _fixture(tmp_path, monkeypatch)
    event["cash_payment_date"] = "2025-12-29"
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
    pages = [page.replace("2025/12/19 2025/12/19", "2025/12/19 2025/12/29") for page in PAGES]
    monkeypatch.setattr(adapter, "extract_pages", lambda path, limit: pages)
    cutoff = datetime(2025, 12, 19, 23, tzinfo=CHINA)
    result = _build(tmp_path, _binding(registry, tmp_path, available_at=cutoff), now=cutoff)
    assert result["status"] == "CONDITIONAL_SINGLE_EVENT_MAPPING", result
    assert result["event_proof"]["cash_payment_status"] == "DECLARED_SCHEDULE_NOT_PROOF_OF_RECEIPT"
    _safe(result)


def test_future_related_disclosure_cannot_enter_mapping(tmp_path, monkeypatch):
    registry, event = _fixture(tmp_path, monkeypatch)
    ref = dict(event["evidence"][0], available_at=NOW.isoformat(),
        url="https://static.cninfo.com.cn/finalpage/2099-01-01/999999.PDF")
    result = _build(tmp_path, _binding(registry, tmp_path), related_disclosure_bindings=(ref,))
    assert result["mapping"] is None
    _safe(result)


def test_registry_coverage_flags_cannot_promote_conditional_mapping(tmp_path, monkeypatch):
    registry, event = _fixture(tmp_path, monkeypatch)
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event],
        complete_window_coverage=True, amendment_chain_verified=True)), encoding="utf-8")
    result = _build(tmp_path, _binding(registry, tmp_path))
    assert result["status"] == "CONDITIONAL_SINGLE_EVENT_MAPPING"
    assert result["mapping"]["same_basis_confirmed"] is False
    assert result["event_proof"]["terms"]["amendment_chain_verified"] is False
    _safe(result)


def test_readable_mapping_preserves_reference_scope_and_no_order(tmp_path, monkeypatch):
    registry, _ = _fixture(tmp_path, monkeypatch)
    result = _build(tmp_path, _binding(registry, tmp_path))
    text = render_cash_event_mapping_markdown(result)
    assert "原保护参考价：100" in text and "保护参考坐标：98" in text
    assert "不是已核验行情" in text and "修订链状态：ABSENCE" in text
    assert "action=no_order" in text and "总回报" in text
    result["action"] = "order"
    with pytest.raises(ValueError):
        render_cash_event_mapping_markdown(result)


@pytest.mark.parametrize("start,end,expected", [
    (date(2025, 12, 18), date(2025, 12, 19), "98"),
    (date(2025, 12, 19), date(2025, 12, 20), "100"),
    (date(2025, 12, 17), date(2025, 12, 18), "100"),
])
def test_ex_date_boundary_and_no_double_subtraction(start, end, expected):
    result = map_cash_price_coordinates(original_protection="100", current_price="99", cash_per_share="2",
        original_basis_date=start, current_basis_date=end, ex_date=date(2025, 12, 19))
    assert result["event_only_protection_on_current_basis"] == expected
    assert result["same_basis_confirmed"] is False


@pytest.mark.parametrize("old,new", [
    ("差异化分红送转：否", "差异化分红送转：是"),
    ("200元", "201元"), ("现金红利2元", "现金红利3元"),
    ("三、相关日期", "每股送股0.1股。三、相关日期"),
    ("权益分派实施公告", "权益分派预案"),
    ("2025/12/19", "2025/12/17"),
    ("公司董事会2025年12月11日", "公司董事会2025年12月20日"),
    ("权益分派实施公告", "权益分派实施公告（修订版）"),
    ("权益分派实施公告", "权益分派实施公告（已取消）"),
    ("TEST_ONLY公司董事会", "另有送红股安排。TEST_ONLY公司董事会"),
    ("证券代码：600519", "证券代码：600887"),
])
def test_unknown_noncash_revisions_and_conflicting_body_rejected(old, new):
    with pytest.raises(ValueError):
        adapter.parse_cash_implementation_pages([p.replace(old, new) for p in PAGES], symbol="600519")


@pytest.mark.parametrize("label", ["更正", "修订", "取消", "撤销"])
def test_bound_related_revision_blocks_mapping_pending_linkage(tmp_path, monkeypatch, label):
    registry, event = _fixture(tmp_path, monkeypatch)
    related = tmp_path / "revision.pdf"
    related.write_bytes((tmp_path / "implementation.pdf").read_bytes())
    monkeypatch.setattr(adapter, "extract_pages", lambda path, limit:
        [f"证券代码：600519 TEST_ONLY 关于临2025-001实施公告的{label}公告"]
        if path.name == "revision.pdf" else PAGES)
    ref = dict(_binding(related, tmp_path), url=event["evidence"][0]["url"])
    result = _build(tmp_path, _binding(registry, tmp_path), related_disclosure_bindings=(ref,))
    assert result["status"] == "NOT_ASSESSABLE" and result["mapping"] is None
    assert result["event_proof"]["revision_status"] == "PENDING_LINKAGE"
    assert "REVISION_OR_CANCELLATION_REQUIRES_LINKAGE" in result["blockers"]
    _safe(result)


@pytest.mark.parametrize("damage", ["hash", "pdf", "future", "naive", "cash", "date", "bonus", "url", "future_effect"])
def test_source_and_registry_conflicts_do_not_produce_mapping(tmp_path, monkeypatch, damage):
    registry, event = _fixture(tmp_path, monkeypatch)
    ref = _binding(registry, tmp_path)
    extra = {}
    if damage == "hash":
        ref["sha256"] = "0" * 64
    elif damage == "pdf":
        (tmp_path / "implementation.pdf").write_bytes(b"tampered")
    elif damage == "future":
        ref["available_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif damage == "naive":
        ref["available_at"] = "2026-10-23T00:00:00"
    elif damage == "future_effect":
        cutoff = datetime(2025, 12, 18, 23, tzinfo=CHINA)
        ref["available_at"] = cutoff.isoformat()
        extra = dict(now=cutoff, current_basis_date=date(2025, 12, 18))
    else:
        if damage == "cash":
            event.update(cash_amount="3", cash_per_share="3")
        elif damage == "date":
            event.update(ex_date="2025-12-20", cash_payment_date="2025-12-20")
        elif damage == "bonus":
            event.update(bonus_shares_per_share="0.1", bonus_listing_date="2025-12-20")
        elif damage == "url":
            event["evidence"][0]["url"] = "https://example.com/fake.PDF"
        registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
        ref = _binding(registry, tmp_path)
    result = _build(tmp_path, ref, **extra)
    assert result["mapping"] is None, result
    assert result["status"] == "NOT_ASSESSABLE"
    _safe(result)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "2"])
def test_invalid_or_exhausted_protection_rejected(value):
    with pytest.raises(ValueError):
        map_cash_price_coordinates(original_protection=value, current_price="99", cash_per_share="2",
            original_basis_date=date(2025, 12, 18), current_basis_date=date(2025, 12, 19),
            ex_date=date(2025, 12, 19))


def test_optional_real_implementation_original_and_reference_only_mapping():
    configured = os.environ.get("HOTSPOT_RETAINED_ROOT")
    if not configured:
        pytest.skip("Retained real official original not configured")
    root = Path(configured)
    registry = root / "docs/reviewed-cash-distributions.json"
    if not registry.is_file():
        pytest.skip("Retained reviewed registry missing")
    result = _build(root, _binding(registry, root), original_protection="1500", current_price="1480")
    assert result["status"] == "CONDITIONAL_SINGLE_EVENT_MAPPING", result
    assert result["event_proof"]["terms"]["cash_per_share"] == "23.957"
    assert result["mapping"]["event_only_protection_on_current_basis"] == "1476.043"
    assert result["mapping"]["event_only_current_on_original_basis"] == "1503.957"
    assert result["mapping"]["event_only_distance_to_protection"] == "3.957"
    assert result["event_proof"]["historical_availability_proven"] is False
    _safe(result)

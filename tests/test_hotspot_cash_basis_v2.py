"""TEST_ONLY transport fixtures; native body, registry and arithmetic are exercised."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import re

import pytest

from value_investment_agent.application.hotspot.cash_action_window_v2 import inspect_cash_action_window_v2
from value_investment_agent.domain.hotspot.cash_basis import reconcile_cash_basis
from value_investment_agent.infrastructure.hotspot import cash_implementation as legacy
from value_investment_agent.infrastructure.hotspot.cash_implementation_v2 import (
    load_cash_implementation_v2, parse_cash_implementation_pages_v2,
)
from value_investment_agent.quote_sessions import CHINA


NOW = datetime(2026, 10, 24, 12, tzinfo=CHINA)
SCHEME = ("实施的2025年度A股权益分派方案为：以公司现有A股总股本1000股剔除回购专用账户中已回购股份100股"
    "后的股本900股为基数，向全体股东每10股派发现金分红人民币10.00元（含税）")
EQUATION = "即900股*1元/股=900.00元。"
PAGES = [
    "证券代码：000001 证券简称：TEST_ONLY 公告编号：2026-001\n2025年度A股权益分派实施公告\n"
    "公司" + SCHEME + "。" + EQUATION + "\n按公司现有A股总股本折算的每10股现金分红为9.000000元"
    "（保留小数点后六位数，最后一位直接截取，不四舍五入）\n=股权登记日收盘价-0.9000000元/股。\n"
    "本次权益分派的股权登记日为2026年4月21日。\n本次权益分派的除息日及现金红利发放日为2026年4月22日。\n"
    "一、股东会审议通过的权益分派方案情况\n2025年度，公司不实施资本公积金转增股本，不送红股。",
    "二、本次实施的权益分派方案\n公司" + SCHEME + "。\n三、股权登记日与除权除息日\n"
    "本次权益分派的股权登记日为：2026年4月21日，除权除息日为：2026年4月22日。\n四、权益分派对象\n"
    "五、权益分派方法\n代派的A股股东现金红利将于2026年4月22日通过股东托管证券公司划入账户。\n"
    "六、调整相关参数\n" + EQUATION + "\n=（900.00元/1000股）*10=9.000000元"
    "（保留到小数点后六位，最后一位直接截取，不四舍五入）\n=股权登记日收盘价-0.9000000元/股。\n"
    "TEST_ONLY公司董事会2026年4月15日",
]


def _binding(path, root, available=NOW):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest(),
        available_at=available.isoformat())


def _registry(root, original, *, symbol="000001", gross="1", amount="10", now=NOW):
    registry = root / "TEST_ONLY-registry.json"
    event = dict(symbol=symbol, record_date="2026-04-21", ex_date="2026-04-22", cash_payment_date="2026-04-22",
        cash_per_share=gross, cash_amount=amount, per_shares="10", amount_basis="implemented_gross_entitlement",
        currency="CNY", share_class="A", evidence=[original])
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
    return registry, event


def _fixture(root, monkeypatch):
    from pypdf import PdfWriter
    path = root / "TEST_ONLY-implementation.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as stream:
        writer.write(stream)
    original = dict(path=path.name, sha256=sha256(path.read_bytes()).hexdigest(),
        url="https://static.cninfo.com.cn/finalpage/2026-04-15/999001.PDF", pages=[1, 2])
    monkeypatch.setattr(legacy, "extract_pages", lambda path, limit: PAGES)
    return _registry(root, original)


def _load(root, registry, **overrides):
    args = dict(root=root, symbol="000001", record_date=date(2026, 4, 21),
        registry_binding=_binding(registry, root), now=NOW)
    args.update(overrides)
    return load_cash_implementation_v2(**args)


def test_cash_entitlement_and_reference_deduction_are_different_typed_fields():
    terms = parse_cash_implementation_pages_v2(PAGES, symbol="000001")
    basis = terms["cash_basis"]
    assert Decimal(basis["gross_cash_per_eligible_a_share"]) == 1
    assert Decimal(basis["reference_deduction_per_total_a_share"]) == Decimal("0.9")
    assert "cash_per_share" not in terms and "cash_per_share" not in basis
    assert basis["price_mapping"] is None and basis["original_protection_adjusted"] is False
    assert terms["amendment_chain_verified"] is False
    assert basis["shareholder_receipt_proven"] is basis["tax_calculated"] is False


@pytest.mark.parametrize("old,new", [
    ("人民币", "港币"), ("A股总股本", "H股总股本"), ("已回购股份100股", "已回购股份101股"),
    ("9.000000", "10.000000"), ("0.9000000", "1.0000000"), ("含税", "税后"),
    ("不送红股", "送红股"), ("2025年度A股权益分派实施公告", "2024年度A股权益分派实施公告"),
    ("公告编号：2026-001", "公告编号：2026-001 更正"),
])
def test_conflicting_currency_share_scope_amount_or_period_is_rejected(old, new):
    with pytest.raises(ValueError):
        parse_cash_implementation_pages_v2([page.replace(old, new) for page in PAGES], symbol="000001")


def test_conflicting_dates_bonus_and_nonidentical_duplicate_schemes_are_rejected():
    for first, second in ((PAGES[0].replace("4月21日", "4月20日"), PAGES[1]),
            (PAGES[0], PAGES[1] + "每10股转增1股"),
            (PAGES[0], PAGES[1].replace("人民币10.00元", "人民币11.00元")),
            (PAGES[0], PAGES[1].replace("三、股权登记日", "另派每股现金1元。三、股权登记日")),
            (PAGES[0], PAGES[1].replace("TEST_ONLY公司董事会", "股权登记日为2026年4月23日。TEST_ONLY公司董事会")),
            (PAGES[0], PAGES[1].replace("三、股权登记日", "【注：另派每股现金1元。】三、股权登记日")),
            tuple(page.replace("2025年度", "2027年度") for page in PAGES)):
        with pytest.raises(ValueError):
            parse_cash_implementation_pages_v2([first, second], symbol="000001")


@pytest.mark.parametrize("change", [dict(currency="HKD"), dict(share_class="H"),
    dict(nonparticipating_a_shares="101"), dict(reference_deduction_per_total_a_share="1"),
    dict(declared_total_gross_cash_cny="NaN")])
def test_domain_rejects_wrong_units_shares_and_entitlement_as_reference(change):
    args = dict(total_a_shares="1000", nonparticipating_a_shares="100", eligible_a_shares="900",
        gross_per_10_eligible_a_shares="10", declared_total_gross_cash_cny="900.00",
        reference_per_10_total_a_shares="9.000000", reference_deduction_per_total_a_share="0.9")
    args.update(change)
    with pytest.raises(ValueError):
        reconcile_cash_basis(**args)


def test_loader_reuses_native_registry_and_never_maps_protection(tmp_path, monkeypatch):
    registry, _ = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    proof = _load(tmp_path, registry)
    assert proof["registry_correspondence"]["status"] == "MATCH"
    assert proof["revision_status"] == "ABSENCE_NOT_PROVEN"
    assert proof["price_mapping"] is None and proof["original_protection_adjusted"] is False
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir()}
    window = inspect_cash_action_window_v2(root=tmp_path, symbol="000001", record_date=date(2026, 4, 21),
        registry_binding=_binding(registry, tmp_path), start=date(2026, 4, 15), end=date(2026, 4, 22), now=NOW)
    assert window["body_terms_status"] == "READY"
    assert window["publication_coverage"]["official_publication_coverage"] == "MISSING"
    assert window["price_comparability"] == "UNKNOWN" and window["mapping"] is None
    assert window["comparison_allowed"] is window["formal_eligibility"] is False


@pytest.mark.parametrize("key,value", [("cash_per_share", "0.9"), ("ex_date", "2026-04-23"),
    ("currency", "HKD"), ("share_class", "H"), ("total_a_shares", "1001")])
def test_rehashed_registry_cannot_replace_gross_cash_with_reference_or_wrong_scope(tmp_path, monkeypatch, key, value):
    registry, event = _fixture(tmp_path, monkeypatch)
    event[key] = value
    if key == "cash_per_share":
        event["cash_amount"] = "9"
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
    with pytest.raises(ValueError):
        _load(tmp_path, registry)


def test_source_byte_changes_future_acquisition_and_amendment_require_review(tmp_path, monkeypatch):
    registry, event = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _load(tmp_path, registry, registry_binding=_binding(registry, tmp_path, NOW + timedelta(days=1)))
    original = tmp_path / event["evidence"][0]["path"]
    before = original.read_bytes()
    original.write_bytes(before + b"TEST_ONLY_CHANGED")
    with pytest.raises(ValueError):
        _load(tmp_path, registry)
    original.write_bytes(before)
    related = dict(event["evidence"][0], available_at=NOW.isoformat())
    related_path = tmp_path / "TEST_ONLY-related.pdf"
    related_path.write_bytes(before)
    related.update(path=related_path.name)
    monkeypatch.setattr(legacy, "extract_pages", lambda path, limit:
        ["证券代码：000001 更正 本次实施公告"] if path.name == related_path.name else PAGES)
    proof = _load(tmp_path, registry, related_disclosure_bindings=(related,))
    assert proof["revision_status"] == "PENDING_LINKAGE"
    assert proof["price_mapping"] is None


@pytest.mark.skipif(not os.environ.get("HOTSPOT_CASH_BASIS_ROOT"), reason="Optional real sealed original/window")
def test_real_300750_basis_fraction_recalculation_and_window(tmp_path):
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    source = Path(os.environ["HOTSPOT_CASH_BASIS_ROOT"])
    relative = Path("runtime/swing-300750-actions-20261024/46d01e8a6ada4f0992e61dfe000e4af8/cash-20260415/300750-1225107879.pdf")
    raw = (source / relative).read_bytes()
    assert sha256(raw).hexdigest() == "3fc437d1dd558cb4455616960a9866905567ee0fda414a0d45d56236c8fbb6e2"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    pages = extract_pages(target, limit=16)
    terms = parse_cash_implementation_pages_v2(pages, symbol="300750")
    basis = terms["cash_basis"]
    assert basis["gross_cash_per_eligible_a_share"] == "6.957"
    assert basis["reference_deduction_per_total_a_share"] == "6.9065252"
    altered = [re.sub(r"不\s*需\s*补\s*缴\s*税\s*款\s*。\s*】",
        "不需补缴税款。另派每股现金1元。】", page) for page in pages]
    assert altered != pages
    with pytest.raises(ValueError):
        parse_cash_implementation_pages_v2(altered, symbol="300750")
    independent = Fraction(3044510180555, 100) * 10 / 4408164828
    truncated = (independent * 10**6).__floor__()
    assert Fraction(truncated, 10**7) == Fraction(basis["reference_deduction_per_total_a_share"])
    assert 4408164828 - 31982306 == 4376182522
    payout_in_cents = Fraction(4376182522) * Fraction(6957, 1000) * 100
    assert (payout_in_cents + Fraction(1, 2)).__floor__() == 3044510180555
    with pytest.raises(ValueError):
        legacy.parse_cash_implementation_pages(pages, symbol="300750")
    evidence = dict(path=relative.as_posix(), sha256=sha256(raw).hexdigest(),
        url="https://static.cninfo.com.cn/finalpage/2026-04-15/1225107879.PDF", pages=list(range(1, 6)))
    now = datetime.now(CHINA)
    registry, _ = _registry(tmp_path, evidence, symbol="300750", gross="6.957", amount="69.57", now=now)
    proof = load_cash_implementation_v2(root=tmp_path, symbol="300750", record_date=date(2026, 4, 21),
        registry_binding=_binding(registry, tmp_path, now), now=now)
    assert proof["terms"] == terms and proof["formal_eligibility"] is False
    folder = Path("runtime/swing-cash-basis-v2-20261024/d316fadf5cd54b9f8f96b36e8f3cb07c/official")
    obs_raw = (source / folder / "observation.json").read_bytes()
    observation = json.loads(obs_raw)
    for ref in [observation["scan_binding"], *observation["source_bindings"]]:
        target = tmp_path / ref["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (source / ref["path"]).read_bytes()
        assert sha256(data).hexdigest() == ref["sha256"]
        target.write_bytes(data)
    path = tmp_path / folder / "observation.json"
    path.write_bytes(obs_raw)
    result = inspect_cash_action_window_v2(root=tmp_path, symbol="300750", record_date=date(2026, 4, 21),
        registry_binding=_binding(registry, tmp_path, now), start=date(2026, 4, 15), end=date(2026, 4, 22), now=now,
        observation_binding=dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256(obs_raw).hexdigest()))
    assert result["body_terms_status"] == "READY"
    assert result["publication_coverage"]["official_publication_coverage"] == "COMPLETE"
    assert result["related_document_count"] == 10
    assert result["price_comparability"] == "UNKNOWN" and result["mapping"] is None

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from product_workbench_candidate_fixture import (
    materialize_synthetic_legacy_packet,
    synthetic_legacy_packet,
)
from value_investment_agent.application.product.product_workbench_candidate import (
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_COMPANIES, SHEET_OPPORTUNITIES, build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path("runtime/prospective-baseline-20260927/snapshot-v12-h1-column-bound.json")
SNAPSHOT_PIN = Path("config/prospective-baseline-publication-v6.json")
SNAPSHOT_SHA256 = "7de4c67f00f1096795b684d7cb1510f0c80418ae92f2ea677c1589e4d8dd988f"
SNAPSHOT_V13 = Path("runtime/prospective-baseline-20260927/snapshot-v13-midea-h1-verified.json")
SNAPSHOT_PIN_V7 = Path("config/prospective-baseline-publication-v7.json")
SNAPSHOT_V13_SHA256 = "ded9fb9176d8d302a97aa527a302744083bf5a37448f28efbf50441fb56269e5"


def _packet(root: Path) -> dict:
    packet = synthetic_legacy_packet("2026-09-27T01:00:00+00:00")
    materialize_synthetic_legacy_packet(root, packet)
    return packet


def _stage_snapshot(
    root: Path, *, snapshot_path: Path = SNAPSHOT, pin_path: Path = SNAPSHOT_PIN,
) -> None:
    snapshot = json.loads((ROOT / snapshot_path).read_text(encoding="utf-8"))
    paths = [snapshot_path, pin_path]
    for card in snapshot["cards"]:
        paths.extend(Path(fact["source_path"]) for fact in card["known_facts"])
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)


def _build(
    packet: dict, root: Path, *, path: Path = SNAPSHOT, digest: str = SNAPSHOT_SHA256,
) -> dict:
    return build_product_workbench_candidate_payload(
        packet, root=root, prospective_snapshot_path=path, prospective_snapshot_sha256=digest,
    )


def test_snapshot_projection_preserves_legacy_and_remains_unapproved(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _stage_snapshot(tmp_path)
    original = build_product_workbench_candidate_payload(packet, root=tmp_path)
    projected = _build(packet, tmp_path)
    model = product_workbench_from_payload(projected)
    companies = {card.symbol: card for card in model.companies}
    opportunities = {card.symbol: card for card in model.opportunities}
    assert set(opportunities) == {"000333", "600887", "601088"}
    assert projected["overview"]["pending_count"] == 3
    assert all(card.action == "no_order" for card in opportunities.values())
    assert all(card.valuation_status.code == "NOT_READY" for card in opportunities.values())
    assert all(card.dividend_status.code == "NOT_READY" for card in opportunities.values())
    assert all(card.price_status.code == "UNAVAILABLE" for card in opportunities.values())
    assert "核对现金流、资本配置与股本披露" in opportunities["000333"].next_trigger
    assert "已接纳 3 项事实" in opportunities["000333"].why_now
    assert set(companies) == {"000333", "600887", "601088"}
    assert all(card.action == "no_order" for card in companies.values())
    assert all(card.price.available is False and card.valuation.available is False
               and card.dividend.available is False for card in companies.values())
    assert all(card.valuation.value_text is None for card in companies.values())
    assert "只记录当前可核验证据" in companies["600887"].latest_change
    assert "不构成同期PIT证明" in companies["600887"].latest_change
    assert "前瞻基线只记录当前可核验证据" in companies["000333"].latest_change
    assert companies["000333"].research_status.code == "NEED_MORE_EVIDENCE"
    assert "prospective-600887-fact-1" in companies["600887"].evidence_refs
    assert "prospective-snapshot-v2" in companies["600887"].evidence_refs
    assert "prospective-snapshot-pin-v6" in companies["000333"].evidence_refs
    assert companies["600887"].sections[1].status.code == "PARTIAL"
    assert "现有分部数据尚不能确认自由现金流口径" in companies["000333"].sections[3].summary
    assert "verified" not in companies["000333"].sections[3].summary.lower()
    coverage = {label: value for label, value in companies["601088"].decision_review}
    assert coverage["基线证据覆盖"] == "6 项事实已准入；1 项待准入；8 个证据引用。"
    facts = dict(companies["601088"].decision_review)
    assert "2026H1 营业收入：189338 百万元" in facts["已准入财务事实"]
    assert "2026-08-30T00:00:00+08:00" in facts["已准入财务事实"]
    assert "prospective-601088-fact-4" in facts["已准入财务事实"]
    assert facts["中期报告保证边界"] == "中期财务报表未经审计；注册会计师实施有限审阅，未发表审计意见。"
    assert "研究进行中" in companies["601088"].latest_change
    assert "revenue, operating profit" in companies["601088"].sections[1].summary
    assert companies["601088"].valuation.available is False
    assert companies["601088"].decision_review[-2][0] == "最强反证"
    assert "next official financial filing" in companies["000333"].next_trigger
    assert any(label == "最强反证" for label, _ in companies["600887"].decision_review)
    assert projected["action"] == "no_order"

    assert "当前注册研究对象为美的集团、伊利股份和中国神华" in projected["system_health"]["message"]
    assert projected["stages"]["m3"]["status"] == "PARTIAL"
    assert "当前注册三家" in projected["stages"]["m3"]["detail"]
    current_home = [
        item for item in projected["today_items"]
        if item.get("symbol") in {"000333", "600887", "601088"}
        and item.get("what_happened", "").startswith("前瞻基线：")
    ]
    assert {item["symbol"] for item in current_home} == set(opportunities)
    assert all(item["current_status"] in {"研究仍在进行；估值未就绪。", "尚无已接纳事实；估值未就绪。"}
               for item in current_home)
    legacy_home = [
        item for item in projected["today_items"]
        if item.get("what_happened", "").startswith("历史/旧来源")
    ]
    assert legacy_home
    assert all("等待人工复核" not in item["current_status"] for item in legacy_home)
    assert "人工批准" not in projected["system_health"]["message"]


def test_verified_quote_is_shown_without_implying_price_attractiveness(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _stage_snapshot(tmp_path)
    bundle_path = Path("runtime/quote-sessions/current/bundle.json")
    bundle_bytes = b"verified dual-source quote bundle fixture"
    bundle = tmp_path / bundle_path
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes(bundle_bytes)
    packet["audit"]["artifacts"].append({
        "label": "bound dual-source quote bundle",
        "path": bundle_path.as_posix(),
        "sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        "action": "no_order",
    })
    packet["daily_quote"] = {
        "schema_version": "daily-quote-binding-v1",
        "as_of": "2026-09-28",
        "coverage_status": "COMPLETE",
        "missing_symbols": [],
        "excluded_symbols": [],
        "quotes": [
            {"symbol": "000333", "price": "82.00"},
            {"symbol": "600887", "price": "27.03"},
            {"symbol": "601088", "price": "48.39"},
        ],
        "bundle_path": bundle_path.as_posix(),
        "action": "no_order",
    }

    model = product_workbench_from_payload(_build(packet, tmp_path))
    opportunities = {card.symbol: card for card in model.opportunities}

    for symbol, price in (("000333", "82.00"), ("600887", "27.03"), ("601088", "48.39")):
        card = opportunities[symbol]
        assert card.price_status.code == "AVAILABLE"
        assert card.price_status.user_label == "行情已验证；吸引力待评估"
        assert f"双源匹配收盘价 {price} 元（2026-09-28）" in card.why_now
        assert "价格吸引力暂不能判断" in card.why_now
        assert card.valuation_status.code == "NOT_READY"
        assert card.action == "no_order"
        assert card.evidence_refs

    workbook = build_product_workbench_workbook(model)
    opportunity_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_OPPORTUNITIES].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "双源匹配收盘价 82.00 元（2026-09-28）" in opportunity_text
    assert "价格吸引力暂不能判断" in opportunity_text


def test_v13_midea_h1_snapshot_projects_only_through_its_v7_pin(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _stage_snapshot(tmp_path, snapshot_path=SNAPSHOT_V13, pin_path=SNAPSHOT_PIN_V7)
    payload = _build(
        packet, tmp_path, path=SNAPSHOT_V13, digest=SNAPSHOT_V13_SHA256,
    )
    model = product_workbench_from_payload(payload)
    companies = {company.symbol: company for company in model.companies}

    assert "prospective-snapshot-pin-v7" in companies["000333"].evidence_refs
    assert "prospective-snapshot-pin-v6" not in companies["000333"].evidence_refs
    pin_evidence = next(
        item for item in payload["audit"]["evidence"]
        if item["evidence_id"] == "prospective-snapshot-pin-v7"
    )
    assert pin_evidence["path"] == SNAPSHOT_PIN_V7.as_posix()
    assert pin_evidence["sha256"] == hashlib.sha256((ROOT / SNAPSHOT_PIN_V7).read_bytes()).hexdigest()
    midea_facts = dict(companies["000333"].decision_review)["已准入财务事实"]
    assert "2026H1" in midea_facts
    assert "260042490" in midea_facts
    assert "26446037" in midea_facts
    assert "37552090" in midea_facts
    assert "2026-08-30T00:00:00+08:00" in midea_facts
    for symbol in ("000333", "600887", "601088"):
        assert companies[symbol].valuation.available is False
        assert companies[symbol].action == "no_order"
    assert "不构成同期PIT证明" in companies["000333"].latest_change


def test_invalid_v7_pin_does_not_fall_back_to_historical_v6(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _stage_snapshot(tmp_path, snapshot_path=SNAPSHOT_V13, pin_path=SNAPSHOT_PIN_V7)
    shutil.copy2(ROOT / SNAPSHOT_PIN, tmp_path / SNAPSHOT_PIN)
    pin_path = tmp_path / SNAPSHOT_PIN_V7
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    pin["snapshot_sha256"] = "0" * 64
    pin_path.write_text(json.dumps(pin), encoding="utf-8")

    with pytest.raises(ValueError, match="repository-pinned verified baseline"):
        _build(packet, tmp_path, path=SNAPSHOT_V13, digest=SNAPSHOT_V13_SHA256)


def test_shenhua_h1_financial_facts_render_with_assurance_and_no_signal(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _stage_snapshot(tmp_path)
    model = product_workbench_from_payload(_build(packet, tmp_path))
    workbook = build_product_workbench_workbook(model)
    company_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_COMPANIES].iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert "2026H1 营业收入：189338 百万元" in company_text
    assert "2026H1 归母净利润：28715 百万元" in company_text
    assert "2026H1 经营活动现金流净额：54664 百万元" in company_text
    assert "2026-08-30T00:00:00+08:00" in company_text
    assert "未经审计；注册会计师实施有限审阅，未发表审计意见" in company_text
    shenhua = next(company for company in model.companies if company.symbol == "601088")
    assert shenhua.valuation.available is False
    assert shenhua.action == "no_order"


def test_tampered_snapshot_and_wrong_digest_fail_closed(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    target = tmp_path / SNAPSHOT
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / SNAPSHOT).read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _build(packet, tmp_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _build(packet, tmp_path, digest="0" * 64)


def test_caller_hash_cannot_admit_an_unpinned_snapshot(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    _stage_snapshot(tmp_path)
    target = tmp_path / SNAPSHOT
    snapshot = json.loads(target.read_text(encoding="utf-8"))
    snapshot["cards"][0]["business_quality"] = "invented"
    target.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="repository-pinned verified baseline"):
        _build(packet, tmp_path, digest=hashlib.sha256(target.read_bytes()).hexdigest())


def test_rehashed_wrong_identity_and_action_fail_closed(tmp_path: Path) -> None:
    packet = _packet(tmp_path)
    target = tmp_path / SNAPSHOT
    target.parent.mkdir(parents=True)
    snapshot = json.loads((ROOT / SNAPSHOT).read_text(encoding="utf-8"))
    snapshot["cards"][0]["symbol"] = "999999"
    target.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    pin_path = tmp_path / SNAPSHOT_PIN
    pin_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / SNAPSHOT_PIN, pin_path)
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    pin["snapshot_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(ValueError, match="issuer identity"):
        _build(packet, tmp_path, digest=hashlib.sha256(target.read_bytes()).hexdigest())
    snapshot["cards"][0]["symbol"] = "000333"
    snapshot["cards"][0]["action"] = "buy"
    target.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    pin["snapshot_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(ValueError, match="no_order"):
        _build(packet, tmp_path, digest=hashlib.sha256(target.read_bytes()).hexdigest())

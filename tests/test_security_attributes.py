"""Synthetic publication fixtures replay real parsers; no real account writes."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import hashlib
import json

import pytest

from value_investment_agent.application.portfolio import security_attributes as application
from value_investment_agent.domain.portfolio.security_attributes import parse_observed_attributes
from value_investment_agent.infrastructure.portfolio.security_attributes import replay_official_attributes
from value_investment_agent.official_universe import parse_sse, VERSION
from test_dual_sleeve_risk import synthetic_input, review, CORE, HOTSPOT
from test_portfolio_risk_assessment import GENERATED_AT


def retained(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return {"path": "runtime/" + path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def published(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    raw = {"actionErrors": [], "pageHelp": {"total": 1}, "result": [
        {"A_STOCK_CODE": "600519", "SEC_NAME_CN": "TEST_ONLY", "LIST_DATE": "20010827",
            "CSRC_CODE": "C", "CSRC_CODE_DESC": "TEST_ONLY_INDUSTRY"}]}
    raw_path = runtime / "original.json"
    binding = retained(raw_path, raw)
    url = "https://query.sse.com.cn/sseQuery/commonQuery.do?STOCK_TYPE=1&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L"
    source = {"label": "SSE_1", "url": url, "request_url": url, "local_path": binding["path"],
        "sha256": binding["sha256"], "fetched_at": GENERATED_AT.isoformat()}
    universe = {"parser_version": VERSION, "complete": True, "fetched_at": GENERATED_AT.isoformat(),
        "records": parse_sse(raw_path.read_bytes(), "\u4e3b\u677f"), "sources": [source]}
    universe_binding = retained(runtime / "universe.json", universe)
    receipt_binding = retained(runtime / "receipt.json", {"universe": {"records": universe["records"],
        "evidence_refs": [universe_binding]}})
    report_binding = retained(runtime / "report.json", {"schema_version": "value-discovery-product-v1",
        "action": "no_order", "receipt_binding": receipt_binding})
    # Explicit TEST_ONLY substitute for the verified publication chain boundary.
    monkeypatch.setattr(application, "load_current_chain", lambda root: {"model": {
        "product_extensions": {"value_discovery_report": report_binding}}})
    return tmp_path, universe, universe_binding, raw_path


def test_published_official_original_proves_only_observed_fields(published):
    root, _, _, _ = published
    attrs = application.load_verified_security_attributes(root, ["600519"], now=GENERATED_AT)
    assert len(attrs) == 1
    row = attrs[0]
    assert row["industry"] == "CSRC_SECTION:C" and row["security_type"] == "A_SHARE"
    assert row["exchange"] == "SSE" and row["company_name"] == "TEST_ONLY"
    assert row["classification_effective_date"] is None and row["historical_pit"] is False
    assert row["known_at"] == GENERATED_AT.isoformat() and row["published_at"] is None
    assert all(row[key] == "UNKNOWN" for key in ("cyclical", "common_factors", "liquidity_profile"))
    assert set(row["field_evidence"]) == {"symbol", "company_name", "exchange", "security_type", "industry"}
    assert all(ref["path"].startswith("runtime/") for ref in row["evidence_refs"])
    payload = synthetic_input()
    payload["security_attributes"] = attrs
    result = review(payload)
    assert result["status"] == "BLOCKED_PRIVATE_INPUT"
    assert "security_attributes.600519.common_factors.unknown" in result["blockers"]
    assert "security_attributes.600519.cyclical.unknown" in result["blockers"]
    assert result["sleeves"][CORE]["industry_exposure_cny"] == {"CSRC_SECTION:C": "600"}
    assert result["sleeves"][CORE]["factor_exposure_cny"] is None
    assert result["sleeves"][CORE]["holdings"][0]["common_factors"] == "UNKNOWN"
    assert result["aggregate"]["total_assets_cny"] == "10000"
    assert result["hotspot_quantity_review"]["review_quantity"] is None
    assert result["trade_eligible"] is False
    assert not any("factor_concentration:" in blocker for blocker in result["blockers"])


def test_source_tamper_cannot_be_rescued_by_retained_attributes(published):
    root, _, _, raw = published
    raw.write_bytes(raw.read_bytes() + b"tamper")
    assert application.load_verified_security_attributes(root, ["600519"], now=GENERATED_AT) is None


def test_private_candidate_adapter_uses_public_chain_not_policy_claims(published):
    from value_investment_agent.application.portfolio.private_risk_projection import _verified_attributes
    root, _, _, raw = published
    replayed = SimpleNamespace(state=SimpleNamespace(lots=()), policy={"security_attribute_bindings": {
        "600519": {"path": "runtime/claimed.json", "sha256": "a" * 64}}})
    assert _verified_attributes(root, replayed, GENERATED_AT) == []
    observed = _verified_attributes(root, replayed, GENERATED_AT, candidate_symbol="600519")
    assert observed[0]["industry"] == "CSRC_SECTION:C"
    assert observed[0]["common_factors"] == "UNKNOWN"
    raw.write_bytes(b"changed")
    assert _verified_attributes(root, replayed, GENERATED_AT, candidate_symbol="600519") is None


@pytest.mark.parametrize("change", ["industry", "identity", "endpoint", "scope", "future", "summary_early", "escape"])
def test_field_semantics_scope_and_known_at_are_replayed(published, change):
    root, original, binding, _ = published
    universe = deepcopy(original)
    if change == "industry": universe["records"][0]["official_industry"] = "fake"
    if change == "identity": universe["records"][0]["security_type"] = "ETF"
    if change == "endpoint": universe["sources"][0]["url"] = "https://query.sse.com.cn.evil.test/sseQuery/commonQuery.do"
    if change == "scope": universe["sources"][0]["url"] = universe["sources"][0]["url"].replace("STOCK_TYPE=1", "STOCK_TYPE=2")
    if change == "future": universe["fetched_at"] = (GENERATED_AT + timedelta(seconds=1)).isoformat()
    if change == "summary_early": universe["sources"][0]["fetched_at"] = (GENERATED_AT + timedelta(seconds=1)).isoformat()
    if change == "escape": universe["sources"][0]["local_path"] = "../outside.json"
    with pytest.raises(ValueError):
        replay_official_attributes(root, universe, binding, {"600519"}, now=GENERATED_AT)


def test_stale_absent_and_unknown_industry_do_not_become_valid_factors(published):
    root, universe, binding, raw = published
    assert application.load_verified_security_attributes(root, ["600519"], now=GENERATED_AT + timedelta(days=8)) == []
    assert application.load_verified_security_attributes(root, ["300364"], now=GENERATED_AT) == []
    data = json.loads(raw.read_bytes())
    del data["result"][0]["CSRC_CODE"]
    raw_binding = retained(raw, data)
    universe["sources"][0]["sha256"] = raw_binding["sha256"]
    result = replay_official_attributes(root, universe, binding, {"600519"}, now=GENERATED_AT)
    assert result[0]["industry"] == "UNKNOWN"
    assert "industry" in parse_observed_attributes(result[0], now=GENERATED_AT).gaps


def test_restored_original_is_rebased_under_runtime_with_same_hash(published):
    root, universe, binding, _ = published
    universe["sources"][0]["local_path"] = "D:/OLD_CHECKOUT/runtime/original.json"
    result = replay_official_attributes(root, universe, binding, {"600519"}, now=GENERATED_AT)
    assert result[0]["evidence_refs"][0]["path"] == "runtime/original.json"


@pytest.mark.parametrize("change", ["historical_pit", "cyclical", "common_factors", "liquidity_profile"])
def test_exchange_identity_is_not_economic_risk_certification(published, change):
    root, _, _, _ = published
    row = application.load_verified_security_attributes(root, ["600519"], now=GENERATED_AT)[0]
    row[change] = True if change in ("historical_pit", "cyclical") else ([] if change == "common_factors" else "LIQUID")
    with pytest.raises(ValueError):
        parse_observed_attributes(row, now=GENERATED_AT)


def test_cross_pool_same_security_risk_consumes_shared_security_allowance():
    payload = synthetic_input()
    payload["allocations"][0]["committed_risk_cny"] = "270"
    result = review(payload)
    assert result["sleeves"][CORE]["available_risk_cny"] == "230"
    assert result["aggregate"]["committed_risk_total_cny"] == "310"
    assert result["hotspot_quantity_review"]["review_quantity"] == 0
    assert result["hotspot_quantity_review"]["same_security_existing_risk_cny"] == "310"
    assert result["hotspot_quantity_review"]["planned_risk_limit_cny"] == "0"


def test_fee_slippage_risk_and_cash_limit_have_no_extra_lot_headroom():
    payload = synthetic_input()
    result = review(payload)["hotspot_quantity_review"]
    from decimal import Decimal
    q = result["review_quantity"] + payload["hotspot_request"]["lot_size"]
    request = payload["hotspot_request"]
    buy = (Decimal(request["entry_price_cny"]) + Decimal(request["entry_slippage_cny"])) * q
    sell = (Decimal(request["stop_price_cny"]) - Decimal(request["gap_stress_cny"]) - Decimal(request["exit_slippage_cny"])) * q
    loss = buy - sell + max(Decimal(request["minimum_buy_fee_cny"]), buy * Decimal(request["buy_fee_fraction"])) + max(Decimal(request["minimum_sell_fee_cny"]), sell * Decimal(request["sell_fee_fraction"]))
    assert loss > Decimal(result["planned_risk_limit_cny"])
    payload["hotspot_request"]["minimum_sell_fee_cny"] = "500"
    assert review(payload)["hotspot_quantity_review"]["review_quantity"] == 0


def test_common_factor_concentration_uses_both_pools():
    payload = synthetic_input()
    payload["sleeves"][CORE]["max_factor_fraction"] = "0.15"
    # Existing core factor exposure is below its own cap; new satellite exposure
    # must still include it when applying the conservative shared factor ceiling.
    result = review(payload)
    assert not result["blockers"]
    assert result["hotspot_quantity_review"]["review_quantity"] == 0


@pytest.fixture
def quantity_original(published, monkeypatch):
    from value_investment_agent.infrastructure.portfolio import security_attributes as infra
    root = published[0]
    directory = root / infra.QUANTITY_DIRECTORY
    directory.mkdir(parents=True)
    # Synthetic parser fixture, explicitly pinned only inside this test process.
    raw = ("<html>For the Main Board each order shall be in multiples of 100 shares "
        "shall not exceed 1 million shares For STAR Market "
        "no less than 200 shares and no more than 100,000 shares</html>").encode()
    path = directory / "synthetic.html"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setitem(infra.QUANTITY_DIGESTS, "SSE_QUANTITY", digest)
    receipt = {"id": "SSE_QUANTITY", "path": path.relative_to(root).as_posix(),
        "sha256": digest, "source_url": infra.QUANTITY_SOURCES["SSE_QUANTITY"],
        "known_at": GENERATED_AT.isoformat()}
    receipt_path = directory / "SSE_QUANTITY.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return root, path, receipt_path, receipt


def test_original_bound_rule_joins_verified_board_without_economic_claims(quantity_original):
    root, _, _, _ = quantity_original
    row = application.load_verified_security_attributes(root, ["600519"], now=GENERATED_AT)[0]
    rule = row["trading_rules"]
    assert (rule["minimum_buy_quantity"], rule["buy_quantity_increment"], rule["lot_size"]) == (100, 100, 100)
    assert rule["maximum_buy_quantity"] == 1000000
    assert len(rule["evidence_refs"]) == 3
    assert row["liquidity_profile"] == row["cyclical"] == row["common_factors"] == "UNKNOWN"


@pytest.mark.parametrize("change", ["tamper", "url", "future", "stale", "digest"])
def test_quantity_failure_preserves_independently_verified_identity(quantity_original, change):
    root, path, receipt_path, receipt = quantity_original
    if change == "tamper": path.write_bytes(b"changed")
    if change == "url": receipt["source_url"] += "?unverified"
    if change == "future": receipt["known_at"] = (GENERATED_AT + timedelta(seconds=1)).isoformat()
    if change == "stale": receipt["known_at"] = (GENERATED_AT - timedelta(days=8)).isoformat()
    if change == "digest": receipt["sha256"] = "a" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    row = application.load_verified_security_attributes(root, ["600519"], now=GENERATED_AT)[0]
    assert row["trading_rules"] is None
    assert row["industry"] == "CSRC_SECTION:C"


@pytest.mark.parametrize("exchange,board,minimum,increment,maximum", [
    ("SSE", "主板", 100, 100, 1000000), ("SSE", "科创板", 200, 1, 100000),
    ("SZSE", "主板", 100, 100, 1000000), ("SZSE", "创业板", 100, 100, 300000),
])
def test_board_specific_rule_contract(exchange, board, minimum, increment, maximum):
    from value_investment_agent.domain.portfolio.security_attributes import auction_buy_rule, quantity_rule_blockers
    rule = auction_buy_rule({"exchange": exchange, "board": board, "security_type": "A_SHARE"})
    assert (rule["minimum_buy_quantity"], rule["buy_quantity_increment"], rule["maximum_buy_quantity"]) == (minimum, increment, maximum)
    assert not quantity_rule_blockers(minimum, rule)
    assert quantity_rule_blockers(minimum - 1, rule)
    assert quantity_rule_blockers(maximum + increment, rule)
    assert bool(quantity_rule_blockers(201, rule)) == (increment != 1)
    assert auction_buy_rule({"exchange": exchange, "board": board, "security_type": "DEPOSITARY_RECEIPT"}) is None
    assert auction_buy_rule({"exchange": "BSE", "board": board, "security_type": "A_SHARE"}) is None

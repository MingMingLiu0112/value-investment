"""TEST_ONLY signed sources through real case/registry/admission loaders."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from decimal import Decimal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from authorization_trust_registry_fixture import pin_test_trust_root
from test_hotspot_current_price_case import NOW, capture
from test_daily_quote_binding import _write_bundle
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES
from value_investment_agent.infrastructure.hotspot.current_price_case import collect_current_price_case
from value_investment_agent.application.hotspot.current_registry import load_price_conditions
from value_investment_agent.application.hotspot.independent_admission import (
    POINTER, PURPOSE, canonical_payload, load_independent_admission,
)
from value_investment_agent.application.hotspot.independent_price_conditions import (
    load_independent_price_conditions, project_independent_price_condition,
)
from value_investment_agent.domain.hotspot.independent_admission import GATES


def qualified_capture(root):
    """Completed synthetic waves and two volume-backed primary breakout bars.

    Feed raw JSONP through the existing collector; no derived level, swing,
    signal or quality result is supplied by this fixture.
    """
    days = []
    day = date(2026, 8, 27)
    while day <= date(2026, 9, 24):
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    values = [12, 13, 20, 13, 12, 8, 12, 14, 22, 14, 12, 9,
              12, 13, 14, 13, 12, 11, 11, 11, Decimal("12.34")]
    assert len(days) == len(values)

    class Response:
        def __init__(self, scale):
            period = "60m" if scale == "60" else "15m"
            self.url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/=/"
                f"CN_MarketDataService.getKLineData?symbol=sh600519&scale={scale}&ma=no")
            rows = []
            for day, value in zip(days, values):
                for index, clock in enumerate(SESSION_TIMES[period]):
                    primary_index = index if period == "60m" else index // 4
                    close = Decimal(value)
                    high, low, volume = close + Decimal("0.5"), close - Decimal("0.5"), Decimal(100)
                    if day == days[-1]:
                        close = [Decimal(11), Decimal(11), Decimal(12), Decimal("12.34")][primary_index]
                        high = [Decimal("11.2"), Decimal("11.2"), Decimal("12.1"), Decimal("12.5")][primary_index]
                        low = Decimal("10.8")
                        volume = [Decimal(100), Decimal(100), Decimal(200), Decimal(300)][primary_index]
                    divisor = 1 if period == "60m" else 4
                    rows.append(dict(day=f"{day} {clock}", open=str(close), close=str(close),
                        high=str(high), low=str(low), volume=str(volume / divisor),
                        amount=str(volume * close / divisor)))
            self.content = ("=(" + json.dumps(rows) + ");").encode("utf-8")

        def raise_for_status(self):
            pass

    bundle = _write_bundle(root)
    return collect_current_price_case(root=root, symbol="600519", as_of=days[-1],
        quote_bundle_path=bundle, quote_bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
        now=NOW, fetch=lambda _url, params, timeout: Response(params["scale"]))


@pytest.fixture
def pipeline(tmp_path, request):
    case = qualified_capture(tmp_path) if getattr(request, "param", None) == "qualified" else capture(tmp_path)

    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical_payload(value)
        path.write_bytes(raw)
        return dict(path=name, sha256=hashlib.sha256(raw).hexdigest())

    source = write("runtime/TEST_ONLY-watch.json", dict(namespace="TEST_ONLY",
        action="no_order", observation_list=[dict(symbol="600519")]))
    write("config/current-price-conditions.json", dict(
        schema_version="current-price-conditions-v1", action="no_order",
        watch_source_binding=source, watch_source_scope="TEST_ONLY",
        items=[dict(symbol="600519", company_name="TEST_ONLY", case_path=case["case_path"],
                    case_sha256=case["case_sha256"])]))
    legacy = load_price_conditions(tmp_path, now=NOW, research_version="TEST_ONLY")
    assert legacy["status"] == "CURRENT_OBSERVATION"
    plan = legacy["items"][0]["price_action_plan"]
    key = Ed25519PrivateKey.generate()
    trust = dict(schema_version="independent-hotspot-trust-root-v1", reviewer_id="TEST_ONLY",
        public_key=key.public_key().public_bytes_raw().hex(),
        scopes=["independent_hotspot_strategy_release"], symbols=["600519"],
        valid_from=(NOW - timedelta(days=1)).isoformat(),
        valid_until=(NOW + timedelta(days=1)).isoformat())
    available = case["verified_available_at"]
    expiry = (NOW + timedelta(hours=1)).isoformat()
    sources = {
        "price_structure": dict(path=case["case_path"], sha256=case["case_sha256"],
                                namespace="TEST_ONLY", available_at=available),
    }
    fallback = dict(**source, namespace="TEST_ONLY", available_at=available)
    gates = [dict(schema_version="independent-hotspot-gate-assessment-v1", action="no_order",
        namespace="TEST_ONLY", symbol="600519", rule_version=plan["model_or_rule_version"],
        gate=name, status="PASS", available_at=available, expires_at=expiry,
        source_bindings=[sources.get(name, fallback).copy()]) for name in GATES]
    payload = dict(schema_version="independent-hotspot-release-v1", action="no_order",
        symbol="600519", namespace="TEST_ONLY", rule_version=plan["model_or_rule_version"],
        reviewer_id="TEST_ONLY", reviewed_at=NOW.isoformat(), expires_at=expiry, gates=[])

    def publish():
        payload["gates"] = [write(f"runtime/TEST_ONLY-gate-{gate['gate']}.json", gate) for gate in gates]
        release = write("runtime/TEST_ONLY-release.json", dict(payload=payload,
            signature=key.sign(PURPOSE + canonical_payload(payload)).hex()))
        write(POINTER, dict(schema_version="current-hotspot-independent-admission-v1",
            action="no_order", items=[dict(symbol="600519", release=release,
                                          trust=write("runtime/TEST_ONLY-trust.json", trust))]))

    publish()
    pin_test_trust_root(trust)
    return dict(root=tmp_path, case=case, plan=plan, gates=gates, publish=publish)


def admit(pipeline, now=NOW):
    return load_independent_admission(pipeline["root"], symbol="600519", now=now,
                                      allow_test_only=True)


def successor(pipeline, *, allow_test_only=False):
    return load_independent_price_conditions(pipeline["root"], now=NOW,
        research_version="TEST_ONLY", allow_test_only=allow_test_only)


@pytest.mark.parametrize("pipeline", ["qualified"], indirect=True)
def test_real_qualified_signed_successor_reaches_only_isolated_risk_review(pipeline):
    before = deepcopy(pipeline["plan"])
    assert before["signal_state"] == "TRIGGER_OBSERVED"
    assert before["opportunity_quality"]["structure_tier"] == "STRUCTURE_QUALIFIED_OBSERVATION"
    assert before["price_behavior"]["breakout"]["confirmed_on_next_completed_bar"] is True
    result = successor(pipeline, allow_test_only=True)["items"][0]["price_action_plan"]
    assert result["risk_review_eligible"] is True
    assert result["blockers"] == []
    assert result["independent_admission"]["namespace"] == "TEST_ONLY"
    assert result["formal_eligibility"] is result["action_eligibility"] is result["trade_eligible"] is False
    assert result["position_guidance"] is result["portfolio_eligibility"] is None
    assert result["action"] == "no_order"
    assert project_independent_price_condition(pipeline["root"], symbol="600519",
        plan=before, now=NOW, allow_test_only=True) == result
    assert pipeline["plan"] == before
    assert not successor(pipeline)["items"][0]["price_action_plan"]["risk_review_eligible"]


def test_real_signed_case_bound_release_reaches_only_isolated_risk_review(pipeline):
    result = admit(pipeline)
    assert result["risk_review_eligible"] is True
    assert result["namespace"] == "TEST_ONLY"
    assert result["formal_eligibility"] is result["trade_eligible"] is False
    assert result["position_guidance"] is None
    assert result["action"] == "no_order"
    assert result["gate_source_bindings"]["price_structure"] == [dict(
        path=pipeline["case"]["case_path"], sha256=pipeline["case"]["case_sha256"])]
    assert not any("VALUE" in blocker or "G3" in blocker for blocker in result["blockers"])
    assert not (pipeline["root"] / "config/m1-valuation-packages-v1").exists()


def test_successor_real_loaders_preserve_test_namespace_and_structure_refusal(pipeline):
    plan = successor(pipeline)["items"][0]["price_action_plan"]
    assert pipeline["plan"]["signal_state"] == "WATCH"
    assert pipeline["plan"]["opportunity_quality"]["structure_tier"] == "ACTIVE_ONLY"
    assert plan["schema_version"] == "price-action-plan-independent-v2"
    assert plan["independent_admission"]["review_status"] == "REJECTED"
    assert "INDEPENDENT_RELEASE_INVALID" in plan["blockers"]
    assert "CURRENT_STRUCTURE_NOT_QUALIFIED" in plan["blockers"]
    assert "CURRENT_ENTRY_CONDITION_NOT_OBSERVED" in plan["blockers"]
    assert plan["risk_review_eligible"] is plan["formal_eligibility"] is False


def test_case_bytes_are_reverified_by_both_signed_and_registry_paths(pipeline):
    path = pipeline["root"] / pipeline["case"]["case_path"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        admit(pipeline)
    result = successor(pipeline)
    assert result["items"] == []
    assert "CURRENT_PRICE_CASE_UNAVAILABLE:600519" in result["blockers"]


@pytest.mark.parametrize("pipeline", ["qualified"], indirect=True)
def test_qualified_successor_rechecks_sources_and_expiry(pipeline):
    expired = load_independent_price_conditions(pipeline["root"],
        now=NOW + timedelta(hours=1), research_version="TEST_ONLY", allow_test_only=True)
    plan = expired["items"][0]["price_action_plan"]
    assert plan["risk_review_eligible"] is False
    assert "INDEPENDENT_RELEASE_INVALID" in plan["blockers"]
    gate = pipeline["gates"][0]
    gate["status"] = "UNKNOWN"
    pipeline["publish"]()
    result = successor(pipeline, allow_test_only=True)["items"][0]["price_action_plan"]
    assert result["risk_review_eligible"] is False
    assert gate["gate"] + ":UNKNOWN" in result["blockers"]


def test_signed_release_expiry_is_not_waived(pipeline):
    with pytest.raises(ValueError, match="expired"):
        admit(pipeline, NOW + timedelta(hours=1))


@pytest.mark.parametrize("mutation", ["namespace", "missing_namespace", "future_available_at", "unknown_gate"])
def test_resigned_unknown_or_future_sources_cannot_authorize(pipeline, mutation):
    gate = pipeline["gates"][0]
    if mutation == "unknown_gate":
        gate["status"] = "UNKNOWN"
    elif mutation == "missing_namespace":
        del gate["source_bindings"][0]["namespace"]
    elif mutation == "namespace":
        gate["source_bindings"][0]["namespace"] = "UNKNOWN"
    else:
        gate["source_bindings"][0]["available_at"] = (NOW + timedelta(minutes=1)).isoformat()
    pipeline["publish"]()
    if mutation == "unknown_gate":
        assert admit(pipeline)["risk_review_eligible"] is False
    else:
        with pytest.raises(ValueError, match="namespace and availability"):
            admit(pipeline)

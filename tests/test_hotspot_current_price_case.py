from datetime import date, datetime
import base64
import hashlib
import json

import pytest

from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES, current_signal
from value_investment_agent.infrastructure.hotspot.current_price_case import collect_current_price_case, load_current_price_case
from value_investment_agent.quote_sessions import CHINA
from test_daily_quote_binding import _write_bundle


NOW = datetime(2026, 9, 26, 16, 15, tzinfo=CHINA)


class Response:
    def __init__(self, scale, *, missing=False, conflict=False):
        period = "60m" if scale == "60" else "15m"
        self.url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/=/"
                    f"CN_MarketDataService.getKLineData?symbol=sh600519&scale={scale}&ma=no")
        rows = []
        for day in (17, 18, 21, 22, 23, 24):
            for clock in SESSION_TIMES[period]:
                if missing and day == 24 and clock == "10:00:00":
                    continue
                rows.append(dict(day=f"2026-09-{day:02} {clock}", open="12", close="12.34",
                                 high="13", low="11", volume="100" if period == "60m" else "25",
                                 amount="1200" if period == "60m" else "300"))
        if conflict and period == "15m":
            rows[-1]["volume"] = "26"
        self.content = ("=(" + json.dumps(rows) + ");").encode()

    def raise_for_status(self):
        pass


def capture(root, **kwargs):
    path = _write_bundle(root)
    return collect_current_price_case(root=root, symbol="600519", as_of=date(2026, 9, 24),
                                      quote_bundle_path=path,
                                      quote_bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                      now=kwargs.pop("now", NOW),
                                      fetch=lambda _url, params, timeout: Response(params["scale"], **kwargs))


def test_current_roundtrip_projection_and_sha_tampering(tmp_path):
    case = capture(tmp_path)
    loaded = load_current_price_case(root=tmp_path, symbol="600519", case_path=case["case_path"],
                                     expected_sha256=case["case_sha256"], now=NOW)
    assert loaded == case
    plan = project_current_price_action_plan(case)
    assert plan["signal_state"] == "WATCH"
    assert plan["next_completed_eligible_session"] == "2026-09-28"
    assert plan["levels"]["60m"]["prior_max_high"] == "13"
    assert plan["action"] == "no_order" and plan["action_eligibility"] is False
    assert plan["trend_state"] == "NOT_CONFIRMED"
    assert plan["period_structure"] == {period: "RANGE" for period in ("daily", "60m", "15m")}
    assert plan["action_intent"] == "WATCH" and plan["formal_eligibility"] is False
    assert plan["portfolio_eligibility"] is None
    assert set(plan["conditional_action_rules"]) == {"OPEN", "ADD", "REDUCE", "EXIT"}
    for field, intent in (("entry_condition", "OPEN"), ("add_condition", "ADD"),
                          ("reduce_condition", "REDUCE"), ("exit_condition", "EXIT")):
        assert plan[field]["intent"] == intent
        assert plan[field]["observed"] is False
        assert plan[field]["personal_permission"] is False
    assert plan["add_trigger_price"] is plan["reduce_trigger_price"] is None
    assert plan["blockers"] == case["blockers"]
    assert plan["expires_after_session"] == "2026-09-28"
    original = tmp_path / case["source_bindings"]["15m"]["path"]
    original.write_bytes(original.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=case["case_path"], now=NOW)


@pytest.mark.parametrize("kwargs,match", [({"missing": True}, "Incomplete"),
                                         ({"conflict": True}, "aggregate conflict")])
def test_missing_session_or_aggregate_conflict_refuses_publication(tmp_path, kwargs, match):
    with pytest.raises(ValueError, match=match):
        capture(tmp_path, **kwargs)
    assert not list((tmp_path / "runtime/hotspot-current-price-cases").rglob("case.json"))


def test_stale_load_and_incomplete_cutoff_fail_closed(tmp_path):
    case = capture(tmp_path)
    with pytest.raises(ValueError, match="B1 current close rejected"):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=case["case_path"],
                                now=datetime(2026, 9, 28, 16, tzinfo=CHINA))
    with pytest.raises(ValueError):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=case["case_path"],
                                now=datetime(2026, 9, 24, 14, tzinfo=CHINA))


def test_signal_uses_only_primary_and_preserves_enum():
    primary = dict(breakout_observed=False, reference_close="10", entry_trigger_price="11",
                   invalidation_price="9")
    levels = {"60m": primary, "15m": dict(breakout_observed=True)}
    assert current_signal(levels)[0] == "WATCH"
    primary["reference_close"] = "12"
    assert current_signal(levels)[0] == "TRIGGER_PENDING"
    primary["breakout_observed"] = True
    assert current_signal(levels)[0] == "TRIGGER_OBSERVED"
    primary.update(breakout_observed=False, reference_close="8")
    assert current_signal(levels)[0] == "TRIGGER_REJECTED"


def test_case_and_b1_tampering_are_rejected(tmp_path):
    case = capture(tmp_path)
    path = tmp_path / case["case_path"]
    altered = json.loads(path.read_bytes())
    altered["action_eligibility"] = True
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="contract"):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=path, now=NOW)
    with pytest.raises(ValueError, match="hash"):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=path,
                                expected_sha256=case["case_sha256"], now=NOW)
    altered["action_eligibility"] = False
    path.write_text(json.dumps(altered), encoding="utf-8")
    bundle_path = tmp_path / case["current_reference_close"]["bundle_path"]
    bundle_path.write_bytes(bundle_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="B1 bundle hash"):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=path, now=NOW)


def test_same_day_after_close_accepted_but_before_buffer_rejected(tmp_path):
    path = _write_bundle(tmp_path)
    bundle = json.loads(path.read_bytes())
    bundle["started_at"] = bundle["finished_at"] = "2026-09-24T08:12:00+00:00"
    documents, ids = {}, {}
    for old_id, original in bundle["documents"].items():
        document = dict(original, fetched_at=bundle["finished_at"])
        raw = base64.b64decode(document["raw_base64"]).replace(b"2026-09-26", b"2026-09-24")
        document["raw_base64"] = base64.b64encode(raw).decode()
        document["sha256"] = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"] + "\n" + document["sha256"]).encode()).hexdigest()
        ids[old_id] = identity
        documents[identity] = document
    bundle["documents"] = documents
    for ref in bundle["references"].values():
        refs = ref["document_refs"]
        for provider in ("tencent", "sina"):
            refs[provider] = ids[refs[provider]]
        refs["calendar_documents"] = [ids[item] for item in refs["calendar_documents"]]
    path.write_text(json.dumps(bundle), encoding="utf-8")
    kwargs = dict(root=tmp_path, symbol="600519", as_of=date(2026, 9, 24), quote_bundle_path=path,
                  quote_bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  fetch=lambda _url, params, timeout: Response(params["scale"]))
    case = collect_current_price_case(**kwargs, now=datetime(2026, 9, 24, 16, 15, tzinfo=CHINA))
    assert case["market_trade_date"] == "2026-09-24"
    with pytest.raises(ValueError):
        collect_current_price_case(**kwargs, now=datetime(2026, 9, 24, 15, 4, tzinfo=CHINA))


def test_repeated_capture_has_identical_computed_levels_and_next_session_plan(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    kwargs = dict(root=tmp_path, symbol="600519", as_of=date(2026, 9, 24),
                  quote_bundle_path=bundle_path,
                  quote_bundle_sha256=hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
                  fetch=lambda _url, params, timeout: Response(params["scale"]), now=NOW)
    first = collect_current_price_case(**kwargs)
    second = collect_current_price_case(**kwargs)
    assert first["case_path"] != second["case_path"]
    assert first["levels"] == second["levels"]
    assert first["bars"] == second["bars"]
    first_plan, second_plan = [project_current_price_action_plan(case) for case in (first, second)]
    for field in ("signal_state", "levels", "entry_trigger_price", "invalidation_price",
                  "current_reference_price", "model_or_rule_version", "next_completed_eligible_session",
                  "action_eligibility", "action", "explanation"):
        assert first_plan[field] == second_plan[field]
    assert first_plan["next_completed_eligible_session"] == "2026-09-28"
    assert first_plan["next_completed_eligible_session"] > first_plan["market_trade_date"]
    assert "next session completes" in first_plan["next_session_rule"]
    assert first_plan["action_eligibility"] is False and first_plan["action"] == "no_order"


def test_unrelated_bundle_failure_does_not_block_valid_security(tmp_path):
    bundle_path = _write_bundle(tmp_path)
    bundle = json.loads(bundle_path.read_bytes())
    bundle.update(status='partial_failure', request_failures=[{'symbol': '300001', 'error': 'timeout'}])
    bundle_path.write_text(json.dumps(bundle), encoding='utf-8')
    case = collect_current_price_case(root=tmp_path, symbol='600519', as_of=date(2026, 9, 24),
        quote_bundle_path=bundle_path, quote_bundle_sha256=hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        fetch=lambda _url, params, timeout: Response(params['scale']), now=NOW)
    assert case['current_reference_close']['status'] == 'VERIFIED_DUAL_SOURCE_CLOSE'


def test_next_day_download_cannot_retroactively_supply_same_day_b1(tmp_path):
    from value_investment_agent.quote_session_conversion import quote_snapshot_from_bundle_file
    bundle_path = _write_bundle(tmp_path)
    bundle = json.loads(bundle_path.read_bytes())
    refs = bundle['references']['600519']['document_refs']
    for provider in ('tencent', 'sina'):
        document = dict(bundle['documents'][refs[provider]], fetched_at='2026-09-26T08:12:00+00:00')
        identity = hashlib.sha256((document['source_url'] + '\n' + document['fetched_at'] + '\n' + document['sha256']).encode()).hexdigest()
        bundle['documents'][identity] = document
        refs[provider] = identity
    bundle_path.write_text(json.dumps(bundle), encoding='utf-8')
    historical = quote_snapshot_from_bundle_file(bundle_path, tmp_path, symbol='600519', ref_id='synthetic')
    assert historical.status == 'verified_close'
    snapshot = quote_snapshot_from_bundle_file(bundle_path, tmp_path, symbol='600519', ref_id='synthetic',
                                               require_current_b1=True)
    assert snapshot.status == 'unverified'
    with pytest.raises(ValueError, match='same-session post-close'):
        collect_current_price_case(root=tmp_path, symbol='600519', as_of=date(2026, 9, 24),
            quote_bundle_path=bundle_path, quote_bundle_sha256=hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
            fetch=lambda *a, **k: pytest.fail('invalid B1 must be rejected before network'), now=NOW)


def display_capture(root, now=NOW):
    path = _write_bundle(root)
    bundle = json.loads(path.read_bytes())
    bundle["finished_at"] = now.isoformat()
    refs = bundle["references"]["600519"]["document_refs"]
    for provider in ("tencent", "sina"):
        document = dict(bundle["documents"][refs[provider]], fetched_at=bundle["finished_at"])
        identity = hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"] + "\n" + document["sha256"]).encode()).hexdigest()
        bundle["documents"][identity] = document
        refs[provider] = identity
    calendar_ids = []
    for old_id in refs["calendar_documents"]:
        document = dict(bundle["documents"][old_id], fetched_at=bundle["finished_at"])
        identity = hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"] + "\n" + document["sha256"]).encode()).hexdigest()
        bundle["documents"][identity] = document
        calendar_ids.append(identity)
    refs["calendar_documents"] = calendar_ids
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return collect_current_price_case(root=root, symbol="600519", as_of=date(2026, 9, 24),
        quote_bundle_path=path, quote_bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        fetch=lambda _url, params, timeout: Response(params["scale"]), now=now,
        observation_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY")


@pytest.mark.parametrize("clock", [NOW, datetime(2026, 9, 28, 8, 30, tzinfo=CHINA)])
def test_later_acquisition_display_scope_roundtrip_uses_same_engine_not_b1(tmp_path, clock):
    case = display_capture(tmp_path, now=clock)
    assert case["current_reference_close"]["status"] == "VERIFIED_LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert case["current_pit"] is case["formal_eligibility"] is case["price_admitted"] is False
    loaded = load_current_price_case(root=tmp_path, symbol="600519", case_path=case["case_path"],
        expected_sha256=case["case_sha256"], now=clock)
    assert loaded == case
    plan = project_current_price_action_plan(case)
    assert plan["reference_price_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert plan["current_pit"] is plan["formal_eligibility"] is plan["price_admitted"] is False
    assert plan["data_available_at"] == case["verified_available_at"]
    assert plan["next_completed_eligible_session"] is None
    assert plan["price_behavior"]["rule_version"]
    assert plan["levels"]["60m"]["last_close"] == "12.34"
    with pytest.raises(ValueError, match="latest completed session"):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=case["case_path"],
            now=datetime(2026, 9, 28, 16, tzinfo=CHINA))


@pytest.mark.parametrize("tamper", ["pit", "scope", "calendar", "bars"])
def test_display_case_cannot_promote_flags_bypass_b1_or_skip_source_verification(tmp_path, tamper):
    case = display_capture(tmp_path)
    path = tmp_path / case["case_path"]
    stored = json.loads(path.read_bytes())
    if tamper == "pit":
        stored["current_pit"] = True
    elif tamper == "scope":
        del stored["observation_scope"]
    elif tamper == "bars":
        original = tmp_path / stored["source_bindings"]["60m"]["path"]
        original.write_bytes(original.read_bytes() + b" ")
    else:
        bundle_path = tmp_path / stored["current_reference_close"]["bundle_path"]
        bundle = json.loads(bundle_path.read_bytes())
        bundle["references"]["600519"]["document_refs"]["calendar_documents"] = []
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(ValueError):
        load_current_price_case(root=tmp_path, symbol="600519", case_path=path, now=NOW)

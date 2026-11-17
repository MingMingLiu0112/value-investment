from value_investment_agent.application.portfolio import judgment_snapshot


def test_recording_snapshot_is_detached_and_never_claims_trade_time_knowledge(monkeypatch, tmp_path):
    plan = dict(entry_trigger_price="12", formal_eligibility=False, action="no_order", research_version="original")
    packet = dict(publication_id="pub-original", content_sha256="a" * 64, research_version="original",
                  price_conditions=dict(items=[dict(symbol="000001", price_action_plan=plan)]))
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    snapshot = judgment_snapshot.capture_judgment_snapshot(tmp_path,
        dict(symbol="000001", sleeve="HOTSPOT_SATELLITE", decision_id="hotspot-000001", research_version="original"))
    plan["entry_trigger_price"] = "99"
    assert snapshot["plan"]["entry_trigger_price"] == "12"
    assert snapshot["trade_time_availability_proven"] is False
    assert snapshot["personal_risk_at_trade"] is None


def test_version_or_security_mismatch_does_not_capture_some_other_judgment(monkeypatch, tmp_path):
    packet = dict(research_version="new", publication_id="p", content_sha256="a" * 64)
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    assert judgment_snapshot.capture_judgment_snapshot(tmp_path,
        dict(symbol="000001", decision_id="hotspot-000001", research_version="old")) is None


def test_value_plan_version_is_bound_instead_of_packet_global_version(monkeypatch, tmp_path):
    packet = dict(research_version="global", publication_id="p", content_sha256="a"*64,
        value_price_conditions={"600887": dict(research_version="company", action="no_order")})
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    fill = dict(symbol="600887", sleeve="CORE_VALUE", decision_id="600887", research_version="company")
    snapshot = judgment_snapshot.capture_judgment_snapshot(tmp_path, fill)
    assert snapshot["research_version"] == snapshot["plan"]["research_version"] == "company"
    assert judgment_snapshot.capture_judgment_snapshot(tmp_path, {**fill, "research_version":"global"}) is None

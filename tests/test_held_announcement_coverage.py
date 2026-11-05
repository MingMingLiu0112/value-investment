"""Held-plan coverage consumes exact registered evidence, never approval flags."""
from datetime import datetime, timezone
import json

import pytest

from value_investment_agent.application.portfolio import held_continuity as held
from value_investment_agent.application.product import incremental_validity as validity
from value_investment_agent.application.product import daily_event_observation as events
from value_investment_agent.application.product.quote_bridge import POINTER_PATH


@pytest.mark.parametrize("failure", [None, "binding", "raw", "no_date"])
def test_held_provider_requires_exact_binding_and_raw_replay(tmp_path, monkeypatch, failure):
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    plan = dict(symbol="000333", action="no_order", signal_state="WATCH",
                market_trade_date="2026-10-16", announcement_coverage_status="COMPLETE")
    if failure == "no_date":
        del plan["market_trade_date"]
    monkeypatch.setattr(held, "load_price_conditions", lambda *args, **kwargs: {
        "items": [dict(symbol="000333", price_action_plan=plan)]})
    monkeypatch.setattr(held, "_case_history", lambda *args: [])
    pointer = tmp_path / POINTER_PATH
    pointer.parent.mkdir(parents=True)
    binding_ref = dict(path="runtime/binding.json", sha256="b" * 64)
    observation_ref = dict(path="runtime/observation.json", sha256="c" * 64)
    pointer.write_text(json.dumps({"quotes": {"000333": {
        "incremental_validity_binding": binding_ref}}}), encoding="utf-8")
    package_ref = dict(path="runtime/package.json", sha256="a" * 64)
    monkeypatch.setattr(validity, "registered_package", lambda *args: (
        package_ref, {"point_in_time": {"research_as_of": "2026-10-11"}}))
    calls = []

    def binding(**kwargs):
        calls.append(("binding", kwargs))
        if failure == "binding":
            raise ValueError("wrong registered window")

    observation = {"TEST_ONLY": True}
    monkeypatch.setattr(validity, "load_incremental_scan_binding", binding)
    monkeypatch.setattr(validity, "read_bound_json", lambda root, ref, label: (
        root / ref["path"], {"observation_ref": observation_ref}
        if ref == binding_ref else observation))

    def verify(root, value, **kwargs):
        calls.append(("raw", kwargs))
        assert value is observation
        if failure == "raw":
            raise ValueError("rehashed index is incomplete")
        return dict(coverage_status="COMPLETE", materiality_approved=False,
                    model_revalidated=False, action="no_order")

    monkeypatch.setattr(events, "verify_retained_event_coverage", verify)
    selected, provider = held.build_held_plan_provider(tmp_path, None, now=now)
    result = provider("000333")
    assert selected == {"000333"}
    assert plan["announcement_coverage_status"] == "COMPLETE"
    assert result["action"] == "no_order"
    if failure is None:
        assert result["announcement_coverage_status"] == "COMPLETE"
        assert [name for name, _ in calls] == ["binding", "raw"]
        assert calls[0][1]["review_cutoff"].isoformat() == "2026-10-16"
        assert calls[1][1]["required_from"].isoformat() == "2026-10-11"
        assert calls[1][1]["required_to"].isoformat() == "2026-10-16"
        coverage = result["announcement_coverage"]
        assert coverage["observation_binding"] == observation_ref
        assert coverage["earlier_event_reviews_replaced"] is False
        assert coverage["materiality_approved"] is False
    else:
        assert result["announcement_coverage_status"] == "UNKNOWN"
        assert "announcement_coverage" not in result

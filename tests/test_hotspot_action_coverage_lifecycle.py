"""TEST_ONLY dated raw price and official archives, never owned Entry or OOS."""
from datetime import date, datetime, timedelta
import hashlib
import json

import pytest

import test_retained_event_coverage as official_fixture
from test_hotspot_lifecycle_bound_history import (
    CURRENT_AT, ENTRY_AT, _assert_no_permission, _binding, _history,
)
from test_hotspot_official_action_coverage import binding, assert_not_admitted
from value_investment_agent.application.hotspot.lifecycle_review import build_hotspot_lifecycle_review
from value_investment_agent.application.hotspot.report_text import (
    render_hotspot_action_coverage_markdown, render_hotspot_lifecycle_markdown,
)
from value_investment_agent.quote_sessions import CHINA


@pytest.mark.parametrize("known_crossing", [False, True])
def test_complete_query_cannot_erase_original_protection_or_raw_breach(tmp_path, monkeypatch, known_crossing):
    _, entry, _, current = _history(tmp_path, breach=True)
    cutoff = datetime(2026, 9, 25, 8, 0, tzinfo=CHINA)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (cutoff - timedelta(minutes=1)).astimezone(tz)

    monkeypatch.setattr(official_fixture, "datetime", Clock)
    monkeypatch.setattr(official_fixture.service, "datetime", Clock)
    monkeypatch.setattr(official_fixture, "START", date(2026, 9, 10))
    monkeypatch.setattr(official_fixture, "END", date(2026, 9, 24))
    observation = official_fixture.archive(tmp_path, monkeypatch)
    args = dict(root=tmp_path, symbol="600519", current_case_binding=_binding(current),
        entry_case_binding=_binding(entry), entry_at=ENTRY_AT, now=cutoff)
    if known_crossing:
        from test_historical_execution_replay import _distribution_fixture
        registry, _, _ = _distribution_fixture(tmp_path)
        payload = json.loads(registry.read_bytes())
        payload["events"][0].update(record_date="2026-09-21", ex_date="2026-09-22",
                                    cash_payment_date="2026-09-22")
        registry.write_text(json.dumps(payload), encoding="utf-8")
        args["corporate_action_registry_binding"] = dict(path=registry.relative_to(tmp_path).as_posix(),
            sha256=hashlib.sha256(registry.read_bytes()).hexdigest(), available_at=CURRENT_AT.isoformat())
    before = build_hotspot_lifecycle_review(**args)
    after = build_hotspot_lifecycle_review(**args,
        official_event_observation_binding=binding(tmp_path, observation))
    assert before["current_data_status"] == after["current_data_status"] == "CURRENT"
    assert before["original_entry_comparison"] == after["original_entry_comparison"]
    assert after["original_entry_comparison"]["original_protection_price"] == "11"
    assert after["original_entry_comparison"]["first_breach_at"] is not None
    assert after["unadjusted_structural_observation"] == before["unadjusted_structural_observation"]
    assert after["observed_review"] == before["observed_review"] == "UNKNOWN"
    assert after["price_comparability"]["status"] == before["price_comparability"]["status"] == (
        "INCOMPARABLE" if known_crossing else "UNKNOWN")
    coverage = after["price_comparability"]["official_disclosure_coverage"]
    assert coverage["official_publication_coverage"] == "COMPLETE"
    assert_not_admitted(coverage)
    _assert_no_permission(after)
    text = render_hotspot_lifecycle_markdown(after)
    assert "零公告不证明" in text and "原始参考保护价（元）：11" in text
    assert "UNKNOWN" in text and "no_order" in text
    assert "OOS" in text and "尚待生效" in text
    # Reuse of this later archive at the prior cutoff must not backdate knowledge.
    historical = build_hotspot_lifecycle_review(**{**args, "now": CURRENT_AT},
        official_event_observation_binding=binding(tmp_path, observation))
    assert historical["price_comparability"]["official_disclosure_coverage"][
        "official_publication_coverage"] == "INVALID_OR_UNAVAILABLE"
    _assert_no_permission(historical)


def test_text_preserves_missing_vs_zero_and_escapes_untrusted_titles(tmp_path, monkeypatch):
    from test_hotspot_official_action_coverage import inspect
    missing = render_hotspot_action_coverage_markdown(inspect(tmp_path))
    assert "归档公告数：未知" in missing
    observation = official_fixture.archive(tmp_path, monkeypatch, populated=True)
    coverage = inspect(tmp_path, binding(tmp_path, observation))
    coverage["pending_announcements"][0]["title"] = "<script>BUY</script>[buy](evil)"
    text = render_hotspot_action_coverage_markdown(coverage)
    assert "<script>" not in text and "[buy](evil)" not in text
    assert "归档公告数：1" in text and "待审公告" in text
    assert "action=no_order" in text


@pytest.mark.parametrize("field,value", [("action", "order"), ("schema_version", "fake")])
def test_report_rejects_foreign_contract(tmp_path, field, value):
    from test_hotspot_official_action_coverage import inspect
    coverage = inspect(tmp_path)
    coverage[field] = value
    with pytest.raises(ValueError):
        render_hotspot_action_coverage_markdown(coverage)

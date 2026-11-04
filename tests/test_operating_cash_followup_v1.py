from datetime import datetime, timezone

from value_investment_agent.application.research import operating_cash_followup_v1 as service


NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def task(**overrides):
    result = dict(task_id="rt-test", symbol="600323", status="SUCCEEDED",
                  scope="LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED", action="no_order",
                  research_as_of="2026-11-03T00:00:00+00:00", context_fingerprint="context",
                  source_binding={"path": "runtime/test.json", "sha256": "a" * 64})
    result.update(overrides)
    return result


def observations(**overrides):
    result = dict(schema_version="parent-cash-observations-v1",
        status="SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS", symbol="600323",
        source_bindings=[{"source_id": "cninfo:1", "source_sha256": "b" * 64}], action="no_order")
    result.update(overrides)
    return result


def test_preparation_binds_verified_observations_without_creating_cash_policy(monkeypatch, tmp_path):
    captured = {}
    def replay(**kwargs):
        captured.update(kwargs)
        return observations()
    monkeypatch.setattr(service, "replay_bound_parent_cash_observations", replay)
    result = service.prepare_operating_cash_followup(root=tmp_path, task=task(), issuer_name="瀚蓝环境股份有限公司",
        receipt_bindings=[{"period": "2026-06-30", "receipt_binding": {"path": "runtime/r.json", "sha256": "b" * 64}}], now=NOW)
    assert result["status"] == "SOURCE_BOUND_PARENT_CASH_OBSERVATIONS_READY_FOR_POLICY"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["valuation"] is result["condition_price"] is None
    assert captured["symbol"] == "600323"
    assert {row["code"] for row in result["current_blockers"]} == {
        "EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED", "MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED",
        "CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED"}


def test_preparation_rejects_non_admitted_task_without_replaying(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "replay_bound_parent_cash_observations", lambda **_: (_ for _ in ()).throw(AssertionError()))
    result = service.prepare_operating_cash_followup(root=tmp_path, task=task(status="FAILED"), issuer_name="瀚蓝环境股份有限公司",
        receipt_bindings=[], now=NOW)
    assert result["status"] == "NOT_READY"


def test_preparation_rejects_future_or_naive_research_clock(tmp_path):
    for stamp in ("2026-11-05T00:00:00+00:00", "2026-11-03T00:00:00"):
        try:
            service.prepare_operating_cash_followup(root=tmp_path, task=task(research_as_of=stamp),
                issuer_name="瀚蓝环境股份有限公司", receipt_bindings=[], now=NOW)
        except ValueError as error:
            assert str(error) == "OPERATING_CASH_FOLLOWUP_CLOCK_INVALID"
        else:
            raise AssertionError("invalid research clock was accepted")


def test_registered_followup_reports_absent_registration_without_searching(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/current-operating-research-sources-v1.json").write_text(
        '{"schema_version":"current-operating-research-sources-v1","action":"no_order","cases":{}}',
        encoding="utf-8")
    result = service.read_registered_operating_cash_followup(root=tmp_path, task=task(), now=NOW)
    assert result["status"] == "NOT_STARTED"
    assert result["reason"] == "PARENT_CASH_OBSERVATION_RECEIPTS_NOT_REGISTERED"

from datetime import datetime, timezone
from types import SimpleNamespace

from value_investment_agent.application.research import operating_cash_consumption_v7 as mod


NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def test_transport_admission_is_the_only_failed_repair_path(monkeypatch, tmp_path):
    spec = dict(symbol="600323", task_id="repair", created_at=NOW.isoformat(),
                repair_requested_at=NOW.isoformat(), repair_of={"task_id": "original"})
    state = dict(status="FAILED", updated_at=NOW.isoformat())
    service = SimpleNamespace(_directory=lambda value: tmp_path,
                              _lock=lambda value: __import__("contextlib").nullcontext(),
                              _load=lambda value: (spec, state, {}))
    monkeypatch.setattr(mod.repair, "OperatingHorizonTaskService", lambda root: service)
    captured = {}
    monkeypatch.setattr(mod.transport, "admit", lambda **kwargs: captured.update(kwargs) or {"status": "admitted"})
    monkeypatch.setattr(mod, "_compile", lambda **kwargs: {"status": "compiled", "years": {}})
    (tmp_path / "input.json").write_text("{}")
    result = mod.read_annual_supplement(root=tmp_path, symbol="600323", now=NOW)
    assert result["status"] == "compiled"
    assert captured["original_task_id"] == "original" and captured["repair_task_id"] == "repair"


def test_nonfailed_task_uses_existing_consumer(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "_failed_repair", lambda root, symbol: None)
    monkeypatch.setattr(mod.prior, "read_annual_supplement", lambda **kwargs: {"status": "NOT_STARTED", "years": {}})
    assert mod.read_annual_supplement(root=tmp_path, symbol="600323", now=NOW)["status"] == "NOT_STARTED"

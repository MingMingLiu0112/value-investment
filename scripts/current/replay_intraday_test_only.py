"""Finite isolated reminder replay. Never acquires data or starts monitoring."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.hotspot.intraday_monitor import (
    read_intraday_monitor, tick_intraday_monitor,
)


def main():
    path = ROOT / "runtime/intraday-monitor/test-only.json"
    if path.exists():
        result = read_intraday_monitor(path)
        print(json.dumps(dict(action="no_order", test_only=True, existing_preserved=True,
            history_count=len(result["history"]), alerts_count=len(result["alerts"]))))
        return
    condition = dict(strategy="HOTSPOT_SATELLITE", symbol="600519", venue="SSE",
        condition_id="TEST_ONLY_price_observation", rule_version="TEST_ONLY_v1",
        source_id="TEST_ONLY", source_url="https://example.invalid/TEST_ONLY",
        input_kind="QUOTE", period="quote", operator="GT", threshold="10", action="no_order")
    start = datetime.fromisoformat("2026-10-16T10:30:02+08:00")
    for offset, price in ((0, "9"), (1, "11"), (2, None), (3, "11")):
        now = start + timedelta(seconds=offset)
        observation = None if price is None else dict(symbol="600519", source_id="TEST_ONLY",
            source_url=condition["source_url"], source_at=now.isoformat(), received_at=now.isoformat(),
            price=price, quality="VERIFIED", suspended=False, evidence_refs=[
                dict(id="TEST_ONLY_synthetic_source", sha256="a" * 64, source_url=condition["source_url"])])
        result = tick_intraday_monitor(path, condition=condition, observation=observation,
            now=now, max_age=timedelta(seconds=30))
    print(json.dumps(dict(action="no_order", test_only=True, monitor_running=False,
        history_count=len(result["history"]), alerts_count=len(result["alerts"]),
        eligibility=result["eligibility"], acceptance_authority="NONE")))


if __name__ == "__main__":
    main()

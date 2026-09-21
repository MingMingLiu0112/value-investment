import importlib.util
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_real_contract", ROOT / "scripts" / "build_moutai_real_execution_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_authenticated_contract_stays_nontrading():
    contract = MODULE.build_contract()
    assert len(contract["sessions"]) == 2674
    assert len(contract["cash_events"]) == 15
    assert sum(row["bonus_shares_per_share"] is not None for row in contract["cash_events"]) == 1
    assert contract["decisions"] == {}
    assert contract["formal_fair_value"] is None
    assert contract["trade_approved"] is False
    assert contract["contract_version"] == "moutai-real-execution-input-v5"
    assert contract["secondary_date_crosscheck"] == {
        "path": "runtime/historical-prices/20260908T061418761988Z/peer-date-audit.json",
        "sha256": "77ab9523b4bab14027fbfb48b4ba708eb23debca387e2d0cd0cec03171bde65b",
        "observed_dates": 2674,
        "unexplained_peer_dates": 0,
        "status": "no_secondary_peer_gap_not_official_calendar",
        "limitation": (
            "The peer union can detect a symbol-specific secondary-provider gap, but cannot "
            "prove an official exchange session or suspension state."
        ),
    }
    assert contract["sse_calendar_audit"] == {
        "path": "runtime/exchange-calendar-probes/moutai-sse-calendar-audit-20260913T093954Z/evidence.json",
        "sha256": "ad5e6eca1515a57a199058d82a7a12d903e2aeb3cae17c51f3f973a6dac8c3b3",
        "sse_open_dates": 2674,
        "calendar_approved": True,
        "execution_approved": False,
        "limitation": (
            "The calendar validates date membership only. It cannot prove a 600519 suspension state, "
            "order-book liquidity, queue priority, transaction cost, or next-open fill."
        ),
    }
    assert contract["sse_suspension_audit"] == {
        "path": "runtime/exchange-suspension-probes/moutai-sse-suspension-audit-20260913T095625Z/evidence.json",
        "sha256": "fc350ba01bd9abea5901962907b31c865fe6f8a88aef29fd5881ba4f8449734b",
        "queried_windows": 4,
        "official_returned_record_count": 0,
        "status": "no_official_listed_stop_resume_records_returned",
        "execution_approved": False,
        "limitation": (
            "An official empty response is not proof of intraday order-book liquidity, auction participation, "
            "queue priority, costs, or any fill. It also does not replace the separately pinned official SSE trading-calendar audit."
        ),
    }
    assert contract["sessions"][0]["execution_status"] == "first_archived_bar_no_prior_close"
    assert contract["sessions"][0]["price_limit_up"] is None
    assert all(row["next_open_fill_eligible"] is False for row in contract["sessions"])
    later_sessions = contract["sessions"][1:]
    assert all(row["execution_status"] == "daily_bar_execution_not_admitted" for row in later_sessions)
    assert all(row["open_limit_classification"] in {
        "open_at_upper_limit_queue_unknown",
        "open_at_lower_limit_queue_unknown",
        "open_not_at_derived_limit_no_orderbook",
    } for row in later_sessions)
    assert all(row["price_limit_up"] is not None and row["price_limit_down"] is not None for row in later_sessions)
    assert all(Decimal(row["volume_raw"]) >= 0 for row in contract["sessions"])

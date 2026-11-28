from decimal import Decimal
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.evidence import yili_interim_payout_stress_v1 as service


def test_hypothetical_payment_changes_only_the_first_year_and_rejects_overlap():
    years = [
        dict(year=year, policy={"payout_ratio": "0"}, scheduled_owner_distribution_cny="0")
        for year in (2027, 2028, 2029)
    ]
    amended = service._conditional_years(years, Decimal("2655895396.14"))
    assert amended[0]["scheduled_owner_distribution_cny"] == "2655895396.14"
    assert amended[1:] == years[1:]
    assert years[0]["scheduled_owner_distribution_cny"] == "0"
    with pytest.raises(ValueError, match="PREDECESSOR_SCHEDULE_CHANGED"):
        service._conditional_years(amended, Decimal("2655895396.14"))


def test_replay_refuses_modified_predecessor(tmp_path):
    path = tmp_path / "predecessor.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        service.replay_yili_interim_payout_stress(root=tmp_path, predecessor_path=path)


def test_real_payout_stress_replays_without_reclassifying_payment():
    root = Path(__file__).resolve().parents[1]
    predecessor = root.parent / "review" / "yili-d2-f1-conditional-replay.json"
    required = [predecessor, *(root / binding["path"] for binding in (service.PROPOSAL, service.RESOLUTION))]
    if not all(path.is_file() for path in required):
        pytest.skip("sealed Yili review and public originals are unavailable")
    first = service.replay_yili_interim_payout_stress(root=root, predecessor_path=predecessor)
    assert first == service.replay_yili_interim_payout_stress(root=root, predecessor_path=predecessor)
    assert first["cash_assumption"]["gross_amount_cny"] == "2655895396.14"
    assert first["cash_assumption"]["actual_payment_verified"] is False
    assert first["cash_assumption"]["actual_payment_date"] is None
    assert first["formal_eligibility"] is False
    assert first["action"] == "no_order"
    assert first["cases"]["FADE_TO_HISTORICAL_FY25"]["result"] == {
        "error": "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2029",
    }


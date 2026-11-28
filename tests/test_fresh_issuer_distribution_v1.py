from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from value_investment_agent.application.research import fresh_issuer_distribution_v1 as fresh

ISSUER = "山西杏花村汾酒厂股份有限公司"
DATES = "Ａ股 2026/7/30 － 2026/7/31 2026/7/31"
NOTICE = [
    f"证券代码：600809 {ISSUER} 2025年年度权益分派实施公告 "
    f"差异化分红送转：否 A 股每股现金红利6.56元 {DATES} "
    "本次利润分配以方案实施前的公司总股本1,219,964,222股为基数，"
    "每股派发现金红利6.56元（含税），共计派发现金红利8,002,965,296.32元。",
    f"{DATES} 中国结算上海分公司 自行发放对象",
]
CONFIRMATION = [
    "2025 年度，以权益分派股权登记日总股本为基数，向全体股东每 10 股"
    "派发现金股利 65.60 元（含税），累计派发现金股利 8,002,965,296.32 元"
]


def test_terms_and_aggregate_confirmation():
    terms = fresh._terms(NOTICE, "600809", ISSUER)
    assert (terms["entitled_shares"], terms["total_cny"], terms["paid_date"]) == (
        1219964222, "8002965296.32", "2026-07-31"
    )
    assert fresh._confirm(CONFIRMATION, terms) == 1


@pytest.mark.parametrize("old,new,reason", [
    ("1,219,964,222", "1,219,964,221", "ARITHMETIC"),
    ("8,002,965,296.32", "8,002,965,296.33", "ARITHMETIC"),
    ("证券代码：600809", "证券代码：600887", "ISSUER"),
    ("2026/7/30", "2026/7/29", "DATES_CONFLICT"),
])
def test_notice_rejects_conflicts(old, new, reason):
    with pytest.raises(ValueError, match=reason):
        fresh._terms([NOTICE[0].replace(old, new), NOTICE[1]], "600809", ISSUER)


def test_confirmation_amount_must_match():
    terms = fresh._terms(NOTICE, "600809", ISSUER)
    with pytest.raises(ValueError, match="AGGREGATE_CONFIRMATION_REQUIRED"):
        fresh._confirm([CONFIRMATION[0].replace("296.32", "296.33")], terms)


def test_schedule_counts_once_and_rejects_an_existing_schedule():
    scenarios = {s: {"years": [{"year": 2026}, {"year": 2027}]} for s in ("bear", "base", "bull")}
    event = dict(symbol="600809", aggregate_status="ISSUER_CONFIRMED_DISTRIBUTED_TOTAL",
                 distribution=fresh._terms(NOTICE, "600809", ISSUER))
    call = dict(event=event, symbol="600809", valuation_date="2025-12-31")
    scheduled = fresh.apply_fresh_issuer_distribution(scenarios=scenarios, **call)
    for s in scenarios:
        assert [r["scheduled_owner_distribution_cny"] for r in scheduled[s]["years"]] == [
            "8002965296.32", "0"
        ]
        assert all("scheduled_owner_distribution_cny" not in row for row in scenarios[s]["years"])
    with pytest.raises(ValueError, match="MODEL_SCHEDULE_NOT_PRISTINE"):
        fresh.apply_fresh_issuer_distribution(scenarios=scheduled, **call)
    with pytest.raises(ValueError, match="MODEL_IDENTITY_MISMATCH"):
        fresh.apply_fresh_issuer_distribution(scenarios=scenarios, **(call | {"symbol": "600887"}))


def test_cold_replay_actual_when_retained():
    root = Path(__file__).resolve().parents[1]
    path = root / "runtime/600809-historical-fyh1-research-v1/fresh-distribution-v1.json"
    if not path.is_file():
        pytest.skip("official 600809 originals are retained in the research runtime")
    pin = dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
    now = datetime.now(timezone.utc)
    result = fresh.replay_fresh_issuer_distribution(root=root, receipt_binding=pin, symbol="600809", now=now)
    assert result["confirmation_page"] == 13
    assert result["distribution"]["record_date"] == "2026-07-30"
    assert result["distribution"]["paid_date"] == "2026-07-31"
    assert result["distribution"]["total_cny"] == "8002965296.32"
    assert result["settlement_status"] == "ROUTE_ACTUALS_UNVERIFIED"
    assert result["route_settlement_cny"] == {"issuer_direct": None, "china_clear_shanghai": None}
    assert json.loads(path.read_bytes())["result"] == result
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        fresh.replay_fresh_issuer_distribution(root=root,
            receipt_binding=pin | {"sha256": "0" * 64}, symbol="600809", now=now)

"""Replay ten real completed-close observations without publishing a pointer."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import pytest
from hotspot_retained_originals import require_retained_originals

from value_investment_agent.application.hotspot.current_refresh import (
    final_observation_key, structure_selection_evidence,
)
from value_investment_agent.application.hotspot.daily_selection import verify_daily_selection
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.infrastructure.hotspot.current_price_case import load_current_price_case


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    "600150-2026-10-16-a1d2229173c84e87803d44f78c288cb7",
    "000338-2026-10-16-2bc8ebe792364a92a055f98decc704ac",
    "600176-2026-10-16-679618f8092a4242b0ecd1574f9982d6",
    "000560-2026-10-16-2f288dd8e2464ce091412f95be968cd0",
    "600667-2026-10-16-df78ab2e2de34fafa31a4d5badd495e7",
    "601857-2026-10-16-15e856c8ecb0473b8178f10b791bad17",
    "002008-2026-10-16-c16b41928f9045c08d2cdda19d55753e",
    "600019-2026-10-16-f50f688ee8df4a6da2e29128b2e17e91",
    "600127-2026-10-16-6700c02ee101483bab640c830e99b097",
    "000333-2026-10-16-835fe9d78ead4a7392a7a014aacc5064",
)


def test_real_ten_symbol_structure_selection_keeps_all_refusals_and_no_admission():
    source = ROOT / "runtime/hotspot-daily-selection/318a078e87de44d9a08b1cecafdda4e1/report.json"
    require_retained_originals(ROOT, source,
        *(ROOT / "runtime/hotspot-current-price-cases" / name / "case.json" for name in CASES))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == "3df8773984d1945607e7197ce4a68fb79ab4bded8d06f198471fadf166cb135e"
    report = json.loads(source.read_bytes())
    verify_daily_selection(ROOT, report)  # Rechecks actual turnover against original quote bytes.
    pool = {row["symbol"]: row for row in report["candidate_pool"]}
    assessed = []
    for name in CASES:
        path = ROOT / "runtime/hotspot-current-price-cases" / name / "case.json"
        original = json.loads(path.read_bytes())
        bundle = json.loads((ROOT / original["current_reference_close"]["bundle_path"]).read_bytes())
        available = max(datetime.fromisoformat(value) for value in (
            bundle["finished_at"], *(s["fetched_at"] for s in original["source_bindings"].values())))
        case = load_current_price_case(root=ROOT, symbol=name[:6], case_path=path, now=available)
        plan = project_current_price_action_plan(case)
        assert plan["formal_eligibility"] is False and plan["action_eligibility"] is False
        assert plan["current_pit"] is False and plan["price_admitted"] is False
        assessed.append(dict(symbol=name[:6], activity_rank=pool[name[:6]]["rank"],
            signal_state=plan["signal_state"], **plan["opportunity_quality"],
            structure_selection_evidence=structure_selection_evidence(plan)))
    assert len(assessed) == len(pool) == 10
    assert Counter(row["structure_tier"] for row in assessed) == {
        "ACTIVE_ONLY": 4, "CONFLICT_OR_REJECTED": 6}
    assert all(row["structure_reasons"] for row in assessed)
    final = sorted(assessed, key=final_observation_key)[:5]
    assert [row["symbol"] for row in final] == ["600150", "600667", "002008", "600019", "000560"]
    assert final[-1]["structure_reasons"] == ["INSUFFICIENT_UPPER_SPACE"]
    assert all(row["formal_eligibility"] is False for row in final)

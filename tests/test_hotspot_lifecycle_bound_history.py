"""TEST_ONLY synthetic raw evidence; no network, private inputs or permissions.

Each dated case is collected and replayed through the production loader. Only
the collector's HTTP transport is supplied; inspection and projection are real.
"""
import base64
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json

import pytest

from test_daily_quote_binding import _document, _write_bundle
from value_investment_agent.application.hotspot.current_case_review import inspect_current_price_case
from value_investment_agent.application.hotspot.lifecycle_review import build_hotspot_lifecycle_review
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES
from value_investment_agent.infrastructure.hotspot.current_price_case import (
    collect_current_price_case, load_current_price_case,
)
from value_investment_agent.quote_sessions import CHINA


SYMBOL = "600519"
ENTRY_AT = datetime(2026, 9, 21, 16, 15, tzinfo=CHINA)
CURRENT_AT = datetime(2026, 9, 24, 16, 15, tzinfo=CHINA)
TEST_ONLY_DAYS = (10, 11, 14, 15, 16, 17, 18, 21, 22, 23, 24)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(case):
    return dict(path=case["case_path"], sha256=case["case_sha256"])


def _dated_bundle(root, cutoff):
    """Rebind both raw quote timestamps and calendar acquisition, not metadata alone."""
    path = _write_bundle(root / "runtime" / f"TEST_ONLY-{cutoff.date()}")
    bundle = json.loads(path.read_bytes())
    reference = bundle["references"][SYMBOL]
    refs = reference["document_refs"]
    documents, identities = {}, {}
    acquired = (cutoff - timedelta(minutes=3)).isoformat()
    day = cutoff.date()
    for old_id in [refs["tencent"], refs["sina"], *refs["calendar_documents"]]:
        document = bundle["documents"][old_id]
        raw = base64.b64decode(document["raw_base64"])
        if old_id in (refs["tencent"], refs["sina"]):
            raw = raw.replace(b"20260924", day.strftime("%Y%m%d").encode("ascii"))
            raw = raw.replace(b"2026-09-24", day.isoformat().encode("ascii"))
        identity, document = _document(document["source_url"], raw, fetched_at=acquired)
        identities[old_id] = identity
        documents[identity] = document
    reference["document_refs"] = {
        provider: identities[refs[provider]] for provider in ("tencent", "sina")
    }
    reference["document_refs"]["calendar_documents"] = [
        identities[item] for item in refs["calendar_documents"]
    ]
    bundle.update(test_only=True, fixture_scope="TEST_ONLY", started_at=acquired,
                  finished_at=acquired, documents=documents, references={SYMBOL: reference})
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


class TestOnlyRawResponse:
    __test__ = False

    def __init__(self, scale, cutoff, *, breach, missing_day):
        period = "60m" if scale == "60" else "15m"
        self.url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/=/"
                    f"CN_MarketDataService.getKLineData?symbol=sh{SYMBOL}&scale={scale}&ma=no")
        rows = []
        for day in TEST_ONLY_DAYS:
            if day > cutoff.day or day == missing_day:
                continue
            for index, clock in enumerate(SESSION_TIMES[period]):
                hour_index = index if period == "60m" else index // 4
                broken = breach and day == 22 and hour_index == 1
                rows.append(dict(day=f"2026-09-{day:02} {clock}", open="12",
                    close="10" if broken else "12.34", high="13",
                    low="9" if breach and day >= 22 else "11",
                    volume="100" if period == "60m" else "25",
                    amount="1200" if period == "60m" else "300"))
        self.content = ("=(" + json.dumps(rows) + ");").encode("utf-8")

    def raise_for_status(self):
        pass


def _capture(root, cutoff, *, breach=False, missing_day=None):
    bundle = _dated_bundle(root, cutoff)
    case = collect_current_price_case(root=root, symbol=SYMBOL, as_of=cutoff.date(),
        quote_bundle_path=bundle, quote_bundle_sha256=_sha(bundle),
        now=cutoff - timedelta(minutes=1),
        fetch=lambda _url, params, timeout: TestOnlyRawResponse(
            params["scale"], cutoff, breach=breach, missing_day=missing_day))
    assert load_current_price_case(root=root, symbol=SYMBOL, case_path=case["case_path"],
        expected_sha256=case["case_sha256"], now=cutoff) == case
    assert case["action"] == "no_order" and case["action_eligibility"] is False
    return case


def _history(tmp_path, *, breach=False, missing_day=None):
    entry = _capture(tmp_path, ENTRY_AT)
    current = _capture(tmp_path, CURRENT_AT, breach=breach, missing_day=missing_day)
    return tmp_path, entry, tmp_path, current


def _review(history, *, entry_at=ENTRY_AT):
    entry_root, entry, _, current = history
    return build_hotspot_lifecycle_review(root=entry_root, symbol=SYMBOL,
        current_case_binding=_binding(current), entry_case_binding=_binding(entry),
        entry_at=entry_at, now=CURRENT_AT)


def _assert_no_permission(result):
    assert result["action"] == "no_order"
    assert result["personal_action"] == "NO_ACTION"
    assert result["position_guidance"] is None
    assert result["holding_ownership"] == "NOT_VERIFIED_HERE"
    for field in ("formal_eligibility", "trade_eligible", "risk_review_eligible"):
        assert result[field] is False
    for rule in result["current_conditions"].values():
        assert rule["personal_permission"] is False


def test_bound_history_recovery_preserves_original_break_despite_lower_rolling_price(tmp_path):
    history = _history(tmp_path, breach=True)
    _, entry, _, current = history
    entry_plan = project_current_price_action_plan(entry)
    current_plan = project_current_price_action_plan(current)
    assert entry["market_trade_date"] == "2026-09-21"
    assert current["market_trade_date"] == "2026-09-24"
    assert Decimal(entry_plan["invalidation_price"]) == Decimal("11")
    assert Decimal(current_plan["invalidation_price"]) == Decimal("9")
    assert Decimal(current["current_reference_price"]) > Decimal("11")
    assert current_plan["conditional_action_rules"]["EXIT"]["observed"] is False
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = _review(history)
    assert result["status"] == "STRUCTURAL_COMPARISON_ONLY"
    assert result["observed_review"] == "EXIT_STRUCTURE_REVIEW"
    comparison = result["original_entry_comparison"]
    assert Decimal(comparison["original_protection_price"]) == Decimal("11")
    assert Decimal(comparison["current_rolling_protection_price"]) == Decimal("9")
    assert comparison["first_breach_at"] == "2026-09-22T11:30:00+08:00"
    assert comparison["breach_count"] == 1
    assert comparison["inspected_bar_count"] == 12
    assert comparison["coverage"] == "COMPLETE"
    assert comparison["missing_completed_bars"] == []
    _assert_no_permission(result)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("missing_day", [None, 23], ids=["complete-control", "missing-whole-session"])
def test_bound_history_whole_session_gap_cannot_grant_hold_or_add(tmp_path, missing_day):
    history = _history(tmp_path, missing_day=missing_day)
    result = _review(history)
    comparison = result["original_entry_comparison"]
    assert result["current_data_status"] == "CURRENT"
    assert comparison["first_breach_at"] is None
    assert comparison["breach_count"] == 0
    if missing_day is None:
        assert comparison["coverage"] == "COMPLETE"
        assert result["observed_review"] == "HOLD_STRUCTURE_OBSERVATION"
    else:
        assert comparison["coverage"] == "INCOMPLETE"
        assert comparison["inspected_bar_count"] == 8
        assert comparison["missing_completed_bars"] == [
            f"2026-09-23T{clock}+08:00" for clock in SESSION_TIMES["60m"]
        ]
        assert result["status"] == "NOT_ASSESSABLE"
        assert result["observed_review"] == "UNKNOWN"
        assert "ENTRY_TO_CURRENT_BAR_COVERAGE_INCOMPLETE" in result["blockers"]
    _assert_no_permission(result)


@pytest.mark.parametrize("side", ["entry", "current"])
@pytest.mark.parametrize("source", ["60m", "15m", "quote_bundle"])
def test_bound_history_source_hash_tampering_is_rejected(tmp_path, side, source):
    history = _history(tmp_path, breach=True)
    root, case = history[:2] if side == "entry" else history[2:]
    path = root / (case["current_reference_close"]["bundle_path"] if source == "quote_bundle"
                   else case["source_bindings"][source]["path"])
    path.write_bytes(path.read_bytes() + b" TEST_ONLY_TAMPER")
    assert _sha(root / case["case_path"]) == case["case_sha256"]
    with pytest.raises(ValueError, match="hash"):
        load_current_price_case(root=root, symbol=SYMBOL, case_path=case["case_path"],
            expected_sha256=case["case_sha256"], now=ENTRY_AT if side == "entry" else CURRENT_AT)
    result = _review(history)
    assert result["status"] == "NOT_ASSESSABLE"
    assert result["observed_review"] == "UNKNOWN"
    assert result["original_entry_comparison"] is None
    assert ("ENTRY_CASE_NOT_VALID_AT_ENTRY" if side == "entry" else
            "CURRENT_CASE_EVIDENCE_INVALID") in result["blockers"]
    _assert_no_permission(result)


def test_bound_history_original_acquired_after_entry_is_rejected(tmp_path):
    history = _history(tmp_path)
    root, case = history[:2]
    entry_at = ENTRY_AT - timedelta(minutes=2)
    assert datetime.fromisoformat(case["source_bindings"]["60m"]["fetched_at"]) > entry_at
    # Quote/calendar are already known; only the raw bars arrive after this entry.
    bundle = json.loads((root / case["current_reference_close"]["bundle_path"]).read_bytes())
    assert all(datetime.fromisoformat(doc["fetched_at"]) <= entry_at
               for doc in bundle["documents"].values())
    inspected = inspect_current_price_case(root=root, symbol=SYMBOL,
        case_binding=_binding(case), now=entry_at)
    assert inspected["data_status"] == "INVALID"
    assert "availability" in inspected["diagnostic"]
    result = _review(history, entry_at=entry_at)
    assert result["status"] == "NOT_ASSESSABLE"
    assert result["observed_review"] == "UNKNOWN"
    assert result["original_entry_comparison"] is None
    assert "ENTRY_CASE_NOT_VALID_AT_ENTRY" in result["blockers"]
    _assert_no_permission(result)

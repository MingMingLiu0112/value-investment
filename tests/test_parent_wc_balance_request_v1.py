"""Direct D2 request tests; never dispatch a provider or produce assumptions."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil

import pytest

from value_investment_agent.application.research.agent_review import parent_wc_balance_request_v1 as mod
from value_investment_agent.infrastructure.filings.parent_wc_history_600519_v1 import read_parent_wc_history

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


@pytest.fixture
def generic_history():
    def observation(end, start, old, new, sha):
        rows = {field: dict(period_start_balance_cny=str(old + i),
                            period_end_balance_cny=str(new + i),
                            balance_change_cny=str(new - old))
                for i, field in enumerate(mod.FIELDS)}
        return dict(period=end, columns=[end, start], unit="CNY", balance_rows=rows,
                    parent_cfo_cny="100", excluded_group_note_cfo_cny="200",
                    parent_balance_pages=[10, 11], source_url="https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
                    original_sha256=sha, available_at="2026-04-18T00:00:00+08:00")
    return dict(status="PARENT_BALANCE_MOVEMENTS_ONLY", symbol="600887",
                issuer_name="内蒙古伊利实业集团股份有限公司", action="no_order",
                formal_eligibility=False, operating_wc_cash_cny="UNKNOWN",
                registry_sha256="c" * 64,
                observations=[observation("2024-12-31", "2023-12-31", 100, 110, "a" * 64),
                              observation("2025-03-31", "2024-12-31", 110, 90, "b" * 64)])


@pytest.fixture
def context():
    # TEST_ONLY baseline drives the existing request contract; parent WC
    # evidence in the opt-in real test comes from the two public originals.
    values = dict(revenue="1000", cost="500", surcharges="10", selling="10",
                  admin="20", research="5", pre_tax_profit="455")
    return dict(symbol="600519", issuer_name="贵州茅台酒股份有限公司",
        as_of="2026-11-11", snapshot_fingerprint="a" * 64,
        evidence=[dict(id="test:" + field, source_id="TEST_ONLY",
            pdf_sha256="b" * 64, available_at="2026-04-01T00:00:00+00:00",
            period="2025-12-31", period_basis="FY", scope="consolidated",
            unit="CNY", field=field, value=value, text="TEST_ONLY baseline row")
            for field, value in values.items()])


def test_clean_missing_source_cannot_enrich(context, tmp_path):
    before = deepcopy(context)
    history = read_parent_wc_history(tmp_path, NOW)
    with pytest.raises(ValueError, match="PARENT_WC_HISTORY_NOT_VERIFIED"):
        mod.attach_parent_wc_balance_anchor(context, history=history, as_of=NOW)
    assert context == before


@pytest.mark.parametrize("change", ["symbol", "issuer", "as_of"])
def test_wrong_request_identity_rejected_before_source_read(context, tmp_path, change):
    if change == "symbol": context["symbol"] = "BAD"
    elif change == "issuer": context["issuer_name"] = ""
    else: context["as_of"] = "2026-11-10"
    with pytest.raises(ValueError, match="PARENT_WC_REQUEST_IDENTITY_OR_AS_OF_INVALID"):
        mod.attach_parent_wc_balance_anchor(context, history={}, as_of=NOW)


def test_portable_other_issuer_and_periods(context, generic_history):
    context.update(symbol="600887", issuer_name="内蒙古伊利实业集团股份有限公司")
    enriched, anchor = mod.attach_parent_wc_balance_anchor(context, history=generic_history, as_of=NOW)
    assert anchor["symbol"] == "600887"
    assert [x["period_end"] for x in anchor["historical_balance_anchors"]] == ["2024-12-31", "2025-03-31"]
    assert [x["proxy_balance_change_cny"] for x in anchor["historical_balance_anchors"]] == ["10", "-20"]
    assert anchor["operating_wc_cash_cny"] == "UNKNOWN"
    assert all(row["scope"] == "ISSUER_PARENT_STANDALONE_BALANCE_PROXY" for row in enriched["evidence"][-2:])
    _, request, _ = mod.build_request_with_parent_wc_balance(
        context, [2026], history=generic_history, as_of=NOW)
    assert "600887" in request.user
    assert "operating_wc_cash_cny to zero" in request.system


@pytest.mark.parametrize("damage,code", [
    ("symbol", "PARENT_WC_HISTORY_NOT_VERIFIED_OR_CROSS_ISSUER"),
    ("issuer", "PARENT_WC_HISTORY_NOT_VERIFIED_OR_CROSS_ISSUER"),
    ("source", "PARENT_WC_SOURCE_BINDING_INVALID"),
    ("opening", "PARENT_WC_OPENING_BALANCES_CHANGED"),
    ("unverified", "PARENT_WC_HISTORY_NOT_VERIFIED_OR_CROSS_ISSUER"),
])
def test_cross_issuer_changed_source_and_unverified_history_rejected(context, generic_history, damage, code):
    context.update(symbol="600887", issuer_name="内蒙古伊利实业集团股份有限公司")
    if damage == "symbol": generic_history["symbol"] = "600519"
    elif damage == "issuer": generic_history["issuer_name"] = "错误发行人"
    elif damage == "source": generic_history["observations"][1]["original_sha256"] = "changed"
    elif damage == "opening":
        generic_history["observations"][1]["balance_rows"]["inventory"].update(
            period_start_balance_cny="112", balance_change_cny="-21")
    else: generic_history["status"] = "UNASSESSABLE"
    with pytest.raises(ValueError, match=code):
        mod.attach_parent_wc_balance_anchor(context, history=generic_history, as_of=NOW)


def test_at_least_two_compatible_intervals_required(context, generic_history):
    context.update(symbol="600887", issuer_name="内蒙古伊利实业集团股份有限公司")
    generic_history["observations"].pop()
    with pytest.raises(ValueError, match="PARENT_WC_HISTORY_PERIODS_INVALID"):
        mod.attach_parent_wc_balance_anchor(context, history=generic_history, as_of=NOW)


def test_real_originals_feed_existing_request_without_cash_default(context):
    root = os.environ.get("TEST_PARENT_WC_ROOT")
    if not root:
        pytest.skip("Set TEST_PARENT_WC_ROOT for real FY/H1 request replay")
    before = deepcopy(context)
    history = read_parent_wc_history(Path(root), NOW)
    enriched, request, anchor = mod.build_request_with_parent_wc_balance(
        context, [2026], history=history, as_of=NOW)
    assert context == before
    assert anchor["operating_wc_cash_cny"] == "UNKNOWN"
    assert [x["proxy_balance_change_cny"] for x in anchor["historical_balance_anchors"]] == [
        "4991116916.48", "-1582382025.64"]
    assert [(x["period_start"], x["period_end"]) for x in anchor["historical_balance_anchors"]] == [
        ("2024-12-31", "2025-12-31"), ("2025-12-31", "2026-06-30")]
    assert len(enriched["evidence"]) == len(context["evidence"]) + 2
    assert all(x["scope"] == "ISSUER_PARENT_STANDALONE_BALANCE_PROXY"
               for x in enriched["evidence"][-2:])
    assert all(x["pdf_sha256"] == a["pdf_sha256"]
               for x, a in zip(enriched["evidence"][-2:], anchor["historical_balance_anchors"]))
    assert "SOURCE_BOUND_PARENT_WC_BALANCE_RISK_ANCHOR=" in request.user
    assert "Do not annualize" in request.system
    assert "Do not default any missing term to zero" in request.system
    assert "operating_wc_cash_cny" in request.output_schema["properties"]["years"]["properties"]["2026"]["properties"]["shareholder_cash_paths"]["properties"]["bear"]["properties"]
    for item in anchor["historical_balance_anchors"]:
        schema = request.output_schema["properties"]["years"]["properties"]["2026"]["properties"]["shareholder_cash_paths"]["properties"]["bear"]["properties"]["operating_wc_cash_cny"]
        assert item["evidence_id"] in schema["properties"]["evidence_ids"]["items"]["enum"]
    assert anchor["formal_eligibility"] is False


def test_real_source_pit_blocks_request(context):
    root = os.environ.get("TEST_PARENT_WC_ROOT")
    if not root:
        pytest.skip("Set TEST_PARENT_WC_ROOT for PIT replay")
    context["as_of"] = "2026-11-10"
    early = datetime.fromisoformat("2026-11-10T13:11:09+00:00")
    history = read_parent_wc_history(Path(root), early)
    with pytest.raises(ValueError, match="PARENT_WC_HISTORY_NOT_VERIFIED"):
        mod.build_request_with_parent_wc_balance(context, [2026], history=history, as_of=early)


def test_changed_real_original_is_rejected_upstream(context, tmp_path):
    root = os.environ.get("TEST_PARENT_WC_ROOT")
    if not root:
        pytest.skip("Set TEST_PARENT_WC_ROOT for changed-original replay")
    root = Path(root)
    for relative in ("config/parent-wc-history-600519-v1.json",
                     "runtime/fy2025-600519-wc/original.pdf",
                     "runtime/h1-2026-ocr/original.pdf"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    with (tmp_path / "runtime/h1-2026-ocr/original.pdf").open("ab") as file:
        file.write(b"changed")
    history = read_parent_wc_history(tmp_path, NOW)
    assert history["status"] == "UNASSESSABLE"
    with pytest.raises(ValueError, match="PARENT_WC_HISTORY_NOT_VERIFIED"):
        mod.attach_parent_wc_balance_anchor(context, history=history, as_of=NOW)

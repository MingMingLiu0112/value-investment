"""TEST_ONLY arithmetic negatives; native quote/coverage/signature replay positives."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from value_investment_agent.application.research import pending_candidate_alignment as service
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.value_research_analysis import _bound
from value_investment_agent.research_artifact_codecs import ValuationResultCodec
from value_investment_agent.quote_snapshot import QuoteSnapshot
from test_d2_conditional_shared_service import synthetic_chain
from test_p7_materiality_review_transport import transport, _inputs


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return dict(path=name, sha256=sha256_file(path))


def test_sse_checkpoint_consumption_preserves_share_class_and_cutoff(tmp_path, monkeypatch):
    """TEST_ONLY extraction cache; native parser and consumer remain real."""
    from test_sse_capital_checkpoint_v1 import sample
    h1, proposal, _ = sample()
    root = tmp_path
    opening = write(root, "runtime/opening.json", {"TEST_ONLY": "ordinary shares"})
    analysis = dict(symbol="600888", consumed_operating_inputs=dict(ordinary_shares="6325360667"),
        source_bindings=[opening], source_catalog=[dict(id="opening", **opening)],
        official_fact_anchors=[dict(source_id="opening", field="ordinary_shares", unit="shares",
            period_end="2025-12-31", source_value="6325360667")],
        review_binding=dict(candidate_binding=opening), input_descriptor_sha256="a" * 64)
    h1_ref = write(root, "runtime/h1.json", h1)
    proposal_ref = write(root, "runtime/proposal.json", proposal)
    sources = {
        (h1_ref["path"], h1_ref["sha256"], "https://static.cninfo.com.cn/finalpage/2026-08-27/123.PDF"): "2026-11-18T00:00:00+00:00",
        (proposal_ref["path"], proposal_ref["sha256"], "https://static.cninfo.com.cn/finalpage/2026-10-30/456.PDF"): "2026-11-18T00:00:00+00:00",
    }
    cache = {h1_ref["sha256"]: h1, proposal_ref["sha256"]: proposal}
    now = datetime(2026, 11, 18, 1, tzinfo=timezone.utc)
    def consume(value, end=date(2026, 11, 17)):
        return service._native_basis_fields(value, date(2025, 12, 31), end, now,
            sources, lambda ref: _bound(root, ref), cache, [])
    result = consume(analysis)
    assert len(result["reports"]) == 2 and not result["unresolved_sources"]
    terms = {r["terms"]["kind"]: r["terms"] for r in result["reports"]}
    assert terms["H1_REPORT_UNCHANGED"]["ordinary_shares"] == "6325360667"
    assert terms["H1_REPORT_UNCHANGED"]["classification"] == "DERIVED_FACT"
    assert terms["INTERIM_PROPOSAL_DATED_SHARES"]["ordinary_shares"] is None
    assert terms["INTERIM_PROPOSAL_DATED_SHARES"]["issued_shares"] == "6325360667"
    assert result["closing_capital"]["ordinary_shares"] is None
    assert result["complete_action_coverage"] is False
    followup = service._basis_followup(analysis, dict(native_source_consumption=result),
        dict(outstanding_authorizations=[]), [], date(2026, 11, 17))
    assert len(followup["capital_checkpoints"]) == 2
    assert followup["latest_capital_checkpoint"]["treasury_shares"] == "1800200"
    assert followup["latest_capital_checkpoint"]["proposal_only"] is True
    assert followup["latest_capital_checkpoint"]["proposed_cash_per_share_cny"] == "0.42"
    assert followup["current_comparison_granted"] is False
    wrong = deepcopy(analysis)
    wrong["official_fact_anchors"] = []
    assert all(r["terms"]["ordinary_shares"] is None for r in consume(wrong)["reports"])
    assert not consume(analysis, date(2026, 8, 26))["reports"]
    h1["43"] = "三、股份总数 ６,３２５,３６０,６６７ １００ 其他变动表"
    guarded = consume(analysis)
    assert all(r["terms"]["kind"] != "H1_REPORT_UNCHANGED" for r in guarded["reports"])
    del h1["43"]
    from value_investment_agent.infrastructure.filings import interim_capital_distribution
    def contradictory(*args, **kwargs):
        raise ValueError("INTERIM_CAPITAL_ROLLFORWARD_CONFLICT")
    monkeypatch.setattr(interim_capital_distribution, "parse_interim_capital_distribution", contradictory)
    rejected = consume(analysis)
    assert not rejected["reports"]
    assert all(r["reason"] == "INTERIM_CAPITAL_ROLLFORWARD_CONFLICT" for r in rejected["unresolved_sources"])


@pytest.fixture
def reconciliation(tmp_path, monkeypatch):
    from pypdf import PdfWriter
    from value_investment_agent.infrastructure.filings import pdf_text
    original = tmp_path / "runtime/original.pdf"
    original.parent.mkdir()
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    with original.open("wb") as stream:
        pdf.write(stream)
    ref = dict(path="runtime/original.pdf", sha256=sha256_file(original))
    # Text extraction seam only: byte integrity and PDF validity are real;
    # calculations, source identity, chronology and evidence checks are unstubbed.
    text = ("证券代码：600519 TEST_ONLY 2020年1月1日 股份总数100股。"
        "2020年1月2日 股份总数100股，增发5股后105股。"
        "2020年1月1日无尚未实施的股本变动及利润分配方案。"
        "2019/12/29 股权登记日；2019/12/30 除息日及支付日，每股2元。"
        "2020/1/1 股权登记日；2020/1/2 除息日及支付日，每股2元。")
    monkeypatch.setattr(pdf_text, "extract_pages", lambda path: [text])
    anchor = dict(binding=ref, source_url="https://static.cninfo.com.cn/finalpage/2020-01-01/123.PDF",
        available_at="2020-01-03T00:00:00+00:00", physical_page=1, excerpt=text)
    candidate = write(tmp_path, "runtime/candidate.json", dict(symbol="600519", action="no_order"))
    a = dict(symbol="600519", valuation_date="2020-01-01", research_as_of="2020-01-03",
        status="CONDITIONAL_ANALYSIS_VERIFIED", action="no_order", arithmetic_complete=True,
        input_descriptor_sha256="a" * 64, review_binding=dict(candidate_binding=candidate),
        consumed_operating_inputs=dict(ordinary_shares="100"), source_bindings=[ref],
        source_catalog=[dict(kind="official_issuer_filing", local_path=ref["path"],
            sha256=ref["sha256"], location=anchor["source_url"],
            issuer_identity=dict(security_code="600519"), source_available_at=anchor["available_at"])],
        official_fact_anchors=[dict(source_id="cninfo:123", field="ordinary_shares",
            unit="shares", period_end="2020-01-01", source_value="100")],
        joint_capital_review=dict(economic_path=dict(currency="CNY")),
        valuation=dict(symbol="600519", model_type="TEST_ONLY", valuation_date="2020-01-01",
            bear_value="10", base_value="20", bull_value="30", confidence="低",
            assumptions={}, sensitivities=[], evidence_refs=[dict(id="TEST_ONLY")], blockers=[],
            status="conditional_research_only", model_version="TEST_ONLY"))
    ledger = dict(schema_version="pending-candidate-basis-reconciliation-v1",
        candidate_binding=candidate, input_descriptor_sha256="a" * 64,
        valuation_date="2020-01-01", comparison_date="2020-01-02", currency="CNY",
        share_basis="ordinary_share_unadjusted",
        opening_shares=dict(value="100", as_of="2020-01-01", evidence=[anchor]),
        closing_shares=dict(value="100", as_of="2020-01-02", evidence=[anchor]),
        share_actions=[], distributions=[], reviewed_documents=[],
        opening_pending_actions=dict(as_of="2020-01-01", pending_action_ids=[],
            rationale="TEST_ONLY exact public statement", evidence=[anchor]))
    windows = [dict(scan_from="2020-01-01", scan_to="2020-01-02", full_calendar_window_elapsed=True,
        announcements=[], observation_binding=dict(path="TEST_ONLY", sha256="b" * 64))]
    return dict(root=tmp_path, analysis=a, ledger=ledger, windows=windows, anchor=anchor,
                now=datetime.now(timezone.utc))


def reconcile(case):
    ref = write(case["root"], "runtime/reconciliation.json", case["ledger"])
    return service._reconcile(case["root"], case["analysis"], ref, date(2020, 1, 2),
        case["windows"], case["now"], lambda binding: _bound(case["root"], binding))


def cash(case, *, in_period=False):
    return dict(id="TEST_ONLY_CASH", record_date="2020-01-01" if in_period else "2019-12-29",
        ex_date="2020-01-02" if in_period else "2019-12-30",
        cash_payment_date="2020-01-02" if in_period else "2019-12-30",
        cash_amount="2", per_shares="1", cash_per_share="2",
        amount_basis="implemented_gross_entitlement", evidence=[case["anchor"]])


@pytest.mark.parametrize(("verified", "elapsed"), [(True, True), (False, True), (True, False)])
def test_publication_window_only_counts_verified_completed_days(reconciliation, verified, elapsed):
    first = reconciliation["windows"][0]
    first.update(scan_to="2020-01-01", source_integrity_verified=True)
    reconciliation["windows"].append(dict(
        first, scan_from="2020-01-02", scan_to="2020-01-02",
        source_integrity_verified=verified, full_calendar_window_elapsed=elapsed,
    ))

    result = reconcile(reconciliation)

    assert ("ACTION_PUBLICATION_WINDOW_MISSING" in result["reason_codes"]) is not (verified and elapsed)
    assert result["current_price_basis_compatible"] is False


def test_cross_date_manual_arithmetic_cannot_grant_native_alignment(reconciliation):
    result = reconcile(reconciliation)
    assert reconciliation["ledger"]["comparison_date"] != reconciliation["ledger"]["valuation_date"]
    assert result["status"] == "PARTIAL" and result["arithmetic_status"] == "RECONCILED"
    assert "CROSS_DATE_NATIVE_CAPITAL_AND_DISTRIBUTION_CLOSURE_NOT_SUPPORTED" in result["reason_codes"]
    assert result["current_price_basis_compatible"] is False
    assert result["native_basis_semantics_verified"] is False
    assert result["closing_shares"] == result["calculated_closing_shares"] == "100"
    assert result["formal_eligibility"] is False
    assert result["action"] == "no_order"


@pytest.mark.parametrize("closing_values,expected_status,expected_gap", [
    (["100", "100"], "EXACT_REPORT_DATE_SHARES_VERIFIED", None),
    (["105"], "EXACT_REPORT_DATE_SHARES_VERIFIED", "NATIVE_CLOSING_SHARE_COUNT_DIFFERS_FROM_ROLLFORWARD"),
    (["100", "105"], "EXACT_CLOSING_REPORT_ANCHORS_CONFLICT", "EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHORS_CONFLICT"),
    ([], "EXACT_CLOSING_REPORT_ANCHOR_MISSING", "EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING"),
])
def test_comparison_date_closing_reports_agree_with_each_other_and_rollforward(
    reconciliation, monkeypatch, closing_values, expected_status, expected_gap
):
    def report(value, index, *, published="2020-01-02", status="NATIVE_REPORT_FIELDS_VERIFIED"):
        return dict(status=status, binding=dict(path=f"TEST_ONLY-{index}", sha256=f"{index:064x}"),
                    published_date=published, terms=dict(period_end="2020-01-02", ordinary_shares=value))

    reports = [
        report(value, index) for index, value in enumerate(closing_values, 1)
    ] + [
        report("200", 10, published="2020-01-03"),
        report("200", 11, status="NATIVE_CAPITAL_CHECKPOINT_VERIFIED"),
    ]

    def native_fields(analysis, start, end, now, native_sources, read, cache, cash_rows):
        return dict(reports=reports, closing_capital=service._close_report_checkpoint(reports, end),
                    distribution_inclusion=dict(comparisons=[]))

    monkeypatch.setattr(service, "_native_basis_fields", native_fields)
    result = reconcile(reconciliation)
    closing = result["native_source_consumption"]["closing_capital"]
    assert closing["status"] == expected_status
    assert len(closing["anchors"]) == len(closing_values)
    assert not closing["continuity_to_opening_verified"]
    assert not result["current_price_basis_compatible"]
    if expected_gap:
        assert expected_gap in result["reason_codes"]
    if expected_status == "EXACT_REPORT_DATE_SHARES_VERIFIED":
        assert closing["rollforward_comparison"]["status"] == ("CONFLICT" if expected_gap else "MATCH")


def test_partial_retains_prevaluation_cash_without_double_deduction(reconciliation):
    case = reconciliation
    case["ledger"].update(closing_shares=None, opening_pending_actions=None,
                          distributions=[cash(case)])
    case["windows"][0]["full_calendar_window_elapsed"] = False
    result = reconcile(case)
    assert result["status"] == "PARTIAL"
    assert result["opening_shares"] == "100" and result["closing_shares"] is None
    assert result["distributions"][0]["period_treatment"] == "BEFORE_VALUATION_DATE_ALREADY_OUTSIDE_INTERVAL"
    assert result["distributions"][0]["price_deduction_applied"] == "0"
    assert result["period_cash_per_share"] == "0"
    assert not result["current_price_basis_compatible"]
    assert "OPENING_PENDING_ACTION_STATE_UNVERIFIED" in result["reason_codes"]


def test_effective_shares_recompute_but_never_mechanically_change_prices(reconciliation):
    case = reconciliation
    case["ledger"]["share_actions"] = [dict(id="TEST_ONLY_ISSUE", kind="INCREASE", shares="5",
        effective_date="2020-01-02", evidence=[case["anchor"]])]
    case["ledger"]["closing_shares"]["value"] = "105"
    result = reconcile(case)
    assert result["arithmetic_status"] == "RECONCILED" and result["calculated_closing_shares"] == "105"
    assert not result["current_price_basis_compatible"]
    assert "EFFECTIVE_SHARE_ACTION_REQUIRES_CANDIDATE_RECOMPUTATION" in result["reason_codes"]
    assert case["analysis"]["valuation"]["bear_value"] == "10"


def test_share_actions_use_effective_order_for_cancellation_basis(reconciliation, monkeypatch):
    from value_investment_agent.infrastructure.filings import pdf_text

    case = reconciliation
    anchor = case["anchor"]
    anchor["excerpt"] += " 2020-01-02 10; 2020-01-03 105"
    monkeypatch.setattr(pdf_text, "extract_pages", lambda path: [anchor["excerpt"]])
    close = date(2020, 1, 3)
    case["ledger"]["comparison_date"] = close.isoformat()
    case["ledger"]["closing_shares"].update(as_of=close.isoformat(), value="105")
    case["windows"][0]["scan_to"] = close.isoformat()
    case["ledger"]["share_actions"] = [
        dict(id="TEST_ONLY_LATER", kind="DECREASE", shares="5",
             effective_date=close.isoformat(), evidence=[anchor]),
        dict(id="TEST_ONLY_EARLIER", kind="INCREASE", shares="10",
             effective_date="2020-01-02", evidence=[anchor]),
    ]
    proof = []

    def verify(row, *, before, after, **kwargs):
        proof.append((before, after))
        return dict(status="NATIVE_CANCELLATION_PAIR_UNVERIFIED")

    monkeypatch.setattr(service, "_verify_period_buyback_cancellation", verify)
    ref = write(case["root"], "runtime/reconciliation.json", case["ledger"])
    result = service._reconcile(case["root"], case["analysis"], ref, close,
        case["windows"], case["now"], lambda binding: _bound(case["root"], binding))
    assert proof == [(110, 105)]
    assert [row["id"] for row in result["share_actions"]] == ["TEST_ONLY_EARLIER", "TEST_ONLY_LATER"]
    assert result["calculated_closing_shares"] == "105"
    assert not result["current_price_basis_compatible"]


def test_reconciled_closing_count_cannot_hide_nonpositive_intermediate_balance(reconciliation):
    case = reconciliation
    case["ledger"]["share_actions"] = [
        dict(id="TEST_ONLY_DECREASE", kind="DECREASE", shares="100",
             effective_date="2020-01-02", evidence=[case["anchor"]]),
        dict(id="TEST_ONLY_REISSUE", kind="INCREASE", shares="100",
             effective_date="2020-01-02", evidence=[case["anchor"]]),
    ]
    with pytest.raises(ValueError, match="NONPOSITIVE_RECONCILED_SHARE_COUNT"):
        reconcile(case)


def test_in_period_cash_is_not_blindly_subtracted_or_declared_included(reconciliation):
    case = reconciliation
    case["ledger"]["distributions"] = [cash(case, in_period=True)]
    result = reconcile(case)
    assert result["period_cash_per_share"] == "2"
    assert not result["current_price_basis_compatible"]
    assert result["distributions"][0]["model_inclusion"] == "NOT_NATIVE_VERIFIED"
    assert result["distributions"][0]["verified_cash_per_share"] is None
    assert result["distributions"][0]["price_deduction_applied"] == "0"


def test_period_decrease_with_only_manual_excerpt_stays_unverified(reconciliation):
    case = reconciliation
    case["ledger"]["share_actions"] = [
        dict(id="TEST_ONLY_DECREASE", kind="DECREASE", shares="5",
             effective_date="2020-01-02", evidence=[case["anchor"]])
    ]
    case["ledger"]["closing_shares"] = None
    result = reconcile(case)
    assert result["calculated_closing_shares"] == "95"
    assert result["share_actions"][0]["native_cancellation"]["status"] == "NATIVE_CANCELLATION_PAIR_UNVERIFIED"
    assert "PERIOD_DECREASE_NATIVE_CANCELLATION_UNVERIFIED" in result["reason_codes"]
    assert not result["current_price_basis_compatible"]


def test_period_cancellation_requires_pair_and_post_publication_cutoff(monkeypatch):
    from value_investment_agent.infrastructure.filings import opening_action_terms, operating_event_terms

    purchase = ("buyback.pdf", "a" * 64, "https://static.cninfo.com.cn/finalpage/2020-01-02/321.PDF")
    confirmation = ("cancel.pdf", "b" * 64, "https://static.cninfo.com.cn/finalpage/2020-01-03/322.PDF")

    def parse_purchase(pages, *, symbol):
        if pages != ["purchase"]:
            raise ValueError("TEST_ONLY_NOT_PURCHASE")
        return dict(symbol=symbol, published_date="2020-01-02",
                    terms=dict(purchase_state="COMPLETED", cancellation_state="SCHEDULED_UNCONFIRMED",
                               scheduled_cancellation_date="2020-01-02",
                               cumulative_purchased_shares=5, planned_post_cancellation_shares=95))

    def parse_confirmation(pages, *, symbol):
        if pages != ["confirmation"]:
            raise ValueError("TEST_ONLY_NOT_CONFIRMATION")
        return dict(symbol=symbol, published_date="2020-01-03",
                    terms=dict(completion_notice_on="2020-01-02", confirmed_cancellation_date="2020-01-02",
                               cancelled_shares="5", issued_shares="95", capital_as_of="2020-01-03"),
                    term_pages=dict(confirmed_cancellation=[2]))

    monkeypatch.setattr(operating_event_terms, "parse_operating_event_terms", parse_purchase)
    monkeypatch.setattr(opening_action_terms, "parse_opening_action_terms", parse_confirmation)
    row = dict(effective_date="2020-01-02", evidence=[
        dict(binding=dict(path=path, sha256=sha), source_url=url)
        for path, sha, url in (purchase, confirmation)
    ])
    inputs = dict(symbol="600519", before=Decimal(100), after=Decimal(95), end=date(2020, 1, 3),
                  cache={purchase[1]: ["purchase"], confirmation[1]: ["confirmation"]},
                  window_sources={purchase, confirmation})
    proof = service._verify_period_buyback_cancellation(row, **inputs)
    assert proof["status"] == "NATIVE_BUYBACK_CANCELLATION_MATCHED"
    assert proof["confirmation_physical_pages"] == [2]
    for changes in (dict(end=date(2020, 1, 2)), dict(window_sources={purchase}), dict(after=Decimal(94))):
        proof = service._verify_period_buyback_cancellation(row, **(inputs | changes))
        assert proof["status"] == "NATIVE_CANCELLATION_PAIR_UNVERIFIED"


def test_exact_consumed_distribution_removes_only_its_recomputation_gap(reconciliation, monkeypatch):
    case = reconciliation
    case["ledger"]["distributions"] = [cash(case, in_period=True)]
    case["analysis"]["consumed_implemented_distributions"] = [dict(
        status="PASS", reason_code="IMPLEMENTED_DISTRIBUTION_INCLUDED_IN_MODEL",
        scope="EXACT_IMPLEMENTED_DISTRIBUTION_ONLY_NOT_PERIOD_COMPLETENESS",
        paid_date="2020-01-02", per_share_cny="2", total_cny="200",
        original_binding=case["anchor"]["binding"], period_cash_coverage_complete=False,
        capital_structure_aligned=False, materiality_approved=False,
        financial_updates_reconciled=False, formal_eligibility=False, action="no_order")]
    with pytest.raises(ValueError, match="CONSUMED_IMPLEMENTED_DISTRIBUTION_NOT_UNIQUELY_RECONCILED"):
        reconcile(case)
    terms = dict(published_date="2020-01-01", record_date="2020-01-01",
        ex_date="2020-01-02", cash_payment_date="2020-01-02",
        cash_per_share="2", total_gross_cash="201")
    monkeypatch.setattr(service, "_cash_terms", lambda pages, symbol: terms)
    with pytest.raises(ValueError, match="CONSUMED_IMPLEMENTED_DISTRIBUTION_NOT_UNIQUELY_RECONCILED"):
        reconcile(case)
    terms["total_gross_cash"] = "200"
    case["ledger"]["distributions"][0]["cash_payment_date"] = "2020-01-03"
    case["analysis"]["consumed_implemented_distributions"][0]["paid_date"] = "2020-01-03"
    terms["cash_payment_date"] = "2020-01-03"
    case["anchor"]["excerpt"] += " 2020-01-03"
    from value_investment_agent.infrastructure.filings import pdf_text
    extract = pdf_text.extract_pages
    monkeypatch.setattr(pdf_text, "extract_pages",
        lambda path: [page + " 2020-01-03" for page in extract(path)])
    with pytest.raises(ValueError, match="CONSUMED_IMPLEMENTED_DISTRIBUTION_NOT_UNIQUELY_RECONCILED"):
        reconcile(case)
    case["ledger"]["distributions"][0]["cash_payment_date"] = "2020-01-02"
    case["analysis"]["consumed_implemented_distributions"][0]["paid_date"] = "2020-01-02"
    terms["cash_payment_date"] = "2020-01-02"

    result = reconcile(case)
    assert result["implemented_distribution_inclusion_complete"] is True
    assert result["unconsumed_period_cash_per_share"] == "0"
    assert result["distributions"][0]["model_inclusion"] == (
        "EXACT_IMPLEMENTED_DISTRIBUTION_COLD_RECOMPUTED_IN_CANDIDATE")
    assert "IN_PERIOD_CASH_FLOW_INCLUSION_REQUIRES_CANDIDATE_RECOMPUTATION" not in result["reason_codes"]
    assert result["current_price_basis_compatible"] is False

    anchor = case["anchor"]
    case["windows"][0].update(
        source_integrity_verified=True, acquired_at=anchor["available_at"],
        announcements=[dict(
            announcement_id="124", title="TEST_ONLY权益分派实施公告更正",
            published_at="2019-12-31T16:00:00+00:00",
            evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])],
        )],
    )
    result = reconcile(case)
    assert result["unconsumed_period_cash_per_share"] == "0"
    assert not result["implemented_distribution_inclusion_complete"]
    assert "COVERED_CASH_IMPLEMENTATION_LINEAGE_UNRESOLVED: 124" in result["reason_codes"]
    assert not result["current_price_basis_compatible"]


@pytest.mark.parametrize("path,value", [
    (("candidate_binding", "sha256"), "b" * 64),
    (("input_descriptor_sha256",), "b" * 64),
    (("currency",), "USD"), (("share_basis",), "adjusted"),
    (("comparison_date",), "2020-01-03"),
    (("opening_shares", "value"), "105"),
    (("closing_shares", "value"), "105"),
    (("closing_shares", "value"), True),
    (("closing_shares", "value"), "NaN"),
    (("closing_shares", "as_of"), "2020-01-01"),
])
def test_reconciliation_basis_mismatch_never_falls_back(reconciliation, path, value):
    case = reconciliation
    # Independent artifact identity: do not mutate the analysis's binding.
    case["ledger"] = deepcopy(case["ledger"])
    row = case["ledger"]
    for part in path[:-1]:
        row = row[part]
    row[path[-1]] = value
    with pytest.raises((ValueError, ArithmeticError)):
        reconcile(case)


@pytest.mark.parametrize("field,value", [("physical_page", True), ("physical_page", 2),
    ("excerpt", "invented"), ("available_at", "2099-01-01T00:00:00+00:00"),
    ("available_at", "2020-01-01"), ("source_url", "https://example.org/a.pdf")])
def test_original_anchor_negative_gates(reconciliation, field, value):
    reconciliation["anchor"][field] = value
    with pytest.raises(ValueError):
        reconcile(reconciliation)


def test_empty_opening_list_without_original_absence_statement_cannot_pass(reconciliation):
    anchor = deepcopy(reconciliation["anchor"])
    anchor["excerpt"] = "2020年1月1日 股份总数100股。"
    reconciliation["ledger"]["opening_pending_actions"]["evidence"] = [anchor]
    result = reconcile(reconciliation)
    assert not result["current_price_basis_compatible"]
    assert "OPENING_NO_PENDING_ACTION_STATEMENT_NOT_PROVEN" in result["reason_codes"]


def test_source_bytes_tamper_rejected(reconciliation):
    (reconciliation["root"] / reconciliation["anchor"]["binding"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        reconcile(reconciliation)


def test_native_raw_window_stays_pending_and_does_not_approve_reconciled_basis(reconciliation, monkeypatch):
    from test_retained_event_coverage import archive
    case = reconciliation
    observation = archive(case["root"], monkeypatch)
    ref = write(case["root"], "runtime/events/observation.json", observation)
    windows, scans = service._event_windows(case["root"], case["analysis"], [ref],
        datetime.now(timezone.utc), lambda binding: _bound(case["root"], binding))
    assert windows[0]["source_integrity_verified"]
    result = reconcile(case)
    quote = QuoteSnapshot("600519", date(2020, 1, 2), Decimal("15"), "verified_close",
                          [dict(id="TEST_ONLY_quote", sha256="b" * 64)])
    q = dict(status="QUALIFIED", reason_codes=[], explanation="TEST_ONLY", bundle_binding=None,
             native_status="TEST_ONLY")
    checks, validity, bridge, ready = service._assess(case["analysis"],
        ValuationResultCodec().from_payload(case["analysis"]["valuation"]), quote, q, windows, scans, result)
    assert checks[1]["status"] == checks[2]["status"] == "BLOCKED"
    assert validity.status == "UNKNOWN" and not ready and bridge.bridge_status != "READY"


def test_legacy_draft_comparison_flags_and_thresholds_stay_unchanged(reconciliation, monkeypatch):
    case = reconciliation
    price = dict(draft_prices=dict(entry="10", reduce="30", add=None, exit=None),
        currentpricecomparison=False, price_comparison=dict(status="not_performed", currentpricecomparison=False))
    case["analysis"]["joint_capital_review"]["conditional_price"] = price
    before = deepcopy(price)
    monkeypatch.setattr(service, "load_pending_candidate_alignment", lambda **kw:
        dict(status="ALIGNED_FOR_RESEARCH_COMPARISON", currentpricecomparison=True))
    service.attach_pending_candidate_alignment(root=case["root"], analysis=case["analysis"], now=case["now"])
    assert {key: price[key] for key in before} == before
    assert case["analysis"]["current_alignment"] == price["alignment"]


def test_existing_signed_materiality_packet_is_consumed_for_exact_package_and_scan(transport):
    from value_investment_agent.application.product.research_materiality_reviews import consume_materiality_review_response
    from value_investment_agent.infrastructure.evidence.trust_root_registry import _use_test_trust_registry
    from value_investment_agent.event_scan import event_scan_from_payload
    f = transport
    registry, args = _inputs(f)
    scan_ref = dict(path=f["scan_path"].relative_to(f["root"]).as_posix(), sha256=f["scan_hash"])
    analysis = dict(symbol=f["handoff"]["symbol"], review_binding=dict(
        package_binding=f["handoff"]["package_binding"]))
    scan = event_scan_from_payload(json.loads(f["scan_path"].read_text(encoding="utf-8")))
    with _use_test_trust_registry(registry):
        receipt = consume_materiality_review_response(**args)
        review, route = service._materiality(f["root"], analysis, receipt["review_packet_binding"],
            [dict(scan_binding=scan_ref)], [scan], datetime.now(timezone.utc),
            lambda ref: _bound(f["root"], ref))
        assert route["status"] == "EXISTING_AUTHENTICATED_MATERIALITY_REPLAYED"
        assert len(review.decisions) == 2
        assert receipt["whole_model_approved"] is False
        assert receipt["research_admitted"] is False


def test_native_candidate_adapter_gap_is_not_described_as_missing_human_approval(reconciliation, monkeypatch):
    from value_investment_agent.application.product import research_materiality_reviews
    case = reconciliation
    package = write(case["root"], "runtime/package.json", {"TEST_ONLY": True})
    scan = write(case["root"], "runtime/scan.json", {"TEST_ONLY": True})
    case["analysis"]["review_binding"]["package_binding"] = package
    def unsupported(**kwargs):
        raise ValueError("Exact annual-retention-v2 scenario required; no scalar retention")
    monkeypatch.setattr(research_materiality_reviews, "prepare_materiality_review_handoff", unsupported)
    review, route = service._materiality(case["root"], case["analysis"], None,
        [dict(scan_binding=scan)], [__import__("types").SimpleNamespace(coverage_status="COMPLETE", validity_from=date(2020,1,1), announcements=[object()])], case["now"], lambda ref: _bound(case["root"], ref))
    assert review is None
    assert route["status"] == "NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED"
    assert route["engineering_gap"]


def test_plausible_official_url_with_wrong_native_document_identity_rejected(reconciliation):
    reconciliation["anchor"]["source_url"] = "https://static.cninfo.com.cn/finalpage/2020-01-01/999.PDF"
    with pytest.raises(ValueError, match="ANCHOR_NOT_BOUND_TO_NATIVE_OFFICIAL_SOURCE"):
        reconcile(reconciliation)


def test_copied_pdf_not_in_native_path_closure_is_not_official_binding(reconciliation):
    case = reconciliation
    original = case["root"] / case["anchor"]["binding"]["path"]
    copied = case["root"] / "runtime/copied.pdf"
    copied.write_bytes(original.read_bytes())
    case["anchor"]["binding"] = dict(path="runtime/copied.pdf", sha256=sha256_file(copied))
    with pytest.raises(ValueError, match="ANCHOR_NOT_BOUND_TO_NATIVE_OFFICIAL_SOURCE"):
        reconcile(case)


def test_cooccurring_amount_and_date_do_not_make_native_field_semantics(reconciliation):
    case = reconciliation
    case["ledger"]["closing_shares"]["evidence"] = [dict(case["anchor"],
        excerpt="2020年1月2日 股份总数100股，增发5股后105股。")]
    result = reconcile(case)
    assert result["arithmetic_status"] == "RECONCILED"
    assert not result["native_basis_semantics_verified"]
    assert "EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING" in result["reason_codes"]


def test_failed_explicit_review_hard_blocks_even_clean_empty_scan(reconciliation):
    from value_investment_agent.event_scan import EventScanResult, EVENT_SCAN_SCHEMA, PRE_MODEL_NONE
    case = reconciliation
    scan = EventScanResult(EVENT_SCAN_SCHEMA, "600519", "cninfo", date(2020, 1, 1), date(2020, 1, 2),
        date(2020, 1, 1), date(2020, 1, 2), "COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW",
        "COMPLETE", PRE_MODEL_NONE, (), (), ({"id": "TEST_ONLY"},), case["now"], "TEST_ONLY")
    quote = QuoteSnapshot("600519", date(2020, 1, 2), Decimal("15"), "verified_close",
                          [dict(id="TEST_ONLY_quote", sha256="b" * 64)])
    q = dict(status="QUALIFIED", reason_codes=[], explanation="TEST_ONLY", bundle_binding=None,
             native_status="TEST_ONLY")
    checks, validity, bridge, ready = service._assess(case["analysis"],
        ValuationResultCodec().from_payload(case["analysis"]["valuation"]), quote, q,
        case["windows"], [scan], reconcile(case), materiality_route=dict(
            status="EXISTING_MATERIALITY_REPLAY_REJECTED", reason="bad signature",
            review_binding=dict(path="bad.json", sha256="a" * 64)))
    assert validity.status != "VALID" and bridge.bridge_status != "READY" and not ready
    assert "EXPLICIT_MATERIALITY_REVIEW_FAILED_NO_SCAN_FALLBACK" in checks[3]["reason_codes"]


def test_native_quote_capture_archive_and_alignment_consumer_positive(tmp_path):
    # Only HTTP transport is synthetic. Collection, native raw-byte hashes,
    # both parsers, exchange calendar, B1 and alignment consumer run unchanged.
    from test_quote_session_collection import Session
    from test_quote_sessions import NOW
    from value_investment_agent.quote_session_collection import collect_session_bundle
    bundle = collect_session_bundle(["000333"], session=Session(), clock=lambda: NOW)
    ref = write(tmp_path, "runtime/TEST_ONLY-quotes/bundle.json", bundle)
    quote, result = service._qualified_quote(tmp_path,
        dict(symbol="000333", research_as_of="2026-09-06"), ref, NOW,
        lambda binding: _bound(tmp_path, binding))
    assert quote.status == "verified_close" and not quote.blockers
    assert result["status"] == "QUALIFIED" and result["current_price"] == "60"
    assert result["latest_completed_session"] == "2026-09-07"
    assert result["native_status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    # Re-sealing one altered provider cannot reuse the previous positive result.
    import base64
    tx = bundle["documents"][bundle["references"]["000333"]["document_refs"]["tencent"]]
    tx["raw_base64"] = base64.b64encode(b"invented provider body").decode()
    changed = write(tmp_path, ref["path"], bundle)
    with pytest.raises(ValueError):
        service._qualified_quote(tmp_path, dict(symbol="000333", research_as_of="2026-09-06"),
            changed, NOW, lambda binding: _bound(tmp_path, binding))


@pytest.fixture(scope="module")
def real_candidate():
    import os
    from pathlib import Path
    from value_investment_agent.application.research.value_research_analysis import load_current_value_research_analysis
    configured = os.environ.get("VALUE_ALIGNMENT_REAL_ROOT")
    if configured is None:
        pytest.skip("VALUE_ALIGNMENT_REAL_ROOT unset: real originals not installed; skip is not real acceptance")
    assert configured.strip(), "VALUE_ALIGNMENT_REAL_ROOT must name the installed real evidence root"
    root = Path(configured).resolve(strict=True)
    now = datetime.now(timezone.utc)
    analysis = load_current_value_research_analysis(root=root, symbol="600519", now=now)
    assert analysis["status"] == "CONDITIONAL_ANALYSIS_VERIFIED", analysis
    candidate = analysis["review_binding"]["candidate_binding"]
    config = json.loads((root / service.CONFIG_DIRECTORY / f"{candidate['sha256']}.json").read_bytes())
    assert config["candidate_binding"] == candidate
    original = json.loads(_bound(root, config["reconciliation_binding"]).read_bytes())
    alignment = analysis["current_alignment"]
    quote = alignment["quote"]
    # Real retained sources outlive a trading session. The same archived quote
    # must turn stale after a newer official close, not make native PDF tests
    # depend on running before 15:00 or silently retain a current price.
    if quote["latest_completed_session"] == quote["quote_date"]:
        assert quote["status"] == "QUALIFIED", alignment
    else:
        assert quote["latest_completed_session"] > quote["quote_date"], alignment
        assert quote["status"] == "BLOCKED" and quote["current_price"] is None
        assert quote["native_status"] == "NOT_ADMITTED"
        assert "QUOTE_NOT_LATEST_QUALIFIED_CLOSE" in quote["reason_codes"]
    assert alignment["checks"][1]["details"].get("reconciliation") is not None, alignment
    for ref in [*analysis["source_bindings"], *alignment["evidence_bindings"]]:
        _bound(root, ref)
    return root, analysis, original, now


def test_real_native_original_and_cash_semantics_end_to_end(real_candidate):
    root, analysis, ledger, now = real_candidate
    alignment = analysis["current_alignment"]
    result = alignment["checks"][1]["details"]["reconciliation"]
    row = result["distributions"][0]
    assert result["status"] == "PARTIAL"
    assert result["opening_shares_semantics"] == "NATIVE_CONSUMED_FACT_MATCHED"
    assert row["verified_cash_per_share"] == "28.02423"
    assert row["native_terms"]["total_gross_cash"] == "35032574305.19"
    assert row["period_treatment"] == "BEFORE_VALUATION_DATE_ALREADY_OUTSIDE_INTERVAL"
    assert row["price_deduction_applied"] == "0"
    assert alignment["quote"]["current_price"] == (
        "1354.00" if alignment["quote"]["status"] == "QUALIFIED" else None)
    assert not alignment["currentpricecomparison"]


@pytest.mark.parametrize("old,new", [("每股派发现金红利", "每十股派发现金红利"),
    ("元（含税），共计", "元（税后），共计"), ("35,032,574,305.19", "35,032,574,305.18"),
    ("股权登记日 最后交易日", "最后交易日 股权登记日")])
def test_native_cash_semantic_label_or_total_mutation_rejected(real_candidate, old, new):
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    root, _, ledger, _ = real_candidate
    pages = extract_pages(_bound(root, ledger["distributions"][0]["evidence"][0]["binding"]))
    assert any(old in p for p in pages)
    with pytest.raises(ValueError):
        service._cash_terms([p.replace(old, new) for p in pages], "600519")


def test_same_day_native_opening_and_collector_window_can_reconcile_basis(real_candidate, tmp_path, monkeypatch):
    # Real consumed H1 fact + real original extraction. Only index HTTP transport
    # is TEST_ONLY; collector/retained-window replay run without flag overrides.
    import test_retained_event_coverage as archive_service
    root, analysis, original, now = real_candidate
    monkeypatch.setattr(archive_service, "START", date(2026, 6, 30))
    monkeypatch.setattr(archive_service, "END", date(2026, 6, 30))
    observation = archive_service.archive(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    ref = write(tmp_path, "runtime/events/observation.json", observation)
    windows, scans = service._event_windows(tmp_path, analysis, [ref], now,
        lambda binding: _bound(tmp_path, binding))
    ledger = deepcopy(original)
    ledger.update(comparison_date="2026-06-30", distributions=[])
    # Mirror the consumed originals with short test-local paths (Windows path
    # limits), preserving bytes/URL/hash and remapping every relevant reference.
    # The real loader above has already verified the original native paths.
    analysis = deepcopy(analysis)
    mapped = {}
    for item in ledger["opening_shares"]["evidence"]:
        binding = item["binding"]
        original_path = _bound(root, binding)
        old_path = binding["path"]
        mapped.setdefault(old_path, f"runtime/consumed-{len(mapped)}.pdf")
        target = tmp_path / mapped[old_path]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original_path.read_bytes())
        binding["path"] = mapped[old_path]
        _bound(tmp_path, binding)
    for binding in analysis["source_bindings"]:
        binding["path"] = mapped.get(binding["path"], binding["path"])
    for source in analysis["source_catalog"]:
        source["local_path"] = mapped.get(source["local_path"], source["local_path"])
    # No fake closing or pending-action assurance is supplied for an empty interval.
    ref = write(tmp_path, "same-day-ledger.json", ledger)
    result = service._reconcile(tmp_path, analysis, ref, date(2026, 6, 30), windows, now,
        lambda binding: _bound(tmp_path, binding))
    assert result["status"] == "RECONCILED"
    assert result["native_basis_semantics_verified"] and result["current_price_basis_compatible"]
    assert result["closing_shares"] == "1250081601"
    # This component success does not turn collector PENDING into model VALID.
    assert scans[0].status == "PENDING_HUMAN_REVIEW"
    windows[0]["full_calendar_window_elapsed"] = False
    rejected = service._reconcile(tmp_path, analysis, ref, date(2026, 6, 30), windows, now,
        lambda binding: _bound(tmp_path, binding))
    assert rejected["status"] == "PARTIAL"


def test_materiality_preflight_does_not_call_adapter_for_incomplete_or_wrong_window(reconciliation, monkeypatch):
    from types import SimpleNamespace
    from value_investment_agent.application.product import research_materiality_reviews
    case = reconciliation
    case["analysis"]["review_binding"]["package_binding"] = dict(path="unread", sha256="a"*64)
    monkeypatch.setattr(research_materiality_reviews, "prepare_materiality_review_handoff",
        lambda **kw: pytest.fail("invalid window must not reach model adapter"))
    review, route = service._materiality(case["root"], case["analysis"], None,
        [dict(scan_binding={}, full_calendar_window_elapsed=False)],
        [SimpleNamespace(coverage_status="COMPLETE", validity_from=date(2019,12,22), announcements=[object()])],
        case["now"], lambda ref: pytest.fail("preflight needs no file reads"))
    assert review is None and route["engineering_gap"] is None
    assert len(route["reason_codes"]) == 2
    assert route["status"] == "NATIVE_MATERIALITY_SCAN_PRECONDITIONS_NOT_MET"


def test_supplemental_window_only_binds_original_not_effective_coverage(reconciliation):
    case = reconciliation
    source = case["analysis"]["source_catalog"].pop()
    supplemental = dict(acquired_at=source["source_available_at"], announcements=[dict(
        announcement_id="cninfo:123", evidence_refs=[dict(path=source["local_path"],
        sha256=source["sha256"], source_url=source["location"])])])
    ref = write(case["root"], "runtime/ledger.json", case["ledger"])
    result = service._reconcile(case["root"], case["analysis"], ref, date(2020,1,2), [], case["now"],
        lambda binding: _bound(case["root"], binding), [supplemental])
    assert "ACTION_PUBLICATION_WINDOW_MISSING" in result["reason_codes"]
    assert "PUBLIC_ACTION_REVIEW_DOES_NOT_COVER_ALL_ANNOUNCEMENTS" not in result["reason_codes"]
    assert not result["native_basis_semantics_verified"]
    supplemental["announcements"][0]["evidence_refs"][0]["source_url"] += "?wrong"
    with pytest.raises(ValueError, match="ANCHOR_NOT_BOUND_TO_NATIVE_OFFICIAL_SOURCE"):
        service._reconcile(case["root"], case["analysis"], ref, date(2020,1,2), [], case["now"],
            lambda binding: _bound(case["root"], binding), [supplemental])


def test_real_cross_date_fields_are_consumed_without_promoting_bridge(real_candidate):
    _, analysis, _, _ = real_candidate
    result = analysis["current_alignment"]["checks"][1]["details"]["reconciliation"]
    native = result["native_source_consumption"]
    assert native["status"] == "NATIVE_FIELDS_VERIFIED_CHAIN_INCOMPLETE"
    report = next(r for r in native["reports"] if r["consumed_opening_fact"])
    assert report["terms"]["ordinary_shares"] == "1250081601"
    completed = native["opening_pending_actions"]["known_completed_actions"]
    assert completed[0]["shares"] == "2188614"
    assert completed[0]["completed_by"] == "2026-06-30"
    assert native["closing_capital"]["ordinary_shares"] is None
    comparison = native["distribution_inclusion"]["comparisons"][0]
    assert comparison["difference_cny"] == "0.01"
    assert comparison["status"] == "AMOUNT_DIFFERENCE_REQUIRES_RECONCILIATION"
    assert "REPORT_AND_IMPLEMENTATION_DIVIDEND_AMOUNT_DIFFER" in result["reason_codes"]
    assert not native["complete_action_coverage"]
    assert not native["historical_availability_proven"]
    assert not result["native_basis_semantics_verified"]
    assert not result["current_price_basis_compatible"]


@pytest.mark.parametrize("old,new", [
    ("公司代码：600519", "公司代码：600518"),
    ("单位：股", "单位：元"),
    ("办理完成注销", "尚未完成注销"),
    ("是否分配或转增 否", "是否分配或转增 是"),
    ("1,250,081,601 100", "1,250,081,602 100"),
    ("应付普通股股利", "应付优先股股利"),
])
def test_real_interim_semantic_mutations_fail_closed(real_candidate, old, new):
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    from value_investment_agent.infrastructure.filings.interim_capital_distribution import parse_interim_capital_distribution
    root, _, ledger, _ = real_candidate
    pages = extract_pages(_bound(root, ledger["opening_shares"]["evidence"][0]["binding"]))
    assert any(old in p for p in pages)
    with pytest.raises(ValueError):
        parse_interim_capital_distribution([p.replace(old, new) for p in pages], symbol="600519")


def test_real_native_report_cutoffs_and_exact_closing_date(real_candidate):
    root, analysis, ledger, now = real_candidate
    source = next(s for s in analysis["source_catalog"]
                  if s.get("sha256") == ledger["opening_shares"]["evidence"][0]["binding"]["sha256"])
    key = (source["local_path"], source["sha256"], source["location"])
    read = lambda ref: _bound(root, ref)
    # Exact report date is a dated fact, not continuity through a later quote.
    native = service._native_basis_fields(analysis, date(2026,6,30), date(2026,10,29), now,
        {key: source["source_available_at"]}, read, {}, [])
    assert native["reports"][0]["consumed_opening_fact"]
    assert native["closing_capital"]["status"] == "EXACT_CLOSING_REPORT_ANCHOR_MISSING"
    early = service._native_basis_fields(analysis, date(2026,6,30), date(2026,8,14), now,
        {key: source["source_available_at"]}, read, {}, [])
    assert not early["reports"]
    assert early["unresolved_sources"][0]["reason"] == "NATIVE_FIELD_PUBLICATION_AFTER_CUTOFF"
    future = service._native_basis_fields(analysis, date(2026,6,30), date(2026,10,29), now,
        {key: "2099-01-01T00:00:00+00:00"}, read, {}, [])
    assert not future["reports"]
    assert future["unresolved_sources"][0]["reason"] == "NATIVE_FIELD_SOURCE_UNAVAILABLE"
    wrong = deepcopy(analysis)
    wrong["official_fact_anchors"] = []
    unmatched = service._native_basis_fields(wrong, date(2026,6,30), date(2026,10,29), now,
        {key: source["source_available_at"]}, read, {}, [])
    assert not unmatched["reports"]
    assert unmatched["unresolved_sources"][0]["reason"] == "NATIVE_REPORT_NOT_MATCHED_TO_CONSUMED_OPENING_FACT"


def test_real_new_complete_window_does_not_grant_semantics_or_materiality(real_candidate):
    root, analysis, ledger, now = real_candidate
    config = json.loads((root / service.CONFIG_DIRECTORY /
        (analysis["review_binding"]["candidate_binding"]["sha256"] + ".json")).read_bytes())
    refs = config["event_observation_bindings"]
    assert len(refs) == 1
    ref = refs[0]
    observation = json.loads(_bound(root, ref).read_bytes())
    windows, scans = service._event_windows(root, analysis, refs, now, lambda r: _bound(root, r))
    assert len(scans[0].announcements) == observation["announcement_count"] > 0
    assert windows[0]["full_calendar_window_elapsed"]
    assert not windows[0]["materiality_approved"]
    sources, _ = service._event_windows(root, analysis, config["source_observation_bindings"], now,
        lambda r: _bound(root, r))
    result = service._reconcile(root, analysis, config["reconciliation_binding"], date.fromisoformat(ledger["comparison_date"]),
        windows, now, lambda r: _bound(root, r), sources)
    assert result["native_source_consumption"]["status"] == "NATIVE_FIELDS_VERIFIED_CHAIN_INCOMPLETE"
    assert not result["native_basis_semantics_verified"]
    # The later acquisition cannot be used immediately before the archived retrieval.
    with pytest.raises(ValueError):
        service._event_windows(root, analysis, [ref], datetime.fromisoformat(observation["acquired_at"]) - timedelta(seconds=1),
            lambda r: _bound(root, r))
    quote, _ = service._qualified_quote(root, analysis, config["quote_bundle_binding"], now, lambda r: _bound(root, r))
    checks, _, _, ready = service._assess(analysis, ValuationResultCodec().from_payload(analysis["valuation"]),
        quote, dict(status="QUALIFIED", reason_codes=[], explanation="TEST", bundle_binding=None,
                    native_status="TEST"), windows, scans, result)
    assert not ready and checks[3]["status"] == "BLOCKED"
    rows = checks[3]["details"]["matched_input_sources"] + checks[3]["details"]["unresolved_sources"]
    assert len(rows) == observation["announcement_count"]
    assert all(r["source_url"].startswith("https://static.cninfo.com.cn/") for r in rows)


@pytest.mark.parametrize("old,new", [
    ("单位：元", "单位：万元"),
    ("币种：人民币", "币种：美元"),
    ("项目 本期 上年度", "项目 上年度 本期"),
])
def test_real_interim_dividend_own_table_header_required(real_candidate, old, new):
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    from value_investment_agent.infrastructure.filings.interim_capital_distribution import parse_interim_capital_distribution
    root, _, ledger, _ = real_candidate
    pages = extract_pages(_bound(root, ledger["opening_shares"]["evidence"][0]["binding"]))
    # Change only the retained-earnings table on physical page 73. The other
    # RMB/yuan tables on that same page must not rescue this invalid table.
    before, separator, remainder = pages[72].partition("42、 未分配利润")
    table, boundary, after = remainder.partition("43、 营业收入和营业成本")
    assert separator and boundary and table.count(old) == 1
    pages[72] = before + separator + table.replace(old, new) + boundary + after
    with pytest.raises(ValueError, match="INTERIM_DIVIDEND_TABLE_UNIT_CURRENCY_OR_PERIOD_UNSUPPORTED"):
        parse_interim_capital_distribution(pages, symbol="600519")


def test_real_interim_dividend_current_rmb_yuan_column(real_candidate):
    from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
    from value_investment_agent.infrastructure.filings.interim_capital_distribution import parse_interim_capital_distribution
    root, _, ledger, _ = real_candidate
    pages = extract_pages(_bound(root, ledger["opening_shares"]["evidence"][0]["binding"]))
    result = parse_interim_capital_distribution(pages, symbol="600519")
    assert result["declared_ordinary_dividend_cny"] == "35032574305.20"
    assert result["declared_ordinary_dividend_cny"] != "64671799277.95"
    assert result["term_pages"]["declared_dividend"] == [73]
    assert result["period_end"] == "2026-06-30"
    assert result["parser_version"] == "interim-capital-distribution-fields-v2"


@pytest.mark.parametrize("record,ex,expected", [
    ("2020-01-01", "2020-01-02", "2"),
    ("2020-01-02", "2020-01-03", "0"),
    ("2019-12-31", "2020-01-01", "0"),
])
def test_pending_payment_keeps_ex_entitlement_in_exact_interval(reconciliation, monkeypatch, record, ex, expected):
    from value_investment_agent.infrastructure.filings import pdf_text
    case = reconciliation
    row = cash(case, in_period=True)
    row.update(record_date=record, ex_date=ex, cash_payment_date="2020-01-03")
    # TEST_ONLY extraction seam; the real ledger/source/date validators run.
    text = case["anchor"]["excerpt"] + " " + " ".join((record, ex, row["cash_payment_date"]))
    case["anchor"]["excerpt"] = text
    monkeypatch.setattr(pdf_text, "extract_pages", lambda path: [text])
    case["ledger"]["distributions"] = [row]
    result = reconcile(case)
    observed = result["distributions"][0]
    assert result["period_cash_per_share"] == expected
    assert observed["ex_entitlement_in_period"] is (expected == "2")
    assert observed["payment_pending_at_comparison"] is True
    assert observed["period_treatment"] == "PENDING_PAYMENT_REQUIRES_REVIEW"
    assert "PENDING_DISTRIBUTION_PAYMENT" in result["reason_codes"]
    inclusion_gap = "IN_PERIOD_CASH_FLOW_INCLUSION_REQUIRES_CANDIDATE_RECOMPUTATION"
    assert (inclusion_gap in result["reason_codes"]) is (expected == "2")
    assert observed["model_inclusion"] == "NOT_NATIVE_VERIFIED"
    assert observed["price_deduction_applied"] == "0"
    assert not result["current_price_basis_compatible"]
    assert case["analysis"]["valuation"]["bear_value"] == "10"


@pytest.mark.parametrize("issue,reason", [
    ("pending", "OPENING_PENDING_ACTION_CHAIN_REQUIRES_REVIEW"),
    ("unresolved", "PUBLIC_ACTION_REVIEW_UNRESOLVED: 123"),
    ("missing_action", "REVIEWED_ACTION_MISSING_LEDGER_ROW: 123"),
    ("unreviewed", "PUBLIC_ACTION_REVIEW_DOES_NOT_COVER_ALL_ANNOUNCEMENTS"),
    ("none", None),
])
def test_same_day_exempts_only_empty_interval_gaps(reconciliation, issue, reason):
    case = reconciliation
    case["ledger"].update(comparison_date="2020-01-01", closing_shares=None, opening_pending_actions=None)
    window = case["windows"][0]
    window.update(scan_to="2020-01-01", source_integrity_verified=True)
    if issue == "pending":
        case["ledger"]["opening_pending_actions"] = dict(as_of="2020-01-01",
            pending_action_ids=["TEST_ONLY_PENDING"], rationale="Explicit pending action",
            evidence=[case["anchor"]])
    elif issue != "none":
        window["acquired_at"] = case["anchor"]["available_at"]
        window["announcements"] = [dict(announcement_id="123", evidence_refs=[dict(
            **case["anchor"]["binding"], source_url=case["anchor"]["source_url"])])]
        if issue != "unreviewed":
            case["ledger"]["reviewed_documents"] = [dict(announcement_id="123",
                disposition="UNRESOLVED" if issue == "unresolved" else "SHARE_ACTION",
                rationale="Explicit review requiring resolution", evidence=[case["anchor"]])]
    ref = write(case["root"], "runtime/same-day.json", case["ledger"])
    result = service._reconcile(case["root"], case["analysis"], ref, date(2020,1,1),
        case["windows"], case["now"], lambda binding: _bound(case["root"], binding))
    assert result["native_basis_semantics_verified"] is (reason is None)
    assert result["current_price_basis_compatible"] is (reason is None)
    assert result["period_cash_coverage_complete"] is (reason is None)
    if reason:
        assert reason in result["reason_codes"]
        assert result["status"] == "PARTIAL"
    else:
        assert result["reason_codes"] == []
        assert result["status"] == "RECONCILED"
        assert result["closing_shares"] == "100"
        assert result["arithmetic_status"] == "RECONCILED"


@pytest.mark.parametrize("disposition,missing", [("SHARE_ACTION", True), ("CASH_DISTRIBUTION", False)])
def test_review_disposition_requires_ledger_row_of_same_kind(reconciliation, disposition, missing):
    case = reconciliation
    anchor = case["anchor"]
    case["windows"][0].update(acquired_at=anchor["available_at"], announcements=[dict(
        announcement_id="123", evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])])])
    case["ledger"].update(distributions=[cash(case)], reviewed_documents=[dict(
        announcement_id="123", disposition=disposition, rationale="TEST_ONLY", evidence=[anchor])])

    result = reconcile(case)

    assert ("REVIEWED_ACTION_MISSING_LEDGER_ROW: 123" in result["reason_codes"]) is missing
    assert result["current_price_basis_compatible"] is False


def test_operating_event_terms_are_research_not_materiality(reconciliation, monkeypatch):
    from value_investment_agent.infrastructure.filings import operating_event_terms
    case = reconciliation
    anchor = case["anchor"]
    monkeypatch.setattr(operating_event_terms, "parse_operating_event_terms",
        lambda pages, symbol: dict(published_date="2020-01-01",
            effective_date="2020-01-02", event_type="TEST_ONLY_OPERATING_PRICE",
            summary="TEST_ONLY source terms", action="no_order"))
    window = dict(acquired_at="2020-01-03T00:00:00+00:00",
        announcements=[dict(announcement_id="123", title="TEST_ONLY",
            published_at="2020-01-01T00:00:00+08:00",
            source_url=anchor["source_url"],
            evidence_refs=[dict(anchor["binding"], source_url=anchor["source_url"])])])
    rows = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))
    assert rows[0]["status"] == "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
    assert rows[0]["candidate_binding"] == case["analysis"]["review_binding"]["candidate_binding"]
    assert rows[0]["materiality_approved"] is False
    assert rows[0]["model_inputs_changed"] is False
    assert rows[0]["facts"][0]["terms"]["effective_date"] == "2020-01-02"
    from value_investment_agent.infrastructure.filings import pdf_text
    extracted, verified = [], []
    original_extract = pdf_text.extract_pages

    def extract_once(path):
        extracted.append(path)
        return original_extract(path)

    def verify(ref):
        verified.append(ref)
        return _bound(case["root"], ref)

    monkeypatch.setattr(pdf_text, "extract_pages", extract_once)
    cache = {}
    for _ in range(2):
        assert service._operating_events(case["analysis"], [window], case["now"],
            verify, page_cache=cache) == rows
    assert len(extracted) == 1 and len(verified) == 2
    original_path = case["root"] / anchor["binding"]["path"]
    original_bytes = original_path.read_bytes()
    try:
        original_path.write_bytes(original_bytes + b"modified")
        modified = service._operating_events(case["analysis"], [window], case["now"],
            verify, page_cache=cache)
        assert not modified[0]["facts"] and modified[0]["unresolved"]
        assert len(extracted) == 1 and len(verified) == 3
    finally:
        original_path.write_bytes(original_bytes)
    window["announcements"][0]["announcement_id"] = "999"
    rows = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))
    assert rows[0]["facts"] == []
    assert "IDENTITY_MISMATCH" in rows[0]["unresolved"][0]["reason"]
    window["acquired_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="ACQUISITION_UNAVAILABLE"):
        service._operating_events(case["analysis"], [window], case["now"],
            lambda ref: _bound(case["root"], ref))


def test_operating_event_parser_failure_is_not_no_effect(reconciliation, monkeypatch):
    from value_investment_agent.infrastructure.filings import operating_event_terms
    case = reconciliation
    anchor = case["anchor"]
    def reject(*args, **kwargs):
        raise ValueError("UNSUPPORTED_LAYOUT")
    monkeypatch.setattr(operating_event_terms, "parse_operating_event_terms", reject)
    window = dict(acquired_at="2020-01-03T00:00:00+00:00",
        announcements=[dict(announcement_id="123", title="TEST_ONLY",
            published_at="2020-01-01T00:00:00+08:00", source_url=anchor["source_url"],
            evidence_refs=[dict(anchor["binding"], source_url=anchor["source_url"])])])
    rows = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))
    assert rows[0]["status"] == "UNSUPPORTED_OR_UNRESOLVED"
    assert rows[0]["unresolved"][0]["reason"] == "UNSUPPORTED_LAYOUT"
    assert rows[0]["materiality_approved"] is False


def test_operating_event_duplicate_id_conflict_is_not_silently_deduplicated(reconciliation, monkeypatch):
    from value_investment_agent.infrastructure.filings import operating_event_terms
    case = reconciliation
    anchor = case["anchor"]
    monkeypatch.setattr(operating_event_terms, "parse_operating_event_terms",
        lambda pages, symbol: dict(published_date="2020-01-01", action="no_order"))
    event = dict(announcement_id="123", title="TEST_ONLY",
        published_at="2020-01-01T00:00:00+08:00", source_url=anchor["source_url"],
        evidence_refs=[dict(anchor["binding"], source_url=anchor["source_url"])])
    window = dict(acquired_at="2020-01-03T00:00:00+00:00", announcements=[event])
    read = lambda ref: _bound(case["root"], ref)
    assert len(service._operating_events(case["analysis"], [window, deepcopy(window)], case["now"], read)) == 1
    other = deepcopy(window)
    other["announcements"][0]["evidence_refs"][0]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="CONFLICTING_OPERATING_EVENT_IDENTITY"):
        service._operating_events(case["analysis"], [window, other], case["now"], read)


@pytest.mark.parametrize("stamp,accepted", [
    ("2020-01-01T00:00:00+08:00", True),
    ("2019-12-31T16:00:00+00:00", True),
    ("2020-01-01T01:00:01+08:00", False),
    ("2020-01-01T00:00:00", False),
])
def test_operating_event_requires_local_day_and_not_after_capture(reconciliation, monkeypatch, stamp, accepted):
    from value_investment_agent.infrastructure.filings import operating_event_terms
    case = reconciliation
    anchor = case["anchor"]
    monkeypatch.setattr(operating_event_terms, "parse_operating_event_terms",
        lambda pages, symbol: dict(published_date="2020-01-01", action="no_order"))
    window = dict(acquired_at="2019-12-31T17:00:00+00:00",
        announcements=[dict(announcement_id="123", title="TEST_ONLY",
            published_at=stamp, source_url=anchor["source_url"],
            evidence_refs=[dict(anchor["binding"], source_url=anchor["source_url"])])])
    rows=service._operating_events(case["analysis"], [window],
        datetime.fromisoformat("2019-12-31T18:00:00+00:00"), lambda ref: _bound(case["root"], ref))
    if accepted:
        assert rows[0]["status"] == "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
    else:
        assert rows[0]["unresolved"][0]["reason"] == "OPERATING_EVENT_PUBLICATION_MISMATCH"


@pytest.mark.parametrize("kind", ["standard", "excluded", "unknown", "full_annual", "full_interim", "full_wrong_year"])
def test_opening_chain_maps_only_supported_distribution_object_contracts(kind):
    analysis = dict(valuation_date="2020-06-30", consumed_operating_inputs=dict(ordinary_shares="100"),
        review_binding=dict(candidate_binding=dict(path="TEST_ONLY", sha256="a"*64)))
    terms = dict(currency="CNY", annual_cash_per_share="2", annual_total_cash_cny="200",
        eligible_distribution_shares="100", annual_distribution_year="2019")
    rows=[dict(facts=[dict(binding=dict(path="TEST_ONLY",sha256="b"*64),
        terms=dict(published_date="2020-06-01",event_type="TEST_ONLY_ADJUSTMENT",terms=terms))])]
    native=dict(currency="CNY",cash_per_share="2",total_gross_cash="200",
        published_date="2020-06-10",ex_date="2020-06-20",cash_payment_date="2020-06-20")
    if kind=="standard":
        native.update(parser_version="sse-explicit-cash-implementation-body-v1",
            event_kind="EXPLICIT_NONDIFFERENTIAL_CASH_ONLY_IMPLEMENTATION", total_shares="100")
    else:
        native.update(parser_version="sse-repurchase-excluded-gross-cash-scheme-v1" if kind=="excluded" else "UNKNOWN",
            eligible_distribution_shares="100", annual_distribution_year="2019")
    if kind.startswith("full_"):
        native.update(parser_version="sse-full-share-cross-page-cash-scheme-v1",
            distribution_period="中期" if kind == "full_interim" else "年度",
            distribution_year="2018" if kind == "full_wrong_year" else "2019",
            body_terms_reconciled=True)
    reconciliation=dict(distributions=[dict(id="TEST_ONLY_CASH",native_terms=native)])
    result=service._opening_chain_research(analysis,rows,reconciliation)
    assert result["distribution_links"][0]["status"] == (
        "TERMS_NOT_MATCHED" if kind in {"unknown", "full_interim", "full_wrong_year"} else "MATCHED_PREVALUATION_IMPLEMENTATION_TERMS")
    assert not result["comparison_date_capital_proven"]
    native["total_gross_cash"]="201"
    changed=service._opening_chain_research(analysis,rows,reconciliation)
    assert changed["distribution_links"][0]["status"]=="TERMS_NOT_MATCHED"


def test_buyback_differences_do_not_cross_plan_windows_or_ambiguous_dates():
    def point(through, shares, paid, plan_end="2026-12-31"):
        return dict(plan_start="2026-01-01", plan_end=plan_end, through=through,
                    shares=shares, paid_cny=Decimal(paid), binding={"path": through})

    first = point("2026-02-01", 10, "100.25")
    second = point("2026-03-01", 15, "145.75")
    other_plan = point("2026-04-01", 99, "999", "2026-11-30")
    result = service._buyback_checkpoint_deltas([second, other_plan, first])
    assert len(result) == 1
    assert result[0]["purchase_share_delta"] == 5
    assert result[0]["disclosed_cash_delta_cny"] == "45.50"
    assert result[0]["before_binding"] == first["binding"]
    assert result[0]["after_binding"] == second["binding"]
    assert service._buyback_checkpoint_deltas([first, second, point("2026-03-01", 12, "120")]) == []
    assert service._buyback_checkpoint_deltas([first, point("2026-03-01", 5, "95")]) == []


def test_basis_followup_keeps_no_proposal_distinct_from_revocation(reconciliation):
    case = reconciliation
    report = dict(status="NATIVE_REPORT_FIELDS_VERIFIED", binding=case["anchor"]["binding"],
        source_url=case["anchor"]["source_url"], source_available_at=case["anchor"]["available_at"],
        published_date="2020-01-02", consumed_opening_fact=True,
        terms=dict(symbol="600519",period_end="2020-01-01",ordinary_shares="100",
            interim_proposal_state="NO_INTERIM_DISTRIBUTION_OR_CAPITALIZATION_PROPOSED",
            subsequent_capital_state="REPORT_SUBSEQUENT_PER_SHARE_IMPACT_SECTION_NOT_APPLICABLE",
            term_pages=dict(proposal=[1])))
    rec=dict(native_source_consumption=dict(reports=[report]))
    opening=dict(outstanding_authorizations=[dict(id="TEST_ONLY")])
    result=service._basis_followup(case["analysis"],rec,opening,[],date(2020,1,3))
    assert result["latest_capital_checkpoint"]["as_of"]=="2020-01-01"
    assert result["uncovered_capital_interval"]==dict(after="2020-01-01",through="2020-01-03")
    assert result["authorization_followup_required"] is True
    assert result["interim_report_followups"][0]["authorization_resolved"] is False
    assert not result["current_comparison_granted"]
    assert not result["complete_effective_action_coverage"]
    assert result["candidate_binding"]==case["analysis"]["review_binding"]["candidate_binding"]
    report["published_date"]="2020-01-04"
    assert service._basis_followup(case["analysis"],rec,opening,[],date(2020,1,3))["capital_checkpoints"]==[]
    report["published_date"]="2020-01-02"
    report["terms"]["symbol"]="000001"
    assert service._basis_followup(case["analysis"],rec,opening,[],date(2020,1,3))["capital_checkpoints"]==[]


def test_basis_empty_retrieval_cannot_prove_capital_or_zero_dividend(reconciliation):
    case=reconciliation
    window=dict(source_integrity_verified=True, scan_from="2020-01-01",scan_to="2020-01-02",
        acquired_at="2020-01-03T00:00:00+00:00",announcement_count=0,
        coverage_status="COMPLETE",observation_binding=case["anchor"]["binding"])
    result=service._basis_followup(case["analysis"],None,dict(outstanding_authorizations=[]),
        [window],date(2020,1,2))
    assert result["status"]=="NO_SUPPORTED_CHECKPOINT"
    assert result["latest_capital_checkpoint"] is None
    assert not result["complete_effective_action_coverage"]
    assert not result["current_comparison_granted"]


def test_basis_followup_classifies_existing_share_purchases_without_granting_continuity(reconciliation):
    case = reconciliation
    event = dict(announcement_id="TEST_ONLY_EVENT", title="完成股票购买的公告",
        published_at="2020-01-02T08:00:00+08:00", facts=[dict(
            binding=case["anchor"]["binding"], terms=dict(
                event_type="PLAN_SECONDARY_MARKET_SHARE_PURCHASE_COMPLETED",
                terms=dict(issued_share_effect="NO_ISSUANCE_OR_CANCELLATION_IN_THIS_PURCHASE_EVENT")))])
    result = service._basis_followup(case["analysis"], None,
        dict(outstanding_authorizations=[]), [], date(2020, 1, 3), [event])
    classified = result["capital_event_classifications"][0]
    assert classified["classification"] == "EXISTING_SHARE_TRANSACTION_NO_ISSUED_SHARE_CHANGE"
    assert classified["window_completeness_granted"] is False
    assert result["complete_effective_action_coverage"] is False
    assert result["current_comparison_granted"] is False


def test_event_impact_binds_consumed_years_not_profit_uplift(reconciliation):
    from value_investment_agent.application.research.candidate_event_impact import build_candidate_event_impact
    a=reconciliation["analysis"]
    candidate=a["review_binding"]["candidate_binding"]
    a["joint_capital_review"]["economic_path"].update(candidate_binding=candidate,
        scenarios=[dict(scenario="base",years=[dict(model_year=1,steps=[
            dict(id="revenue",status="available",unit="CNY",classification="CONDITIONAL_CALCULATION",
                values=dict(revenue="100",cost="20"))])])])
    fact=dict(binding=reconciliation["anchor"]["binding"],source_url=reconciliation["anchor"]["source_url"],
        source_available_at=reconciliation["anchor"]["available_at"],
        terms=dict(event_type="OPERATING_PRICE_CHANGE",affected_model_fields=["revenue","profit"],
            terms=dict(retail_price=dict(before="100",after="110",unit="CNY/bottle"),
                sales_contract_price=dict(before="80",after="90",unit="CNY/bottle"))))
    event=dict(status="SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW",
        candidate_binding=candidate,input_descriptor_sha256=a["input_descriptor_sha256"],
        announcement_id="TEST_ONLY",title="TEST_ONLY price",published_at="2020-01-02",facts=[fact])
    before=deepcopy(a)
    result=build_candidate_event_impact(a,[event])
    row=result["items"][0]
    assert [x["relative_change"] for x in row["derived_price_changes"]]==["0.1","0.125"]
    assert row["consumed_model_values"][0]["value"]=="100"
    assert row["unmapped_model_fields"]==["profit"]
    assert row["quantified_profit_effect"] is None
    assert row["model_inputs_changed"] is False
    assert not result["materiality_approved"]
    assert a==before
    event["input_descriptor_sha256"]="f"*64
    assert build_candidate_event_impact(a,[event])["items"]==[]
    event["input_descriptor_sha256"]=a["input_descriptor_sha256"]
    fact["terms"]["terms"]["retail_price"]["before"]="NaN"
    with pytest.raises(ValueError,match="NONPOSITIVE_OR_NONFINITE"):
        build_candidate_event_impact(a,[event])


def test_event_review_drafts_do_not_approve_materiality(reconciliation):
    from value_investment_agent.application.research.candidate_event_impact import build_candidate_event_impact
    a=reconciliation["analysis"]
    candidate=a["review_binding"]["candidate_binding"]
    a["joint_capital_review"]["economic_path"].update(candidate_binding=candidate,
        scenarios=[dict(scenario="base", years=[dict(model_year=1, steps=[
            dict(id="access", status="available", unit="CNY",
                 values=dict(opening_cash="1000", closing_cash="900"))])])])
    for kind,status in [
        ("ACCOUNTING_POLICY_IMPACT_STATEMENT","ISSUER_NO_MATERIAL_IMPACT_REQUIRES_REVIEW"),
        ("INTERNAL_ASSET_TRANSFER_RESOLUTION","CASH_ACCESS_AND_CAPITAL_REVIEW_REQUIRED"),
        ("REPORTED_BUYBACK_PROGRESS","BUYBACK_CASH_AND_SHARE_BASIS_REVIEW_REQUIRED")]:
        event=dict(status="SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW",
            candidate_binding=candidate,input_descriptor_sha256=a["input_descriptor_sha256"],
            announcement_id="TEST_ONLY",title="TEST_ONLY",published_at="2020-01-02",
            facts=[dict(binding=reconciliation["anchor"]["binding"],source_url=reconciliation["anchor"]["source_url"],
                source_available_at=reconciliation["anchor"]["available_at"],terms=dict(event_type=kind,
                affected_model_fields=["cash", "ordinary_shares"] if kind == "REPORTED_BUYBACK_PROGRESS"
                else ["profit"],terms={}))])
        result=build_candidate_event_impact(a,[event])
        assert result["items"][0]["status"]==status
        if kind == "REPORTED_BUYBACK_PROGRESS":
            references = result["items"][0]["consumed_model_values"]
            assert [r["field"] for r in references] == ["opening_cash", "closing_cash", "ordinary_shares"]
            assert references[-1]["classification"] == "CANDIDATE_VALUATION_SHARE_BASIS_NOT_CURRENT"
            assert not result["items"][0]["unmapped_model_fields"]
        assert result["items"][0]["quantified_profit_effect"] is None
        assert not result["materiality_approved"]


def test_shenzhen_clearing_date_does_not_verify_issuer_direct_payment():
    from value_investment_agent.infrastructure.filings.szse_cash_entitlement import (
        parse_mixed_cash_entitlement,
    )

    pages = [
        "证券代码：000001 证券简称：样本 2025年度分红派息实施公告"
        "样本股份有限公司。现金分红金额为441.71元（含税）。"
        "公司总股本由110股变动至100股。"
        "本次利润分配不送红股，不以资本公积金转增股本。",
        "二、本次实施的利润分配方案公司2025年度利润分配方案以固定总额的方式分配："
        "以公司现有总股本剔除已回购股份0股后的100股为基数，"
        "向全体股东每10股派44.171215元人民币现金（含税；其他说明）。"
        "三、分红派息日期1.股权登记日：2026年8月27日。"
        "2.除权除息日：2026年8月28日。四、分红派息对象",
        "五、分配方法1.公司此次委托中国结算深圳分公司代派的A股股东现金红利"
        "将于2026年8月28日通过股东托管证券公司（或其他托管机构）直接划入其资金账户。"
        "2.以下A股股东的现金红利由我公司自行派发：",
        "董事会2026年8月20日",
    ]
    result = parse_mixed_cash_entitlement(pages, symbol="000001")
    assert result["cash_per_share"] == "4.4171215"
    assert result["clearing_house_scheduled_payment_date"] == "2026-08-28"
    assert result["issuer_direct_payment_date"] is None
    assert "cash_payment_date" not in result
    with pytest.raises(ValueError):
        parse_mixed_cash_entitlement(pages, symbol="000002")
    with pytest.raises(ValueError):
        parse_mixed_cash_entitlement([*pages, "更正"], symbol="000001")


def test_mixed_payment_ledger_does_not_claim_issuer_payment(reconciliation, monkeypatch):
    from value_investment_agent.infrastructure.filings import szse_cash_entitlement

    case = reconciliation
    case["ledger"]["distributions"] = [cash(case, in_period=True)]
    terms = dict(cash_per_share="2", record_date="2020-01-01", ex_date="2020-01-02",
                 published_date="2020-01-01", clearing_house_scheduled_payment_date="2020-01-02",
                 issuer_direct_payment_date=None, cash_payment_status="ISSUER_DIRECT_PAYMENT_UNVERIFIED")
    monkeypatch.setattr(szse_cash_entitlement, "parse_mixed_cash_entitlement", lambda *a, **k: terms)
    anchor = case["anchor"]
    case["windows"][0].update(source_integrity_verified=True, acquired_at=anchor["available_at"],
        announcements=[dict(announcement_id="123", title="TEST_ONLY年度分红派息实施公告",
            published_at="2019-12-31T16:00:00+00:00",
            evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])])])
    result = reconcile(case)
    observed, = result["covered_cash_implementations"]
    assert observed["status"] == "ENTITLEMENT_MATCHED_PAYMENT_UNRESOLVED"
    assert observed["matched_ledger_ids"] == ["TEST_ONLY_CASH"]
    row = result["distributions"][0]
    assert row["field_semantics_status"] == "NATIVE_ENTITLEMENT_ONLY_VERIFIED"
    assert row["verified_cash_per_share"] == "2"
    assert row["period_treatment"] == "MIXED_PAYMENT_SCOPE_REQUIRES_REVIEW"
    assert row["payment_pending_at_comparison"] is None
    assert row["native_entitlement_only"]["issuer_direct_payment_date"] is None
    assert row["price_deduction_applied"] == "0"
    assert "ISSUER_DIRECT_PAYMENT_UNVERIFIED" in result["reason_codes"]
    assert not result["current_price_basis_compatible"]
    terms["clearing_house_scheduled_payment_date"] = "2020-01-03"
    with pytest.raises(ValueError, match="CASH_LEDGER_DIFFERS_FROM_NATIVE_IMPLEMENTATION_FIELDS"):
        reconcile(case)


@pytest.mark.parametrize("net_change", ["0", "-5"])
def test_unlock_notice_is_not_effective_share_reduction(reconciliation, monkeypatch, net_change):
    from value_investment_agent.infrastructure.filings import native_capital_observation_v1

    case = reconciliation
    source = dict(case["anchor"]["binding"],
                  source_url="https://static.cninfo.com.cn/finalpage/2020-01-02/123.PDF")
    monkeypatch.setattr(native_capital_observation_v1, "parse_native_capital_observation",
        lambda pages, symbol: dict(kind="share_unlock_notice", status="VERIFIED",
            observation_date="2020-01-02", share_effective_date="2020-01-06",
            net_share_change=net_change, historical_cancelled_shares="5"))
    window = dict(acquired_at="2020-01-03T00:00:00+08:00", announcements=[dict(
        announcement_id="123", title="TEST_ONLY 解除限售股份上市流通的提示性公告",
        published_at="2020-01-02T00:00:00+08:00", source_url=source["source_url"], evidence_refs=[source])])
    row, = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))
    assert not row["materiality_approved"] and not row["model_inputs_changed"]
    if net_change == "0":
        terms = row["facts"][0]["terms"]
        assert terms["event_type"] == "REPORTED_SHARE_UNLOCK_NOTICE"
        assert terms["effective_date"] is None
        assert terms["planned_implementation_date"] == "2020-01-06"
        assert terms["affected_model_fields"] == []
        from value_investment_agent.application.research.candidate_event_impact import build_candidate_event_impact

        analysis = case["analysis"]
        analysis["joint_capital_review"]["economic_path"]["candidate_binding"] = row["candidate_binding"]
        draft = build_candidate_event_impact(analysis, [row])
        impact, = draft["items"]
        assert impact["status"] == "SHARE_CLASS_TRANSFER_FOLLOWUP_REQUIRED"
        assert impact["consumed_model_values"] == []
        assert not draft["materiality_approved"] and not draft["model_validity_granted"]
    else:
        assert not row["facts"]
        assert row["unresolved"][0]["reason"] == "UNLOCK_ORIGINAL_NOT_VERIFIED_FOR_EVENT"


@pytest.mark.parametrize("report_end,verified", [("2020-09-30", True), ("2021-09-30", False)])
@pytest.mark.parametrize("title", ["2020年第三季度报告", "2020年三季度报告"])
def test_quarter_event_keeps_candidate_review_separate(reconciliation, monkeypatch, report_end, verified, title):
    from value_investment_agent.infrastructure.filings import native_capital_observation_v1

    case = reconciliation
    source = dict(case["anchor"]["binding"], source_url="https://static.cninfo.com.cn/finalpage/2020-10-29/123.PDF")
    monkeypatch.setattr(native_capital_observation_v1, "parse_native_capital_observation",
        lambda pages, symbol: dict(kind="q3", financial_update=dict(status="VERIFIED",
            period_start=report_end[:4] + "-01-01", period_end=report_end,
            fields=dict(revenue_cny={"value": "200"}, parent_profit_cny={"value": "20"}))))
    window = dict(acquired_at="2020-10-30T00:00:00+08:00", announcements=[dict(
        announcement_id="123", title="TEST_ONLY " + title,
        published_at="2020-10-29T00:00:00+08:00", source_url=source["source_url"], evidence_refs=[source])])
    row, = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))
    assert not row["materiality_approved"] and not row["model_inputs_changed"]
    if verified:
        assert row["facts"][0]["terms"]["event_type"] == "REPORTED_QUARTERLY_FINANCIAL_UPDATE"
        assert row["facts"][0]["terms"]["effective_date"] is None
        from value_investment_agent.application.research.candidate_event_impact import build_candidate_event_impact

        analysis = case["analysis"]
        descriptor = analysis["input_descriptor_sha256"]
        analysis["source_native_cash_review"] = dict(candidate_binding=row["candidate_binding"],
            model_context=dict(input_descriptor_sha256=descriptor))
        draft = build_candidate_event_impact(analysis, [row])
        impact, = draft["items"]
        assert impact["status"] == "RECALCULATION_REVIEW_REQUIRED"
        assert impact["consumed_model_values"] == []
        assert impact["quantified_profit_effect"] is None
        analysis["source_native_cash_review"]["model_context"]["input_descriptor_sha256"] = "b" * 64
        assert not build_candidate_event_impact(analysis, [row])["items"]
    else:
        assert not row["facts"]
        assert row["unresolved"][0]["reason"] == "QUARTERLY_ORIGINAL_NOT_VERIFIED_FOR_EVENT"



def test_szse_interim_entitlement_reconciles_declared_total_and_payment_scope():
    from value_investment_agent.infrastructure.filings.szse_cash_entitlement import (
        parse_mixed_cash_entitlement,
    )

    pages = [
        "证券代码：000001 证券简称：示例 2025 年中期分红派息实施公告"
        "以公司现有总股本100股为基数，向全体股东每10股派1.25元人民币现金"
        "（含税），现金分红金额12.50元（含税）"
        "本次利润分配公司不送红股，不进行资本公积金转增股本。",
        "现有总股本剔除已回购股份0股后的100股为基数，"
        "向全体股东每10股派1.25元人民币现金（含税；扣税条款）"
        "股权登记日：2026年1月29日。除权除息日：2026年1月30日。",
        "代派的A股股东现金红利将于2026年1月30日通过托管机构划入。"
        "以下A股股东的现金红利由我公司自行派发：董事会2026年1月24日",
    ]
    result = parse_mixed_cash_entitlement(pages, symbol="000001")
    assert result["cash_per_share"] == "0.125"
    assert result["gross_declared_cash_cny"] == "12.50"
    assert result["fiscal_year"] == 2025
    assert result["ex_date"] == "2026-01-30"
    assert result["issuer_direct_payment_date"] is None
    with pytest.raises(ValueError, match="DOES_NOT_RECONCILE"):
        parse_mixed_cash_entitlement(
            [pages[0].replace("12.50", "12.51"), *pages[1:]], symbol="000001"
        )
    with pytest.raises(ValueError, match="DATE_ORDER_INVALID"):
        parse_mixed_cash_entitlement(
            [*pages[:2], pages[2].replace("1月30日", "1月28日")], symbol="000001"
        )

@pytest.mark.parametrize("confirmed_quantity,expected", [
    ("2", "MATCHED_COMPLETED_BEFORE_VALUATION"),
    ("3", "CANCELLATION_NOT_UNIQUELY_RECONCILED"),
])
def test_opening_purchase_link_needs_exact_later_confirmation(reconciliation, confirmed_quantity, expected):
    purchase = dict(binding={"sha256": "a" * 64}, terms=dict(published_date="2019-12-29",
        terms=dict(purchase_state="COMPLETED", cancellation_state="SCHEDULED_UNCONFIRMED",
            through="2019-12-28", scheduled_cancellation_date="2019-12-30",
            cumulative_purchased_shares=2, cumulative_paid_cny="20", planned_post_cancellation_shares=100)))
    confirmation = dict(binding={"sha256": "b" * 64}, terms=dict(published_date="2019-12-31",
        terms=dict(completion_notice_on="2019-12-29", confirmed_cancellation_date="2019-12-30",
            capital_as_of="2019-12-31", cancelled_shares=confirmed_quantity, issued_shares="100", treasury_shares="0")))
    result = service._opening_chain_research(reconciliation["analysis"],
        [{"facts": [purchase, confirmation]}], None)
    assert result["purchase_links"][0]["status"] == expected
    assert (result["purchase_links"][0]["cancellation_binding"] == confirmation["binding"]) == (confirmed_quantity == "2")
    assert not result["complete_opening_action_coverage"]
    assert not result["comparison_date_capital_proven"]


@pytest.mark.parametrize("signed_date,fiscal_year", [("2020-10-29", "2019"),
    ("2020-10-28", "2019"), ("2020-10-29", "2018")])
def test_dividend_schedule_does_not_admit_payment(reconciliation, monkeypatch, signed_date, fiscal_year):
    from value_investment_agent.infrastructure.filings import native_capital_observation_v1

    case = reconciliation
    source = dict(case["anchor"]["binding"],
                  source_url="https://static.cninfo.com.cn/finalpage/2020-10-29/123.PDF")
    monkeypatch.setattr(native_capital_observation_v1, "parse_native_capital_observation",
        lambda pages, symbol: dict(kind="dividend_implementation", status="VERIFIED",
            observation_date=signed_date, dividend_fiscal_year=fiscal_year,
            record_date="2020-11-02", ex_date="2020-11-03",
            dividend_per_10_shares_cny="10.50", payment_completion_state="UNKNOWN"))
    window = dict(acquired_at="2020-10-30T00:00:00+08:00", announcements=[dict(
        announcement_id="123", title="2019年度分红派息实施公告",
        published_at="2020-10-29T00:00:00+08:00", source_url=source["source_url"], evidence_refs=[source])])
    row, = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))
    assert not row["materiality_approved"] and not row["model_inputs_changed"]
    if signed_date != "2020-10-29" or fiscal_year != "2019":
        assert not row["facts"]
        assert row["unresolved"][0]["reason"] == "DIVIDEND_ORIGINAL_NOT_VERIFIED_FOR_EVENT"
        return
    fact, = row["facts"]
    terms = fact["terms"]
    assert terms["event_type"] == "REPORTED_ANNUAL_DIVIDEND_IMPLEMENTATION_SCHEDULE"
    assert terms["effective_date"] is None
    assert terms["terms"]["payment_completion_state"] == "UNKNOWN"
    assert terms["action"] == "no_order"


@pytest.mark.parametrize(("first_end", "required_end", "covered"), [
    ("2026-11-17", "2026-11-18", True),
    ("2026-11-16", "2026-11-18", False),
    ("2026-11-17", "2026-11-19", False),
])
def test_publication_window_can_use_adjacent_archives(first_end, required_end, covered):
    windows = [
        {"scan_from": "2026-11-18", "scan_to": "2026-11-18"},
        {"scan_from": "2025-12-31", "scan_to": first_end},
    ]
    assert service._continuous_publication_window(
        windows, date(2025, 12, 31), date.fromisoformat(required_end),
    ) is covered


@pytest.mark.parametrize("observed_date,lower,upper,expected", [
    ("2020-01-02", 95, 104, True),
    ("2020-01-02", 101, 110, False),
    ("2020-01-01", 95, 104, None),
])
def test_rounded_capital_never_supplies_exact_closing_shares(
    reconciliation, monkeypatch, observed_date, lower, upper, expected,
):
    from value_investment_agent.infrastructure.filings import sse_current_capital_snapshot_v1 as sse

    case = reconciliation
    snapshot = write(case["root"], "runtime/rounded.json", {"scope": "TEST_ONLY"})
    case["ledger"].update(closing_shares=None, rounded_capital_snapshot_binding=snapshot)

    def replay(*, receipt_path, symbol, as_of):
        assert receipt_path == case["root"] / snapshot["path"]
        assert symbol == case["analysis"]["symbol"] and as_of == case["now"]
        return dict(trade_date=observed_date, lower_bound_shares=lower,
                    upper_bound_shares=upper, exact_share_count=False)

    monkeypatch.setattr(sse, "replay_sse_current_capital_snapshot", replay)
    if expected is None:
        with pytest.raises(ValueError, match="ROUNDED_CAPITAL_SNAPSHOT_COMPARISON_DATE_MISMATCH"):
            reconcile(case)
        return
    result = reconcile(case)
    assert result["rounded_capital_observation"]["rollforward_within_range"] is expected
    assert result["closing_shares"] is None
    assert not result["current_price_basis_compatible"]
    assert ("ROUNDED_CAPITAL_SNAPSHOT_CONFLICTS_WITH_ROLLFORWARD" in result["reason_codes"]) is not expected


def test_sse_closing_value_corroboration_requires_same_day_and_integral_shares(tmp_path):
    packet = {"code": "600887", "date": 20261119, "time": 162900,
              "snap": ["TEST_ONLY", 32.91, 32.39, None, None, 208167619550.97, "E110    "]}
    ref = write(tmp_path, "runtime/TEST_ONLY-sse-close.json", packet)
    binding = dict(
        source_url="https://yunhq.sse.com.cn:32042/v1/sh1/snap/600887"
                   "?select=name%2Clast%2Cprev_close%2CtotalShares%2CnonRestrictedShares%2CtotalValue%2Ctradephase",
        observed_at="2026-11-19T21:00:00+08:00", response_binding=ref,
    )
    now = datetime.fromisoformat("2026-11-19T21:01:00+08:00")
    options = dict(symbol="600887", comparison_date=date(2026, 11, 19), now=now,
                   read=lambda ref: _bound(tmp_path, ref))
    result = service._market_value_share_corroboration(binding, **options)
    assert result["share_count"] == 6325360667
    assert not result["exact_registry_count"] and not result["continuity_verified"]
    with pytest.raises(ValueError, match="SSE_CLOSING_VALUE_SOURCE_OR_CLOCK_INVALID"):
        service._market_value_share_corroboration(
            binding, **{**options, "comparison_date": date(2026, 11, 18)},
        )
    packet["snap"][5] = 208167619550.98
    binding["response_binding"] = write(tmp_path, "runtime/TEST_ONLY-fractional.json", packet)
    with pytest.raises(ValueError, match="SSE_CLOSING_VALUE_SHARE_COUNT_NOT_INTEGRAL"):
        service._market_value_share_corroboration(binding, **options)


@pytest.mark.parametrize("conflict", [False, True])
def test_overlapping_action_windows_require_same_announcement_original(reconciliation, conflict):
    root = reconciliation["root"]
    url = "https://static.cninfo.com.cn/finalpage/2020-01-02/123.PDF"
    original = dict(**write(root, "runtime/first.pdf", {"1": "TEST_ONLY original"}), source_url=url)
    other = dict(**write(root, "runtime/second.pdf",
                         {"1": "TEST_ONLY changed" if conflict else "TEST_ONLY original"}), source_url=url)
    window = reconciliation["windows"][0]
    window["acquired_at"] = reconciliation["now"].isoformat()
    window["announcements"] = [dict(announcement_id="123", evidence_refs=[original])]
    replay = deepcopy(window)
    replay["announcements"][0]["evidence_refs"] = [other]
    reconciliation["windows"].append(replay)
    if conflict:
        with pytest.raises(ValueError, match="PUBLIC_ACTION_ANNOUNCEMENT_ORIGINAL_CONFLICT"):
            reconcile(reconciliation)
    else:
        result = reconcile(reconciliation)
        assert "PUBLIC_ACTION_REVIEW_DOES_NOT_COVER_ALL_ANNOUNCEMENTS" in result["reason_codes"]


@pytest.mark.parametrize("payment,outside", [("2020-01-01", True), ("2020-01-02", False)])
def test_opening_dividend_schedule_does_not_claim_receipt(reconciliation, payment, outside):
    rows = [{"facts": [{"binding": reconciliation["anchor"]["binding"],
        "terms": {"event_type": "PREVALUATION_DISTRIBUTION_SCHEDULE",
                  "published_date": "2019-12-31", "terms": {"cash_per_share": "0.48",
                  "ex_date": "2020-01-01", "cash_payment_date": payment}}}]}]
    result = service._opening_chain_research(reconciliation["analysis"], rows, None)
    schedule, = result["prevaluation_distribution_schedules"]
    assert schedule["outside_comparison_interval"] is outside
    assert schedule["cash_receipt_proven"] is False
    assert result["complete_opening_action_coverage"] is False


@pytest.mark.parametrize("stamp,rejected", [
    ("2019-12-31T16:00:01+00:00", False),
    ("2019-12-31T15:59:59+00:00", True),
])
def test_reconciliation_uses_exchange_local_day_for_publication(reconciliation, stamp, rejected):
    assert "/2020-01-01/" in reconciliation["anchor"]["source_url"]
    reconciliation["anchor"]["available_at"] = stamp
    reconciliation["analysis"]["source_catalog"][0]["source_available_at"] = stamp
    if rejected:
        with pytest.raises(ValueError, match="OFFICIAL_RECONCILIATION_SOURCE_UNAVAILABLE"):
            reconcile(reconciliation)
    else:
        result = reconcile(reconciliation)
        assert result["arithmetic_status"] == "RECONCILED"
        assert not result["current_price_basis_compatible"]


@pytest.mark.parametrize("row_count", [0, 1, 2])
def test_covered_cash_original_requires_exactly_one_ledger_row(reconciliation, monkeypatch, row_count):
    case = reconciliation
    anchor = case["anchor"]
    case["windows"][0].update(source_integrity_verified=True, acquired_at=anchor["available_at"],
        announcements=[dict(announcement_id="123", title="TEST_ONLY权益分派实施公告",
            published_at="2019-12-31T16:00:00+00:00",
            evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])])])
    case["ledger"]["distributions"] = [
        dict(cash(case, in_period=True), id=f"TEST_ONLY_CASH_{i}") for i in range(row_count)
    ]
    terms = dict(published_date="2020-01-01", record_date="2020-01-01",
        ex_date="2020-01-02", cash_payment_date="2020-01-02",
        cash_per_share="2", total_gross_cash="200")
    monkeypatch.setattr(service, "_cash_terms", lambda pages, symbol: terms)

    result = reconcile(case)

    observed, = result["covered_cash_implementations"]
    assert observed["terms"] == terms
    assert len(observed["matched_ledger_ids"]) == row_count
    assert observed["status"] == ("MATCHED" if row_count == 1 else "LEDGER_MISMATCH")
    assert ("COVERED_CASH_IMPLEMENTATION_REQUIRES_UNIQUE_LEDGER_ROW: 123" in
            result["reason_codes"]) == (row_count != 1)
    assert result["period_cash_coverage_complete"] is False


@pytest.mark.parametrize("suffix", ["（修订版）", "（已取消）"])
@pytest.mark.parametrize("notice_title", ["权益分派实施公告", "利润分配实施公告", "现金分红实施公告"])
def test_covered_cash_notice_variants_require_lineage_resolution(reconciliation, suffix, notice_title):
    case = reconciliation
    anchor = case["anchor"]
    case["windows"][0].update(source_integrity_verified=True, acquired_at=anchor["available_at"],
        announcements=[dict(announcement_id="123", title="TEST_ONLY" + notice_title + suffix,
            evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])])])

    result = reconcile(case)

    assert result["covered_cash_implementations"] == [
        dict(announcement_id="123", status="LINEAGE_UNRESOLVED")
    ]
    assert "COVERED_CASH_IMPLEMENTATION_LINEAGE_UNRESOLVED: 123" in result["reason_codes"]
    assert not result["current_price_basis_compatible"]

@pytest.mark.parametrize(("effective", "expects_mismatch"), [
    ("2020-01-02", True), ("2020-01-01", False),
])
def test_covered_cancellation_cannot_be_omitted(reconciliation, monkeypatch, effective, expects_mismatch):
    from value_investment_agent.infrastructure.filings import opening_action_terms

    case = reconciliation
    anchor = case["anchor"]
    case["windows"][0].update(source_integrity_verified=True, acquired_at=anchor["available_at"],
        announcements=[dict(announcement_id="123", title="TEST_ONLY完成回购注销公告",
            published_at="2020-01-01T16:00:00+00:00",
            evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])])])
    monkeypatch.setattr(opening_action_terms, "parse_opening_action_terms", lambda pages, symbol: dict(
        terms=dict(confirmed_cancellation_date=effective), published_date="2020-01-02"))

    result = reconcile(case)

    assert ("COVERED_CANCELLATION_REQUIRES_UNIQUE_LEDGER_ROW: 123" in result["reason_codes"]
            ) is expects_mismatch
    assert result["current_price_basis_compatible"] is False
    assert [row["status"] for row in result["covered_share_cancellations"]] == (
        ["LEDGER_MISMATCH"] if expects_mismatch else [])


def test_dividend_adjustment_without_cancellation_is_not_a_share_action(reconciliation):
    case = reconciliation
    anchor = case["anchor"]
    case["windows"][0].update(source_integrity_verified=True, acquired_at=anchor["available_at"],
        announcements=[dict(announcement_id="123", title="TEST_ONLY调整年度利润分配方案每股分红金额的公告",
            published_at="2020-01-01T16:00:00+00:00",
            evidence_refs=[dict(**anchor["binding"], source_url=anchor["source_url"])])])

    result = reconcile(case)

    assert result["covered_share_cancellations"] == []
    assert not any(code.startswith("COVERED_CANCELLATION") for code in result["reason_codes"])
    assert not result["current_price_basis_compatible"]


@pytest.mark.parametrize("matches_original_title", [True, False])
def test_interim_distribution_schedule_is_not_payment(reconciliation, monkeypatch, matches_original_title):
    from value_investment_agent.infrastructure.filings import pdf_text

    case = reconciliation
    source = dict(case["anchor"]["binding"],
                  source_url="https://static.cninfo.com.cn/finalpage/2020-01-02/123.PDF")
    heading = "中期权益分派实施公告" if matches_original_title else "中期利润分配预案的公告"
    monkeypatch.setattr(pdf_text, "extract_pages", lambda path: [heading])
    monkeypatch.setattr(service, "_cash_terms", lambda pages, symbol: dict(
        published_date="2020-01-02", cash_per_share="0.42", cash_payment_date="2020-01-08"))
    window = dict(acquired_at="2020-01-03T00:00:00+08:00", announcements=[dict(
        announcement_id="123", title="TEST_ONLY 中期权益分派实施公告",
        published_at="2020-01-02T00:00:00+08:00", source_url=source["source_url"], evidence_refs=[source])])
    row, = service._operating_events(case["analysis"], [window], case["now"],
        lambda ref: _bound(case["root"], ref))

    assert not row["materiality_approved"] and not row["model_inputs_changed"]
    if matches_original_title:
        event = row["facts"][0]["terms"]
        assert event["event_type"] == "REPORTED_INTERIM_DIVIDEND_IMPLEMENTATION_SCHEDULE"
        assert event["effective_date"] is None
        assert event["terms"]["cash_payment_date"] == "2020-01-08"
        assert event["action"] == "no_order"
    else:
        assert not row["facts"]


def test_implementation_schedule_requires_actual_cash_review(reconciliation):
    from value_investment_agent.application.research.candidate_event_impact import build_candidate_event_impact

    analysis = reconciliation["analysis"]
    candidate = analysis["review_binding"]["candidate_binding"]
    analysis["joint_capital_review"]["economic_path"]["candidate_binding"] = candidate
    event = dict(status="SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW",
                 announcement_id="TEST_ONLY", title="TEST_ONLY", published_at="2020-01-02",
                 source_url="https://static.cninfo.com.cn/finalpage/2020-01-02/123.PDF",
                 candidate_binding=candidate, input_descriptor_sha256=analysis["input_descriptor_sha256"],
                 facts=[dict(terms=dict(
                     event_type="REPORTED_INTERIM_DIVIDEND_IMPLEMENTATION_SCHEDULE",
                     summary="每股派现0.42元", effective_date=None,
                     affected_model_fields=["shareholder_distributions"]),
                     binding=reconciliation["anchor"]["binding"], source_url=reconciliation["anchor"]["source_url"],
                     source_available_at=reconciliation["anchor"]["available_at"])])
    result = build_candidate_event_impact(analysis, [event])
    item, = result["items"]
    assert item["status"] == "INTERIM_DISTRIBUTION_PAYMENT_AND_MODEL_REVIEW_REQUIRED"
    assert "实际支付" in item["rationale"]
    assert not result["materiality_approved"]
    assert result["action"] == "no_order"


@pytest.mark.parametrize("mutation", [None, "issuer", "vote_count", "outcome", "agenda"])
def test_interim_dividend_resolution_never_confirms_payment(mutation):
    from value_investment_agent.infrastructure.filings.interim_dividend_resolution import (
        parse_interim_dividend_resolution,
    )
    pages = [
        "证券代码：600123\n2026年第二次临时股东会决议公告\n"
        "股东会召开的时间：2026年11月20日\n"
        "2、出席会议的股东所持有表决权的股份总数（股） 10,000\n3、其他信息",
        "1、议案名称：《公司2026年中期利润分配预案》\n审议结果：通过\n"
        "A 股 9,800 98.00 100 1.00 100 1.00\n"
        "2、议案名称：《其他议案》\n审议结果：通过\n董事会\n2026年11月21日",
    ]
    if mutation:
        old, new = {
            "issuer": ("600123", "600124"),
            "vote_count": ("9,800", "9,999"),
            "outcome": ("结果：通过", "结果：未通过"),
            "agenda": ("中期利润分配预案", "回购股份"),
        }[mutation]
        with pytest.raises(ValueError, match="INTERIM_DIVIDEND_RESOLUTION"):
            parse_interim_dividend_resolution([p.replace(old, new, 1) for p in pages],
                                              symbol="600123", published=date(2026, 11, 21))
    else:
        result = parse_interim_dividend_resolution(pages, symbol="600123", published=date(2026, 11, 21))
        assert result["decision"] == "APPROVED"
        assert result["meeting_date"] == "2026-11-20"
        assert not result["payment_verified"] and not result["implementation_verified"]
        assert result["action"] == "no_order"


def test_quarterly_unlock_confirmation_requires_completed_listing_in_report_period():
    from value_investment_agent.application.research.pending_candidate_alignment import (
        _reported_unlock_completions,
    )

    title = "关于股权激励解除限售股份上市流通的提示性公告"
    text = (
        f"2026 年 9 月 23 日，公司披露了《{title}》，"
        "公司该计划限制性股票于 2026 年 9 月 28 日上市流通。"
    )
    assert list(_reported_unlock_completions(["非相关页", text], "2026-09-30")) == [{
        "notice_date": "2026-09-23",
        "listing_date": "2026-09-28",
        "normalized_notice_title": title,
        "physical_page": 2,
    }]
    assert not list(_reported_unlock_completions([text], "2026-09-27"))
    assert not list(_reported_unlock_completions([text.replace("于 2026", "拟于 2026")], "2026-09-30"))


@pytest.mark.parametrize("complete", [True, False])
def test_adjacent_full_windows_report_coverage_without_materiality_admission(reconciliation, complete):
    from types import SimpleNamespace

    analysis = reconciliation["analysis"]
    valuation = ValuationResultCodec().from_payload(analysis["valuation"])
    start = valuation.valuation_date
    end = start + timedelta(days=1)
    windows = [
        dict(scan_from=day.isoformat(), scan_to=day.isoformat(),
             source_integrity_verified=True, full_calendar_window_elapsed=True,
             observation_binding={"sha256": "a" * 64})
        for day in (start, end)
    ]
    scans = [
        SimpleNamespace(scan_from=day, scan_to=day, announcements=(), blockers=(),
                        status="COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW",
                        coverage_status="COMPLETE" if index == 0 or complete else "INCOMPLETE")
        for index, day in enumerate((start, end))
    ]
    quote = QuoteSnapshot(valuation.symbol, end, Decimal("15"), "verified_close", [dict(id="TEST_ONLY", sha256="b" * 64)])
    quote_result = dict(status="QUALIFIED", reason_codes=[], explanation="TEST_ONLY",
                        bundle_binding=None, native_status="TEST_ONLY")
    checks, validity, _, ready = service._assess(analysis, valuation, quote, quote_result, windows, scans)
    event = next(check for check in checks if check["id"] == "material_events")
    assert event["details"]["publication_window_continuous"] is complete
    assert event["status"] == "BLOCKED" and validity.status != "VALID" and not ready
    expected = ("MULTI_WINDOW_MATERIALITY_REPLAY_NOT_SUPPORTED" if complete
                else "EVENT_WINDOW_DOES_NOT_COVER_VALUATION_TO_QUOTE")
    assert expected in event["reason_codes"]

def test_opening_share_excerpt_requires_exact_compiler_binding(reconciliation, monkeypatch):
    from value_investment_agent.infrastructure.filings import pdf_text

    case = reconciliation
    original = "半年报股本章节：股份总数100股；股份余额仍为100股。"
    monkeypatch.setattr(pdf_text, "extract_pages", lambda path: [original])
    excerpt = {**case["anchor"], "excerpt": "股份总数100股"}
    case["analysis"]["consumed_opening_capital_excerpt"] = {
        **excerpt, "period_end": case["ledger"]["valuation_date"],
    }
    case["ledger"].update(closing_shares=None, opening_pending_actions=None)
    case["ledger"]["opening_shares"]["evidence"] = [excerpt]
    result = reconcile(case)
    assert result["opening_shares_semantics"] == "NATIVE_CONSUMED_FACT_MATCHED"
    assert result["current_price_basis_compatible"] is False

    case["ledger"]["opening_shares"]["evidence"] = [{**excerpt, "excerpt": "股份余额仍为100股"}]
    with pytest.raises(ValueError, match="RECONCILIATION_EXCERPT_OR_ISSUER_MISMATCH"):
        reconcile(case)

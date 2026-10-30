"""TEST_ONLY arithmetic negatives; native quote/coverage/signature replay positives."""
from copy import deepcopy
from datetime import date, datetime, timezone
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


def test_cross_date_manual_arithmetic_cannot_grant_native_alignment(reconciliation):
    result = reconcile(reconciliation)
    assert reconciliation["ledger"]["comparison_date"] != reconciliation["ledger"]["valuation_date"]
    assert result["status"] == "PARTIAL" and result["arithmetic_status"] == "RECONCILED"
    assert result["current_price_basis_compatible"] is False
    assert result["native_basis_semantics_verified"] is False
    assert result["closing_shares"] == result["calculated_closing_shares"] == "100"
    assert result["formal_eligibility"] is False
    assert result["action"] == "no_order"


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


def test_in_period_cash_is_not_blindly_subtracted_or_declared_included(reconciliation):
    case = reconciliation
    case["ledger"]["distributions"] = [cash(case, in_period=True)]
    result = reconcile(case)
    assert result["period_cash_per_share"] == "2"
    assert not result["current_price_basis_compatible"]
    assert result["distributions"][0]["model_inclusion"] == "NOT_NATIVE_VERIFIED"
    assert result["distributions"][0]["verified_cash_per_share"] is None
    assert result["distributions"][0]["price_deduction_applied"] == "0"


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
    ledger = root / "config/pending-candidate-alignments-v1/600519-basis-reconciliation-20261029.json"
    original = json.loads(ledger.read_bytes())  # Explicit opt-in: missing evidence must fail.
    now = datetime.now(timezone.utc)
    analysis = load_current_value_research_analysis(root=root, symbol="600519", now=now)
    assert analysis["status"] == "CONDITIONAL_ANALYSIS_VERIFIED", analysis
    alignment = analysis["current_alignment"]
    assert alignment["quote"]["status"] == "QUALIFIED", alignment
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
    assert alignment["quote"]["current_price"] == "1354.00"
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
    path = root / "runtime/value-alignment-event-observation/20261030T034906348838Z/observation.json"
    assert path.is_file(), "Explicit real run requires Root supplied complete window"
    ref = dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))
    windows, scans = service._event_windows(root, analysis, [ref], now, lambda r: _bound(root, r))
    assert len(scans[0].announcements) == 7
    assert windows[0]["full_calendar_window_elapsed"]
    assert not windows[0]["materiality_approved"]
    config = json.loads((root / service.CONFIG_DIRECTORY /
        (analysis["review_binding"]["candidate_binding"]["sha256"] + ".json")).read_bytes())
    sources, _ = service._event_windows(root, analysis, config["source_observation_bindings"], now,
        lambda r: _bound(root, r))
    result = service._reconcile(root, analysis, config["reconciliation_binding"], date(2026,10,29),
        windows, now, lambda r: _bound(root, r), sources)
    assert result["native_source_consumption"]["status"] == "NATIVE_FIELDS_VERIFIED_CHAIN_INCOMPLETE"
    assert not result["native_basis_semantics_verified"]
    # Acquisition on Oct 30 must never become an Oct 29 historical proof.
    with pytest.raises(ValueError):
        service._event_windows(root, analysis, [ref], datetime(2026,10,29,15,tzinfo=timezone.utc),
            lambda r: _bound(root, r))
    quote, _ = service._qualified_quote(root, analysis, config["quote_bundle_binding"], now, lambda r: _bound(root, r))
    checks, _, _, ready = service._assess(analysis, ValuationResultCodec().from_payload(analysis["valuation"]),
        quote, dict(status="QUALIFIED", reason_codes=[], explanation="TEST", bundle_binding=None,
                    native_status="TEST"), windows, scans, result)
    assert not ready and checks[3]["status"] == "BLOCKED"
    rows = checks[3]["details"]["matched_input_sources"] + checks[3]["details"]["unresolved_sources"]
    assert len(rows) == 7 and all(r["source_url"].startswith("https://static.cninfo.com.cn/") for r in rows)


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

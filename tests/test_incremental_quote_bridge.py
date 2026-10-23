"""Production entrypoint tests using synthetic evidence, never real approval."""
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from test_d2_conditional_shared_service import synthetic_chain, SYMBOL, DAY, SYNTHETIC
from test_quote_sessions import sse_evidence
from test_research_validity_review import _write
from test_daily_public_packet_identity import build_verified_tree
from value_investment_agent.application.product import incremental_validity as service
from value_investment_agent.application.product.daily_public_packet import build_daily_public_packet, ENGINE_VERSION
from value_investment_agent.application.product.quote_bridge import (
    execute_quote_bridge_for_symbol, pin_quote_bridge_for_symbol,
)

NOW = datetime(2026, 9, 23, 1, tzinfo=timezone.utc)  # Before next session opens.
CUTOFF = date(2026, 9, 22)


@pytest.fixture
def production_chain(synthetic_chain):
    root, original, _, _, _, _, _, _ = synthetic_chain
    package = json.loads(original.read_text(encoding="utf-8"))
    # This independent synthetic case declares no unresolved earlier events.
    package["model_validity_input"].pop("event_scan_ref")
    package["model_validity_input"]["events"] = []
    package_path = root / "runtime/original/package.json"
    package_sha = _write(package_path, package)
    evidence = sse_evidence(price=5, day=CUTOFF.isoformat())
    documents, refs = {}, {}
    for role in ("tencent", "sina", "calendar_documents"):
        values = evidence[role] if role == "calendar_documents" else [evidence[role]]
        ids = []
        for doc in values:
            document = dict(doc, http_status=200)
            identity = hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"]
                                       + "\n" + document["sha256"]).encode()).hexdigest()
            documents[identity] = document
            ids.append(identity)
        refs[role] = ids if role == "calendar_documents" else ids[0]
    bundle = root / "runtime/quotes/bundle.json"
    _write(bundle, {"version": "quote-session-collection-v1", "status": "collected_not_verified",
        "finished_at": "2026-09-22T08:00:00+00:00", "documents": documents,
        "references": {SYMBOL: {"symbol": SYMBOL, "calendar_exchange": "SSE", "document_refs": refs}}})
    pin_quote_bridge_for_symbol(root, SYMBOL, bundle, package_path)
    source = root / "runtime/incremental/source.json"
    source_sha = _write(source, {"TEST_ONLY": SYNTHETIC})
    source_ref = {"id": "TEST_ONLY-window", "path": source.relative_to(root).as_posix(), "sha256": source_sha}
    scan = {"schema_version": "m1-event-scan-v1", "symbol": SYMBOL, "provider": SYNTHETIC,
        "scan_from": DAY.isoformat(), "scan_to": CUTOFF.isoformat(), "validity_from": DAY.isoformat(),
        "validity_to": CUTOFF.isoformat(), "status": "COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW",
        "coverage_status": "COMPLETE", "pre_model_review_status": "NONE", "announcements": [],
        "blockers": [], "evidence_refs": [source_ref], "retrieved_at": "2026-09-23T00:00:00+00:00",
        "parser_version": "TEST_ONLY-reviewed-window"}
    scan_path = root / "runtime/incremental/scan.json"
    scan_ref = {"path": scan_path.relative_to(root).as_posix(), "sha256": _write(scan_path, scan)}
    observation = {"schema_version": "daily-event-observation-v1", "symbol": SYMBOL,
        "scan_from": DAY.isoformat(), "scan_to": CUTOFF.isoformat(), "scan_binding": scan_ref,
        "acquired_at": scan["retrieved_at"], "pagination_complete": True,
        "collection_status": "OFFICIAL_QUERY_ARCHIVED", "announcement_count": 0,
        "source_bindings": [source_ref], "full_calendar_window_elapsed": True}
    observation_path = root / "runtime/incremental/observation.json"
    observation_ref = {"path": observation_path.relative_to(root).as_posix(), "sha256": _write(observation_path, observation)}
    binding = {"schema_version": service.BINDING_SCHEMA, "symbol": SYMBOL, "action": "no_order",
        "package_ref": {"path": package_path.relative_to(root).as_posix(), "sha256": package_sha},
        "research_as_of": DAY.isoformat(), "review_cutoff": CUTOFF.isoformat(),
        "model_id": package["model_validity_input"]["model_id"],
        "observation_ref": observation_ref, "scan_ref": scan_ref}
    binding_path = root / "runtime/incremental/binding.json"
    binding_ref = {"path": binding_path.relative_to(root).as_posix(), "sha256": _write(binding_path, binding)}
    return root, binding_ref, binding, package_path, source


def test_production_pointer_rebuilds_model_and_computes_shared_price_bridge(production_chain):
    root, ref, _, package, _ = production_chain
    before = package.read_bytes()
    unbound = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert unbound["compatibility"]["comparison_eligible"]["eligible"] is False
    registration = service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    pointer = root / "config/current-quote-bridge.json"
    pinned = pointer.read_bytes()
    assert service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW) == registration
    assert pointer.read_bytes() == pinned
    execution = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert execution["status"] == "INCREMENTAL_VALIDITY_BLOCKED", execution.get("reason")
    comparison = execution["historical_price_comparison"]
    valuation = execution["conditional_valuation"]
    assert comparison["bridge_status"] == "READY"
    assert Decimal(comparison["margin_to_base"]) == (Decimal(valuation["base_value"]) - Decimal("5")) / Decimal(valuation["base_value"])
    assert execution["research_day"] == DAY.isoformat()
    assert execution["compatibility"]["original_cutoff_compatible"]["eligible"] is False
    assert execution["compatibility"]["research_compatible"]["eligible"] is False
    assert execution["quote_verification_status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert execution["compatibility"]["comparison_eligible"]["eligible"] is False
    assert execution["price_admitted"] is False
    assert execution["price_comparison"]["bridge_status"] != "READY"
    assert execution["historical_model_validity"]["status"] == "VALID"
    assert execution["incremental_validity"]["model_validity"]["status"] == "UNKNOWN"
    assert "CURRENT_EVENT_COVERAGE_NOT_VERIFIED" in execution["incremental_validity"]["blockers"]
    assert execution["current_event_coverage"]["required_through"] == "2026-09-23"
    assert execution["current_event_coverage"]["covered_through"] == CUTOFF.isoformat()
    assert execution["current_event_coverage"]["status"] == "CLOSED_WINDOW_NOT_CURRENT"
    assert execution["quote"]["quote_date"] == CUTOFF.isoformat()
    assert "READY" not in execution["compatibility"]["comparison_eligible"]["reason"]
    assert execution["compatibility"]["formal_decision_eligible"]["eligible"] is False
    assert execution["action"] == "no_order"
    assert package.read_bytes() == before
    assert any(item.get("path") == ref["path"] for item in comparison["evidence_refs"])


def test_v2_real_consumer_keeps_raw_complete_window_pending_not_price_ready(production_chain, monkeypatch):
    import test_retained_event_coverage as retained
    from value_investment_agent.application.product import daily_event_observation

    root, _, _, package_path, _ = production_chain
    package = json.loads(package_path.read_bytes())
    start = date.fromisoformat(package["model_validity_input"]["valid_from"])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(retained, "START", start)
    monkeypatch.setattr(retained, "END", CUTOFF)
    monkeypatch.setattr(retained, "datetime", Clock)
    monkeypatch.setattr(daily_event_observation, "datetime", Clock)
    observation = retained.archive(root, monkeypatch)
    binding = {"schema_version": service.BINDING_SCHEMA_V2, "symbol": SYMBOL, "action": "no_order",
        "package_ref": {"path": package_path.relative_to(root).as_posix(), "sha256": service.sha256_file(package_path)},
        "research_as_of": package["point_in_time"]["research_as_of"],
        "valuation_date": package["point_in_time"]["valuation_date"],
        "model_valid_from": start.isoformat(), "scan_from": start.isoformat(),
        "review_cutoff": CUTOFF.isoformat(), "model_id": package["model_validity_input"]["model_id"],
        "scan_ref": observation["scan_binding"], "observation_ref": {"path": "runtime/events/observation.json",
            "sha256": _write(root / "runtime/events/observation.json", observation)},
        "materiality_approved": False, "g3_approval_granted": False, "research_cutoff_changed": False,
        "coverage_mode": "FULL_ELAPSED_WINDOW"}
    ref = {"path": "runtime/events/v2-binding.json",
        "sha256": _write(root / "runtime/events/v2-binding.json", binding)}
    registration = service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    assert registration["model_validity_status"] == "UNKNOWN"
    execution = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert execution["status"] == "INCREMENTAL_VALIDITY_BLOCKED"
    assert execution["compatibility"]["comparison_eligible"]["eligible"] is False
    assert execution["compatibility"]["formal_decision_eligible"]["eligible"] is False
    assert execution["action"] == "no_order"


def test_known_stale_model_survives_missing_current_coverage(production_chain, monkeypatch):
    """Inject an already-established typed adverse verdict, not an approval."""
    from dataclasses import replace
    from value_investment_agent import price_bridge

    root, ref, _, package, _ = production_chain
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    resolve = service.resolve_incremental_model_validity
    bridge = price_bridge.bridge_with_quote
    seen = []

    def stale(**kwargs):
        return replace(resolve(**kwargs), status="STALE", material_event_found=True,
                       blockers=["TEST_ONLY_KNOWN_MATERIAL_DAMAGE"])

    def observe(valuation, validity, quote, **kwargs):
        seen.append(validity)
        return bridge(valuation, validity, quote, **kwargs)

    monkeypatch.setattr(service, "resolve_incremental_model_validity", stale)
    monkeypatch.setattr(price_bridge, "bridge_with_quote", observe)
    before = package.read_bytes()
    result = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    current = result["incremental_validity"]["model_validity"]
    assert current["status"] == "STALE"
    assert current["material_event_found"] is True
    assert "TEST_ONLY_KNOWN_MATERIAL_DAMAGE" in current["blockers"]
    assert "CURRENT_EVENT_COVERAGE_NOT_VERIFIED" in current["blockers"]
    assert seen[0].status == "STALE"  # Actual shared bridge receives the adverse typed input.
    assert "CURRENT_EVENT_COVERAGE_NOT_VERIFIED" in seen[0].blockers
    assert result["historical_model_validity"]["status"] == "STALE"
    assert "CURRENT_EVENT_COVERAGE_NOT_VERIFIED" not in result["historical_model_validity"]["blockers"]
    assert result["historical_price_comparison"]["bridge_status"] != "READY"
    assert result["price_comparison"]["bridge_status"] != "READY"
    assert result["status"] == "INCREMENTAL_VALIDITY_BLOCKED"
    assert result["price_admitted"] is False
    assert result["quote"]["quote_date"] == CUTOFF.isoformat()
    assert result["conditional_valuation"]["base_value"]
    assert result["action"] == "no_order"
    assert package.read_bytes() == before


def test_failed_current_collection_cannot_promote_retained_historical_ready(production_chain, monkeypatch):
    from value_investment_agent.application.product import daily_event_observation

    root, ref, _, _, _ = production_chain
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    pointer = root / "config/current-quote-bridge.json"
    before = pointer.read_bytes()
    clock_calls = []

    def unavailable(**kwargs):
        clock_calls.append(kwargs)
        raise OSError("TEST_ONLY Saturday/next-day acquisition unavailable")

    monkeypatch.setattr(daily_event_observation, "collect_daily_event_observation", unavailable)
    with pytest.raises(OSError, match="acquisition unavailable"):
        service.collect_registered_validity_scan(root=root, symbol=SYMBOL,
            review_cutoff=NOW.date(), output_dir=root / "runtime/failed-current-scan")
    assert clock_calls[0]["end"] == NOW.date()
    assert pointer.read_bytes() == before
    result = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert result["historical_price_comparison"]["bridge_status"] == "READY"
    assert result["historical_model_validity"]["status"] == "VALID"
    assert result["incremental_validity"]["status"] == "UNKNOWN"
    assert result["price_comparison"]["bridge_status"] != "READY"
    assert result["price_admitted"] is False
    assert result["conditional_valuation"]["base_value"]
    assert result["quote"]["quote_date"] == CUTOFF.isoformat()


def test_next_morning_verified_display_names_b1_comparison_refusal(production_chain):
    root, ref, _, package, _ = production_chain
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    before = package.read_bytes()
    bundle_path = root / "runtime/quotes/bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    refs = bundle["references"][SYMBOL]["document_refs"]
    for role in ("tencent", "sina"):
        document = bundle["documents"].pop(refs[role])
        document["fetched_at"] = "2026-09-23T00:59:00+00:00"
        identity = hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"]
            + "\n" + document["sha256"]).encode()).hexdigest()
        bundle["documents"][identity] = document
        refs[role] = identity
    bundle["finished_at"] = "2026-09-23T00:59:30+00:00"
    _write(bundle_path, bundle)
    pin_quote_bridge_for_symbol(root, SYMBOL, bundle_path, package)
    result = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert result["status"] == "INCREMENTAL_VALIDITY_BLOCKED"
    assert result["quote_verification_status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert result["quote"]["display_price"] == "5"
    assert result["quote"]["display_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert result["compatibility"]["verified_quote"]["eligible"] is True
    assert result["price_comparison"]["bridge_status"] == "INVALID"
    assert result["price_admitted"] is False
    assert result["compatibility"]["comparison_eligible"]["eligible"] is False
    assert result["compatibility"]["formal_decision_eligible"]["eligible"] is False
    assert "未满足 B1" in result["reason"]
    assert "报价未通过核验" not in result["reason"]
    assert "展示收盘无需重复核验" in result["next_step"]
    assert result["incremental_validity"]["status"] == "UNKNOWN"
    assert result["historical_model_validity"]["status"] == "VALID"
    assert "conditional_valuation" not in result
    assert package.read_bytes() == before


@pytest.mark.parametrize("failure", ["source", "binding", "model_rebuild", "expired_quote"])
def test_production_incremental_failures_never_reuse_ready(production_chain, monkeypatch, failure):
    root, ref, _, _, source = production_chain
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    previous = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert previous["historical_price_comparison"]["bridge_status"] == "READY"
    assert previous["price_admitted"] is False
    if failure == "source":
        source.write_text("changed", encoding="utf-8")
    elif failure == "binding":
        (root / ref["path"]).write_text("{}", encoding="utf-8")
    elif failure == "model_rebuild":
        def fail(*args):
            raise ValueError("TEST_ONLY original model cannot be reconstructed")
        monkeypatch.setattr(service, "rebuild_registered_valuation", fail)
    now = NOW.replace(hour=10) if failure == "expired_quote" else NOW
    result = execute_quote_bridge_for_symbol(root, SYMBOL, today=now)
    assert result["status"] == "INCREMENTAL_VALIDITY_BLOCKED"
    assert result["compatibility"]["comparison_eligible"]["eligible"] is False
    assert result["price_comparison"]["bridge_status"] != "READY"
    assert result["price_admitted"] is False
    if failure != "expired_quote":
        assert result["quote_verification_status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
        assert Decimal(result["quote"]["display_price"]) == Decimal("5")
    if failure in {"source", "model_rebuild", "expired_quote"}:
        assert result["incremental_validity"]["review_cutoff"] == CUTOFF.isoformat()
        assert result["incremental_validity"]["announcement_count"] == 0
        assert result["incremental_validity"]["scan_ref"]["path"]


def test_packet_consumes_production_comparison_and_tracks_source_bytes(production_chain):
    root, ref, _, _, source = production_chain
    build_verified_tree(root)
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    packet = build_daily_public_packet(root, generated_at=NOW)
    row = packet["price_bridge_statuses"][SYMBOL]
    assert row["comparison_eligible"] is False, row
    assert row["price_comparison"]["bridge_status"] != "READY"
    company = packet["company_statuses"][SYMBOL]
    assert company["incremental_status"] == "UNKNOWN"
    assert company["incremental_validity_binding"] == ref
    assert company["review_cutoff"] == CUTOFF.isoformat()
    assert company["announcement_count"] == 0
    assert company["model_validity"]["status"] == "UNKNOWN"
    assert packet["engine_version"] == ENGINE_VERSION
    source.write_text("tampered", encoding="utf-8")
    changed = build_daily_public_packet(root, generated_at=NOW)
    assert changed["publication_id"] != packet["publication_id"]
    assert changed["price_bridge_statuses"][SYMBOL]["comparison_eligible"] is False
    assert changed["company_statuses"][SYMBOL]["incremental_status"] == "UNKNOWN"
    assert any(item["code"] == "INCREMENTAL_EVENT_MATERIALITY_REVIEW"
               for item in changed["company_statuses"][SYMBOL]["pending_actions"])


def test_pending_action_never_renders_missing_scan_window_as_none(production_chain):
    root, ref, _, _, source = production_chain
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    build_verified_tree(root)
    source.write_text("changed", encoding="utf-8")
    packet = build_daily_public_packet(root, generated_at=NOW)
    task = next(row for row in packet["company_statuses"][SYMBOL]["pending_actions"]
                if row["code"] == "INCREMENTAL_EVENT_MATERIALITY_REVIEW")
    assert task["label"] == f"复核截至 {CUTOFF.isoformat()} 的 0 份公告及原模型适用性；不预支 G3。"
    assert "None" not in task["label"]


def test_registration_rejects_tampered_sources_without_changing_pointer(production_chain):
    root, ref, _, _, source = production_chain
    pointer = root / "config/current-quote-bridge.json"
    before = pointer.read_bytes()
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="changed incremental source"):
        service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    assert pointer.read_bytes() == before


def test_production_pending_announcements_are_handoff_tasks_not_comparison(production_chain):
    root, ref, binding, _, _ = production_chain
    scan_path = root / binding["scan_ref"]["path"]
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan["status"] = "PENDING_HUMAN_REVIEW"
    scan["announcements"] = [{"announcement_id": str(identity), "title": "TEST_ONLY pending official filing",
        "published_at": "2026-09-22T00:00:00+08:00", "source_url": "https://example.test/TEST_ONLY.pdf",
        "rule_kind": "unknown", "review_status": "PENDING_HUMAN_REVIEW", "materiality_candidate": True,
        "pre_model": False, "evidence_refs": scan["evidence_refs"]} for identity in (1, 2)]
    binding["scan_ref"]["sha256"] = _write(scan_path, scan)
    obs_path = root / binding["observation_ref"]["path"]
    obs = json.loads(obs_path.read_text(encoding="utf-8"))
    obs.update(scan_binding=binding["scan_ref"], announcement_count=2)
    binding["observation_ref"]["sha256"] = _write(obs_path, obs)
    ref["sha256"] = _write(root / ref["path"], binding)
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    build_verified_tree(root)
    packet = build_daily_public_packet(root, generated_at=NOW)
    bridge = packet["price_bridge_statuses"][SYMBOL]
    assert bridge["incremental_status"] == "UNKNOWN"
    assert bridge["quote_verification_status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE"
    assert bridge["current_price"] == "5"
    assert bridge["price_comparison"]["bridge_status"] == "INVALID"
    task = next(row for row in packet["company_statuses"][SYMBOL]["pending_actions"]
                if row["code"] == "INCREMENTAL_EVENT_MATERIALITY_REVIEW")
    assert task["binding_ref"] == ref
    assert len(task["announcements"]) == 2
    assert task["evidence_refs"]
    assert task["evidence_refs"][0]["title"] == "TEST_ONLY pending official filing"
    assert task["evidence_refs"][0]["source_url"] == "https://example.test/TEST_ONLY.pdf"
    route = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)["incremental_validity"]["materiality_review_route"]
    assert route["status"] == "EXTERNAL_SIGNATURE_REQUIRED"
    assert route["handoff_binding"]["sha256"]
    assert route["approval_granted"] is False


def test_new_scan_does_not_erase_unresolved_original_event_review(production_chain):
    root, ref, binding, package_path, _ = production_chain
    package = json.loads(package_path.read_text(encoding="utf-8"))
    original_scan = root / "synthetic-scan.json"
    package["model_validity_input"]["event_scan_ref"] = {"id": "TEST_ONLY-original-pending",
        "path": original_scan.name, "sha256": service.sha256_file(original_scan)}
    binding["package_ref"]["sha256"] = _write(package_path, package)
    pin_quote_bridge_for_symbol(root, SYMBOL, root / "runtime/quotes/bundle.json", package_path)
    ref["sha256"] = _write(root / ref["path"], binding)
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    result = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert result["incremental_validity"]["status"] == "UNKNOWN"
    assert "ORIGINAL_EVENT_REVIEW_UNRESOLVED" in result["incremental_validity"]["blockers"]
    assert result["price_comparison"]["bridge_status"] != "READY"


def test_repin_same_package_preserves_binding_but_changed_package_clears_it(production_chain):
    root, ref, _, package, _ = production_chain
    service.register_incremental_validity_binding(root, SYMBOL, ref, CUTOFF, NOW)
    bundle = root / "runtime/quotes/bundle.json"
    pin_quote_bridge_for_symbol(root, SYMBOL, bundle, package)
    pointer = root / "config/current-quote-bridge.json"
    assert json.loads(pointer.read_text(encoding="utf-8"))["quotes"][SYMBOL]["incremental_validity_binding"] == ref
    result = execute_quote_bridge_for_symbol(root, SYMBOL, today=NOW)
    assert result["historical_price_comparison"]["bridge_status"] == "READY"
    assert result["price_admitted"] is False
    payload = json.loads(package.read_text(encoding="utf-8"))
    payload["name"] = "TEST_ONLY changed research bytes"
    _write(package, payload)
    pin_quote_bridge_for_symbol(root, SYMBOL, bundle, package)
    assert "incremental_validity_binding" not in json.loads(pointer.read_text(encoding="utf-8"))["quotes"][SYMBOL]

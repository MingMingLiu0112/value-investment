"""Synthetic v2 source-package boundary tests; no real research admission."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json

import pytest

from fixed_sample_runtime_fixture import _cash_return
from test_m1_valuation_package_builder import _package
from test_quote_sessions import evidence, sse_evidence
from test_source_bound_research_inputs import source
from value_investment_agent.application.product.source_bound_inputs import (
    validate_source_bound_descriptor,
    verify_package_local_sources,
)
from value_investment_agent.event_scan import EventScanResult
from value_investment_agent.m1_distribution_package_builder import build_dividend_result
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import build_research_run_spec, descriptor_from_payload
from value_investment_agent.research_application import ResearchApplicationService


DAY = "2026-09-22"
SYNTHETIC = "SYNTHETIC_SOURCE_CONTRACT_TEST_ONLY"
FIELDS = ("cost_of_equity", "forecast_roes.0", "terminal_roe", "terminal_growth", "retention")


@pytest.fixture
def source_package(tmp_path):
    package = _package()
    row = source(tmp_path)
    row.update(
        kind="research_artifact", published_at="2026-09-21T12:00:00+08:00",
        source_available_at=DAY + "T12:00:00+08:00", availability_basis=SYNTHETIC,
    )
    package.update(
        schema_version="m1-valuation-package-v2", name=SYNTHETIC,
        run_id="synthetic-source-bound-v2", descriptor_version="synthetic-source-bound-v2",
        sources=[row, {**row, "id": "synthetic-second-source"}],
        quote=None, model_validity_input=None,
        source_contract={
            "schema_version": "source-bound-research-inputs-v1",
            "cutoff_at": DAY + "T16:00:00+08:00",
            "distribution_input_status": "NOT_ADMITTED",
        },
        point_in_time={
            "report_period": DAY, "research_as_of": DAY, "valuation_date": DAY,
            "available_at": DAY + "T17:00:00+08:00",
            "computed_at": DAY + "T17:01:00+08:00",
        },
    )
    ref = {"id": row["id"], "sha256": row["sha256"]}
    package["research_case"].update(
        name=SYNTHETIC, as_of=DAY, financial_period=DAY, run_id=package["run_id"],
        generated_at=DAY + "T16:00:00+08:00", evidence_refs=[ref],
    )
    for group in ("positives", "counter_evidence", "thesis_breakers", "next_events"):
        for statement in package["research_case"][group]:
            statement.update(text=SYNTHETIC, evidence_refs=[row["id"]])
    package["facts"] = {
        "kind": "quality_compounder", "symbol": package["symbol"], "as_of": DAY,
        "verified": True, "confidence": "\u4f4e", "evidence_refs": [ref], "blockers": [],
        "operating_inputs": {"start_book_equity": "1000", "ordinary_shares": "100"},
        "scenario_inputs": {
            scenario: {"cost_of_equity": "0.10", "forecast_roes": ["0.10"],
                       "terminal_roe": roe, "terminal_growth": "0.02", "retention": "0.30"}
            for scenario, roe in (("bear", "0.08"), ("base", "0.10"), ("bull", "0.12"))
        },
    }
    assumptions, bindings = [], []
    for field in FIELDS:
        values = {
            scenario: inputs["forecast_roes"][0] if field == "forecast_roes.0" else inputs[field]
            for scenario, inputs in package["facts"]["scenario_inputs"].items()
        }
        assumptions.append({
            "name": field, "unit": "ratio", **values, "basis": SYNTHETIC,
            "rationale": SYNTHETIC, "as_of": DAY, "confidence": "low",
            "sensitivity": "high", "ordering": "ascending", "evidence_refs": [ref],
            "blockers": [],
        })
        for scenario, value in values.items():
            bindings.append({"assumption_name": field, "scenario": scenario,
                             "field_path": field, "expected_value": value,
                             "evidence_refs": [ref]})
    package["assumptions"] = {"assumptions": assumptions, "evidence_refs": [ref], "blockers": []}
    package["assumption_bindings"] = bindings
    # Every rejected mutation starts from a package proven valid by the real builder.
    assert build_descriptor(package, root=tmp_path).distribution_result is None
    return tmp_path, package


def _set(package, path, value):
    parent = package
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value


@pytest.mark.parametrize("path, value", [
    (("sources",), []),
    (("sources", 0, "local_path"), ""),
    (("sources", 1, "local_path"), ""),
    (("sources", 0, "local_path"), "missing-original.pdf"),
    (("sources", 0, "local_path"), "../outside.pdf"),
    (("sources", 0, "sha256"), "0" * 64),
    (("sources", 1, "id"), "synthetic-official"),
    (("sources", 1, "id"), ""),
    (("sources", 1, "id"), "   "),
    (("source_contract", "schema_version"), "unsupported-source-contract"),
    (("source_contract", "cutoff_at"), None),
    (("source_contract", "cutoff_at"), "not-a-timestamp"),
    (("source_contract", "cutoff_at"), DAY + "T16:00:00"),
    (("source_contract", "cutoff_at"), "2026-09-21T16:00:00+08:00"),
    (("source_contract", "cutoff_at"), DAY + "T18:00:00+08:00"),
    (("sources", 0, "source_available_at"), None),
    (("sources", 1, "source_available_at"), DAY + "T12:00:00"),
    (("sources", 1, "source_available_at"), DAY + "T16:00:01+08:00"),
    (("sources", 1, "source_available_at"), DAY + "T08:00:01+00:00"),
    (("sources", 0, "source_available_at"), "2026-09-21T11:59:59+08:00"),
    (("sources", 0, "availability_basis"), ""),
    (("research_case", "as_of"), "2026-09-21"),
    (("source_contract", "distribution_input_status"), None),
    (("source_contract", "distribution_input_status"), "ADMITTED"),
], ids=[
    "no-sources", "first-missing-local-path", "second-missing-local-path",
    "missing-original", "escaping-local-path", "wrong-local-hash", "duplicate-source-id",
    "unnamed-source", "blank-source", "wrong-source-contract", "missing-cutoff",
    "invalid-cutoff", "naive-cutoff", "cutoff-research-day-mismatch", "cutoff-after-output",
    "missing-source-availability", "naive-source-availability", "second-source-after-cutoff",
    "utc-source-after-cutoff", "availability-before-publication", "missing-availability-basis",
    "case-research-day-mismatch", "missing-distribution-scope", "admitted-distribution-scope",
])
def test_v2_rejects_source_cutoff_and_scope_contract_mutations(source_package, path, value):
    root, package = source_package
    _set(package, path, value)
    with pytest.raises((ValueError, FileNotFoundError)):
        build_descriptor(package, root=root)


@pytest.mark.parametrize("missing", ["all-local-paths", "source-contract", "cutoff", "availability"])
def test_v2_rejects_omitted_binding_metadata(source_package, missing):
    root, package = source_package
    if missing == "all-local-paths":
        for row in package["sources"]:
            row.pop("local_path")
    elif missing == "source-contract":
        package.pop("source_contract")
    elif missing == "cutoff":
        package["source_contract"].pop("cutoff_at")
    else:
        package["sources"][1].pop("source_available_at")
    with pytest.raises(ValueError):
        build_descriptor(package, root=root)


def test_v2_rejects_changed_original_bytes_despite_unchanged_source_metadata(source_package):
    root, package = source_package
    (root / package["sources"][0]["local_path"]).write_bytes(b"SYNTHETIC_CHANGED_ORIGINAL")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_descriptor(package, root=root)


@pytest.mark.parametrize("mutation", [
    "duplicate-assumption", "unnamed-assumption", "no-assumptions", "no-bindings",
    "partial-bindings", "duplicate-binding", "unnamed-binding", "unknown-assumption",
    "unconsumed-field", "unknown-scenario", "wrong-expected-value", "wrong-reviewed-value",
    "wrong-consumed-value", "binding-without-evidence", "assumption-without-evidence",
    "unbound-binding-evidence", "unbound-assumption-evidence", "unnamed-binding-evidence",
    "unnamed-binding-path", "unbound-additional-forecast", "consumed-and-binding-drift",
    "partially-unbound-binding-evidence", "binding-evidence-hash-drift",
    "assumption-evidence-hash-drift",
])
def test_v2_rejects_incomplete_or_inconsistent_scenario_contract(source_package, mutation):
    root, package = source_package
    assumptions = package["assumptions"]["assumptions"]
    bindings = package["assumption_bindings"]
    if mutation == "duplicate-assumption":
        assumptions.append(deepcopy(assumptions[0]))
    elif mutation == "unnamed-assumption":
        assumptions[0]["name"] = "   "
    elif mutation == "no-assumptions":
        assumptions.clear()
    elif mutation == "no-bindings":
        bindings.clear()
    elif mutation == "partial-bindings":
        bindings.pop()
    elif mutation == "duplicate-binding":
        bindings.append(deepcopy(bindings[0]))
    elif mutation == "unnamed-binding":
        bindings[0]["assumption_name"] = "   "
    elif mutation == "unknown-assumption":
        bindings[0]["assumption_name"] = "unregistered-assumption"
    elif mutation == "unconsumed-field":
        bindings[0]["field_path"] = "unconsumed-field"
    elif mutation == "unknown-scenario":
        bindings[0]["scenario"] = "unregistered-scenario"
    elif mutation == "wrong-expected-value":
        bindings[0]["expected_value"] = "0.11"
    elif mutation == "wrong-reviewed-value":
        assumptions[0]["bear"] = "0.11"
    elif mutation == "wrong-consumed-value":
        package["facts"]["scenario_inputs"]["bear"]["cost_of_equity"] = "0.11"
    elif mutation == "binding-without-evidence":
        bindings[0]["evidence_refs"] = []
    elif mutation == "assumption-without-evidence":
        assumptions[0]["evidence_refs"] = []
    elif mutation == "unbound-binding-evidence":
        bindings[0]["evidence_refs"] = [{"id": "not-in-local-sources"}]
    elif mutation == "unbound-assumption-evidence":
        assumptions[0]["evidence_refs"] = [{"id": "not-in-local-sources"}]
    elif mutation == "unnamed-binding-evidence":
        bindings[0]["evidence_refs"] = [{"sha256": "a" * 64}]
    elif mutation == "unnamed-binding-path":
        bindings[0]["field_path"] = "   "
    elif mutation == "unbound-additional-forecast":
        package["facts"]["scenario_inputs"]["bear"]["forecast_roes"].append("0.10")
    elif mutation == "consumed-and-binding-drift":
        package["facts"]["scenario_inputs"]["bear"]["cost_of_equity"] = "0.11"
        bindings[0]["expected_value"] = "0.11"
    elif mutation == "partially-unbound-binding-evidence":
        bindings[0]["evidence_refs"] = [*bindings[0]["evidence_refs"],
                                       {"id": "not-in-local-sources"}]
    elif mutation == "binding-evidence-hash-drift":
        bindings[0]["evidence_refs"] = [{"id": package["sources"][0]["id"], "sha256": "0" * 64}]
    else:
        assumptions[0]["evidence_refs"] = [{"id": package["sources"][0]["id"], "sha256": "0" * 64}]
    with pytest.raises(ValueError):
        build_descriptor(package, root=root)


def test_v2_complete_bindings_equal_reviewed_and_consumed_numeric_inputs(source_package):
    root, package = source_package
    descriptor = build_descriptor(package, root=root)
    spec = build_research_run_spec(descriptor)
    assert len(verify_package_local_sources(root, package)) == 2
    assert descriptor.point_in_time.research_as_of == date.fromisoformat(DAY)
    named = {item.name: item for item in descriptor.assumptions.assumptions}
    assert len(descriptor.assumption_bindings) == 3 * len(FIELDS)
    assert {(item.scenario, item.field_path) for item in descriptor.assumption_bindings} == {
        (scenario, field) for scenario in ("bear", "base", "bull") for field in FIELDS
    }
    for binding in descriptor.assumption_bindings:
        scenario = spec.facts.scenario_inputs[binding.scenario]
        consumed = scenario.forecast_roes[0] if binding.field_path == "forecast_roes.0" else getattr(scenario, binding.field_path)
        assert getattr(named[binding.assumption_name], binding.scenario) == Decimal(str(binding.expected_value)) == consumed
    restored = descriptor_from_payload(descriptor.as_policy())
    assert restored.as_policy() == descriptor.as_policy()
    assert spec.distribution_result is None


REFERENCE_PATHS = {
    "facts": ("facts",),
    "assumption-set": ("assumptions",),
    "assumption": ("assumptions", "assumptions", 0),
    "binding": ("assumption_bindings", 0),
}


@pytest.fixture
def reference_package(source_package):
    root, package = source_package
    directory = root / "synthetic-references"
    directory.mkdir()
    first, second = package["sources"]
    first_path = directory / "first.pdf"
    first_path.write_bytes((root / first["local_path"]).read_bytes())
    first["local_path"] = first_path.relative_to(root).as_posix()
    second_path = directory / "second.pdf"
    second_path.write_bytes(b"SYNTHETIC_DISTINCT_SECOND_SOURCE_ONLY")
    second.update(local_path=second_path.relative_to(root).as_posix(),
                  sha256=hashlib.sha256(second_path.read_bytes()).hexdigest())
    assert first["sha256"] != second["sha256"]
    assert build_descriptor(package, root=root).distribution_result is None
    return root, package


@pytest.mark.parametrize("role", REFERENCE_PATHS)
@pytest.mark.parametrize("mutation", [
    "unknown-id", "missing-id", "sha-drift", "other-source-sha",
    "path-drift", "other-source-path", "local-path-drift", "other-source-local-path",
])
def test_v2_evidence_reference_declared_identity_hash_and_path_must_match_catalog(
    reference_package, role, mutation,
):
    root, package = reference_package
    first, second = package["sources"]
    reference = {"id": first["id"], "sha256": first["sha256"]}
    if mutation == "unknown-id":
        reference.update(id="synthetic-unregistered-reference", path=first["local_path"])
    elif mutation == "missing-id":
        reference.pop("id")
        reference["path"] = first["local_path"]
    elif mutation == "sha-drift":
        reference["sha256"] = "0" * 64
    elif mutation == "other-source-sha":
        reference["sha256"] = second["sha256"]
    else:
        key = "local_path" if "local-path" in mutation else "path"
        reference[key] = (second["local_path"] if mutation.startswith("other-source")
                          else "synthetic-references/unregistered.pdf")
    # Keep a valid first reference so validation must inspect every declared ref.
    _set(package, (*REFERENCE_PATHS[role], "evidence_refs"), [
        {"id": first["id"], "sha256": first["sha256"]}, reference,
    ])
    with pytest.raises(ValueError):
        build_descriptor(package, root=root)


@pytest.mark.parametrize("role", REFERENCE_PATHS)
def test_v2_known_evidence_id_without_optional_sha_or_path_remains_compatible(
    reference_package, role,
):
    root, package = reference_package
    reference = {"id": package["sources"][0]["id"]}
    _set(package, (*REFERENCE_PATHS[role], "evidence_refs"), [reference])
    descriptor = build_descriptor(package, root=root)
    assert descriptor.valuation_approval is None
    assert descriptor.distribution_result is None
    parent = descriptor.as_policy()
    for key in REFERENCE_PATHS[role]:
        parent = parent[key]
    assert parent["evidence_refs"] == [reference]


@pytest.mark.parametrize("role", REFERENCE_PATHS)
@pytest.mark.parametrize("path_keys", [("path",), ("local_path",), ("path", "local_path")],
                         ids=["path", "local-path", "both-path-aliases"])
def test_v2_matching_evidence_sha_and_declared_paths_accept_normalized_slashes(
    reference_package, role, path_keys,
):
    root, package = reference_package
    first = package["sources"][0]
    reference = {"id": first["id"], "sha256": first["sha256"]}
    for key in path_keys:
        reference[key] = first["local_path"].replace("/", "\\") if key == "path" else first["local_path"]
    _set(package, (*REFERENCE_PATHS[role], "evidence_refs"), [reference])
    descriptor = build_descriptor(package, root=root)
    assert descriptor.valuation_approval is None
    assert descriptor.distribution_result is None
    parent = descriptor.as_policy()
    for key in REFERENCE_PATHS[role]:
        parent = parent[key]
    assert parent["evidence_refs"] == [reference]


@pytest.mark.parametrize("boundary", ["equal-cutoff", "utc-same-instant", "utc-shanghai-next-day"])
def test_v2_cutoff_uses_instants_and_shanghai_research_day(source_package, boundary):
    root, package = source_package
    if boundary == "equal-cutoff":
        package["sources"][1]["source_available_at"] = DAY + "T16:00:00+08:00"
    elif boundary == "utc-same-instant":
        package["source_contract"]["cutoff_at"] = DAY + "T08:00:00+00:00"
        package["sources"][1]["source_available_at"] = DAY + "T08:00:00+00:00"
    else:
        package["source_contract"]["cutoff_at"] = "2026-09-21T16:30:00+00:00"
        for row in package["sources"]:
            row["source_available_at"] = "2026-09-21T16:30:00+00:00"
    assert build_descriptor(package, root=root).point_in_time.research_as_of == date.fromisoformat(DAY)


@pytest.mark.parametrize("ambient", ["valid-package", "malformed-json"])
def test_v2_not_admitted_distribution_does_not_glob_ambient_packages(source_package, ambient):
    root, package = source_package
    before = build_descriptor(package, root=root).as_policy()
    directory = root / "config" / "m1-distribution-packages-v1"
    directory.mkdir(parents=True)
    target = directory / "synthetic-unadmitted.json"
    if ambient == "malformed-json":
        target.write_text("SYNTHETIC_INVALID_JSON", encoding="utf-8")
    else:
        dividend = {
            "schema_version": "m1-distribution-package-v1", "name": SYNTHETIC,
            "symbol": package["symbol"], "profile_id": package["profile_id"],
            "run_id": "synthetic-unadmitted-distribution", "research_as_of": DAY,
            "action": "no_order",
            "sources": [{**package["sources"][0], "location": "issuer.pdf"}],
            "dividend_result": _cash_return(package["symbol"], package["profile_id"],
                                            as_of=date.fromisoformat(DAY)),
        }
        assert build_dividend_result(dividend, root=root).symbol == package["symbol"]
        target.write_text(json.dumps(dividend, ensure_ascii=False), encoding="utf-8")
    descriptor = build_descriptor(package, root=root)
    assert descriptor.distribution_result is None
    assert build_research_run_spec(descriptor).distribution_result is None
    assert descriptor.as_policy() == before


def _write_market_source(root, package, name, payload):
    path = root / "synthetic-markets" / (name + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = path.relative_to(root).as_posix()
    package["sources"].append({
        "id": name, "kind": "research_artifact", "location": relative,
        "local_path": relative, "sha256": digest,
        "source_available_at": DAY + "T16:00:00+08:00", "availability_basis": SYNTHETIC,
    })
    return relative, digest


@pytest.fixture
def market_package(source_package):
    root, package = source_package
    raw = evidence(price=5, day=DAY, symbol=package["symbol"])
    raw["calendar_exchange"] = "SSE"
    raw["calendar_documents"] = sse_evidence(day=DAY)["calendar_documents"]
    documents, refs = {}, {}
    for role in ("tencent", "sina", "calendar_documents"):
        items = raw[role] if role == "calendar_documents" else [raw[role]]
        identities = []
        for item in items:
            item = dict(item, fetched_at=DAY + "T08:00:00+00:00", http_status=200)
            identity = hashlib.sha256(
                (item["source_url"] + "\n" + item["fetched_at"] + "\n" + item["sha256"]).encode()
            ).hexdigest()
            documents[identity] = item
            identities.append(identity)
        refs[role] = identities if role == "calendar_documents" else identities[0]
    quote_path, quote_hash = _write_market_source(root, package, "synthetic-quote", {
        "version": "quote-session-collection-v1", "status": "collected_not_verified",
        "scope": SYNTHETIC, "finished_at": DAY + "T08:00:00+00:00", "documents": documents,
        "references": {package["symbol"]: {"symbol": package["symbol"],
                                            "calendar_exchange": "SSE", "document_refs": refs}},
    })
    package["quote"] = {
        "kind": "quote_session", "symbol": package["symbol"], "ref_id": "synthetic-quote",
        "bundle_path": quote_path, "bundle_sha256": quote_hash,
    }
    scan = EventScanResult(
        schema_version="m1-event-scan-v1", symbol=package["symbol"], provider=SYNTHETIC,
        scan_from=date.fromisoformat(DAY), scan_to=date.fromisoformat(DAY),
        validity_from=date.fromisoformat(DAY), validity_to=date.fromisoformat(DAY),
        status="COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW", coverage_status="COMPLETE",
        pre_model_review_status="NONE", retrieved_at=datetime.fromisoformat(DAY + "T08:00:00+00:00"),
        parser_version="synthetic-scan-v1", announcements=(), blockers=(),
        evidence_refs=tuple(package["facts"]["evidence_refs"]),
    )
    event_path, event_hash = _write_market_source(root, package, "synthetic-event", scan.as_policy())
    package["model_validity_input"] = {
        "model_id": package["dependencies"]["model_version"], "valid_from": DAY,
        "event_scan_ref": {"id": "synthetic-event", "symbol": package["symbol"],
                           "path": event_path, "sha256": event_hash},
    }
    descriptor = build_descriptor(package, root=root)
    assert descriptor.quote.status == "verified_close"
    assert descriptor.model_validity_input.event_scan.coverage_status == "COMPLETE"
    return root, package, descriptor


@pytest.mark.parametrize("role", ["quote", "event"])
@pytest.mark.parametrize("mutation", ["missing-catalog-entry", "different-local-path"])
def test_v2_market_input_must_match_verified_source_catalog(market_package, role, mutation):
    root, package, _ = market_package
    source_id = "synthetic-" + role
    row = next(row for row in package["sources"] if row["id"] == source_id)
    if mutation == "missing-catalog-entry":
        package["sources"] = [row for row in package["sources"] if row["id"] != source_id]
    else:
        original = root / row["local_path"]
        alternate = original.with_name("alternate-" + original.name)
        alternate.write_bytes(original.read_bytes())
        row["local_path"] = alternate.relative_to(root).as_posix()
    with pytest.raises(ValueError, match="market input.*source catalog"):
        build_descriptor(package, root=root)


@pytest.mark.parametrize("role", ["quote", "event"])
def test_v2_market_reference_hash_must_match_source_catalog(market_package, role):
    root, package, descriptor = market_package
    reference = package["quote"] if role == "quote" else package["model_validity_input"]["event_scan_ref"]
    reference["bundle_sha256" if role == "quote" else "sha256"] = "0" * 64
    # Isolate catalog closure after real input decoding, without mocking the decoder.
    with pytest.raises(ValueError, match="market input.*source catalog"):
        validate_source_bound_descriptor(package, descriptor)
    with pytest.raises(ValueError, match="hash"):
        build_descriptor(package, root=root)


@pytest.mark.parametrize("catalog_backslashes", [True, False])
def test_v2_market_catalog_normalizes_slashes_without_changing_admission(market_package, catalog_backslashes):
    root, package, baseline = market_package
    for row in package["sources"]:
        if row["id"] in {"synthetic-quote", "synthetic-event"} and catalog_backslashes:
            row["local_path"] = row["local_path"].replace("/", "\\")
    if not catalog_backslashes:
        package["quote"]["bundle_path"] = package["quote"]["bundle_path"].replace("/", "\\")
        reference = package["model_validity_input"]["event_scan_ref"]
        reference["path"] = reference["path"].replace("/", "\\")
    descriptor = build_descriptor(package, root=root)
    assert descriptor.quote == baseline.quote
    assert descriptor.facts == baseline.facts
    assert descriptor.assumption_bindings == baseline.assumption_bindings
    assert descriptor.model_validity_input.event_scan.coverage_status == "COMPLETE"
    assert descriptor.model_validity_input.event_scan.scan_to == baseline.model_validity_input.event_scan.scan_to
    assert descriptor.valuation_approval is None
    assert descriptor.distribution_result is None


@pytest.mark.parametrize("mutation", ["unbound-id", "after-cutoff", "naive-availability"])
def test_v2_financial_fact_evidence_requires_catalog_and_cutoff(market_package, mutation):
    root, package, _ = market_package
    reference = dict(package["facts"]["evidence_refs"][0])
    if mutation == "unbound-id":
        reference["id"] = "synthetic-unregistered-fact"
    else:
        reference["available_at"] = DAY + ("T16:00:01+08:00" if mutation == "after-cutoff" else "T16:00:00")
    package["facts"]["evidence_refs"] = [reference]
    with pytest.raises(ValueError, match="unbound source|financial fact|fact available_at"):
        build_descriptor(package, root=root)


@pytest.mark.parametrize("key", ["fetched_at", "observed_trade_at"])
def test_v2_decoded_quote_observations_after_cutoff_are_rejected(market_package, key):
    root, package, descriptor = market_package
    refs = deepcopy(descriptor.quote.evidence_refs)
    refs[-1][key] = DAY + "T16:00:01+08:00"
    descriptor = replace(descriptor, quote=replace(descriptor.quote, evidence_refs=refs), input_sha256=None)
    with pytest.raises(ValueError, match="quote observation follows research cutoff"):
        validate_source_bound_descriptor(package, descriptor)


def test_v1_without_new_source_metadata_stays_compatible_and_unadmitted(market_package):
    root, package, _ = market_package
    package["schema_version"] = "m1-valuation-package-v1"
    package.pop("source_contract")
    for row in package["sources"]:
        for field in ("local_path", "source_available_at", "availability_basis"):
            row.pop(field, None)
    assert verify_package_local_sources(root, package) == ()
    descriptor = build_descriptor(package, root=root)
    assert descriptor.quote.status == "verified_close"
    assert descriptor.valuation_approval is None
    outcome = ResearchApplicationService().run_company_research(build_research_run_spec(descriptor))
    assert outcome.issuer_identity_status == "NOT_READY"
    assert outcome.gate.ready_for_price_assessment is False
    assert outcome.decision_recommendation.recommendation_action == "NO_ACTION"
    assert outcome.decision_recommendation.action == "no_order"
    assert outcome.decision_recommendation.position_guidance is None

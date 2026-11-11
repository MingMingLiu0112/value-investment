"""TEST_ONLY namespace attacks using synthetic, natively replayed evidence.

ACTUAL is an adversarial request label here, never a claim about these fixtures.
No provider network, private data, registry publication or production inputs.
"""
import base64
from copy import deepcopy
from datetime import date
import hashlib
import json

import pytest

from test_hotspot_candidate_selection import _fixture, NOW
from value_investment_agent.application.hotspot import selection_history as subject
from value_investment_agent.application.hotspot.candidate_selection import select_current_hotspot_candidates
from value_investment_agent.infrastructure.hotspot.current_price_case import _build, load_current_price_case


SYMBOL = "600519"
LAYERS = (
    "watch", "classification", "classification_row", "calendar_bundle",
    "calendar_document", "calendar_payload", "tencent_document", "sina_document",
    "quote_source_binding", "case", "60m_source_binding", "15m_source_binding",
    "60m_payload", "15m_payload", "case_quote_bundle", "case_tencent_document",
    "case_sina_document", "case_calendar_document",
)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return _sha(path)


def _rebind_documents(bundle):
    """Recompute embedded raw hashes, identities and every referring anchor."""
    documents, identities = {}, {}
    for old_id, document in bundle["documents"].items():
        raw = base64.b64decode(document["raw_base64"])
        document["sha256"] = hashlib.sha256(raw).hexdigest()
        identity = hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"]
                                  + "\n" + document["sha256"]).encode()).hexdigest()
        identities[old_id] = identity
        documents[identity] = document
    bundle["documents"] = documents
    for reference in bundle["references"].values():
        refs = reference["document_refs"]
        for provider in ("tencent", "sina"):
            refs[provider] = identities[refs[provider]]
        refs["calendar_documents"] = [identities[item] for item in refs["calendar_documents"]]


def _bound_fixture(root, *, layer=None, marker=None):
    watch_binding, case_binding, watch, _ = _fixture(root, count=1)
    case_path = root / case_binding["path"]
    case = json.loads(case_path.read_bytes())
    classification_binding = watch["source_bindings"][0]
    classification_path = root / classification_binding["path"]
    classification = json.loads(classification_path.read_bytes())
    calendar_binding = watch["source_bindings"][1]
    calendar_path = root / calendar_binding["path"]
    bundle = json.loads(calendar_path.read_bytes())
    case_bundle = deepcopy(bundle)
    refs = bundle["references"][SYMBOL]["document_refs"]

    if layer == "watch":
        watch["namespace"] = marker
    elif layer == "classification":
        classification["namespace"] = marker
    elif layer == "classification_row":
        classification["rows"][0]["namespace"] = marker
    elif layer == "calendar_bundle":
        bundle["namespace"] = marker
    elif layer == "calendar_document":
        bundle["documents"][refs["calendar_documents"][0]]["namespace"] = marker
    elif layer == "calendar_payload":
        # The watch selector consumes the SZSE JSON calendar alongside SSE HTML.
        key = bundle["references"]["000333"]["document_refs"]["calendar_documents"][0]
        document = bundle["documents"][key]
        payload = json.loads(base64.b64decode(document["raw_base64"]))
        payload["namespace"] = marker
        document["raw_base64"] = base64.b64encode(json.dumps(payload).encode()).decode("ascii")
    elif layer in {"tencent_document", "sina_document"}:
        provider = layer.removesuffix("_document")
        bundle["documents"][refs[provider]]["namespace"] = marker
    elif layer == "case_quote_bundle":
        case_bundle["namespace"] = marker
    elif layer in {"case_tencent_document", "case_sina_document", "case_calendar_document"}:
        provider = layer.removeprefix("case_").removesuffix("_document")
        key = refs["calendar_documents"][0] if provider == "calendar" else refs[provider]
        case_bundle["documents"][key]["namespace"] = marker
    elif layer == "provider_text":
        document = bundle["documents"][refs["calendar_documents"][0]]
        raw = base64.b64decode(document["raw_base64"])
        raw += ('<!-- namespace="' + marker + '" is ordinary provider text -->').encode()
        document["raw_base64"] = base64.b64encode(raw).decode("ascii")
    elif layer == "quote_source_binding":
        watch["source_bindings"][2]["namespace"] = marker
    elif layer in {"60m_source_binding", "15m_source_binding"}:
        period = layer.removesuffix("_source_binding")
        case["source_bindings"][period]["namespace"] = marker
    elif layer in {"60m_payload", "15m_payload"}:
        period = layer.removesuffix("_payload")
        source = case["source_bindings"][period]
        raw_path = root / source["path"]
        text = raw_path.read_text(encoding="utf-8")
        opening, closing = text.index("=(["), text.rindex("]);")
        payload = json.loads(text[opening + 2:closing + 1])
        payload[-1]["namespace"] = marker
        raw_path.write_text("=(" + json.dumps(payload) + ");", encoding="utf-8")
        source["sha256"] = _sha(raw_path)
    elif layer not in {None, "case"}:
        raise AssertionError("Unknown test injection layer")

    classification_binding["sha256"] = _save(classification_path, classification)
    _rebind_documents(bundle)
    calendar_binding["sha256"] = _save(calendar_path, bundle)
    # Independent quote bundles prevent the watch scan from masking a missing
    # traversal through the case's own reference-close evidence.
    _rebind_documents(case_bundle)
    case_bundle_path = case_path.parent / "quote-bundle.json"
    case_bundle_sha = _save(case_bundle_path, case_bundle)
    case["source_bindings"]["daily"] = {
        **case["source_bindings"]["60m"], "scope": "DERIVED_FROM_SINA_60M_NOT_INDEPENDENT_DAILY_SOURCE",
    }
    # Rebuild derived close bindings and evidence_refs with the native calculator.
    case = _build(root.resolve(), SYMBOL, date.fromisoformat(case["market_trade_date"]),
        case["source_bindings"], case_bundle_path, case_bundle_sha, NOW)
    if layer == "case":
        case["namespace"] = marker
    case_binding["sha256"] = _save(case_path, case)
    watch_binding["sha256"] = _save(root / watch_binding["path"], watch)
    spec = dict(schema_version=subject.SPEC_VERSION, namespace="TEST_ONLY", action="no_order",
        registered_at=NOW.isoformat(), start_date="2026-09-24", end_date="2026-09-24",
        rule_bindings=subject.implementation_bindings(), snapshots=[dict(session="2026-09-24",
            decision_at=NOW.isoformat(), watch_binding=watch_binding, case_bindings={SYMBOL: case_binding})])
    _assert_hash_chain(root, spec)
    return spec


def _assert_hash_chain(root, spec):
    snapshot = spec["snapshots"][0]
    watch_binding = snapshot["watch_binding"]
    assert _sha(root / watch_binding["path"]) == watch_binding["sha256"]
    watch = json.loads((root / watch_binding["path"]).read_bytes())
    for binding in watch["source_bindings"]:
        assert _sha(root / binding["path"]) == binding["sha256"]
    binding = snapshot["case_bindings"][SYMBOL]
    assert _sha(root / binding["path"]) == binding["sha256"]
    case = json.loads((root / binding["path"]).read_bytes())
    for source in case["source_bindings"].values():
        assert _sha(root / source["path"]) == source["sha256"]
    close = case["current_reference_close"]
    assert _sha(root / close["bundle_path"]) == close["bundle_sha256"]
    bundle = json.loads((root / close["bundle_path"]).read_bytes())
    for identity, document in bundle["documents"].items():
        assert hashlib.sha256(base64.b64decode(document["raw_base64"])).hexdigest() == document["sha256"]
        assert identity == hashlib.sha256((document["source_url"] + "\n" + document["fetched_at"]
                                          + "\n" + document["sha256"]).encode()).hexdigest()


def _assert_no_admission(report):
    assert report["action"] == "no_order"
    assert report["strategy_validation"] == "NOT_PROVEN"
    assert report["elapsed_real_shadow_sessions"] == 0
    for field in ("strict_pit_admitted", "strict_oos_admitted", "formal_eligibility", "trade_eligible"):
        assert report[field] is False


@pytest.mark.parametrize("marker", ["TEST_ONLY", "SIMULATED"])
@pytest.mark.parametrize("layer", LAYERS)
def test_actual_rejects_explicit_markers_after_native_hash_chain_rebinding(tmp_path, layer, marker):
    spec = _bound_fixture(tmp_path, layer=layer, marker=marker)
    snapshot = spec["snapshots"][0]
    native = select_current_hotspot_candidates(root=tmp_path, now=NOW,
        watch_binding=snapshot["watch_binding"], case_bindings=snapshot["case_bindings"])
    if layer != "case":
        assert native["data_status"] == "CURRENT", native
        assert native["coverage"]["unknown"] == 0
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    test_report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert test_report["namespace"] == "TEST_ONLY"
    assert test_report["source_namespace_assurance"] == "TEST_ONLY_NOT_ACTUAL_EVIDENCE"
    # Namespace checks must not change the loader's existing exact-case contract.
    assert test_report["rows"][0]["selection"] == native
    if layer != "case":
        assert test_report["status"] == "REPLAYED"
    _assert_no_admission(test_report)
    actual_spec = deepcopy(spec)
    actual_spec["namespace"] = "ACTUAL"
    with pytest.raises(ValueError, match=r"(?i)(namespace|simulation|test evidence)"):
        subject.replay_selection_history(root=tmp_path, specification=actual_spec, now=NOW)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("namespace", ["ACTUAL", "TEST_ONLY"])
def test_unlabelled_provider_format_replays_without_authenticity_or_admission_claim(tmp_path, namespace):
    spec = _bound_fixture(tmp_path)
    spec["namespace"] = namespace
    binding = spec["snapshots"][0]["case_bindings"][SYMBOL]
    loaded = load_current_price_case(root=tmp_path, symbol=SYMBOL, case_path=binding["path"],
        expected_sha256=binding["sha256"], now=NOW)
    assert "namespace" not in loaded
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["status"] == "REPLAYED"
    assert report["source_namespace_assurance"] == (
        "EXPLICIT_TEST_MARKERS_REJECTED_NOT_SOURCE_AUTHENTICATION" if namespace == "ACTUAL"
        else "TEST_ONLY_NOT_ACTUAL_EVIDENCE")
    assert report["registration_assurance"] == "DECLARED_TIMESTAMP_NOT_INDEPENDENT_PREREGISTRATION_PROOF"
    _assert_no_admission(report)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("marker", [" test_only ", " simulated "])
def test_actual_normalizes_explicit_namespace_without_scanning_plain_text(tmp_path, marker):
    spec = _bound_fixture(tmp_path, layer="provider_text", marker=marker)
    spec["namespace"] = "ACTUAL"
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["status"] == "REPLAYED"
    _assert_no_admission(report)
    watch_binding = spec["snapshots"][0]["watch_binding"]
    path = tmp_path / watch_binding["path"]
    watch = json.loads(path.read_bytes())
    watch["namespace"] = marker
    watch_binding["sha256"] = _save(path, watch)
    _assert_hash_chain(tmp_path, spec)
    with pytest.raises(ValueError, match=r"(?i)(namespace|simulation|test evidence)"):
        subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)


@pytest.mark.parametrize("source", ["watch", "minute"])
def test_actual_unmarked_hash_failure_still_uses_existing_partial_path(tmp_path, source):
    spec = _bound_fixture(tmp_path)
    spec["namespace"] = "ACTUAL"
    snapshot = spec["snapshots"][0]
    if source == "watch":
        path = tmp_path / snapshot["watch_binding"]["path"]
    else:
        case = json.loads((tmp_path / snapshot["case_bindings"][SYMBOL]["path"]).read_bytes())
        path = tmp_path / case["source_bindings"]["60m"]["path"]
    path.write_bytes(path.read_bytes() + b" ")
    report = subject.replay_selection_history(root=tmp_path, specification=spec, now=NOW)
    assert report["status"] == "PARTIAL"
    assert report["replayed_sessions"] == 0
    assert report["rows"][0]["membership_change"] is None
    _assert_no_admission(report)
